# Module 02: Time Zones and DST

## The Concept

A calendar event says "09:00 in Berlin". That is a **wall-clock time plus a zone**. It is not
yet a moment in time. Only when you ask "what instant is that?" does it become a point on the
UTC line, and the answer depends on the date:

| Wall clock | Zone | Instant (UTC) |
|------------|------|---------------|
| 2026-03-20 09:00 | Europe/Berlin (CET, +01:00) | 08:00 |
| 2026-04-03 09:00 | Europe/Berlin (CEST, +02:00) | 07:00 |
| any day 09:00 | Europe/Istanbul (+03:00, no DST since 2016) | 06:00 |

Everything in this module follows from one rule: **keep wall-clock and instant apart, and convert
as late as possible.** The code is in [`minical/zones.py`](../minical/zones.py).

### The two awkward days

When clocks go **forward** (New York, 2026-03-08: 02:00 becomes 03:00) the wall times
02:00-02:59 **do not exist**. A calendar can still contain `DTSTART;TZID=America/New_York:20260308T023000`
(a weekly 02:30 meeting lands there). RFC 5545 section 3.3.5 says: interpret it with the offset
from *before* the change. 02:30 EST is 07:30Z, which is 03:30 EDT. The event happens, one hour
"late" on the wall clock.

When clocks go **back** (2026-11-01: 02:00 becomes 01:00) the wall times 01:00-01:59 happen
**twice**. The RFC says: the *first* one. A 01:30 event is 01:30 EDT (05:30Z), not 01:30 EST.

Python's `zoneinfo` implements exactly that with `fold=0`, the default. So:

```python
def place(wall, tz):
    return wall.replace(tzinfo=tz).astimezone(UTC).astimezone(tz)
```

The round trip through UTC is not decoration: it *normalises* a nonexistent time. Without it, a
gap time prints as `02:30-05:00`, a wall time that never showed on any clock.

### The trap: subtracting two aware datetimes

```python
a = place(datetime(2026, 10, 31, 23), NY)   # 23:00 EDT
b = place(datetime(2026, 11, 1, 3), NY)     # 03:00 EST, after the clocks fell back
b - a            # 4 hours   <- WRONG
```

When both datetimes carry the **same `tzinfo` object**, Python subtracts the wall clocks and
ignores the offset change between them. Five real hours passed. `elapsed()` converts both to UTC
first. The same holds for `<`, `>`, `==` between datetimes that share a zone. In this code base
every comparison and every length goes through UTC.

This is the single most common DST bug in calendar code, and it is invisible in tests that do
not cross a transition.

### Value types

A `DTSTART` value is one of four things, and each has different semantics:

| Looks like | Kind | Meaning |
|------------|------|---------|
| `20260302` (`VALUE=DATE`) | date | all-day; no time, no zone |
| `20260302T090000Z` | utc | an exact instant |
| `20260302T090000` + `TZID=...` | zoned | wall clock in that zone |
| `20260302T090000` | floating | wall clock in *whoever's* zone is asking |

A floating time is "09:00 wherever you are". The server reads it in the `tz` the caller passes
and says so. Never in the machine's local zone: the server may run somewhere else than you, and
an answer that depends on the host's clock settings is a bug that only appears in production.

### Rejecting abbreviations

`CEST`, `EST`, `IST`: `IST` is India, Israel *and* Irish Standard Time. `get_zone` accepts IANA
names only and the error tells the agent what to pass.

## Run It

```bash
python 02-time-zones-and-dst/main.py
```

It asserts the table above, the gap (`03:30 EDT`), the overlap (first = `-04:00`, `fold=1` =
`-05:00`), and that `b - a` is four hours while `elapsed(a, b)` is five.

## Takeaways

- Event = wall clock + zone. Instant is derived.
- Gap: offset from before. Overlap: first occurrence. `fold=0` does both.
- Never subtract or compare aware datetimes without converting to UTC.
- Floating means "the caller's zone", and the tool must say which zone it used.
