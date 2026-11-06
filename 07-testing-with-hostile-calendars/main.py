"""Module 07 check: calendars that are damaged, odd or adversarial.

Run:  python 07-testing-with-hostile-calendars/main.py
The theme: every failure is REPORTED, one bad event or file never hides the good ones,
and the answers are checked against something independent.
"""

import asyncio
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from minical import server  # noqa: E402
from minical.events import expand_all, load_events  # noqa: E402
from minical.parse import ICalError, parse  # noqa: E402

UTC = timezone.utc
DATA = Path(ROOT) / "data"


def cal(*events: str) -> str:
    return "BEGIN:VCALENDAR\r\nVERSION:2.0\r\n" + "".join(events) + "END:VCALENDAR\r\n"


def vevent(*lines: str) -> str:
    return "BEGIN:VEVENT\r\n" + "".join(f"{ln}\r\n" for ln in lines) + "END:VEVENT\r\n"


# --- 1. the hostile fixture: each flaw becomes one readable problem ----------------------------------------
events, problems = load_events(parse((DATA / "hostile.ics").read_bytes().decode("utf-8")), "hostile.ics")
assert [e.uid for e in events] == ["ok-1"], "only the healthy event survives"
joined = "\n".join(problems)
for needle in ("line 4: malformed property", "no DTSTART", "FREQ=HOURLY", "DTEND is before DTSTART",
               "Mars/Olympus_Mons", "bad DATE-TIME"):
    assert needle in joined, needle
print("1. six flaws, six explanations:", len(problems))

# --- 2. one broken FILE must not hide the others ------------------------------------------------------------------
with tempfile.TemporaryDirectory() as tmp:
    d = Path(tmp)
    (d / "good.ics").write_text(cal(vevent("UID:1", "DTSTART:20260302T090000Z", "DURATION:PT1H", "SUMMARY:Still here")), newline="")
    (d / "truncated.ics").write_text("BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:2\r\n", newline="")
    (d / "latin1.ics").write_bytes(b"BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nSUMMARY:Caf\xe9\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n")
    (d / "binary.ics").write_bytes(bytes(range(256)) * 8)
    server.configure(d)
    out = server.calendar_overview()
    assert "good.ics: 1 events" in out and "Still here" in server.agenda("2026-03-02", "2026-03-02")
    assert "truncated.ics" in out and "never closed" in out
    assert "latin1.ics" in out and "binary.ics" in out
    print("2. broken files are listed, good files still work")

    # --- 3. the sandbox ---------------------------------------------------------------------------------------------
    for bad in ("../outside.ics", "..\\outside.ics", str(d.parent / "outside.ics")):
        try:
            server.add_event(bad, "x", "2026-03-02T10:00", 30)
        except ICalError as e:
            assert "outside the allowed directory" in str(e) or "not found" in str(e), str(e)
        else:
            raise AssertionError(bad)
    print("3. path escapes refused")

# --- 4. odd but legal ------------------------------------------------------------------------------------------------
odd = parse(cal(
    vevent("UID:a", "DTSTART:20260302T090000Z", "DTEND:20260302T090000Z", "SUMMARY:Zero length"),
    vevent("UID:b", "DTSTART;VALUE=DATE:20260302", "SUMMARY:All day, no end"),
    vevent("UID:c", "DTSTART:20260302T100000Z", "SUMMARY:No end at all"),
    vevent("DTSTART:20260302T110000Z", "DURATION:PT1H", "SUMMARY:No UID"),
    vevent("UID:e", "DTSTART:20260302T120000Z", "DURATION:PT1H", "RRULE:FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=30", "SUMMARY:Never matches"),
    vevent("UID:f", "DTSTART:20260302T130000Z", "DESCRIPTION:" + "x" * 300_000, "SUMMARY:Huge description"),
))
evs, probs = load_events(odd, "odd.ics")
assert not probs and len(evs) == 6
occ = expand_all(evs, datetime(2026, 3, 2, tzinfo=UTC), datetime(2026, 3, 3, tzinfo=UTC), UTC)
assert {o.event.summary for o in occ} == {e.summary for e in evs}, "all six show up"
assert next(e for e in evs if e.summary == "No UID").uid.startswith("no-uid"), "a missing UID gets a stable stand-in"
print("4. odd-but-legal events ok")

# --- 5. never hang: an impossible rule with a far window --------------------------------------------------------------
t0 = time.perf_counter()
far = expand_all(evs, datetime(2300, 1, 1, tzinfo=UTC), datetime(2300, 12, 31, tzinfo=UTC), UTC)
assert far == [] and time.perf_counter() - t0 < 5
print("5. impossible rules return promptly")

# --- 6. scale: 10,000 events -------------------------------------------------------------------------------------------
body = "".join(
    vevent(f"UID:e{i}", f"DTSTART;TZID=Europe/Berlin:2026{(i % 12) + 1:02d}{(i % 28) + 1:02d}T{9 + i % 8:02d}0000",
           "DURATION:PT30M", "RRULE:FREQ=WEEKLY;COUNT=20" if i % 4 == 0 else "COMMENT:single", f"SUMMARY:Event {i}")
    for i in range(10_000)
)
t0 = time.perf_counter()
big, probs = load_events(parse(cal(body)), "big.ics")
occ = expand_all(big, datetime(2026, 3, 1, tzinfo=UTC), datetime(2026, 4, 1, tzinfo=UTC), UTC)
elapsed = time.perf_counter() - t0
assert len(big) == 10_000 and not probs and elapsed < 30, (len(big), elapsed)
print(f"6. 10,000 events parsed and a month expanded ({len(occ)} occurrences) in {elapsed:.1f}s")


# --- 7. the same answers over the real wire, including failure ---------------------------------------------------------
async def over_stdio() -> None:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    with tempfile.TemporaryDirectory() as tmp:
        shutil.copy(DATA / "hostile.ics", tmp)
        shutil.copy(DATA / "google.ics", tmp)
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONPATH": ROOT}
        p = StdioServerParameters(command=sys.executable, args=["-m", "minical.server", "--dir", tmp], env=env, cwd=ROOT)
        async with stdio_client(p) as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            res = await s.call_tool("calendar_overview", {})
            assert not res.is_error and "Problems (6)" in res.content[0].text, res.content[0].text
            res = await s.call_tool("agenda", {"start": "2026-03-02", "end": "2026-03-02", "tz": "UTC"})
            assert "Fine event" in res.content[0].text and "Warnings:" in res.content[0].text
            res = await s.call_tool("delete_event", {"calendar": "google.ics", "event_uid": "nope"})
            assert res.is_error and "no event with UID" in res.content[0].text


asyncio.run(over_stdio())
print("7. hostile calendars over stdio ok")

print("MODULE 07 OK")
