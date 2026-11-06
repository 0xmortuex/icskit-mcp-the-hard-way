"""Module 02: wall clocks, instants and daylight saving time.

The one idea to take away: a calendar event is a WALL-CLOCK time in a ZONE, and
only turns into an instant (a point on the UTC time line) when you ask.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .parse import ICalError, Prop, is_date_value, parse_date, parse_datetime

UTC = timezone.utc


class ZoneError(ICalError):
    pass


def get_zone(name: str) -> tzinfo:
    """Resolve an IANA name. Module 03 adds calendars' own VTIMEZONE blocks."""
    if name.strip().upper() in ("UTC", "Z"):
        return UTC
    try:
        return ZoneInfo(name.strip())
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise ZoneError(
            f"unknown time zone {name!r}; use an IANA name like 'Europe/Istanbul' or 'UTC'"
        ) from None


def place(wall: datetime, tz: tzinfo) -> datetime:
    """Wall clock -> aware datetime in tz, using RFC 5545's policy:
      * a wall time that happens TWICE (clocks go back) means the FIRST one;
      * a wall time that DOES NOT EXIST (clocks go forward) is read with the
        offset from BEFORE the change, so it lands after the gap.
    zoneinfo's fold=0 is exactly that policy. The round trip through UTC
    normalises a nonexistent time (02:30 -> 03:30) so what we display is real."""
    return wall.replace(tzinfo=tz).astimezone(UTC).astimezone(tz)


def elapsed(a: datetime, b: datetime) -> timedelta:
    """Real elapsed time between two aware datetimes.

    Python's trap: if both datetimes carry the SAME tzinfo object, `b - a`
    subtracts the WALL CLOCKS and ignores the offset change between them.
    Converting both to UTC first always gives the truth."""
    return b.astimezone(UTC) - a.astimezone(UTC)


@dataclass(frozen=True)
class TimeVal:
    """A DTSTART/DTEND/EXDATE value: 'date' (all-day), 'floating', 'utc' or 'zoned'."""

    kind: str
    wall: date | datetime
    tz: tzinfo | None = None

    def instant(self, floating: tzinfo) -> datetime:
        """The moment in time, as aware UTC. `floating` is the zone to read a
        floating time in (the caller's zone)."""
        assert isinstance(self.wall, datetime)
        return place(self.wall, self.tz or floating).astimezone(UTC)


def parse_timeval(prop: Prop, resolve: Callable[[str], tzinfo] = get_zone) -> TimeVal:
    """`resolve` maps a TZID to a tzinfo. Module 03 passes one that also knows the
    calendar's own VTIMEZONE blocks."""
    v = prop.value.strip()
    if is_date_value(v):
        return TimeVal("date", parse_date(v))
    wall, z = parse_datetime(v)
    if z:
        return TimeVal("utc", wall, UTC)
    tzid = prop.param("TZID")
    return TimeVal("zoned", wall, resolve(tzid)) if tzid else TimeVal("floating", wall)
