# Module 03: RRULE Expansion

## The Concept

`RRULE:FREQ=MONTHLY;BYDAY=-1FR` means "the last Friday of every month, forever". A calendar file
stores the *rule*, not the dates, and the agent needs the dates between two points in time.
Nearly every expansion bug comes from forgetting that this is a **calendar** problem, not a
`timedelta` problem: months have different lengths, "last Friday" depends on the month, and "every
other week" depends on which day your week starts.

This module has three parts: the rule engine ([`minical/rrule.py`](../minical/rrule.py)), a
`tzinfo` built from a calendar's own time zone definition
([`minical/vtimezone.py`](../minical/vtimezone.py)), and the glue that turns a VEVENT into
real intervals ([`minical/events.py`](../minical/events.py)).

## Part 1: the engine works on wall clocks only

The engine takes a naive `datetime` (or a `date` for all-day events) and yields naive values. It
never sees a time zone. That separation is what keeps "every Monday at 09:00" at 09:00 across a
clock change: the engine says "Monday, 09:00 wall clock", and only *afterwards* does `place()`
(Module 02) decide which instant that is.

### Periods

The RFC's expansion is described as "take each period, generate candidates inside it, filter":

| FREQ | one period is | candidate days |
|------|---------------|----------------|
| DAILY | a day | that day |
| WEEKLY | a week starting on `WKST` | the 7 days |
| MONTHLY | a calendar month | all days of the month |
| YEARLY | a year | all days of the year |

`INTERVAL=n` jumps `n` periods at a time. Inside each period apply the `BYxxx` parts as filters:
`BYMONTH`, `BYMONTHDAY` (negative counts from the month end), `BYDAY`. `BYDAY=2MO` and `-1FR` are
*ordinals*: they pick the nth matching weekday within the month (or within the year for a
`YEARLY` rule without `BYMONTH`). Then `BYSETPOS` selects positions from the period's sorted
result ("the 3rd of Tue/Wed/Thu"; "the second-to-last weekday").

### Defaults come from DTSTART

`FREQ=MONTHLY` with no `BYxxx` means "the same day of the month as DTSTART". `FREQ=WEEKLY` with
no `BYDAY` means "the same weekday". `FREQ=YEARLY` means the same month and day. If that date
does not exist (`Jan 31` monthly; `Feb 29` yearly) the period yields nothing and the series skips
it. That is the standard's behaviour, and the RFC's own example, `BYMONTHDAY=15,30` in February,
is a test.

### WKST really matters

`FREQ=WEEKLY;INTERVAL=2;BYDAY=TU,SU` starting Tuesday 1997-08-05 yields Aug 5, **10**, 19, 24 with
`WKST=MO` (Sunday is the *end* of the week that began Aug 4) but Aug 5, **17**, 19, 31 with
`WKST=SU` (Sunday starts a new week). Both are in the test file.

### COUNT, UNTIL and skipping ahead

`COUNT` is a number of *generated* instances, so you can't skip ahead: you must walk from DTSTART.
Without `COUNT`, a query for next March does not need to walk 2015-2026: jump to the period
containing the window start (`_first_period`) and begin there. That turns a ten-year-old daily
event from 4,000 iterations into a few.

`UNTIL` is inclusive. When it is a UTC instant (`...Z`) and the event is zoned, it must be
converted into the event's zone *before* comparing with wall-clock occurrences. See `_walls` in
`events.py`.

### What we refuse

`FREQ=HOURLY`, `BYWEEKNO`, `BYYEARDAY`, `BYHOUR`... A minimal engine that ignores them produces
confident, wrong dates. `parse_rule` raises `ICalError("... not supported")`; `load_events`
turns that into "event skipped: reason", and the agent can tell the user.

### DTSTART is always the first instance

RFC 5545: DTSTART defines the first instance, even if the rule would not generate it. We emit it
first and count it in `COUNT`. (`python-dateutil` only returns it if it matches, which is why the
oracle comparison below drops it first.)

## Part 2: a second opinion

The engine is tested two ways, and both are in `main.py`:

1. The worked examples from RFC 5545 section 3.8.5.3 ("every other week...", "the second-to-last
   weekday of the month", the WKST pair, the February-30 rule), with dates copied from the RFC.
2. 300 random rules compared against `python-dateutil`, which is an independent implementation by
   a different author. If the two agree on hundreds of random rules, a shared bug is unlikely.

This is the pattern for anything with a published specification: let the spec supply expected
values, and let a second implementation supply volume.

## Part 3: VTIMEZONE

Outlook writes `TZID=W. Europe Standard Time`, which is not an IANA name. The file defines it:

```
BEGIN:VTIMEZONE
TZID:W. Europe Standard Time
BEGIN:DAYLIGHT
DTSTART:16010101T020000
TZOFFSETFROM:+0100
TZOFFSETTO:+0200
RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=3
END:DAYLIGHT
...
```

"On the last Sunday of March, at 02:00 local, the offset changes from +01:00 to +02:00." That is
an RRULE, and we just wrote an RRULE engine. `VTimezone` expands each block into transitions
(`onset - TZOFFSETFROM` is the UTC instant, because the onset is written in the *old* offset),
sorts them, and answers `utcoffset` by bisecting.

Two subtleties:

- Going from wall clock to offset is the hard direction. A candidate offset `o` is right for wall
  time `w` if the instant `w - o` really has offset `o`. Zero candidates means the gap (use the
  smaller offset, or the larger for `fold=1`); two candidates means the overlap (`fold=0` takes the
  first pass).
- `fromutc` must set `fold=1` on the second pass through a repeated hour, otherwise
  `astimezone(custom)` loses an hour on exactly one day a year.

`main.py` checks the custom zone against `ZoneInfo("Europe/Berlin")` every 5.5 hours for ten
years, plus the gap and the overlap explicitly. When a TZID is *both* IANA and defined in the
file, prefer IANA: it carries the full history of rule changes that a file's rule list may
simplify.

## Part 4: from VEVENT to intervals

`occurrences(event, window_start, window_end, floating_zone)`:

1. get wall-clock starts from the engine, limited to the window padded by the event's length (an
   occurrence that began yesterday may still overlap today);
2. drop `EXDATE`s (compare instants for timed events, dates for all-day), and instances
   replaced by a modified instance (`expand_all`: same UID + `RECURRENCE-ID`);
3. `place()` each wall start in the event's zone and add the length;
4. keep those overlapping `[ws, we)`.

**Lengths.** `DTEND - DTSTART` is *exact elapsed time*. A 23:00 -> 03:00 event over the fall-back
night is 5 hours, not 4. A `DURATION` in days (`P1D`) is *nominal*: noon to noon, 23 hours across
the spring-forward. `PT24H` is 24 hours. `_length` keeps (days, exact) separately.

**All-day events** are dates. They occupy whole local days in whatever zone the caller asks about,
so "all day on March 20" does not move when you change `tz`.

## Run It

```bash
python 03-rrule-expansion/main.py
```

## Takeaways

- Engine on wall clocks; zones applied afterwards.
- Period, candidates, filter, `BYSETPOS`, defaults from DTSTART.
- Refuse what you cannot do; test with the spec's examples plus a second implementation.
- A `VTIMEZONE` is just another use of the RRULE engine.
- Exact length for `DTEND`, nominal days for `DURATION`.
