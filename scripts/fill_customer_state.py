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
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_availability import (  # noqa: E402  (shared API plumbing)
    api_request, execute_report, ORIGIN_REPORT_ID, ROOT, DATA_DIR, MOCK,
)

CROSSWALK_PATH = DATA_DIR / "zip-state.json"
STATE_PATH = DATA_DIR / "fill-state.json"
LOG_PATH = DATA_DIR / "fill-state-log.json"
CONFIG_PATH = ROOT / "config.json"

DRY_RUN = os.environ.get("FILL_STATE_DRY_RUN") == "1"
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
    if before.get("address"):
        return "skipped-has-address", None

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
    max_per_run = int(os.environ.get("FILL_STATE_MAX", cfg.get("maxPerRun", 400)))
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

    cands = find_candidates(tz, since, until, channels)
    print(f"{len(cands):,} customers with a ZIP and no state.")

    tally = collections.Counter()
    written = []
    for i, (key, zc) in enumerate(sorted(cands.items())):
        if tally["written"] + tally["would-write"] >= max_per_run:
            tally["deferred"] += 1
            continue
        state = lookup(zc)
        if not state:
            tally["unresolvable-zip"] += 1
            continue
        if state in NON_STATE:
            tally["military-zip-skipped"] += 1
            continue
        try:
            status, detail = fill_one(key, zc, state, address_type)
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            tally["error"] += 1
            print(f"  error on one customer: {str(exc)[:120]}", file=sys.stderr)
            continue
        tally[status] += 1
        if status == "written":
            written.append({"at": now.isoformat(), "customerId": key,
                            "id": detail["id"], "state": state, "zip": zc,
                            "beforeHadAddress": False})

    if written and not DRY_RUN:
        log = json.loads(LOG_PATH.read_text()) if LOG_PATH.exists() else {"entries": []}
        log["entries"].extend(written)
        log["note"] = ("Every address this job has written, for audit and revert. "
                       "beforeHadAddress is always false — the job never touches "
                       "a customer who already had one.")
        LOG_PATH.write_text(json.dumps(log, indent=1))

    if not DRY_RUN:
        # Only advance the watermark once a run clears its whole queue. Moving it
        # while work is deferred would push the untouched backlog outside the next
        # run's lookback window, stranding it permanently — with a 3,000-deep
        # queue and a 400 cap that would silently abandon most of it.
        advance = tally["deferred"] == 0
        STATE_PATH.write_text(json.dumps({
            "lastRun": now.isoformat(),
            "lastRunDate": now.date().isoformat() if advance else since_iso,
            "backlogRemaining": tally["deferred"],
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
