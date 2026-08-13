#!/usr/bin/env python3
"""
Fetch General Admission availability-by-time-slot from the ACME Reporting API,
compute sold-out status and sell-out risk, and publish:

  data/availability.json   consumed by the public widgets
  data/history.json        rolling 72h of 15-min snapshots (intraday pace)
  data/leads.json          pct-sold observed at each days-out lead time
  data/archive/YYYY-MM.json permanent per-day outcomes (grows forever -> YoY)
  data/analytics.json      day-of-week sell-out behavior over the lookback window

The report ("TRPL: 2026 Availability", definition 69c18975669b758620b4c586)
returns one row per GA event instance with EventStartTime, AvailableQuantity,
and Capacity. Each run requests (today - lookbackDays) -> (today + daysAhead):
past days bootstrap the archive with final outcomes, future days feed the
widgets and lead curves.

Why day-of-week analytics: percent-sold alone is misleading. A day can sit at
60% sold the night before and still sell out by mid-morning from walk-up
demand. Risk is therefore driven by observed same-day demand for that weekday
(and per-slot sell-out history), not just current supply.

ACME Reporting API flow (see
https://developers.acmeticketing.com/support/solutions/articles/33000275437):
  1. GET  /v2/b2b/analytics/report/definitions/{id}
  2. POST /v2/b2b/async/report   {reportUuid, queryExpression, dateRangeField,
                                  startDate, endDate}
  3. GET  /v2/b2b/async/report/{id}        poll until Completed
  4. GET  /v2/b2b/async/report/json/{id}   columnar results

Environment variables (a gitignored .env at the repo root is loaded first):
  ACME_API_KEY     required for live mode (GitHub Actions secret)
  ACME_API_BASE    default https://api.acmeticketing.com
  ACME_REPORT_ID   default 69c18975669b758620b4c586
  MOCK             set to "1" to force sample data (no API call)

Runs on Python 3.9+ stdlib only.
"""

import calendar
import json
import os
import random
import statistics
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timedelta, date
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent

# Load .env for local testing (gitignored). Real env vars take precedence.
_env_file = ROOT / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

DATA_DIR = ROOT / "data"
ARCHIVE_DIR = DATA_DIR / "archive"
CONFIG_PATH = ROOT / "config.json"
HISTORY_PATH = DATA_DIR / "history.json"
LEADS_PATH = DATA_DIR / "leads.json"
ANALYTICS_PATH = DATA_DIR / "analytics.json"
OUTPUT_PATH = DATA_DIR / "availability.json"
RAW_PATH = DATA_DIR / "raw-report.json"  # last raw API response, for debugging

API_BASE = os.environ.get("ACME_API_BASE", "https://api.acmeticketing.com").rstrip("/")
API_KEY = os.environ.get("ACME_API_KEY", "")
if API_KEY == "paste-key-here":
    API_KEY = ""
REPORT_ID = os.environ.get("ACME_REPORT_ID", "69c18975669b758620b4c586")
MOCK = os.environ.get("MOCK", "") == "1" or not API_KEY

POLL_INTERVAL_S = 5
POLL_TIMEOUT_S = 300
HISTORY_KEEP_HOURS = 72


# ---------------------------------------------------------------- API helpers

def api_request(method, path, payload=None):
    url = f"{API_BASE}{path}"
    headers = {
        "x-acme-api-key": API_KEY,
        "Accept": "application/json",
        "User-Agent": "TRPL-TicketingWidgets/1.0 (github.com/Theodore-Roosevelt-Presidential-Library/TicketingWidgets)",
    }
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")[:500]
            if e.code == 429 and attempt < 2:
                print("429 rate limited; retrying in 30s ...", file=sys.stderr)
                time.sleep(30)
                continue
            raise RuntimeError(f"{method} {path} -> HTTP {e.code}: {body}") from e
        except urllib.error.URLError:
            if attempt < 2:
                time.sleep(10)
                continue
            raise


