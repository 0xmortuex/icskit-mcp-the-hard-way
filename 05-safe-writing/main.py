"""Module 05 check: line-surgery edits, round trips and the safety defaults.

Run:  python 05-safe-writing/main.py
"""

import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from minical import writer  # noqa: E402
from minical.parse import ICalError, parse, unescape_text  # noqa: E402

DATA = Path(ROOT) / "data"


def read(p: Path) -> str:
    return p.read_bytes().decode("utf-8")  # bytes -> str, no newline translation


def blocks(text: str) -> list[str]:
    """The raw text of every top-level component (VEVENT, VTIMEZONE...), in file order."""
    p = parse(text)
    return ["".join(p.lines[c.first : c.last + 1]) for r in p.roots for c in r.children]


old = read(DATA / "apple.ics")

# --- 1. add_event: everything that existed is byte-identical ----------------------------------------------------
new, uid = writer.add_event(old, "Dentist, 3rd floor; bring card", "2026-03-10T15:00", 45, "Europe/Istanbul")
ob, nb = blocks(old), blocks(new)
assert nb[: len(ob)] == ob and len(nb) == len(ob) + 1, "old blocks identical, one block appended"
assert "DTSTART;TZID=Europe/Istanbul:20260310T150000" in new
assert unescape_text(writer.find_event(new, uid).get("SUMMARY").value) == "Dentist, 3rd floor; bring card"
assert "X-CUSTOM-FLAG:keep-me" in new and "BEGIN:VALARM" in new, "unknown properties and alarms survive"
print("1. add_event ok")

# --- 2. set_summary touches one property (and SEQUENCE) -------------------------------------------------------------
changed = writer.set_summary(old, "market-day@apple", "Big farmers market")
ob, nb = blocks(old), blocks(changed)
diff = [i for i in range(len(ob)) if ob[i] != nb[i]]
assert len(ob) == len(nb) and len(diff) == 1 and "market-day@apple" in nb[diff[0]], diff
assert "SUMMARY:Big farmers market" in changed and "SEQUENCE:1" in changed and "X-CUSTOM-FLAG:keep-me" in changed
print("2. set_summary ok")

# --- 3. delete is the inverse of add: the file comes back byte for byte -----------------------------------------------
assert writer.delete_event(new, uid) == old
print("3. add then delete round-trips byte for byte")

# --- 4. line endings and folding ------------------------------------------------------------------------------------------
lf = old.replace("\r\n", "\n")
new_lf, _ = writer.add_event(lf, "x", "2026-03-10T15:00", 30, "UTC")
assert "\r" not in new_lf, "an LF file stays LF"
long_title = "Ünïcode " * 30
new2, uid2 = writer.add_event(old, long_title, "2026-03-10T15:00", 30, "UTC")
assert all(len(ln.encode("utf-8")) <= 75 for ln in new2.split("\r\n"))
assert unescape_text(writer.find_event(new2, uid2).get("SUMMARY").value) == long_title
print("4. endings and folding ok")

# --- 5. hostile input cannot inject properties ---------------------------------------------------------------------------
new3, uid3 = writer.add_event(old, "x\nATTENDEE:mailto:evil@x.org", "2026-03-10T15:00", 30, "UTC")
assert not writer.find_event(new3, uid3).get_all("ATTENDEE"), "the newline was escaped, not obeyed"
for bad in ("bad\x00title",):
    try:
        writer.add_event(old, bad, "2026-03-10T15:00", 30, "UTC")
    except ICalError as e:
        assert "control character" in str(e)
    else:
        raise AssertionError("control characters must be refused")
try:
    writer.add_event(old, "gap", "2026-03-29T02:30", 30, "Europe/Berlin")
except ICalError as e:
    assert "does not exist" in str(e)
else:
    raise AssertionError("a time in the DST gap must be refused")
print("5. injection and gap guards ok")

# --- 6. commit: copy by default, dry run, in place, refusals --------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp) / "apple.ics"
    shutil.copy(DATA / "apple.ics", path)
    sha = hashlib.sha256(path.read_bytes()).hexdigest()

    r = writer.commit(path, old, new, dry_run=True)
    assert "nothing written" in r.message and "+SUMMARY:Dentist" in r.diff
    assert not (Path(tmp) / "apple.ics.new").exists()

    r = writer.commit(path, old, new)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == sha, "the original is untouched"
    assert (Path(tmp) / "apple.ics.new").read_bytes().decode("utf-8") == new
    try:
        writer.commit(path, old, new)
    except ICalError as e:
        assert "already exists" in str(e)
    else:
        raise AssertionError("must not overwrite an existing copy")

    path.write_bytes(path.read_bytes() + b"X-LATE:edit\r\n")  # someone else edits the file meanwhile
    try:
        writer.commit(path, old, new, in_place=True)
    except ICalError as e:
        assert "changed on disk" in str(e)
    else:
        raise AssertionError("stale in-place write must be refused")
    shutil.copy(DATA / "apple.ics", path)
    r = writer.commit(path, old, new, in_place=True)
    assert read(path) == new and not list(Path(tmp).glob("*.tmp"))

    try:
        writer.commit(path, old, "BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\n")
    except ICalError as e:
        assert "never closed" in str(e)
    else:
        raise AssertionError("a result that no longer parses must never be written")
print("6. commit safety ok")

print("MODULE 05 OK")
