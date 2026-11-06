"""Module 04: free/busy interval arithmetic.

Everything is a half-open interval [start, end) of aware UTC datetimes, so that
"back to back" (one ends exactly when the next starts) is not an overlap, and a
daylight-saving day is just a shorter or longer pair of endpoints.

    free = working_time - busy          (merge, then subtract)
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, time, timedelta, tzinfo

from .events import Occurrence
from .parse import ICalError
from .zones import UTC, place

Interval = tuple[datetime, datetime]


def merge(intervals: Iterable[Interval]) -> list[Interval]:
    """Union of intervals. Touching intervals are joined: [9,10) + [10,11) = [9,11)."""
    out: list[Interval] = []
    for s, e in sorted(intervals):
        if out and s <= out[-1][1]:
            if e > out[-1][1]:
                out[-1] = (out[-1][0], e)
        else:
            out.append((s, e))
    return out


def subtract(free: list[Interval], busy: list[Interval]) -> list[Interval]:
    """free minus busy. Both inputs must already be merged (sorted, disjoint)."""
    out: list[Interval] = []
    j = 0
    for s, e in free:
        cur = s
        while j < len(busy) and busy[j][1] <= cur:  # busy entirely before us
            j += 1
        k = j
        while k < len(busy) and busy[k][0] < e:
            bs, be = busy[k]
            if bs > cur:
                out.append((cur, bs))  # the gap before this busy block
            cur = max(cur, be)
            if cur >= e:
                break
            k += 1
        if cur < e:
            out.append((cur, e))
    return out


def parse_hours(text: str) -> list[tuple[time, time | None]]:
    """'09:00-12:00,13:00-17:00'; '24:00' (-> None) means the end of the day."""
    out: list[tuple[time, time | None]] = []
    for chunk in text.split(","):
        m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*", chunk)
        if not m:
            raise ICalError(f"working hours {text!r} should look like '09:00-17:00'")
        h1, m1, h2, m2 = (int(x) for x in m.groups())
        end = None if (h2, m2) == (24, 0) else time(h2, m2)
        if end is not None and end <= time(h1, m1):
            raise ICalError(f"working hours {chunk.strip()!r} ends before it starts")
        out.append((time(h1, m1), end))
    return out


def working_intervals(
    ws: datetime, we: datetime, tz: tzinfo, hours: list[tuple[time, time | None]], weekdays: set[int]
) -> list[Interval]:
    """Working time inside [ws, we). Built from LOCAL wall clocks, so 09:00-17:00 is
    09:00-17:00 on a daylight-saving day too (8 real hours), while 00:00-24:00 is 23 or 25."""
    ws, we = ws.astimezone(UTC), we.astimezone(UTC)
    out: list[Interval] = []
    day = ws.astimezone(tz).date() - timedelta(days=1)
    last = we.astimezone(tz).date() + timedelta(days=1)
    while day <= last:
        if day.weekday() in weekdays:
            for t1, t2 in hours:
                s = place(datetime.combine(day, t1), tz).astimezone(UTC)
                e = place(datetime.combine(day + timedelta(days=1) if t2 is None else day,
                                           time.min if t2 is None else t2), tz).astimezone(UTC)
                s, e = max(s, ws), min(e, we)
                if e > s:
                    out.append((s, e))
        day += timedelta(days=1)
    return merge(out)


def busy_from(occs: Iterable[Occurrence], buffer: timedelta = timedelta(0),
              include_all_day: bool = False, include_transparent: bool = False) -> list[Interval]:
    out: list[Interval] = []
    for o in occs:
        ev = o.event
        if ev.status == "CANCELLED":
            continue
        if ev.all_day and not include_all_day:
            continue
        if ev.transp == "TRANSPARENT" and not include_transparent:
            continue
        if o.end > o.start:
            out.append((o.start - buffer, o.end + buffer))
    return merge(out)


def free_slots(
    ws: datetime, we: datetime, tz: tzinfo, occs: Iterable[Occurrence], minutes: int,
    hours: str = "09:00-17:00", weekdays: set[int] | None = None, buffer_minutes: int = 0,
) -> list[Interval]:
    """Maximal free blocks of at least `minutes`."""
    work = working_intervals(ws, we, tz, parse_hours(hours), weekdays or {0, 1, 2, 3, 4})
    busy = busy_from(occs, timedelta(minutes=buffer_minutes))
    need = timedelta(minutes=minutes)
    return [(s, e) for s, e in subtract(work, busy) if e - s >= need]


@dataclass(frozen=True)
class Conflict:
    a: Occurrence
    b: Occurrence
    start: datetime
    end: datetime


def find_conflicts(occs: Iterable[Occurrence], include_all_day: bool = False,
                   include_transparent: bool = False) -> list[Conflict]:
    """Every pair of occurrences that overlap, via a sweep over start times."""
    items = sorted(
        (o for o in occs
         if o.event.status != "CANCELLED"
         and (include_all_day or not o.event.all_day)
         and (include_transparent or o.event.transp != "TRANSPARENT")
         and o.end > o.start),
        key=lambda o: (o.start, o.end),
    )
    out: list[Conflict] = []
    active: list[Occurrence] = []
    for o in items:
        active = [a for a in active if a.end > o.start]  # drop the ones that already ended
        out.extend(Conflict(a, o, o.start, min(a.end, o.end)) for a in active)
        active.append(o)
    return out
