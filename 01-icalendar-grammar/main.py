"""Module 01 check: the grammar of an .ics file, parsed by hand.

Run:  python 01-icalendar-grammar/main.py
Every claim in the README is asserted here against the real exports in data/.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from minical.parse import (  # noqa: E402
    ICalError,
    escape_text,
    parse,
    parse_content_line,
    split_physical,
    unescape_text,
)

DATA = os.path.join(ROOT, "data")


def read(name: str) -> str:
    with open(os.path.join(DATA, name), "rb") as fh:  # bytes -> str, no newline translation
        return fh.read().decode("utf-8")


# --- 1. physical lines: three line endings, and why splitlines() is wrong ----------------
assert split_physical("a\r\nb\nc\rd") == ["a\r\n", "b\n", "c\r", "d"]
assert split_physical("x y\x0cz") == ["x y\x0cz"], "U+2028 and form feed are NOT line breaks"
print("1. physical lines ok")

# --- 2. content lines: parameters, quoting ------------------------------------------------
name, params, value = parse_content_line('ATTENDEE;CN="Doe; Jane: Jr.";ROLE=CHAIR:mailto:j@x.org')
assert (name, value) == ("ATTENDEE", "mailto:j@x.org")
assert params == {"CN": ["Doe; Jane: Jr."], "ROLE": ["CHAIR"]}, "a quoted value may contain ; : ,"
print("2. content lines ok")

# --- 3. a real Google export: unfolding, escaping, the component tree ------------------------
parsed = parse(read("google.ics"))
cal = parsed.roots[0]
assert cal.name == "VCALENDAR" and len(cal.sub("VEVENT")) == 5
standup = cal.sub("VEVENT")[0]
assert standup.get("RRULE").value == "FREQ=WEEKLY;BYDAY=MO,WE,FR"
assert unescape_text(standup.get("DESCRIPTION").value) == "Daily sync.\nAgenda: blockers, plans; notes."
assert unescape_text(standup.get("LOCATION").value) == "Room 4, HQ"
long_title = cal.sub("VEVENT")[2].get("SUMMARY")
assert long_title.last > long_title.first, "a folded property spans several physical lines"
assert "several physical lines" in long_title.value, "unfolding drops exactly one space"
guest = standup.get_all("ATTENDEE")[0]
assert guest.param("PARTSTAT") == "ACCEPTED" and guest.value == "mailto:jane@example.com"
assert escape_text(unescape_text(standup.get("DESCRIPTION").value)) == standup.get("DESCRIPTION").value
print("3. google.ics parsed:", len(cal.sub("VEVENT")), "events")

# --- 4. spans: the tree remembers its physical lines (Module 05 needs this) -----------------
lines = parsed.lines
assert lines[standup.first].startswith("BEGIN:VEVENT") and lines[standup.last].startswith("END:VEVENT")
print("4. spans ok")

# --- 5. damage is reported, structure errors are errors -------------------------------------
bad = parse(read("hostile.ics"))
assert any("malformed property" in w and "line 4" in w for w in bad.warnings)
for broken, why in [
    ("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:1\r\n", "never closed"),
    ("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nEND:VTODO\r\nEND:VCALENDAR\r\n", "does not match"),
    ("just some text\r\n", "no BEGIN:VCALENDAR"),
]:
    try:
        parse(broken)
    except ICalError as e:
        assert why in str(e), str(e)
    else:
        raise AssertionError("should have raised")
print("5. errors ok")

print("MODULE 01 OK")
