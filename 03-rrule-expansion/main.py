"""Module 03 check: RRULE expansion, a VTIMEZONE tzinfo, and events across DST.

Run:  python 03-rrule-expansion/main.py
"""

import os
import random
import sys
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from dateutil.rrule import rrulestr  # noqa: E402  (the independent oracle)

from minical.events import expand_all, load_events, occurrences  # noqa: E402
from minical.parse import ICalError, parse  # noqa: E402
from minical.rrule import iterate, parse_rule  # noqa: E402
from minical.vtimezone import VTimezone  # noqa: E402
from minical.zones import place  # noqa: E402

UTC = timezone.utc
DATA = os.path.join(ROOT, "data")


def gen(start, rule, **kw):
    return list(iterate(parse_rule(rule), start, **kw))


def d(y, m, dd):
    return datetime(y, m, dd, 9)


# --- 1. RFC 5545 section 3.8.5.3 examples (DTSTART 9:00) --------------------------------------------
assert gen(d(1997, 9, 2), "FREQ=DAILY;INTERVAL=10;COUNT=5") == [
    d(1997, 9, 2), d(1997, 9, 12), d(1997, 9, 22), d(1997, 10, 2), d(1997, 10, 12)]
assert gen(d(1997, 9, 2), "FREQ=WEEKLY;COUNT=10;WKST=SU;BYDAY=TU,TH")[:4] == [
    d(1997, 9, 2), d(1997, 9, 4), d(1997, 9, 9), d(1997, 9, 11)]
assert gen(d(1997, 9, 22), "FREQ=MONTHLY;COUNT=6;BYDAY=-2MO") == [
    d(1997, 9, 22), d(1997, 10, 20), d(1997, 11, 17), d(1997, 12, 22), d(1998, 1, 19), d(1998, 2, 16)]
assert gen(d(1997, 9, 4), "FREQ=MONTHLY;COUNT=3;BYDAY=TU,WE,TH;BYSETPOS=3") == [
    d(1997, 9, 4), d(1997, 10, 7), d(1997, 11, 6)]
assert gen(d(1997, 8, 5), "FREQ=WEEKLY;INTERVAL=2;COUNT=4;BYDAY=TU,SU;WKST=MO") == [
    d(1997, 8, 5), d(1997, 8, 10), d(1997, 8, 19), d(1997, 8, 24)]
assert gen(d(1997, 8, 5), "FREQ=WEEKLY;INTERVAL=2;COUNT=4;BYDAY=TU,SU;WKST=SU") == [
    d(1997, 8, 5), d(1997, 8, 17), d(1997, 8, 19), d(1997, 8, 31)], "WKST changes the answer"
assert gen(datetime(2007, 1, 15, 9), "FREQ=MONTHLY;BYMONTHDAY=15,30;COUNT=5")[3:] == [
    datetime(2007, 3, 15, 9), datetime(2007, 3, 30, 9)], "Feb 30 simply does not exist"
assert gen(date(2024, 2, 29), "FREQ=YEARLY;COUNT=3") == [date(2024, 2, 29), date(2028, 2, 29), date(2032, 2, 29)]
print("1. RFC examples ok")

# --- 2. rules we refuse rather than mis-expand -------------------------------------------------------
for bad in ("FREQ=HOURLY", "FREQ=YEARLY;BYWEEKNO=20", "FREQ=WEEKLY;BYDAY=2MO", "COUNT=3"):
    try:
        parse_rule(bad)
    except ICalError:
        pass
    else:
        raise AssertionError(bad)
print("2. unsupported rules rejected")

# --- 3. a second opinion: compare with python-dateutil on random rules -----------------------------------
rng = random.Random(3)
wd = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]
checked = 0
for _ in range(300):
    freq = rng.choice(["DAILY", "WEEKLY", "MONTHLY", "YEARLY"])
    parts = [f"FREQ={freq}", f"INTERVAL={rng.randint(1, 3)}"]
    if freq == "WEEKLY":
        parts.append("BYDAY=" + ",".join(rng.sample(wd, rng.randint(1, 3))))
    elif freq == "MONTHLY":
        parts.append(f"BYDAY={rng.choice([-1, 1, 2, 3])}{rng.choice(wd)}")
    elif freq == "YEARLY":
        parts.append(f"BYMONTH={rng.randint(1, 12)}")
    text = ";".join(parts)
    start = datetime(rng.randint(2019, 2027), rng.randint(1, 12), rng.randint(1, 28), 9)
    hi = start + timedelta(days=1500)
    mine = gen(start, text, hi=hi)
    theirs = list(rrulestr(text, dtstart=start).between(start - timedelta(seconds=1), hi, inc=True))
    if mine and mine[0] == start and (not theirs or theirs[0] != start):
        mine = mine[1:]  # RFC: DTSTART is always the first instance; dateutil only if it matches
    assert mine == theirs, (text, start)
    checked += 1
