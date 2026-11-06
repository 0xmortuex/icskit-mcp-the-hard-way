"""Module 06: the MCP wrapper. Six tools over everything built so far.

Run:  python -m minical.server --dir data
"""

from __future__ import annotations

import argparse
import functools
import sys
from collections.abc import Callable
from datetime import datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import writer
from .events import Event, Occurrence, expand_all, load_events
from .freebusy import find_conflicts as conflicts_of
from .freebusy import free_slots
from .parse import ICalError, parse
from .zones import get_zone, place

mcp = MCPServer(
    "minical",
    instructions=(
        "Local .ics calendars. Always pass tz (an IANA zone such as Europe/Istanbul); every time "
        "in every answer is shown in that zone. Start with calendar_overview. Write tools never "
        "touch the original unless in_place=true; dry_run=true shows the patch only."
    ),
)

_root: Path | None = None
F = TypeVar("F", bound=Callable[..., Any])


def tool(fn: F) -> F:
    """Register fn. mcp>=2 only shows the client a ToolError's message, so expected
    failures are re-raised as ToolError; anything else stays a hidden crash (a real bug)."""

    @functools.wraps(fn)
    def wrapper(*a: Any, **kw: Any) -> Any:
        try:
            return fn(*a, **kw)
        except (ICalError, OSError, ValueError) as e:
            raise ToolError(str(e)) from e

    mcp.tool()(wrapper)
    return fn


def configure(root: str | Path) -> None:
    global _root
    p = Path(root).resolve()
    if not p.is_dir():
        raise ICalError(f"--dir {root!r} is not a directory")
    _root = p


def _dir() -> Path:
    if _root is None:
        raise ICalError("server not configured: start it with --dir <folder of .ics files>")
    return _root


def _files() -> list[Path]:
    return sorted(p for p in _dir().rglob("*.ics") if p.resolve().is_relative_to(_dir()))


def _load_all() -> tuple[list[Event], list[str]]:
    events: list[Event] = []
    problems: list[str] = []
    for path in _files():
        rel = path.relative_to(_dir()).as_posix()
        try:
            evs, probs = load_events(parse(path.read_text(encoding="utf-8")), rel)
        except (ICalError, UnicodeDecodeError) as e:
            problems.append(f"{rel}: {e}")  # one broken file must not hide the others
            continue
        events.extend(evs)
        problems.extend(probs)
    return events, problems


def _window(start: str, end: str, tz_name: str) -> tuple[datetime, datetime, tzinfo]:
    tz = get_zone(tz_name)

    def one(text: str, end_of_day: bool) -> datetime:
        v = datetime.fromisoformat(text.strip().replace(" ", "T"))
        if len(text.strip()) == 10 and end_of_day:  # date-only end includes the whole day
            v += timedelta(days=1)
        return place(v, tz) if v.tzinfo is None else v.astimezone(tz)

    ws, we = one(start, False), one(end, True)
    if we <= ws:
        raise ICalError("end must be after start")
    return ws, we, tz


def _fmt(dt: datetime, tz: tzinfo) -> str:
    return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M %Z")


def _gather(ws: datetime, we: datetime, tz: tzinfo) -> tuple[list[Occurrence], list[str]]:
    events, problems = _load_all()
    return expand_all(events, ws, we, tz), problems


def _line(o: Occurrence, tz: tzinfo) -> str:
    when = "all day" if o.event.all_day else f"{_fmt(o.start, tz)} -> {o.end.astimezone(tz):%H:%M}"
    tag = " [recurring]" if o.recurring else ""
    return f"{when}  {o.event.summary or '(no title)'}{tag}  ({o.event.calendar}, uid {o.event.uid})"


@tool
def calendar_overview() -> str:
    """List the .ics files under the server directory with event counts, and any problems
    found (broken files, skipped events and why). Call this first."""
    events, problems = _load_all()
    lines = [f"Directory: {_dir()}"]
    for p in _files():
        rel = p.relative_to(_dir()).as_posix()
        lines.append(f"- {rel}: {sum(1 for e in events if e.calendar == rel)} events")
    if problems:
        lines.append(f"Problems ({len(problems)}):")
        lines.extend(f"  {x}" for x in problems)
    return "\n".join(lines)


