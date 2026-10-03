#!/usr/bin/env python3
"""Regenerate data/zip-state.json — the five-digit ZIP to state crosswalk.

WHY A GENERATED FILE: fetch_availability.py and fill_customer_state.py are
stdlib-only so the GitHub Action needs no install step and no network beyond
ACME. Rather than add a runtime dependency, this script is run by hand and the
result committed.

SOURCE: the `zipcodes` package on PyPI (MIT licensed, so redistributable),
which bundles a USPS-derived table of ~42,800 ZIPs. Checked at build time:
every ZIP in that table maps to exactly one state, so there is no ambiguity to
resolve and no guessing — a ZIP either resolves or it doesn't.

UPDATE CADENCE: ZIP-to-state assignments barely move. State lines do not
change and the USPS adds a handful of ZIPs a year, none of which relocate an
existing one. Once a year is ample; run it if visitors start reporting ZIPs
that fail to resolve (fill_customer_state.py logs those as `unresolved`).

    pip install zipcodes
    python scripts/build_zip_crosswalk.py

Output is range-compressed: ZIPs are allocated in contiguous blocks per state,
so ~42,800 entries collapse to a few thousand ranges, which keeps the committed
file small and the lookup a cheap bisect.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "zip-state.json"

# USPS state and territory codes we accept as an address `state`. AE/AA/AP are
# overseas military and are legitimate USPS values. FM, MH and PW are sovereign
# nations that happen to use US ZIPs — they are not US states, so they are
# excluded rather than written into anyone's address.
VALID = set("""
AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO
MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY
PR VI GU AS MP AE AA AP
""".split())
EXCLUDED = {"FM", "MH", "PW"}


def main():
    try:
        import zipcodes
    except ImportError:
        sys.exit("pip install zipcodes, then re-run")

    rows = zipcodes.list_all()
    by_zip, skipped = {}, {}
    for r in rows:
        z, st = r.get("zip_code"), (r.get("state") or "").strip().upper()
        if not (z and z.isdigit() and len(z) == 5):
            continue
        if st in EXCLUDED:
            skipped[st] = skipped.get(st, 0) + 1
            continue
        if st not in VALID:
            skipped[st] = skipped.get(st, 0) + 1
            continue
        if z in by_zip and by_zip[z] != st:
            # Would mean a ZIP straddles a state line. Refuse rather than pick.
            sys.exit(f"ZIP {z} maps to both {by_zip[z]} and {st} — resolve before shipping")
        by_zip[z] = st

    # Collapse to [start, end, state] ranges over the sorted integer ZIPs.
    ranges = []
    for z in sorted(by_zip, key=int):
        n, st = int(z), by_zip[z]
        if ranges and ranges[-1][2] == st and ranges[-1][1] == n - 1:
            ranges[-1][1] = n
        else:
            ranges.append([n, n, st])

    # Round-trip check: every source ZIP must resolve back to its own state.
    import bisect
    starts = [r[0] for r in ranges]
    def lookup(n):
        i = bisect.bisect_right(starts, n) - 1
        if i < 0:
            return None
        s, e, st = ranges[i]
        return st if s <= n <= e else None
    bad = [z for z, st in by_zip.items() if lookup(int(z)) != st]
    if bad:
        sys.exit(f"range compression is lossy for {len(bad)} ZIPs, e.g. {bad[:5]}")

    OUT.write_text(json.dumps({
        "source": "PyPI `zipcodes` (MIT), USPS-derived",
        "generatedFrom": f"{len(by_zip)} five-digit ZIPs",
        "note": "Range-compressed [start, end, state]. Regenerate with "
                "scripts/build_zip_crosswalk.py; see that file for cadence.",
        "ranges": ranges,
    }, separators=(",", ":")))
    print(f"{len(by_zip):,} ZIPs -> {len(ranges):,} ranges -> {OUT} "
          f"({OUT.stat().st_size / 1024:.0f} KB)")
    if skipped:
        print("excluded (not US states):", skipped)


if __name__ == "__main__":
    main()