print(f"3. {checked} random rules agree with dateutil")

# --- 4. skipping ahead: no COUNT means we can jump to the window ---------------------------------------------
rule = "FREQ=WEEKLY;INTERVAL=3;BYDAY=MO,FR"
start = datetime(2020, 1, 3, 9)
full = gen(start, rule, hi=datetime(2030, 1, 1))
lo, hi = datetime(2026, 6, 1), datetime(2026, 9, 1)
assert gen(start, rule, lo=lo, hi=hi) == [x for x in full if lo <= x <= hi]
print("4. window skipping ok")

# --- 5. VTIMEZONE: Outlook's 'W. Europe Standard Time' must behave like Europe/Berlin ----------------------------
root = parse(open(os.path.join(DATA, "outlook.ics"), encoding="utf-8", newline="").read()).roots[0]
w_europe = next(c for c in root.sub("VTIMEZONE") if c.get("TZID").value == "W. Europe Standard Time")
custom, berlin = VTimezone("W. Europe Standard Time", w_europe), ZoneInfo("Europe/Berlin")
t = datetime(2022, 1, 1, tzinfo=UTC)
while t < datetime(2032, 1, 1, tzinfo=UTC):
    assert t.astimezone(custom).utcoffset() == t.astimezone(berlin).utcoffset(), t
    t += timedelta(minutes=330)
for wall in (datetime(2026, 3, 29, 2, 30), datetime(2026, 10, 25, 2, 30)):  # the gap and the overlap
    assert place(wall, custom).astimezone(UTC) == place(wall, berlin).astimezone(UTC), wall
print("5. VTIMEZONE matches Europe/Berlin through the gap and the overlap")

# --- 6. whole events, real files -----------------------------------------------------------------------------
events, problems = load_events(parse(open(os.path.join(DATA, "google.ics"), encoding="utf-8", newline="").read()), "google.ics")
assert not problems
standup = next(e for e in events if e.uid == "standup-001@google.com")
IST = ZoneInfo("Europe/Istanbul")
got = occurrences(standup, datetime(2026, 3, 1, tzinfo=UTC), datetime(2026, 3, 14, tzinfo=UTC), IST)
days = [o.start.astimezone(IST).strftime("%d %H:%M") for o in got]
assert days == ["02 10:00", "04 10:00", "09 10:00", "11 10:00", "13 10:00"], days  # Mar 6 is an EXDATE
# ...and with the modified instance (RECURRENCE-ID) applied, Mar 9 moved to 14:30:
both = [e for e in events if e.uid == "standup-001@google.com"]
got = expand_all(both, datetime(2026, 3, 1, tzinfo=UTC), datetime(2026, 3, 14, tzinfo=UTC), IST)
days = [o.start.astimezone(IST).strftime("%d %H:%M") for o in got]
assert days == ["02 10:00", "04 10:00", "09 14:30", "11 10:00", "13 10:00"], days

berlin_meeting = parse(
    "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:b\r\nDTSTART;TZID=Europe/Berlin:20260320T090000\r\n"
    "DURATION:PT1H\r\nRRULE:FREQ=WEEKLY;COUNT=4\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
ev = load_events(berlin_meeting, "b.ics")[0][0]
occ = occurrences(ev, datetime(2026, 3, 1, tzinfo=UTC), datetime(2026, 5, 1, tzinfo=UTC), UTC)
assert [o.start.hour for o in occ] == [8, 8, 7, 7], "09:00 Berlin: 08Z before Mar 29, 07Z after"

night = parse(
    "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:n\r\nDTSTART;TZID=America/New_York:20261031T230000\r\n"
    "DTEND;TZID=America/New_York:20261101T030000\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
nev = load_events(night, "n.ics")[0][0]
(o,) = occurrences(nev, datetime(2026, 10, 30, tzinfo=UTC), datetime(2026, 11, 3, tzinfo=UTC), UTC)
assert o.end - o.start == timedelta(hours=5), "DTEND is exact elapsed time across the fall-back"
print("6. events across DST ok")

print("MODULE 03 OK")
