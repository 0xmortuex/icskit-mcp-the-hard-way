# Calendar MCP Server - The Hard Way

Build an MCP server that lets an AI agent work with the `.ics` calendar files on your disk:
what is on the agenda, when you are free, what overlaps, and safe edits. You start from raw
text and end with an agent finding a meeting slot across three calendars on a daylight-saving
Sunday. No calendar library, no account, no network.

At the end you will have built a small version of
[icskit-mcp](https://github.com/0xmortuex/icskit-mcp) yourself, and you will understand the
three things that make calendar software wrong in practice: **time zones**, **recurrence**
and **editing a file you did not write**.

## Why This Exists

Most "calendar tool" demos call a hosted API. The interesting part is everything underneath:

- an `.ics` file is a 25-year-old text format with folding, escaping, quoting and three
  different line endings;
- "every Monday at 09:00" is a rule, not a list, and 09:00 means a different instant before and
  after the clocks change;
- "find me 90 free minutes" is interval arithmetic that has to survive 23-hour and 25-hour days;
- an agent that edits your calendar must not quietly rewrite the rest of your file.

## Who This Is For

Developers who built a hello-world MCP server and want a real one, and anyone who has been
bitten by a time-zone bug. **Prerequisites:** Python 3.10+ and a little comfort with `datetime`.

```bash
pip install -r requirements.txt
python verify.py
```

## Modules

| # | Module | What You'll Build |
|---|--------|-------------------|
| 01 | [iCalendar Grammar](01-icalendar-grammar/) | Line folding, parameters and quoting, TEXT escaping, and a component tree that remembers its physical lines |
| 02 | [Time Zones and DST](02-time-zones-and-dst/) | Wall clock vs instant, the gap and the overlap, and the subtraction trap in `datetime` |
| 03 | [RRULE Expansion](03-rrule-expansion/) | A recurrence engine checked against RFC 5545's own examples and `python-dateutil`, a `tzinfo` built from Outlook's `VTIMEZONE`, and events across DST |
| 04 | [Free/Busy Math](04-free-busy-math/) | Interval merge and subtract, working hours that survive 23 and 25 hour days, buffers, and conflict detection |
| 05 | [Safe Writing](05-safe-writing/) | Editing by line surgery so everything else stays byte-identical, with copy-by-default and a dry run |
| 06 | [The MCP Wrapper](06-the-mcp-wrapper/) | Six tools, errors that tell the agent what to do next, tested over real stdio |
| 07 | [Testing with Hostile Calendars](07-testing-with-hostile-calendars/) | Damaged files, adversarial text, impossible rules, 10,000 events, and an independent oracle |

Each module contains:

- **`README.md`**: the concepts and the design decisions
- **`main.py`**: runnable checks. Every claim in the README is an `assert` against the real files in [`data/`](data/)
- **`break-it.md`**: challenges that break your own code, with hints

## How the Code Is Organised

The modules build one small package, [`minical/`](minical/). Each module adds a file:

```
minical/parse.py       Module 01   tokenizer + component tree
minical/zones.py       Module 02   wall clock <-> instant
minical/rrule.py       Module 03   recurrence rules
minical/vtimezone.py   Module 03   tzinfo from a VTIMEZONE block
minical/events.py      Module 03   VEVENT -> occurrences
minical/freebusy.py    Module 04   intervals, free time, conflicts
minical/writer.py      Module 05   safe edits
minical/server.py      Module 06   the MCP server
```

So `main.py` of module N imports what modules 1..N built. Read the README, read the file it
points to, run `main.py`, then try `break-it.md`.

## The Data

[`data/`](data/) holds four hand-written calendars in the style of real exports:

| File | Style | What it exercises |
|------|-------|-------------------|
| `google.ics` | Google Calendar | `TZID=Europe/Istanbul`, a weekly rule with `EXDATE`, a moved instance (`RECURRENCE-ID`), folded and escaped text, a cancelled event, a transparent all-day event |
| `apple.ics` | Apple Calendar | an embedded `VTIMEZONE`, a `VALARM`, a floating time, `DURATION`, a daily rule across the Berlin clock change, `2SA` monthly rule |
| `outlook.ics` | Outlook / Exchange | Windows time zone names (`W. Europe Standard Time`) defined only by `VTIMEZONE`, an event spanning the US spring-forward |
| `hostile.ics` | damaged | a garbage line, a missing `DTSTART`, an unsupported rule, `DTEND` before `DTSTART`, an unknown zone, a bad date |

## Key Design Principles

**1. Wall clock first, instant last.** An event is "09:00 in Berlin". Recurrence works on wall
clocks; only the final step turns them into instants.

**2. Never trust a subtraction between two datetimes that share a `tzinfo`.** Convert to UTC.

**3. Reject what you cannot do correctly.** An unsupported recurrence rule is reported and the
event is skipped. It is never silently expanded into the wrong dates.

**4. Don't regenerate a file you only mean to change.** Find the lines, splice the lines.

**5. Errors are instructions.** "unknown time zone 'CEST'; use an IANA name like
'Europe/Istanbul'" is the next step. A stack trace is a dead end.

**6. Check against something independent.** The RFC's examples and `python-dateutil` are the
second opinion for the recurrence engine; `zoneinfo` is the second opinion for the custom
`VTIMEZONE` zone.

## Every Module Is Verified

```bash
python verify.py          # all
python verify.py 03 05    # some
```

CI runs it on Linux and Windows on every push and weekly.

MIT licensed.
