# Module 07: Testing with Hostile Calendars

## The Concept

You have a calendar server that works on four tidy fixtures. Real calendars are not tidy. They
are exports from five different programs over twenty years, edited by hand, truncated by a bad
download, or written by someone who wants your server to misbehave. This module is about how to
know your server survives them, using the tests of the finished
[icskit-mcp](https://github.com/0xmortuex/icskit-mcp) as the model.

The standard to hold yourself to, in order:

1. **Nothing is swallowed.** A damaged file, a skipped event, an unsupported rule: each one
   appears in a message the agent can see.
2. **One bad thing does not hide the good things.** A broken event does not stop the file; a
   broken file does not stop the folder.
3. **It never hangs and never crashes** on input it can read.
4. **Answers are checked against something independent**, not against the code that produced them.

## 1. A fixture per flaw

[`data/hostile.ics`](../data/hostile.ics) contains six distinct problems in one file, each its
own event:

| Event | Flaw | Result the agent sees |
|-------|------|-----------------------|
| (line 4) | a line with no colon | `line 4: malformed property (...) ; skipped` |
| `no-start` | no `DTSTART` | `event 'No DTSTART' skipped: no DTSTART` |
| `bad-rule` | `FREQ=HOURLY` | `... skipped: ... FREQ=HOURLY is not supported ...` |
| `backwards` | `DTEND` before `DTSTART` | `... skipped: DTEND is before DTSTART` |
| `mystery-zone` | `TZID=Mars/Olympus_Mons` | `... not an IANA name and the file has no VTIMEZONE for it` |
| `garbage-date` | `DTSTART:2026-03-02 09:00` | `... bad DATE-TIME ...` |

and one healthy event, `ok-1`, which must still appear in the agenda. The test asserts all
six messages *and* that `ok-1` survives. Writing a fixture first and then making the code
produce a message for it is how you avoid "it returns an empty list and nobody knows why".

## 2. Damaged files, not just damaged events

Truncated download; a Latin-1 export (`Caf\xe9`); a binary file named `.ics`; an empty file. Each
should be listed under **Problems** with its file name, while the healthy file next to it keeps
working. We do not guess an encoding: a silent fallback to cp1252 would turn some other
program's bytes into plausible-looking wrong text. The message says "re-save as UTF-8".

## 3. Odd but legal

Legal files that trip naive code: a zero-length event, an all-day event with no `DTEND`, a timed
event with neither `DTEND` nor `DURATION`, an event with no `UID`, a 300 KB description, a rule
that can never match. The test asserts they all appear. Decide, per case, whether to be lenient
or strict, and then make the decision a test; a missing UID gets a stable stand-in because
rejecting it would hide a meeting.

## 4. Adversarial text

The writer (Module 05) is where an attacker's text meets your file. Tests in the full project:
a summary with `\r\nATTENDEE:mailto:evil@x.org`; control characters; an RRULE with an embedded
newline; paths with `..`, absolute paths, backslashes, and a symlink that points outside the
folder. Each is either escaped or refused, never obeyed.

## 5. Never hang

The impossible rule (`BYMONTH=2;BYMONTHDAY=30`) with a window in the year 2300 must return, not
spin. The engine stops at the window end or year 9999, and the full tool asks for
`next_occurrences` with growing windows so a question always has an end.

## 6. Scale

10,000 events in one file: parse them, expand a month, assert how long it took. The numbers here
are generous on purpose (CI machines are slow), but a `O(n^2)` bug or a missing skip-ahead shows
up as a 100x difference, not a 20% one. Parse once and cache by `(mtime, size)`; re-parse only
when the file changes.

## 7. An independent oracle

If the only check on your recurrence engine is "it matches what I expected when I wrote it", it
has the same blind spot you do. Module 03 compared against the RFC's examples and
`python-dateutil`. For time zones, compare your custom `VTIMEZONE` zone against `zoneinfo`. For
free time, hand-compute the answer for a tiny calendar. The finished project's test suite has all
of these, plus a `Friday the 13th` and an `every other month, first and last Sunday` rule from the
RFC.

## 8. Test the server the way it is used

`main.py` finishes with a stdio session against the hostile folder: `calendar_overview` reports
`Problems (6)`, `agenda` still shows `Fine event` with a `Warnings:` block, and `delete_event` with
an unknown UID returns `no event with UID 'nope'` as a tool error the client can read. Unit tests
on functions cannot tell you that the message actually crosses the process boundary.

## Run It

```bash
python 07-testing-with-hostile-calendars/main.py
python verify.py        # the whole course
```

## What To Do Next

You now have the skeleton of a calendar server whose answers you can defend. What
[icskit-mcp](https://github.com/0xmortuex/icskit-mcp) adds on top, and what you could build as
exercises:

- cache parsed files by `(mtime, size)`;
- `update_event` with attendee merging, `SEQUENCE` bumps, and "keep the event's length when the
  start moves";
- deleting a single occurrence by adding an `EXDATE` (and removing a matching modified instance);
- `search_events` by text, attendee and regex;
- `export_agenda_markdown`;
- the full `RRULE` set you declined here, with a loud error for what is still missing.

MIT licensed.
