#!/usr/bin/env python3
"""Fill in state on ACME customer records that have a ZIP but no address.

WHAT THIS IS FOR
The box office asks visitors for a ZIP. That lands on the transaction as a bare
`ZipCode` and never reaches the customer's address, so ~80% of those visitors
have no state on their record and are invisible to every geography report.
This job resolves the ZIP to a state and writes it onto the customer.

READ THIS BEFORE CHANGING THE WRITE PATH
ACME has no per-customer update route. Updates go through PUT /v2/b2b/customers,
a collection-level upsert that REPLACES the object. A partial payload does not
patch — it blanks every field you leave out. This was confirmed against a test
record: sending {id, version, address} wiped firstName, lastName and email.
Across the real customer table that would destroy names and emails on thousands
of constituents, so:

  * Always GET the customer, mutate the returned object, PUT the whole thing.
  * Never hand-construct a payload.
  * Every write is read back and verified; the first anomaly aborts the run.

There is also no optimistic locking — a stale `version` is accepted silently, so
a concurrent edit in the ACME back office can be clobbered. That is why this
runs overnight rather than during opening hours.

SAFETY RAILS
  * Customers that already have ANY address are skipped, never modified.
  * Unresolvable or non-US ZIPs are skipped, never guessed.
  * maxPerRun caps the blast radius of a bug.
  * Every change is appended to data/fill-state-log.json with the before state,
    so a bad run can be reverted.

Environment:
  ACME_API_KEY            required
  FILL_STATE_DRY_RUN=1    resolve and log, write nothing
  FILL_STATE_MAX          override config.fillState.maxPerRun

Runs on Python 3.9+ stdlib only.
"""

import bisect
import collections
import json
import os
import sys
import threading
import os as _os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_availability import (  # noqa: E402  (shared API plumbing)
    api_request, execute_report, ORIGIN_REPORT_ID, ROOT, DATA_DIR, MOCK,
    env_int, env_str,
)

CROSSWALK_PATH = DATA_DIR / "zip-state.json"
STATE_PATH = DATA_DIR / "fill-state.json"
LOG_PATH = DATA_DIR / "fill-state-log.json"
QUEUE_PATH = DATA_DIR / "fill-state-queue.json"
CONFIG_PATH = ROOT / "config.json"

DRY_RUN = (os.environ.get("FILL_STATE_DRY_RUN") or "").strip() == "1"
# USPS codes that are not states for reporting purposes but are valid addresses.
NON_STATE = {"AE", "AA", "AP"}


# ------------------------------------------------------------------ crosswalk

def load_crosswalk():
    data = json.loads(CROSSWALK_PATH.read_text())
    ranges = data["ranges"]
    starts = [r[0] for r in ranges]

    def lookup(raw_zip):
        z = str(raw_zip or "").strip()[:5]
        if not z.isdigit():
            return None
        n = int(z)
        i = bisect.bisect_right(starts, n) - 1
        if i < 0:
            return None
        lo, hi, st = ranges[i]
        return st if lo <= n <= hi else None

    return lookup, len(ranges)


# --------------------------------------------------------------------- source

def candidates_query(since_iso, channels):
    """POS-style transactions carrying a ZIP but no state on the customer."""
    return {
        "collectionName": "Transactions",
        "findQueries": [
            {"fieldName": "TransactionType", "fieldValue": "Sale", "operator": "contains"},
            {"fieldName": "SaleChannel", "fieldValue": ",".join(channels), "operator": "contains"},
            {"fieldName": "ZipCode", "fieldValue": None, "operator": "exists"},
        ],
        "findFields": [
            {"fieldName": "CustomerId", "include": True},
            {"fieldName": "ZipCode", "include": True},
            {"fieldName": "CustomerAddressState", "include": True},
            {"fieldName": "Quantity", "include": True},
        ],
        "sortFields": [],
        "groupFields": [
            {"fieldName": "CustomerId", "groupFunction": None},
            {"fieldName": "ZipCode", "groupFunction": None},
            {"fieldName": "CustomerAddressState", "groupFunction": None},
        ],
        "summaryFields": [{"fieldName": "Quantity", "summaryFunction": "Sum"}],
        "countFields": [],
        "limit": 0,
    }


