"""Module 01: an iCalendar (RFC 5545) tokenizer and component tree.

Three layers, each one small:
  1. physical lines   - split text on CRLF / LF / CR, keep the endings
  2. logical lines    - unfold: a physical line starting with space or tab continues the previous one
  3. content lines    - NAME;PARAM=value;PARAM="quoted":VALUE  ->  (name, params, value)
Then BEGIN/END pairs become a tree of Components.

Every Component and Prop remembers which physical lines it came from. Module 05 uses
that to edit a file without disturbing anything else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime


class ICalError(Exception):
    """The calendar text is malformed. The message says where."""


_LINE_RE = re.compile(r"[^\r\n]*(?:\r\n|\n|\r)|[^\r\n]+")


def split_physical(text: str) -> list[str]:
    # NOT str.splitlines(): that also splits on form feed, U+2028 and others,
    # which are legal inside values.
    return _LINE_RE.findall(text)


@dataclass
class Prop:
    name: str
    params: dict[str, list[str]]
    value: str
    first: int  # first physical line index
    last: int  # last physical line index (folded continuations included)

    def param(self, key: str) -> str | None:
        vals = self.params.get(key.upper())
        return vals[0] if vals else None


@dataclass
class Component:
    name: str
    first: int
    last: int = -1
    props: list[Prop] = field(default_factory=list)
    children: list[Component] = field(default_factory=list)

    def get(self, name: str) -> Prop | None:
        for p in self.props:
            if p.name == name.upper():
                return p
        return None

    def get_all(self, name: str) -> list[Prop]:
        return [p for p in self.props if p.name == name.upper()]

    def sub(self, name: str) -> list[Component]:
        return [c for c in self.children if c.name == name.upper()]


def parse_content_line(s: str) -> tuple[str, dict[str, list[str]], str]:
    """'ATTENDEE;CN="Doe; Jane":mailto:j@x' -> ('ATTENDEE', {'CN': ['Doe; Jane']}, 'mailto:j@x')"""
    n = len(s)
    i = 0
    while i < n and s[i] not in ";:":
        i += 1
    if i >= n:
        raise ValueError("no ':' separating the name from the value")
    name = s[:i].strip().upper()
    params: dict[str, list[str]] = {}
    while s[i] == ";":
        i += 1
        j = i
        while j < n and s[j] not in "=:;":
            j += 1
        if j >= n or s[j] != "=":
            raise ValueError("parameter without '='")
        pname = s[i:j].strip().upper()
        i = j + 1
        values: list[str] = []
        while True:
            if i < n and s[i] == '"':  # quoted: may contain ; : ,
                k = s.find('"', i + 1)
                if k < 0:
                    raise ValueError("unterminated quote")
                values.append(s[i + 1 : k])
                i = k + 1
            else:
                k = i
                while k < n and s[k] not in ",;:":
                    k += 1
                values.append(s[i:k])
                i = k
            if i < n and s[i] == ",":
                i += 1
                continue
            break
        params.setdefault(pname, []).extend(values)
        if i >= n:
            raise ValueError("no ':' after the parameters")
    return name, params, s[i + 1 :]


@dataclass
class Parsed:
    roots: list[Component]
    lines: list[str]  # physical lines, endings included
    warnings: list[str]


def parse(text: str) -> Parsed:
    if text.startswith("\ufeff"):
        text = text[1:]
    phys = split_physical(text)
    warnings: list[str] = []
    roots: list[Component] = []
    stack: list[Component] = []
    i = 0
    while i < len(phys):
        first = i
        body = phys[i].rstrip("\r\n")
        i += 1
        if not body:
            continue
        if body[0] in " \t":
            warnings.append(f"line {first + 1}: continuation with nothing to continue; skipped")
            continue
        parts = [body]
        while i < len(phys):  # unfold
            nxt = phys[i].rstrip("\r\n")
            if nxt and nxt[0] in " \t":
                parts.append(nxt[1:])  # drop exactly ONE leading whitespace char
                i += 1
            else:
                break
        last = i - 1
        try:
            name, params, value = parse_content_line("".join(parts))
        except ValueError as e:
            # A damaged line is reported, never silently dropped.
            warnings.append(f"line {first + 1}: malformed property ({e}); skipped")
            continue
        if name == "BEGIN":
            comp = Component(value.strip().upper(), first)
            (stack[-1].children if stack else roots).append(comp)
            stack.append(comp)
        elif name == "END":
            end = value.strip().upper()
            if not stack or stack[-1].name != end:
                raise ICalError(f"line {first + 1}: END:{end} does not match an open BEGIN")
            stack[-1].last = last
            stack.pop()
        elif stack:
            stack[-1].props.append(Prop(name, params, value, first, last))
        else:
            warnings.append(f"line {first + 1}: property outside any component; skipped")
    if stack:
        raise ICalError(f"BEGIN:{stack[-1].name} on line {stack[-1].first + 1} is never closed")
    if not any(r.name == "VCALENDAR" for r in roots):
        raise ICalError("no BEGIN:VCALENDAR - not an iCalendar file")
    return Parsed(roots, phys, warnings)


# --- values ---------------------------------------------------------------------------


def unescape_text(v: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(v):
        if v[i] == "\\" and i + 1 < len(v):
            out.append("\n" if v[i + 1] in "nN" else v[i + 1])
            i += 2
        else:
            out.append(v[i])
            i += 1
    return "".join(out)


def escape_text(v: str) -> str:
    return (
        v.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
        .replace("\r\n", "\\n").replace("\n", "\\n")
    )


_DT = re.compile(r"^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(Z?)$")


def is_date_value(v: str) -> bool:
    return bool(re.fullmatch(r"\d{8}", v.strip()))


def parse_date(v: str) -> date:
    if not re.fullmatch(r"\d{8}", v):
        raise ICalError(f"bad DATE {v!r} (want YYYYMMDD)")
    return date(int(v[:4]), int(v[4:6]), int(v[6:]))


def parse_datetime(v: str) -> tuple[datetime, bool]:
    """-> (naive wall-clock datetime, ends_with_Z)"""
    m = _DT.match(v)
    if not m:
        raise ICalError(f"bad DATE-TIME {v!r} (want YYYYMMDDTHHMMSS or ...Z)")
    y, mo, d, h, mi, s = (int(x) for x in m.groups()[:6])
    return datetime(y, mo, d, h, mi, s), m[7] == "Z"