@tool
def agenda(start: str, end: str, tz: str = "UTC") -> str:
    """Every event occurrence between start and end (recurrences expanded), sorted.
    start/end: '2026-03-02' or '2026-03-02T09:30'; a date-only end includes that whole day.
    tz: IANA zone used to read start/end and to show every time."""
    ws, we, z = _window(start, end, tz)
    occs, problems = _gather(ws, we, z)
    head = f"Agenda {_fmt(ws, z)} -> {_fmt(we, z)} (zone {tz})"
    body = [_line(o, z) for o in occs if o.event.status != "CANCELLED"] or ["No events."]
    warn = ["Warnings:", *problems] if problems else []
    return "\n".join([head, *body, *warn])


@tool
def find_free_time(start: str, end: str, duration_minutes: int, tz: str = "UTC",
                   working_hours: str = "09:00-17:00", buffer_minutes: int = 0) -> str:
    """Free blocks of at least duration_minutes inside working_hours (local wall clock in tz,
    Monday to Friday), across ALL calendars. buffer_minutes is kept clear around every busy event.
    All-day and TRANSPARENT ('free') events do not block."""
    if duration_minutes <= 0:
        raise ICalError("duration_minutes must be positive")
    ws, we, z = _window(start, end, tz)
    occs, _ = _gather(ws - timedelta(days=1), we + timedelta(days=1), z)
    slots = free_slots(ws, we, z, occs, duration_minutes, working_hours, None, buffer_minutes)
    head = f"Free blocks >= {duration_minutes} min, {working_hours} Mon-Fri (zone {tz})"
    if not slots:
        return head + "\nNone."
    return "\n".join([head] + [f"  {_fmt(s, z)} -> {e.astimezone(z):%H:%M}  ({int((e - s).total_seconds() // 60)} min)" for s, e in slots])


@tool
def find_conflicts(start: str, end: str, tz: str = "UTC") -> str:
    """Pairs of events that overlap (also across calendars). Back-to-back is not a conflict.
    Cancelled, all-day and TRANSPARENT events are ignored."""
    ws, we, z = _window(start, end, tz)
    occs, _ = _gather(ws, we, z)
    found = conflicts_of(occs)
    if not found:
        return f"No conflicts between {_fmt(ws, z)} and {_fmt(we, z)} (zone {tz})."
    out = [f"{len(found)} conflict(s) (zone {tz}):"]
    for c in found:
        out.append(f"- overlap {_fmt(c.start, z)} -> {c.end.astimezone(z):%H:%M}")
        out.append(f"    {_line(c.a, z)}")
        out.append(f"    {_line(c.b, z)}")
    return "\n".join(out)


def _target(calendar: str) -> Path:
    full = (_dir() / calendar).resolve()
    if not full.is_relative_to(_dir()):
        raise ICalError(f"{calendar!r} is outside the allowed directory")
    if not full.is_file():
        raise ICalError(f"{calendar!r} not found; call calendar_overview for the file names")
    return full


@tool
def add_event(calendar: str, summary: str, start: str, duration_minutes: int, tz: str = "UTC",
              in_place: bool = False, dry_run: bool = False) -> str:
    """Add a timed event to a calendar file. start is '2026-03-10T15:00' read in tz.
    SAFETY: the original is not modified unless in_place=true; by default an edited copy is
    written as '<file>.new'. dry_run=true writes nothing and shows the patch."""
    path = _target(calendar)
    old = path.read_text(encoding="utf-8")
    new, uid = writer.add_event(old, summary, start, duration_minutes, tz)
    res = writer.commit(path, old, new, in_place, dry_run)
    return f"{res.message}\nUID: {uid}\n\n{res.diff}"


@tool
def delete_event(calendar: str, event_uid: str, in_place: bool = False, dry_run: bool = False) -> str:
    """Delete one event (all of a recurring series) by UID. Same safety rules as add_event."""
    path = _target(calendar)
    old = path.read_text(encoding="utf-8")
    res = writer.commit(path, old, writer.delete_event(old, event_uid), in_place, dry_run)
    return f"{res.message}\n\n{res.diff}"


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="minical")
    ap.add_argument("--dir", required=True, help="folder with .ics files; nothing outside it is visible")
    args = ap.parse_args(argv)
    try:
        configure(args.dir)
    except ICalError as e:
        print(f"minical: {e}", file=sys.stderr)
        raise SystemExit(2) from None
    mcp.run()


if __name__ == "__main__":
    main()