def run_report(tz, horizon_days, lookback_days):
    """Execute the report for (today - lookback) -> (today + horizon)."""
    print(f"Fetching report definition {REPORT_ID} ...")
    definition = api_request("GET", f"/v2/b2b/analytics/report/definitions/{REPORT_ID}")

    query_expression = definition.get("queryExpression")
    if not query_expression:
        raise RuntimeError(
            f"Report definition missing queryExpression. Keys: {list(definition.keys())}"
        )
    date_field = (definition.get("dateSettings") or {}).get("dateRangeField", "EventStartTime")

    now = datetime.now(tz)
    start = (now - timedelta(days=lookback_days)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = (now + timedelta(days=horizon_days)).replace(hour=23, minute=59, second=59, microsecond=0)
    payload = {
        "reportUuid": REPORT_ID,
        "queryExpression": query_expression,
        "dateRangeField": date_field,
        "startDate": start.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "endDate": end.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }

    print(f"Executing report for {payload['startDate']} -> {payload['endDate']} ...")
    instance = api_request("POST", "/v2/b2b/async/report", payload)
    instance_id = instance.get("id")
    if not instance_id:
        raise RuntimeError(f"No report instance id in response: {instance}")

    print(f"Polling report instance {instance_id} ...")
    deadline = time.time() + POLL_TIMEOUT_S
    while time.time() < deadline:
        status_obj = api_request("GET", f"/v2/b2b/async/report/{instance_id}")
        status = str(status_obj.get("status", "")).lower()
        if status in ("complete", "completed", "success"):
            break
        if status in ("failed", "error", "cancelled"):
            raise RuntimeError(f"Report failed: {status_obj}")
        time.sleep(POLL_INTERVAL_S)
    else:
        raise RuntimeError("Timed out waiting for report to complete")

    print("Retrieving results ...")
    return api_request("GET", f"/v2/b2b/async/report/json/{instance_id}")


# ------------------------------------------------------------- result parsing

def parse_availability(raw, tz):
    """Return {(iso_date, "HH:MM"): {"available": int, "capacity": int}}."""
    field_list = raw.get("resultFieldList") if isinstance(raw, dict) else None
    if not field_list:
        raise RuntimeError(
            f"Unexpected report result shape. Keys: {list(raw.keys()) if isinstance(raw, dict) else type(raw)}"
        )
    cols = {str(f.get("fieldName", "")).lower(): (f.get("values") or []) for f in field_list}

    def col(*needles):
        for name, values in cols.items():
            if any(n in name for n in needles):
                return values
        return None

    times = col("starttime", "start time", "eventstart")
    avail = col("availablequantity", "available")
    cap = col("capacity")
    if times is None or avail is None or cap is None:
        raise RuntimeError(f"Could not identify report columns. Found: {list(cols.keys())}")

    out = {}
    for i, t in enumerate(times):
        try:
            dt = datetime.fromisoformat(str(t)).astimezone(tz)
        except ValueError:
            continue
        key = (dt.date().isoformat(), dt.strftime("%H:%M"))
        a = int(float(avail[i])) if i < len(avail) and avail[i] is not None else 0
        c = int(float(cap[i])) if i < len(cap) and cap[i] is not None else 0
        if key in out:  # multiple instances in one slot: sum
            out[key]["available"] += a
            out[key]["capacity"] += c
        else:
            out[key] = {"available": a, "capacity": c}
    return out


# --------------------------------------------------------------- mock data

def mock_availability(config, tz, past_days, future_days):
    """Plausible August pattern, including past finals for analytics testing."""
    random.seed(20260813)
    now = datetime.now(tz)
    out = {}
    slots8 = ["09:00", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00"]
    cap = 200
    for d in past_days:
        dow = date.fromisoformat(d).weekday()
        heavy = dow in (3, 4, 5)  # Thu/Fri/Sat sell out
        for j, slot in enumerate(slots8):
            if heavy:
                avail = 0 if j < 7 else random.choice([0, 0, 40])
            else:
                avail = int(cap * random.uniform(0.0, 0.35)) if j < 5 else int(cap * random.uniform(0.2, 0.6))
            out[(d, slot)] = {"available": avail, "capacity": cap}
    for i, d in enumerate(future_days):
        for j, slot in enumerate(slots8):
            slot_dt = datetime.fromisoformat(f"{d}T{slot}").replace(tzinfo=tz)
            if i == 0:
                if slot_dt < now or j < len(slots8) * 0.5:
                    avail = 0
                else:
                    avail = random.choice([0, 1, 1, 13, int(cap * 0.6)])
            elif i in (1, 2):
                avail = int(cap * random.uniform(0.0, 0.5))
            else:
                avail = int(cap * random.uniform(0.4, 0.9))
            out[(d, slot)] = {"available": avail, "capacity": cap}
    return out


# ---------------------------------------------------------------- small utils

def slot_label(hhmm):
    h, m = map(int, hhmm.split(":"))
    suffix = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12}:{m:02d} {suffix}"


def load_json(path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            pass
    return default


def dow_name(iso_date):
    return calendar.day_name[date.fromisoformat(iso_date).weekday()]


# ---------------------------------------------------------------- history

def load_history():
    return load_json(HISTORY_PATH, {"snapshots": []})


def compute_velocity(history, day_iso, now):
    """Tickets/hour sold for a given day over roughly the last 3 hours of snapshots."""
    points = []
    for snap in history.get("snapshots", []):
        try:
            t = datetime.fromisoformat(snap["t"])
        except (KeyError, ValueError):
            continue
        if (now - t).total_seconds() > 3 * 3600:
            continue
        day = snap.get("days", {}).get(day_iso)
        if day is not None:
            points.append((t, day.get("sold", 0)))
    if len(points) < 2:
        return None
    points.sort(key=lambda p: p[0])
    (t0, s0), (t1, s1) = points[0], points[-1]
    hours = (t1 - t0).total_seconds() / 3600
    if hours < 0.4:
        return None
    return max(0.0, (s1 - s0) / hours)


def sellout_times_from_history(history, day_iso, capacities):
    """{slot: iso_time_or_None} — first snapshot at which each slot hit 0 remaining."""
    out = {}
    for snap in sorted(history.get("snapshots", []), key=lambda s: s.get("t", "")):
        day = snap.get("days", {}).get(day_iso)
        if not day:
            continue
        for slot, sold in day.get("slots", {}).items():
            cap = capacities.get(slot)
            if cap and sold >= cap and slot not in out:
                out[slot] = snap["t"]
    return {slot: out.get(slot) for slot in capacities}


def update_history(history, availability, now):
    snap = {"t": now.isoformat(), "days": {}}
    for day in availability["days"]:
        if not day.get("closed"):
            snap["days"][day["date"]] = {
                "sold": day["totalSold"],
                "slots": {s["time"]: s["sold"] for s in day["slots"]},
            }
    history["snapshots"].append(snap)
    cutoff = now - timedelta(hours=HISTORY_KEEP_HOURS)
    history["snapshots"] = [
        s for s in history["snapshots"]
        if datetime.fromisoformat(s["t"]) >= cutoff
    ]
    return history



# ---------------------------------------------------------------- closures

CLOSURES_PATH = ROOT / "closures.json"
DOW_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def closure_reason(d, closures):
    """Return a human-readable closure reason for date d, or None if open."""
    d_iso = d.isoformat()
    for h in closures.get("holidays", []):
        if h.get("date") == d_iso:
            return h.get("name", "Holiday")
    dow = DOW_NAMES[d.weekday()]
    for w in closures.get("weeklyClosures", []):
        if w.get("validFrom", "") <= d_iso <= w.get("validThrough", "") and dow in w.get("daysClosed", []):
            label = (w.get("label") or "seasonal hours").split(" (")[0]
            return f"Closed {dow}s ({label})"
    return None

# ---------------------------------------------------------------- lead curves

def update_leads(leads, slot_data, today_iso, tz):
    """Record the first-seen pct sold for each future date at each days-out."""
    by_date = {}
    for (d_iso, hhmm), rec in slot_data.items():
        by_date.setdefault(d_iso, []).append(rec)
    today = date.fromisoformat(today_iso)
    for d_iso, recs in by_date.items():
        d = date.fromisoformat(d_iso)
        days_out = (d - today).days
        if days_out < 0:
            continue
        # Keep the file bounded over a full year: daily resolution inside 30
        # days, weekly beyond that.
        if days_out > 30 and days_out % 7 != 0:
            continue
        cap = sum(r["capacity"] for r in recs)
        sold = cap - sum(min(r["available"], r["capacity"]) for r in recs)
        entry = leads.setdefault(d_iso, {"obs": {}})
        key = str(days_out)
        if key not in entry["obs"]:
            entry["obs"][key] = {
                "sold": sold,
                "capacity": cap,
                "pct": round(100 * sold / cap) if cap else 0,
                "at": datetime.now(tz).isoformat(),
            }
    return leads


# ---------------------------------------------------------------- archive

def archive_month_path(d_iso):
    return ARCHIVE_DIR / f"{d_iso[:7]}.json"


def load_archive_record(d_iso):
    month = load_json(archive_month_path(d_iso), {})
    return month.get(d_iso)


def save_archive_record(d_iso, record):
    path = archive_month_path(d_iso)
    month = load_json(path, {})
    month[d_iso] = record
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(sorted(month.items())), indent=1))


