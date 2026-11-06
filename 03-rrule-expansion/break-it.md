# Break It: RRULE Expansion

## Challenge 1: Ignore WKST

Hard-code `wkst = 0` in `_period_days` and `_first_period` (always Monday). Which assert in
`main.py` fails? Does the `dateutil` comparison also fail, and with which kind of rule?

**Hint:** Only rules that combine `WEEKLY`, an `INTERVAL` greater than 1 and several `BYDAY`s
can tell the difference. The random test only generates `INTERVAL` 1-3 with up to three days; it
may or may not find it. If it does not, that is a finding about your test, not your code.

## Challenge 2: Expand in UTC

In `occurrences`, convert DTSTART to UTC first and run the rule engine on the UTC wall clock,
then convert back. Run the weekly Berlin meeting test (`09:00 Berlin: 08Z before Mar 29, 07Z
after`). What do you get after the clock change?

**Hint:** In UTC the meeting is a fixed 08:00 forever, so the local time drifts to 10:00 in
summer. This is the bug "my recurring meeting moved an hour in March".

## Challenge 3: Walk from the beginning

Remove the `_first_period` shortcut so every query starts at DTSTART. Time a query for next month
on a daily event that started in 1990. Then put 10,000 such events in a file (Module 07 has the
generator) and time the agenda.

**Hint:** 12,000 iterations per event times 10,000 events. The skip-ahead is what makes
"what's on my agenda?" instant.

## Challenge 4: A rule that never matches

`RRULE:FREQ=YEARLY;BYMONTH=2;BYMONTHDAY=30` has no instances. What does your engine do when
asked for the next 3 occurrences with no end date? Where did the loop stop?

**Hint:** `_period_days` returns `None` after year 9999. In the full icskit-mcp, `next_occurrences`
asks with growing windows (1, 5, 25, 100 years) so the question always has an end.

## Challenge 5: Accept BYWEEKNO

Delete `BYWEEKNO` from the unsupported list and let it fall through. Expand
`FREQ=YEARLY;BYWEEKNO=20;BYDAY=MO`. What dates do you get, and does anything tell you they are
wrong?

**Hint:** The part is ignored, so you get every Monday of the year. Nothing complains. That is
why unsupported parts raise.
