"""Module 03 (second half): a tzinfo built from a calendar's own VTIMEZONE.

Outlook exports TZID:W. Europe Standard Time, which is not an IANA name. The file
ships the rules itself:

    BEGIN:VTIMEZONE
    TZID:W. Europe Standard Time
    BEGIN:DAYLIGHT  DTSTART:16010101T020000  TZOFFSETFROM:+0100  TZOFFSETTO:+0200
                    RRULE:FREQ=YEARLY;BYDAY=-1SU;BYMONTH=3
    BEGIN:STANDARD  ...

Each block says: "at this local wall time, the offset changes from X to Y, and
repeats by this RRULE". We already have an RRULE engine, so a transition list is:
expand each block, and convert each local onset to UTC using the OLD offset.
"""

from __future__ import annotations

import bisect
from datetime import datetime, timedelta, tzinfo

from .parse import Component, ICalError, parse_datetime
from .rrule import iterate, parse_rule


def parse_offset(v: str) -> timedelta:
    sign = -1 if v.startswith("-") else 1
    digits = v[1:]
    return sign * timedelta(hours=int(digits[:2]), minutes=int(digits[2:4]))


def _need(comp: Component, name: str) -> str:
    p = comp.get(name)
    if p is None:
        raise ICalError(f"{comp.name} block has no {name}")
    return p.value


class VTimezone(tzinfo):
    def __init__(self, tzid: str, comp: Component, last_year: int = 2100) -> None:
        self._tzid = tzid
        transitions: list[tuple[datetime, timedelta]] = []  # (UTC instant, offset after)
        self._first = timedelta(0)
        earliest: datetime | None = None
        for sub in comp.children:
            if sub.name not in ("STANDARD", "DAYLIGHT"):
                continue
            start, _ = parse_datetime(_need(sub, "DTSTART"))
            off_from = parse_offset(_need(sub, "TZOFFSETFROM"))
            off_to = parse_offset(_need(sub, "TZOFFSETTO"))
            rr = sub.get("RRULE")
            if rr is None:
                onsets = [start]
            else:
                # Outlook starts its rules in the year 1601; nothing before 1900 matters.
                lo = max(start, datetime(1900, 1, 1))
                onsets = [
                    o for o in iterate(parse_rule(rr.value), start, lo=lo, hi=datetime(last_year, 12, 31))
                    if isinstance(o, datetime)
                ]
            for onset in onsets:
                transitions.append((onset - off_from, off_to))  # onset is in the OLD offset
            if earliest is None or start < earliest:
                earliest, self._first = start, off_from
        if not transitions:
            raise ICalError(f"VTIMEZONE {tzid!r} has no STANDARD/DAYLIGHT block")
        transitions.sort()
        self._instants = [t[0] for t in transitions]
        self._offsets = [t[1] for t in transitions]
        self._all = set(self._offsets) | {self._first}

    def _at_utc(self, utc_naive: datetime) -> timedelta:
        i = bisect.bisect_right(self._instants, utc_naive) - 1
        return self._offsets[i] if i >= 0 else self._first

    def utcoffset(self, dt: datetime | None) -> timedelta:
        if dt is None:
            return timedelta(0)
        wall = dt.replace(tzinfo=None)
        # An offset o is valid for this wall time if, using o, the instant we get
        # really has offset o.
        valid = [o for o in self._all if self._at_utc(wall - o) == o]
        if len(valid) == 1:
            return valid[0]
        if valid:  # clocks went back: the wall time happens twice
            return max(valid) if dt.fold == 0 else min(valid)  # fold=0 -> first pass (the larger offset)
        # clocks went forward: the wall time does not exist
        before_after = [self._at_utc(wall - o) for o in self._all]
        return max(before_after) if dt.fold == 1 else min(before_after)

    def dst(self, dt: datetime | None) -> timedelta:
        return timedelta(0)

    def tzname(self, dt: datetime | None) -> str | None:
        return self._tzid

    def fromutc(self, dt: datetime) -> datetime:
        naive = dt.replace(tzinfo=None)
        off = self._at_utc(naive)
        wall = (naive + off).replace(tzinfo=self)
        # the second pass through a repeated hour needs fold=1
        if self.utcoffset(wall) != off:
            wall = wall.replace(fold=1)
        return wall