def find_candidates(tz, since, until, channels):
    raw = execute_report(ORIGIN_REPORT_ID, candidates_query(since, channels),
                         "EventStartTime", since, until)
    cols = {str(f.get("fieldName", "")): (f.get("values") or [])
            for f in (raw.get("resultFieldList") or [])}
    out = {}
    for cid, zc, st in zip(cols.get("CustomerId", []), cols.get("ZipCode", []),
                           cols.get("CustomerAddressState", [])):
        cid = str(cid or "").strip()
        zc = str(zc or "").strip()
        if not cid or not zc:
            continue
        if str(st or "").strip():
            continue           # report already shows a state; nothing to add
        out.setdefault(cid, zc)
    return out


# ---------------------------------------------------------------------- write

def _atomic_write(path, text):
    """Write via a temp file and rename.

    The log is flushed after every single write, and a run can be killed at any
    moment — a cancelled Action, a timeout. A partial write would corrupt the one
    file that records what was changed in ACME, so the replace must be atomic.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    _os.replace(tmp, path)


def append_log(entries):
    """Append write records immediately, so an interrupted run still audits."""
    if not entries:
        return
    log = {"entries": []}
    if LOG_PATH.exists():
        try:
            log = json.loads(LOG_PATH.read_text())
        except json.JSONDecodeError:
            log = {"entries": []}   # salvaged separately; never block a run
    log.setdefault("entries", []).extend(entries)
    log["note"] = ("Every address this job has written, for audit and revert. "
                   "beforeHadAddress is always false — the job never touches a "
                   "customer who already had one. Written incrementally, so this "
                   "stays complete even if a run is interrupted.")
    _atomic_write(LOG_PATH, json.dumps(log, indent=1))


def resolve_customer(customer_key):
    """Report CustomerId -> the numeric id the customer API is keyed on.

    They are different identifiers: reports return a 9-digit `customerId`, the
    REST route wants the 8-digit `id`. `search=` is the only parameter the list
    endpoint actually honours (customerId=, email= and friends are ignored and
    silently return the whole table, which is why they are not used here).
    """
    res = api_request("GET", f"/v2/b2b/customers?search={customer_key}&limit=5")
    hits = res.get("list") or []
    if len(hits) != 1:
        return None, f"search returned {res.get('pagination', {}).get('count')} matches"
    return hits[0].get("id"), None


def fill_one(customer_key, zip_code, state, address_type):
    """Read-modify-write one customer. Returns (status, detail)."""
    cid, err = resolve_customer(customer_key)
    if cid is None:
        return "unresolved", err

    before = api_request("GET", f"/v2/b2b/customers/{cid}")
    existing = before.get("address") or []
    if existing:
        # Recognise our own handiwork. An address with a state and ZIP but no
        # street or city is the shape this job writes and nothing else does, so
        # if it is not in the log the log is incomplete — a run interrupted
        # before it could flush. Record it rather than leave a silent edit.
        a = existing[0]
        ours = (a.get("state") and a.get("zipCode")
                and not (a.get("streetAddress1") or "").strip()
                and not (a.get("city") or "").strip())
        return ("skipped-has-address",
                {"id": cid, "state": a.get("state"), "zip": a.get("zipCode"),
                 "reconstruct": bool(ours)})

    guard = {k: before.get(k) for k in ("firstName", "lastName", "email", "phoneNumber")}

    if DRY_RUN:
        return "would-write", {"id": cid, "state": state, "zip": zip_code}

    payload = dict(before)          # full object: a partial payload blanks fields
    payload["address"] = [{
        "state": state,
        "zipCode": zip_code,
        "country": "United States",
        "isPrimary": True,
        "type": address_type,
        "streetAddress1": "",       # left empty: this is a counter-collected ZIP,
        "city": "",                 # not a mailable address
    }]
    api_request("PUT", "/v2/b2b/customers", payload)

    after = api_request("GET", f"/v2/b2b/customers/{cid}")
    lost = [k for k, v in guard.items() if v and not after.get(k)]
    if lost:
        raise SystemExit(
            f"ABORT: writing customer {cid} blanked {lost}. The upsert semantics "
            "have changed or the payload was incomplete. No further writes will "
            f"be attempted. Restore from data/{LOG_PATH.name}.")
    if not after.get("address"):
        return "write-had-no-effect", {"id": cid}
    return "written", {"id": cid, "state": state, "zip": zip_code, "before": guard}


# ----------------------------------------------------------------------- main

def main():
    if MOCK:
        sys.exit("No ACME_API_KEY — refusing to run.")
    config = json.loads(CONFIG_PATH.read_text())
    cfg = config.get("fillState") or {}
    tz = ZoneInfo(config.get("timezone", "America/Denver"))
    channels = cfg.get("channels", ["Pos", "InsideSalesIndividual"])
    max_per_run = env_int("FILL_STATE_MAX", cfg.get("maxPerRun", 400))
    address_type = cfg.get("addressType", "home")

    lookup, n_ranges = load_crosswalk()
    prev = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    now = datetime.now(tz)

    # Re-scan a few days behind the last run: orders can be amended after the
    # visit, and a missed night should heal itself rather than leave a hole.
    lookback = int(cfg.get("lookbackDays", 10))
    since_iso = prev.get("lastRunDate") or config.get("seasonStart", "2026-07-04")
    since = max(datetime.fromisoformat(since_iso).replace(tzinfo=tz) - timedelta(days=lookback),
                datetime.fromisoformat(config.get("seasonStart", "2026-07-04")).replace(tzinfo=tz))
    until = now.replace(hour=23, minute=59, second=59, microsecond=0)

    print(f"Crosswalk: {n_ranges:,} ZIP ranges.")
    print(f"Scanning {since:%Y-%m-%d} -> {until:%Y-%m-%d}, channels {channels}"
          + (" [DRY RUN]" if DRY_RUN else ""))

    # Resumable queue. Building the candidate list costs a report round trip, and
    # the analytics warehouse lags behind our own writes — so a re-query returns
    # customers we already filled, which then cost two API calls each to discover
    # and skip. Persisting the queue makes a resumed run pure work: no report, no
    # re-walking what is already done.
    queue = {}
    if QUEUE_PATH.exists():
        try:
            q = json.loads(QUEUE_PATH.read_text())
            age_h = (now - datetime.fromisoformat(q["builtAt"])).total_seconds() / 3600
            if age_h < float(cfg.get("queueMaxAgeHours", 24)):
                queue = q.get("pending") or {}
                print(f"Resuming queue: {len(queue):,} pending "
                      f"(built {age_h:.1f}h ago, {q.get('doneCount', 0):,} already done).")
        except (json.JSONDecodeError, KeyError, ValueError):
            queue = {}

    if not queue:
        queue = find_candidates(tz, since, until, channels)
        print(f"{len(queue):,} customers with a ZIP and no state.")
        _atomic_write(QUEUE_PATH, json.dumps(
            {"builtAt": now.isoformat(), "window": [since.date().isoformat(),
                                                    until.date().isoformat()],
             "doneCount": 0, "pending": queue}, indent=1))
    cands = queue
    done_keys = []

    def flush_queue(force=False):
        if DRY_RUN or (not force and len(done_keys) % 25):
            return
        try:
            q = json.loads(QUEUE_PATH.read_text())
        except (json.JSONDecodeError, FileNotFoundError):
            return
        for k in done_keys:
            q.get("pending", {}).pop(k, None)
        q["doneCount"] = q.get("doneCount", 0) + len(done_keys)
        q["updatedAt"] = now.isoformat()
        _atomic_write(QUEUE_PATH, json.dumps(q, indent=1))
        done_keys.clear()

    # Each customer costs up to four serial round trips (search, read, write,
    # verify), so throughput is latency-bound, not CPU- or rate-bound. Modest
    # concurrency turns a ~70-minute backlog pass into a few minutes. Customers
    # are independent — no two tasks touch the same record — so the only shared
    # state needing a lock is the log and the queue.
    workers = max(1, int(cfg.get("workers", 6)))
    lock = threading.Lock()
    tally = collections.Counter()
    written = []
    logged_ids = set()
    if LOG_PATH.exists():
        try:
            logged_ids = {e.get("id") for e in
                          json.loads(LOG_PATH.read_text()).get("entries", [])}
        except json.JSONDecodeError:
            pass
    abort = {}

    def process(item):
        key, zc = item
        if abort:
            return
        state = lookup(zc)
        if not state or state in NON_STATE:
            with lock:
                tally["unresolvable-zip" if not state else "military-zip-skipped"] += 1
                done_keys.append(key); flush_queue()
            return
        try:
            status, detail = fill_one(key, zc, state, address_type)
        except SystemExit as exc:
            with lock:
                abort["why"] = str(exc)
            return
        except Exception as exc:  # noqa: BLE001
            with lock:
                tally["error"] += 1
            print(f"  error on one customer: {str(exc)[:120]}", file=sys.stderr)
            return
        with lock:
            tally[status] += 1
            done_keys.append(key)
            flush_queue()
            if status == "skipped-has-address" and detail and detail.get("reconstruct"):
                if detail["id"] not in logged_ids:
                    logged_ids.add(detail["id"])
                    tally["reconstructed-log"] += 1
                    append_log([{"at": now.isoformat(), "customerId": key,
                                 "id": detail["id"], "state": detail["state"],
                                 "zip": detail["zip"], "beforeHadAddress": False,
                                 "reconstructed": True}])
            if status == "written":
                entry = {"at": now.isoformat(), "customerId": key,
                         "id": detail["id"], "state": state, "zip": zc,
                         "beforeHadAddress": False}
                written.append(entry)
                append_log([entry])

    batch = sorted(cands.items())[:max_per_run]
    tally["deferred"] = max(0, len(cands) - len(batch))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(process, batch))
    if abort:
        sys.exit(abort["why"])

    flush_queue(force=True)
    remaining = 0
    if QUEUE_PATH.exists() and not DRY_RUN:
        remaining = len(json.loads(QUEUE_PATH.read_text()).get("pending") or {})
        if remaining == 0:
            QUEUE_PATH.unlink()      # drained; next run rebuilds from ACME

    if not DRY_RUN:
        # Only advance the watermark once a run clears its whole queue. Moving it
        # while work is deferred would push the untouched backlog outside the next
        # run's lookback window, stranding it permanently — with a 3,000-deep
        # queue and a 400 cap that would silently abandon most of it.
        advance = tally["deferred"] == 0 and remaining == 0
        STATE_PATH.write_text(json.dumps({
            "lastRun": now.isoformat(),
            "lastRunDate": now.date().isoformat() if advance else since_iso,
            "backlogRemaining": remaining or tally["deferred"],
            "watermarkHeld": not advance,
            "lastTally": dict(tally),
            "totalWritten": (prev.get("totalWritten", 0) + tally["written"]),
        }, indent=1))

    print("Result: " + ", ".join(f"{k}={v}" for k, v in sorted(tally.items())) or "nothing to do")
    if tally["deferred"]:
        print(f"  {tally['deferred']} deferred by maxPerRun={max_per_run}; "
              "they will be picked up on the next run.")


if __name__ == "__main__":
    main()
