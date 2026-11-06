"""Module 04 check: free/busy interval arithmetic with exact answers.

Run:  python 04-free-busy-math/main.py
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from minical.events import load_events, occurrences  # noqa: E402
from minical.freebusy import (  # noqa: E402
    find_conflicts,
    free_slots,
    merge,
    parse_hours,
    subtract,
    working_intervals,
)
from minical.parse import parse  # noqa: E402

UTC = timezone.utc


def iv(a, b):
    return (datetime(2026, 1, 1, a, tzinfo=UTC), datetime(2026, 1, 1, b, tzinfo=UTC))


# --- 1. the two primitives ------------------------------------------------------------------------
assert merge([iv(9, 11), iv(10, 12), iv(12, 13), iv(15, 16)]) == [iv(9, 13), iv(15, 16)], "touching joins"
assert subtract([iv(9, 17)], [iv(10, 11), iv(12, 13)]) == [iv(9, 10), iv(11, 12), iv(13, 17)]
assert subtract([iv(9, 17)], [iv(8, 10), iv(16, 18)]) == [iv(10, 16)]
assert subtract([iv(9, 10), iv(11, 12)], [iv(9, 12)]) == []
print("1. merge/subtract ok")


# --- 2. exact free time across two calendars -----------------------------------------------------------
def cal(*events):
    body = "".join(
        f"BEGIN:VEVENT\r\nUID:{uid}\r\nDTSTART:{s}\r\nDTEND:{e}\r\nSUMMARY:{uid}\r\n{extra}END:VEVENT\r\n"
        for uid, s, e, extra in events
    )
    return parse("BEGIN:VCALENDAR\r\n" + body + "END:VCALENDAR\r\n")


a = load_events(cal(("a1", "20260303T093000Z", "20260303T100000Z", ""),
                    ("a2", "20260303T110000Z", "20260303T123000Z", ""),
                    ("a3", "20260303T123000Z", "20260303T130000Z", "")), "a.ics")[0]  # a3 touches a2
b = load_events(cal(("b1", "20260303T150000Z", "20260303T160000Z", "")), "b.ics")[0]
ws, we = datetime(2026, 3, 3, tzinfo=UTC), datetime(2026, 3, 4, tzinfo=UTC)
occs = [o for ev in a + b for o in occurrences(ev, ws, we, UTC)]


def hhmm(slots):
    return [f"{s:%H:%M}-{e:%H:%M}" for s, e in slots]


assert hhmm(free_slots(ws, we, UTC, occs, 30, weekdays={1})) == ["09:00-09:30", "10:00-11:00", "13:00-15:00", "16:00-17:00"]
assert hhmm(free_slots(ws, we, UTC, occs, 60, weekdays={1})) == ["10:00-11:00", "13:00-15:00", "16:00-17:00"]
assert hhmm(free_slots(ws, we, UTC, occs, 61, weekdays={1})) == ["13:00-15:00"]
assert hhmm(free_slots(ws, we, UTC, occs, 30, weekdays={1}, buffer_minutes=15)) == [
    "10:15-10:45", "13:15-14:45", "16:15-17:00"], "a buffer pads BOTH sides of every busy block"
assert hhmm(free_slots(ws, we, UTC, occs, 60, hours="09:00-12:00,13:00-17:00", weekdays={1})) == [
    "10:00-11:00", "13:00-15:00", "16:00-17:00"]
print("2. exact free slots ok")

# --- 3. daylight-saving days keep their wall hours and have the right length -----------------------------
NY = ZoneInfo("America/New_York")


def total(day, zone, hours):
    ws = datetime.fromisoformat(day).replace(tzinfo=zone)
    work = working_intervals(ws, ws + timedelta(days=1), zone, parse_hours(hours), set(range(7)))
    return sum((e - s for s, e in work), timedelta(0))


assert total("2026-03-08", NY, "09:00-17:00") == timedelta(hours=8)
assert total("2026-03-08", NY, "00:00-24:00") == timedelta(hours=23), "spring forward: a 23 hour day"
assert total("2026-11-01", NY, "00:00-24:00") == timedelta(hours=25), "fall back: a 25 hour day"
assert total("2026-03-29", ZoneInfo("Europe/Berlin"), "00:00-24:00") == timedelta(hours=23)
assert total("2026-03-29", ZoneInfo("Europe/Istanbul"), "00:00-24:00") == timedelta(hours=24)
print("3. DST days ok")

# --- 4. conflicts: sweep line -----------------------------------------------------------------------------------
c = load_events(cal(("x1", "20260303T090000Z", "20260303T100000Z", ""),
                    ("x2", "20260303T100000Z", "20260303T110000Z", ""),  # touches x1: no conflict
                    ("x3", "20260303T093000Z", "20260303T103000Z", ""),  # overlaps both
                    ("x4", "20260303T093000Z", "20260303T103000Z", "STATUS:CANCELLED\r\n"),
                    ("x5", "20260303T093000Z", "20260303T103000Z", "TRANSP:TRANSPARENT\r\n")), "c.ics")[0]
found = find_conflicts(o for ev in c for o in occurrences(ev, ws, we, UTC))
pairs = {frozenset((f.a.event.uid, f.b.event.uid)) for f in found}
assert pairs == {frozenset(("x1", "x3")), frozenset(("x2", "x3"))}, "x1/x2 touch; x4 is cancelled; x5 is free"
assert sorted((f"{f.start:%H:%M}", f"{f.end:%H:%M}") for f in found) == [("09:30", "10:00"), ("10:00", "10:30")]
print("4. conflicts ok")

print("MODULE 04 OK")
