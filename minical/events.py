"""Module 03: from a VEVENT to the intervals it occupies.

    wall-clock recurrence  (rrule.iterate)   -> list of naive datetimes in the event's zone
    place each one in its zone               -> aware datetimes
    add the event's length                   -> [start, end) in UTC

Lengths: DTEND - DTSTART is EXACT elapsed time; a DURATION of days is NOMINAL days
(wall-clock), hours/minutes are exact. All-day events are dates: whole local days
in whatever zone the caller asks about.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo

from .parse import Component, ICalError, Parsed, Prop, unescape_text
from .rrule import Rule, iterate, parse_rule
from .vtimezone import VTimezone
from .zones import UTC, TimeVal, ZoneError, get_zone, parse_timeval, place

_DUR = re.compile(r"^([+-])?P(?:(\d+)W)?(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")


def parse_duration(v: str) -> tuple[int, timedelta]:
    """'P1DT2H30M' -> (1 nominal day, 2h30m exact)."""
    m = _DUR.match(v.strip().upper())
    if not m or v.strip().upper() in ("P", "PT"):
        raise ICalError(f"bad DURATION {v!r} (want PT1H30M, P1D, P2W)")
    w, d, h, mi, s = (int(x) if x else 0 for x in m.groups()[1:])
    if m[1] == "-":
        raise ICalError("negative DURATION on an event")
    return w * 7 + d, timedelta(hours=h, minutes=mi, seconds=s)


@dataclass
class Event:
    uid: str
    calendar: str
    summary: str
    location: str
    status: str
    transp: str
    start: TimeVal
    end: TimeVal | None
    duration: tuple[int, timedelta] | None
    rule: Rule | None
    exdates: list[TimeVal]
    recurrence_id: TimeVal | None  # set on a "modified instance" of a recurring series
    comp: Component

    @property
    def all_day(self) -> bool:
        return self.start.kind == "date"


def make_resolver(vtimezones: list[Component]) -> Callable[[str], tzinfo]:
    """TZID -> tzinfo: IANA first (full history), else the file's own VTIMEZONE."""
    defs = {p.value.strip(): c for c in vtimezones if (p := c.get("TZID")) is not None}
    cache: dict[str, tzinfo] = {}

    def resolve(tzid: str) -> tzinfo:
        if tzid not in cache:
            try:
                cache[tzid] = get_zone(tzid)
            except ZoneError:
                if tzid not in defs:
                    raise ZoneError(
                        f"time zone {tzid!r} is not an IANA name and the file has no VTIMEZONE for it"
                    ) from None
                cache[tzid] = VTimezone(tzid, defs[tzid])
        return cache[tzid]

    return resolve


def load_events(parsed: Parsed, calendar: str) -> tuple[list[Event], list[str]]:
    """Every VEVENT as an Event. A bad event is skipped WITH a message, never silently."""
    problems: list[str] = list(parsed.warnings)
    events: list[Event] = []
    for root in parsed.roots:
        resolve = make_resolver(root.sub("VTIMEZONE"))
        for comp in root.sub("VEVENT"):
            try:
                events.append(_build(comp, calendar, resolve))
            except ICalError as e:
                s = comp.get("SUMMARY")
                title = unescape_text(s.value) if s else "(no title)"
                problems.append(f"{calendar}: line {comp.first + 1}: event {title!r} skipped: {e}")
    return events, problems


def _text(comp: Component, name: str, default: str = "") -> str:
    p = comp.get(name)
    return unescape_text(p.value) if p else default


def _build(comp: Component, calendar: str, resolve: Callable[[str], tzinfo]) -> Event:
    ds = comp.get("DTSTART")
    if ds is None:
        raise ICalError("no DTSTART")
    start = parse_timeval(ds, resolve)
    de, du = comp.get("DTEND"), comp.get("DURATION")
    end = parse_timeval(de, resolve) if de else None
    if end is not None:
        if (end.kind == "date") != (start.kind == "date"):
            raise ICalError("DTSTART and DTEND must both be dates or both be date-times")
        if end.kind != "date" and end.instant(UTC) < start.instant(UTC):  # instants, not wall clocks
            raise ICalError("DTEND is before DTSTART")
        if end.kind == "date" and end.wall < start.wall:
            raise ICalError("DTEND is before DTSTART")
    rr = comp.get("RRULE")
    uid = comp.get("UID")
    rid = comp.get("RECURRENCE-ID")
    exdates: list[TimeVal] = []
    for p in comp.get_all("EXDATE"):
        for piece in p.value.split(","):
            exdates.append(parse_timeval(Prop(p.name, p.params, piece.strip(), p.first, p.last), resolve))
    return Event(
        uid=uid.value.strip() if uid else f"no-uid:{calendar}:{comp.first + 1}",
        calendar=calendar,
        summary=_text(comp, "SUMMARY"),
        location=_text(comp, "LOCATION"),
        status=_text(comp, "STATUS").upper(),
        transp=_text(comp, "TRANSP", "OPAQUE").upper(),
        start=start,
        end=end,
        duration=parse_duration(du.value) if du else None,
        rule=parse_rule(rr.value) if rr else None,
        exdates=exdates,
        recurrence_id=parse_timeval(rid, resolve) if rid else None,
        comp=comp,
    )


