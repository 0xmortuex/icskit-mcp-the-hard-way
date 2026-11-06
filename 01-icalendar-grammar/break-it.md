# Break It: iCalendar Grammar

## Challenge 1: `splitlines()`

Replace `split_physical` with `text.splitlines(keepends=True)` and parse an event whose
`SUMMARY` contains a form feed (`\x0c`) or U+2028. What happens to that event? Which assert in
`main.py` notices?

**Hint:** `splitlines` treats those characters as line breaks. Half of the title becomes a
"continuation with nothing to continue" or a malformed property.

## Challenge 2: `lstrip()` while unfolding

In `parse`, change `parts.append(nxt[1:])` to `parts.append(nxt.lstrip())`. Feed it
`SUMMARY:Hello\r\n   world` (three spaces on the second line). What do you get? What *should* you
get?

**Hint:** RFC 5545 removes exactly one whitespace character. The other two spaces are part of the
text.

## Challenge 3: Split on the first colon

Rewrite `parse_content_line` as `name, value = line.split(":", 1)`. Which line in `data/google.ics`
breaks first, and why? (Look at the `ATTENDEE` lines.)

**Hint:** The `CN` parameter is quoted and contains `\,`; a quoted parameter may also contain `:`.

## Challenge 4: A calendar from the wild

Take `data/google.ics`, delete its last line (`END:VCALENDAR`) and parse it. Then delete a
single `END:VEVENT` in the middle. Compare the two error messages. Which one points at the right
line, and could the other do better?

**Hint:** The second error is detected one event later than the real mistake. What information
would you need to point at the true culprit?
