"""Module 05: editing a calendar file without damaging it.

The rule: never regenerate a file from a data model. Parse it only to learn WHICH
PHYSICAL LINES to touch, then splice lines. Everything else - other events,
VTIMEZONE blocks, X- properties, folding, line endings, a BOM - is carried over
byte for byte, because it is never re-serialised.
"""

from __future__ import annotations

import difflib
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .parse import Component, ICalError, escape_text, parse, split_physical
from .zones import get_zone, place


def detect_newline(text: str) -> str:
    for ln in split_physical(text):
        for nl in ("\r\n", "\n", "\r"):
            if ln.endswith(nl):
                return nl
    return "\r\n"


def fold_line(line: str, limit: int = 75) -> list[str]:
    """RFC 5545: at most 75 OCTETS per physical line; continuations start with a
    space. Octets, not characters, and never inside a multi-byte character."""
    out: list[str] = []
    cur, size = "", 0
    for ch in line:
        b = len(ch.encode("utf-8"))
        if size + b > limit:
            out.append(cur)
            cur, size = " ", 1
        cur += ch
        size += b
    out.append(cur)
    return out


def splice(lines: list[str], remove: list[tuple[int, int]], insert: dict[int, list[str]]) -> list[str]:
    """Skip the inclusive (first, last) ranges in `remove`; put insert[i] before original line i."""
    skip = {i for a, b in remove for i in range(a, b + 1)}
    out: list[str] = []
    for i, ln in enumerate(lines):
        out.extend(insert.get(i, []))
        if i not in skip:
            out.append(ln)
    return out


def _fold_all(logical: list[str], nl: str) -> list[str]:
    return [piece + nl for ln in logical for piece in fold_line(ln)]


def _check_text(value: str, what: str) -> str:
    for ch in value:
        if (ord(ch) < 32 and ch not in "\n\r\t") or ord(ch) == 127:
            raise ICalError(f"{what} contains a control character; refusing to write it")
    return value


def add_event(text: str, summary: str, start: str, minutes: int, tz_name: str) -> tuple[str, str]:
    """Insert a timed VEVENT before END:VCALENDAR. start is '2026-03-10T15:00' in tz_name."""
    root = next(r for r in parse(text).roots if r.name == "VCALENDAR")
    nl = detect_newline(text)
    tz = get_zone(tz_name)
    wall = datetime.fromisoformat(start)
    # a time inside the daylight-saving gap does not exist: say so instead of writing a lie
    if place(wall, tz).replace(tzinfo=None) != wall:
        raise ICalError(f"{start} does not exist in {tz_name} (clocks go forward over it)")
    uid = f"{uuid.uuid4()}@minical"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    zone_param = "" if tz_name.upper() == "UTC" else f";TZID={tz_name}"
    z = "Z" if tz_name.upper() == "UTC" else ""
    block = [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{stamp}",
        f"DTSTART{zone_param}:{wall:%Y%m%dT%H%M%S}{z}",
        f"DURATION:PT{minutes}M",
        f"SUMMARY:{escape_text(_check_text(summary, 'summary'))}",
        "END:VEVENT",
    ]
    phys = split_physical(text)
    return "".join(splice(phys, [], {root.last: _fold_all(block, nl)})), uid


def find_event(text: str, uid: str) -> Component:
    for root in parse(text).roots:
        for ev in root.sub("VEVENT"):
            p = ev.get("UID")
            if p is not None and p.value.strip() == uid:
                return ev
    raise ICalError(f"no event with UID {uid!r}")


def set_summary(text: str, uid: str, summary: str) -> str:
    """Replace the SUMMARY lines of one event; bump SEQUENCE. Nothing else changes."""
    ev = find_event(text, uid)
    nl = detect_newline(text)
    remove: list[tuple[int, int]] = []
    insert: dict[int, list[str]] = {}
    old = ev.get("SUMMARY")
    new_line = _fold_all([f"SUMMARY:{escape_text(_check_text(summary, 'summary'))}"], nl)
    if old is not None:
        remove.append((old.first, old.last))  # the whole folded property, all its physical lines
        insert[old.first] = new_line
    else:
        insert[ev.last] = new_line
    seq = ev.get("SEQUENCE")
    seq_line = _fold_all([f"SEQUENCE:{int(seq.value) + 1 if seq else 1}"], nl)
    if seq is not None:
        remove.append((seq.first, seq.last))
        insert[seq.first] = seq_line
    else:
        insert.setdefault(ev.last, []).extend(seq_line)
    return "".join(splice(split_physical(text), remove, insert))


def delete_event(text: str, uid: str) -> str:
    ev = find_event(text, uid)
    return "".join(splice(split_physical(text), [(ev.first, ev.last)], {}))


@dataclass
class Result:
    message: str
    diff: str


def commit(path: Path, old: str, new: str, in_place: bool = False, dry_run: bool = False) -> Result:
    """Validate, then write. Default: a NEW file next to the original."""
    parse(new)  # refuse to write something that no longer parses
    a = [x.rstrip("\r\n") for x in split_physical(old)]
    b = [x.rstrip("\r\n") for x in split_physical(new)]
    diff = "\n".join(difflib.unified_diff(a, b, path.name, path.name + " (edited)", lineterm="", n=1))
    if dry_run:
        return Result("dry run: nothing written", diff)
    if in_place:
        if path.read_bytes() != old.encode("utf-8"):
            raise ICalError(f"{path.name} changed on disk since it was read; nothing written")
        tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex[:8]}.tmp")
        tmp.write_bytes(new.encode("utf-8"))
        os.replace(tmp, path)  # atomic: readers see the old file or the new one, never half
        return Result(f"modified {path.name} in place", diff)
    target = path.with_name(path.name + ".new")
    try:
        with open(target, "xb") as fh:  # 'x': fail rather than overwrite
            fh.write(new.encode("utf-8"))
    except FileExistsError:
        raise ICalError(f"{target.name} already exists; refusing to overwrite it") from None
    return Result(f"wrote {target.name}; the original is untouched", diff)