@dataclass(frozen=True)
class Occurrence:
    event: Event
    start: datetime  # aware UTC
    end: datetime  # aware UTC, exclusive
    recurring: bool


def _length(ev: Event, floating: tzinfo) -> tuple[int, timedelta]:
    """(nominal days, exact time): end = place(wall + days) + exact."""
    if ev.all_day:
        if ev.end is not None:
            return max((ev.end.wall - ev.start.wall).days, 1), timedelta(0)
        return (ev.duration[0] if ev.duration else 1), timedelta(0)
    if ev.end is not None:
        return 0, ev.end.instant(floating) - ev.start.instant(floating)
    return ev.duration or (0, timedelta(0))


def _walls(ev: Event, ws: datetime, we: datetime, floating: tzinfo) -> Iterator[date | datetime]:
    if ev.rule is None:
        yield ev.start.wall
        return
    days, exact = _length(ev, floating)
    pad = timedelta(days=days + 2) + exact  # an occurrence that began earlier may still overlap
    zone = ev.start.tz or floating
    lo = ws.astimezone(zone).replace(tzinfo=None) - pad
    hi = we.astimezone(zone).replace(tzinfo=None) + timedelta(days=1)
    until = ev.rule.until
    if until is not None and ev.rule.until_utc and isinstance(until, datetime):
        until = place(until, UTC).astimezone(zone).replace(tzinfo=None)  # UNTIL...Z is an instant
    if ev.all_day:
        yield from iterate(ev.rule, ev.start.wall, lo.date(), hi.date(), until)
    else:
        yield from iterate(ev.rule, ev.start.wall, lo, hi, until)


def _key(v: TimeVal, floating: tzinfo) -> date | datetime:
    return v.wall if v.kind == "date" else v.instant(floating)  # type: ignore[return-value]


def occurrences(ev: Event, ws: datetime, we: datetime, floating: tzinfo,
                hide: set[date | datetime] | None = None) -> list[Occurrence]:
    """Occurrences overlapping the half-open window [ws, we) (aware datetimes).
    `hide` holds instants/dates replaced by a modified instance (RECURRENCE-ID)."""
    ws, we = ws.astimezone(UTC), we.astimezone(UTC)
    days, exact = _length(ev, floating)
    gone = {_key(x, floating) for x in ev.exdates} | (hide or set())
    out: list[Occurrence] = []
    for wall in _walls(ev, ws, we, floating):
        if isinstance(wall, datetime):
            zone = ev.start.tz or floating
            s = place(wall, zone).astimezone(UTC)
            if s in gone or wall.date() in gone:
                continue
            e = (place(wall + timedelta(days=days), zone).astimezone(UTC) + exact) if days else s + exact
        else:
            if wall in gone:
                continue
            s = place(datetime.combine(wall, time.min), floating).astimezone(UTC)
            e = place(datetime.combine(wall + timedelta(days=days), time.min), floating).astimezone(UTC)
        if (e > s and s < we and e > ws) or (e == s and ws <= s < we):
            out.append(Occurrence(ev, s, e, ev.rule is not None))
    return out


def expand_all(events: list[Event], ws: datetime, we: datetime, floating: tzinfo) -> list[Occurrence]:
    """Occurrences of every event, with modified instances (same UID + RECURRENCE-ID)
    replacing the instance of their series that they were made from."""
    replaced: dict[tuple[str, str], set[date | datetime]] = {}
    for ev in events:
        if ev.recurrence_id is not None:
            replaced.setdefault((ev.calendar, ev.uid), set()).add(_key(ev.recurrence_id, floating))
    out: list[Occurrence] = []
    for ev in events:
        hide = replaced.get((ev.calendar, ev.uid)) if ev.recurrence_id is None else None
        out.extend(occurrences(ev, ws, we, floating, hide))
    return sorted(out, key=lambda o: (o.start, o.end))
