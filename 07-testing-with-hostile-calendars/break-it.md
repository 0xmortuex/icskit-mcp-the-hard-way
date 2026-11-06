# Break It: Testing with Hostile Calendars

## Challenge 1: Swallow the warning

In `parse`, replace `warnings.append(...)` for malformed lines with `continue`. Run
`python 07-testing-with-hostile-calendars/main.py`. Which assertion notices? Now imagine the same
change with no test: how would a user find out their meeting is missing?

**Hint:** They would not. The agenda would simply be shorter.

## Challenge 2: Fall back to cp1252

In `_load_all`, catch `UnicodeDecodeError` and re-read the file as `cp1252`. Open `latin1.ics`'s
agenda. It "works". What is the downside, and when would it silently show the wrong text?

**Hint:** cp1252 decodes almost any byte sequence. A UTF-16 or Shift-JIS file turns into gibberish
with no error. Reporting is more honest than guessing.

## Challenge 3: One bad file kills the folder

Remove the `try/except` around `parse(...)` in `_load_all` and drop `truncated.ics` next to a good
calendar. What does `agenda` return?

**Hint:** The whole tool fails because of a file the user did not ask about.

## Challenge 4: Write your own hostile event

Add an event to `data/hostile.ics` that you think could break the server: an `RDATE` with a
nonsense value, a `DURATION` of `PT0S`, `RRULE` with `UNTIL` before `DTSTART`, two events with the
same UID. Run `calendar_overview`. Does the server report it, skip it, or crash? Whichever it is,
write down the behaviour you *want* and make it a test.

**Hint:** The first run will probably teach you something. That is the point of the exercise.

## Challenge 5: Make the oracle disagree

Change the engine so `FREQ=MONTHLY;BYDAY=-1FR` returns the second-to-last Friday (an off-by-one in
`_nth`). Run Module 03. How many of the 300 random rules does it take for the `dateutil`
comparison to catch it? Which of the RFC examples catches it?

**Hint:** Both do, quickly. Now remove the ordinal rules from the random generator and see how
much weaker the oracle becomes: a test is only as strong as what it generates.