def write_archive_index():
    """data/archive/index.json — lets the calendar page discover archive months."""
    months = sorted(p.stem for p in ARCHIVE_DIR.glob("*.json") if p.stem != "index")
    (ARCHIVE_DIR / "index.json").write_text(json.dumps({"months": months}))


def update_archive(slot_data, leads, history, today_iso):
    """Write final outcomes for every past date present in the report window."""
    by_date = {}
    for (d_iso, hhmm), rec in slot_data.items():
        if d_iso < today_iso:
            by_date.setdefault(d_iso, {})[hhmm] = rec

    archived = 0
    for d_iso, slots in sorted(by_date.items()):
        existing = load_archive_record(d_iso) or {}
        capacities = {t: r["capacity"] for t, r in slots.items()}
        slot_records = {}
        total_cap = total_sold = 0
        for t in sorted(slots):
            cap = max(0, slots[t]["capacity"])
            remaining = max(0, min(slots[t]["available"], cap))
            sold = cap - remaining
            total_cap += cap
            total_sold += sold
            slot_records[t] = {"capacity": cap, "sold": sold, "soldOut": remaining <= 0}

        sellouts = sellout_times_from_history(history, d_iso, capacities)
        # Preserve anything richer we captured earlier (live sellout times, leads)
        prev_sellouts = existing.get("selloutTimes", {})
        sellouts = {t: sellouts.get(t) or prev_sellouts.get(t) for t in capacities}

        lead_entry = leads.get(d_iso, {}).get("obs", {}) or existing.get("leadCurve", {})
        baseline = lead_entry.get("0", {}).get("sold")
        record = {
            "date": d_iso,
            "dow": dow_name(d_iso),
            "capacity": total_cap,
            "sold": total_sold,
            "pctSold": round(100 * total_sold / total_cap) if total_cap else 0,
            "fullySoldOut": total_cap > 0 and all(r["soldOut"] for r in slot_records.values()),
            "slots": slot_records,
            "selloutTimes": sellouts,
            "leadCurve": lead_entry,
            "dayOfTickets": (total_sold - baseline) if baseline is not None else None,
        }
        save_archive_record(d_iso, record)
        archived += 1
        leads.pop(d_iso, None)  # archived; no longer a future date
    return archived


