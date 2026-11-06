"""Module 02 check: wall clocks, instants and the two DST traps.

Run:  python 02-time-zones-and-dst/main.py
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from minical.parse import Prop  # noqa: E402
from minical.zones import ZoneError, elapsed, get_zone, parse_timeval, place  # noqa: E402

UTC = timezone.utc
NY, BERLIN, IST = ZoneInfo("America/New_York"), ZoneInfo("Europe/Berlin"), ZoneInfo("Europe/Istanbul")

# --- 1. same wall clock, different offset ----------------------------------------------------
winter = place(datetime(2026, 3, 20, 9), BERLIN).astimezone(UTC)
summer = place(datetime(2026, 4, 3, 9), BERLIN).astimezone(UTC)
assert (winter.hour, summer.hour) == (8, 7), "09:00 Berlin is 08:00Z in winter and 07:00Z in summer"
ist = {place(datetime(2026, m, 15, 9), IST).astimezone(UTC).hour for m in range(1, 13)}
assert ist == {6}, "Istanbul has had no DST since 2016: 09:00 is always 06:00Z"
print("1. wall clock -> instant ok")

# --- 2. the gap: clocks jump 02:00 -> 03:00; 02:30 does not exist -----------------------------
gap = place(datetime(2026, 3, 8, 2, 30), NY)
assert gap.astimezone(UTC) == datetime(2026, 3, 8, 7, 30, tzinfo=UTC)
assert (gap.hour, gap.minute) == (3, 30), "RFC 5545: use the offset from BEFORE the change"
print("2. gap ok:", gap.isoformat())

# --- 3. the overlap: clocks fall back 02:00 -> 01:00; 01:30 happens twice --------------------------
first = place(datetime(2026, 11, 1, 1, 30), NY)
assert first.utcoffset() == timedelta(hours=-4), "RFC 5545: the FIRST occurrence (still daylight time)"
second = datetime(2026, 11, 1, 1, 30, fold=1, tzinfo=NY)
assert second.utcoffset() == timedelta(hours=-5) and second.astimezone(UTC) - first.astimezone(UTC) == timedelta(hours=1)
print("3. overlap ok")

# --- 4. Python's trap: same tzinfo => wall-clock subtraction ----------------------------------------
a = place(datetime(2026, 10, 31, 23), NY)  # 23:00 EDT
b = place(datetime(2026, 11, 1, 3), NY)  # 03:00 EST, after the clocks fell back
assert b - a == timedelta(hours=4), "the trap: Python subtracts the wall clocks"
assert elapsed(a, b) == timedelta(hours=5), "the truth: five real hours passed"
print("4. subtraction trap ok")

# --- 5. properties -> TimeVal -----------------------------------------------------------------------
assert parse_timeval(Prop("DTSTART", {"VALUE": ["DATE"]}, "20260302", 0, 0)).kind == "date"
assert parse_timeval(Prop("DTSTART", {}, "20260302T090000Z", 0, 0)).kind == "utc"
assert parse_timeval(Prop("DTSTART", {}, "20260302T090000", 0, 0)).kind == "floating"
z = parse_timeval(Prop("DTSTART", {"TZID": ["Europe/Berlin"]}, "20260302T090000", 0, 0))
assert z.kind == "zoned" and z.instant(UTC) == datetime(2026, 3, 2, 8, tzinfo=UTC)
fl = parse_timeval(Prop("DTSTART", {}, "20260302T090000", 0, 0))
assert fl.instant(IST) == datetime(2026, 3, 2, 6, tzinfo=UTC), "floating = read it in the caller's zone"
try:
    get_zone("CEST")
except ZoneError as e:
    assert "IANA" in str(e)
else:
    raise AssertionError("abbreviations are ambiguous and must be rejected")
print("5. time values ok")

print("MODULE 02 OK")