def load_recent_archive(today_iso, lookback_days):
    """Archive records for the lookback window, newest last."""
    today = date.fromisoformat(today_iso)
    records = []
    months = set()
    for i in range(1, lookback_days + 1):
        months.add((today - timedelta(days=i)).isoformat()[:7])
    data = {}
    for m in sorted(months):
        data.update(load_json(ARCHIVE_DIR / f"{m}.json", {}))
    for i in range(lookback_days, 0, -1):
        d_iso = (today - timedelta(days=i)).isoformat()
        if d_iso in data:
            records.append(data[d_iso])
    return records


# ---------------------------------------------------------------- analytics

def compute_analytics(records, lookback_days, today_iso, tz):
    """Day-of-week sell-out behavior over the lookback window."""
    per_dow = {}
    for rec in records:
        per_dow.setdefault(rec["dow"], []).append(rec)

    dows = {}
    for dow, recs in per_dow.items():
        pcts = [r["pctSold"] for r in recs]
        sold_out_days = [r for r in recs if r.get("fullySoldOut")]
        day_of = [r["dayOfTickets"] for r in recs if r.get("dayOfTickets") is not None]

        # Per-slot sell-out rate (how often each entry time ended sold out)
        slot_rates = {}
        for r in recs:
            for t, s in r.get("slots", {}).items():
                slot_rates.setdefault(t, []).append(1 if s["soldOut"] else 0)
        slot_rates = {t: round(sum(v) / len(v), 2) for t, v in sorted(slot_rates.items())}

        # Typical first entry time still available at end of day
        first_avail = []
        for r in recs:
            open_slots = [t for t, s in sorted(r.get("slots", {}).items()) if not s["soldOut"]]
            first_avail.append(open_slots[0] if open_slots else None)
        non_null = sorted(t for t in first_avail if t)
        typical_first = non_null[len(non_null) // 2] if non_null else None

        # Observed sell-out clock times (when a slot's last ticket went)
        sellout_clocks = []
        for r in recs:
            times = [v for v in (r.get("selloutTimes") or {}).values() if v]
            if times and r.get("fullySoldOut"):
                sellout_clocks.append(max(times)[11:16])

        dows[dow] = {
            "daysObserved": len(recs),
            "medianFinalPctSold": round(statistics.median(pcts)) if pcts else None,
            "fullSelloutRate": round(len(sold_out_days) / len(recs), 2) if recs else None,
            "fullSelloutCount": len(sold_out_days),
            "medianDayOfTickets": round(statistics.median(day_of)) if day_of else None,
            "slotSelloutRate": slot_rates,
            "typicalFirstAvailableAtEndOfDay": slot_label(typical_first) if typical_first else (
                "none — fully sold out" if first_avail and all(t is None for t in first_avail) else None),
            "observedFullSelloutClockTimes": sellout_clocks or None,
        }

    return {
        "generatedAt": datetime.now(tz).isoformat(),
        "lookbackDays": lookback_days,
        "windowEnd": today_iso,
        "recentDays": [
            {
                "date": r["date"], "dow": r["dow"], "pctSold": r["pctSold"],
                "fullySoldOut": r.get("fullySoldOut", False),
                "soldOutSlots": sum(1 for s in r.get("slots", {}).values() if s["soldOut"]),
                "slotCount": len(r.get("slots", {})),
                "dayOfTickets": r.get("dayOfTickets"),
            }
            for r in records
        ],
        "byDayOfWeek": dows,
    }


def compute_month_outlook(records, availability, tz):
    """Compose a short, friendly narrative: what this month has looked like and
    what to expect. Rendered verbatim by the 'outlook' text widget."""
    now = datetime.now(tz)
    month_name = now.strftime("%B")
    heading = f"What to Expect in {month_name}"
    n = len(records)
    if n < 3:
        return {
            "heading": heading,
            "text": ("The Library uses timed-entry tickets, and busy days can sell out — "
                     "sometimes well before midday. Reserving tickets online before arriving "
                     "is the surest way in."),
            "updatedAt": now.isoformat(),
        }

    pcts = [r["pctSold"] for r in records]
    med = round(statistics.median(pcts))
    full = sum(1 for r in records if r.get("fullySoldOut"))
    morning_days = 0
    first_opens = []
    for r in records:
        slots = sorted(r.get("slots", {}).items())
        if any(s["soldOut"] for _, s in slots[:3]):
            morning_days += 1
        open_slots = [t for t, s in slots if not s["soldOut"]]
        first_opens.append(open_slots[0] if open_slots else None)

    sentences = []
    if med >= 90:
        s = (f"{month_name} has been busy: over the last {n} days, daily ticket sales "
             f"reached a median {med}% of capacity")
        s += f", and {full} {'day' if full == 1 else 'days'} sold out completely." if full else "."
        sentences.append(s)
    elif med >= 65:
        sentences.append(f"{month_name} has been steady: over the last {n} days, daily ticket "
                         f"sales reached a median {med}% of capacity.")
    else:
        sentences.append(f"{month_name} has had good availability, with daily ticket sales at "
                         f"a median {med}% of capacity over the last {n} days.")

    if morning_days / n >= 0.5:
        opens = sorted(t for t in first_opens if t)
        typical = slot_label(opens[len(opens) // 2]) if opens else None
        s = f"Mornings go first — morning entry times sold out on {morning_days} of those days"
        s += f", often leaving {typical} or later as the earliest way in." if typical else "."
        sentences.append(s)

    upcoming = [d for d in availability["days"][1:8] if not d.get("closed")]
    hot = sum(1 for d in upcoming if d["selloutRisk"] in ("high", "sold_out"))
    if upcoming and hot >= max(1, len(upcoming) // 2):
        sentences.append(f"The week ahead looks similar: {hot} of the next {len(upcoming)} open "
                         "days are likely to sell out.")
    elif upcoming and hot:
        sentences.append(f"In the week ahead, {hot} {'day looks' if hot == 1 else 'days look'} "
                         "likely to sell out.")

    sentences.append("Reserving tickets online before arriving is strongly recommended, "
                     "especially for mornings and weekends."
                     if med >= 65 else
                     "Advance tickets guarantee an entry time.")

    return {"heading": heading, "text": " ".join(sentences), "updatedAt": now.isoformat()}


# ------------------------------------------------------------- availability

def build_availability(slot_data, config, tz, history, analytics, closures=None):
    now = datetime.now(tz)
    days_ahead = config.get("daysAhead", 7)
    lim_pct = config.get("limitedThresholdPct", 15)
    lim_min = config.get("limitedThresholdMin", 10)

    by_date = {}
    for (d_iso, hhmm), rec in slot_data.items():
        if d_iso >= now.date().isoformat():
            by_date.setdefault(d_iso, {})[hhmm] = rec

    days_out = []
    for i in range(days_ahead + 1):
        d = now.date() + timedelta(days=i)
        d_iso = d.isoformat()
        day_label = "Today" if i == 0 else ("Tomorrow" if i == 1 else d.strftime("%a %b %-d"))
        day_slots = by_date.get(d_iso)
        reason = closure_reason(d, closures or {})

        if day_slots and reason:
            print(f"WARNING: {d_iso} is marked closed ({reason}) but ACME has "
                  f"{len(day_slots)} sellable slots — closure wins for display. "
                  "Check closures.json vs ACME.", file=sys.stderr)
            day_slots = None

        if not day_slots:
            days_out.append({
                "date": d_iso, "dayLabel": day_label, "closed": True, "slots": [],
                "closedReason": reason,
                "status": "closed", "selloutRisk": "none",
                "riskNote": f"Closed — {reason}" if reason else "Closed",
                "totalCapacity": 0, "totalSold": 0, "pctSold": 0,
                "soldOutSlots": 0, "firstAvailable": None,
            })
            continue

        slots = []
        total_cap = total_sold = sold_out_count = 0
        first_available = None
        for t in sorted(day_slots):
            rec = day_slots[t]
            cap = max(0, rec["capacity"])
            remaining = max(0, min(rec["available"], cap))
            sold = cap - remaining
            slot_dt = datetime.fromisoformat(f"{d_iso}T{t}").replace(tzinfo=tz)
            past = i == 0 and slot_dt <= now
            if past:
                status = "past"
            elif remaining <= 0:
                status = "sold_out"
            elif remaining <= max(lim_min, cap * lim_pct / 100):
                status = "limited"
            else:
                status = "available"
            if status == "sold_out":
                sold_out_count += 1
            if status in ("available", "limited") and first_available is None:
                first_available = slot_label(t)
            total_cap += cap
            total_sold += sold
            slots.append({
                "time": t, "label": slot_label(t), "capacity": cap,
                "sold": sold, "remaining": remaining, "status": status,
            })

        pct = round(100 * total_sold / total_cap) if total_cap else 0
        future = [s for s in slots if s["status"] != "past"]
        all_out = bool(future) and all(s["status"] == "sold_out" for s in future)

        risk, note = day_risk(d_iso, i, pct, all_out, slots, tz, now, history, analytics)
        status = ("sold_out" if all_out else
                  "selling_fast" if risk == "high" else
                  "limited" if pct >= 60 else "available")

        days_out.append({
            "date": d_iso, "dayLabel": day_label, "closed": False,
            "totalCapacity": total_cap, "totalSold": total_sold, "pctSold": pct,
            "soldOutSlots": sold_out_count, "firstAvailable": first_available,
            "status": status, "selloutRisk": risk, "riskNote": note,
            "slots": slots,
        })

    return {
        "generatedAt": now.isoformat(),
        "timezone": str(tz),
        "today": now.date().isoformat(),
        "ticketsUrl": config.get("ticketsUrl", "https://www.trlibrary.com/tickets"),
        "days": days_out,
    }


def day_risk(d_iso, day_index, pct, all_out, slots, tz, now, history, analytics):
    """Risk = supply vs expected demand for this weekday, not just pct sold."""
    if all_out:
        return "sold_out", "Sold out — no remaining time slots."

    dow = dow_name(d_iso)
    dowa = (analytics or {}).get("byDayOfWeek", {}).get(dow, {})
    remaining = sum(s["remaining"] for s in slots if s["status"] in ("available", "limited"))
    day_of_demand = dowa.get("medianDayOfTickets")  # walk-up + same-day online

    if day_index == 0:
        # Blend observed pace with historical same-day demand for this weekday
        velocity = compute_velocity(history, d_iso, now) or 0.0
        hist_rate = 0.0
        if day_of_demand:
            open_hours = max(1.0, len([s for s in slots]) )  # ~1 slot per hour
            hist_rate = day_of_demand / open_hours
        rate = max(velocity, hist_rate)
        if rate > 1 and remaining > 0:
            projected = now + timedelta(hours=remaining / rate)
            close_dt = datetime.fromisoformat(f"{d_iso}T{slots[-1]['time']}").replace(tzinfo=tz)
            if projected <= close_dt:
                t = projected.strftime("%-I:%M %p")
                src = "today's pace" if velocity >= hist_rate else f"typical {dow} walk-up demand"
                return "high", f"Based on {src}, remaining tickets may be gone by about {t}."
        if pct >= 85:
            return "high", "Very few tickets remain today — buy online before you drive."
        if pct >= 65:
            return "medium", "Today is filling up — buying online is recommended."
        return "low", "Good availability today."

    # ---- Future days: what has same-day demand done to this weekday recently?
    n = dowa.get("daysObserved", 0)
    if day_of_demand is not None and remaining <= day_of_demand:
        return "high", (f"Recent {dow}s have sold {day_of_demand}+ tickets on the day itself — "
                        "more than what's left. Reserve in advance.")
    if n >= 2:
        sellout_rate = dowa.get("fullSelloutRate") or 0
        median_final = dowa.get("medianFinalPctSold") or 0
        first_end = dowa.get("typicalFirstAvailableAtEndOfDay")
        if sellout_rate >= 0.5 and pct >= 25:
            return "high", (f"{dowa.get('fullSelloutCount')} of the last {n} {dow}s sold out "
                            "completely — reserve in advance.")
        if median_final >= 90 and pct >= 25:
            note = f"{dow}s have been selling out"
            if first_end and "none" not in str(first_end):
                note += f" — recently only {first_end} or later entry remained"
            return "high", note + ". Reserve in advance."
    # Percent-sold fallback (early sell-through at a distance implies risk)
    threshold_high = 80 - day_index * 5
    threshold_med = 55 - day_index * 5
    if pct >= threshold_high:
        return "high", "Expected to sell out — reserve in advance."
    if pct >= threshold_med:
        return "medium", "Filling up — advance tickets recommended."
    return "low", "Good availability."


# ------------------------------------------------------------------- main

def main():
    config = json.loads(CONFIG_PATH.read_text())
    tz = ZoneInfo(config.get("timezone", "America/Denver"))
    now = datetime.now(tz)
    today_iso = now.date().isoformat()
    days_ahead = config.get("daysAhead", 7)
    horizon = max(days_ahead, config.get("futureDaysAhead", 365))
    # ACME_LOOKBACK_DAYS overrides for one-off archive backfills (e.g. season start)
    lookback = int(os.environ.get("ACME_LOOKBACK_DAYS", config.get("lookbackDays", 15)))
    DATA_DIR.mkdir(exist_ok=True)

    if MOCK:
        print("MOCK mode (no ACME_API_KEY set) — generating sample data.")
        past = [(now.date() - timedelta(days=i)).isoformat() for i in range(lookback, 0, -1)]
        future = [(now.date() + timedelta(days=i)).isoformat() for i in range(days_ahead + 1)]
        slot_data = mock_availability(config, tz, past, future)
        for i in range(days_ahead + 1, 90):  # sparse advance sales further out
            d = (now.date() + timedelta(days=i)).isoformat()
            for slot in ["09:00", "11:00", "13:00", "15:00"]:
                pct = max(0.02, 0.5 - i * 0.005)
                slot_data[(d, slot)] = {"available": int(200 * (1 - pct)), "capacity": 200}
    else:
        raw = run_report(tz, horizon, lookback)
        RAW_PATH.write_text(json.dumps(raw, indent=2)[:4_000_000])
        slot_data = parse_availability(raw, tz)
        print(f"Parsed {len(slot_data)} (date, slot) pairs from report.")
        if not any(d >= today_iso for d, _ in slot_data):
            raise RuntimeError("Report returned no current/future slot data — refusing to publish.")

    closures = load_json(CLOSURES_PATH, {})
    history = load_history()
    leads = load_json(LEADS_PATH, {})

    archived = update_archive(slot_data, leads, history, today_iso)
    print(f"Archive updated ({archived} past days in window).")

    records = load_recent_archive(today_iso, lookback)
    analytics = compute_analytics(records, lookback, today_iso, tz)
    print(f"Analytics over {len(records)} archived days "
          f"({', '.join(sorted(set(r['dow'] for r in records))) or 'none yet'}).")

    availability = build_availability(slot_data, config, tz, history, analytics, closures)
    analytics["monthOutlook"] = compute_month_outlook(records, availability, tz)
    leads = update_leads(leads, slot_data, today_iso, tz)
    history = update_history(history, availability, now)
    write_archive_index()

    # Advance reservations beyond the widget window -> compact future.json
    window_end = (now.date() + timedelta(days=days_ahead)).isoformat()
    closed_dates = {}
    for i in range(366):
        d = now.date() + timedelta(days=i)
        r = closure_reason(d, closures)
        if r:
            closed_dates[d.isoformat()] = r
    (DATA_DIR / "closures.json").write_text(json.dumps(
        {"generatedAt": now.isoformat(), "timezone": str(tz), "dates": closed_dates}, indent=1))
    print(f"closures.json: {len(closed_dates)} closed dates in the next year.")

    future_days = {}
    for (d_iso, t), rec in slot_data.items():
        if d_iso in closed_dates:
            continue  # closure wins; conflicts warned in build_availability
        if d_iso > window_end:
            f = future_days.setdefault(d_iso, {"capacity": 0, "sold": 0, "soldOutSlots": 0, "slotCount": 0})
            cap = max(0, rec["capacity"])
            remaining = max(0, min(rec["available"], cap))
            f["capacity"] += cap
            f["sold"] += cap - remaining
            f["slotCount"] += 1
            if cap and remaining <= 0:
                f["soldOutSlots"] += 1
    for d_iso, f in future_days.items():
        f["pct"] = round(100 * f["sold"] / f["capacity"]) if f["capacity"] else 0
    (DATA_DIR / "future.json").write_text(json.dumps(
        {"generatedAt": now.isoformat(), "days": dict(sorted(future_days.items()))}, indent=1))
    print(f"future.json: {len(future_days)} days of advance sales beyond the widget window.")

    OUTPUT_PATH.write_text(json.dumps(availability, indent=2))
    ANALYTICS_PATH.write_text(json.dumps(analytics, indent=2))
    LEADS_PATH.write_text(json.dumps(leads, indent=1))
    HISTORY_PATH.write_text(json.dumps(history))
    open_days = sum(1 for d in availability["days"] if not d["closed"])
    print(f"Wrote availability ({open_days} open days), analytics, leads, history.")


if __name__ == "__main__":
    main()
