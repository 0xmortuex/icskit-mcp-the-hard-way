# Break It: Safe Writing

## Challenge 1: Re-serialise

Write `add_event_naive(text, ...)` that parses with `parse()`, builds a list of "lines" from the
tree (`NAME;PARAMS:VALUE` for each prop), appends the new event, and joins with `\r\n`. Run the
round-trip assert (`delete_event(add_event(x)) == x`). What is lost on `data/apple.ics`?

**Hint:** Count the differences: the folded `SUMMARY`, the `VALARM`, the order of properties, the
final newline.

## Challenge 2: Lose a continuation line

In `set_summary`, remove only `old.first` instead of `(old.first, old.last)`. Edit
the long-titled event in `data/google.ics` (`utc-meeting-002@google.com`). What does the file
look like afterwards, and does `commit` catch it?

**Hint:** The orphaned continuation line starts with a space, so it is glued onto the line
before it: your freshly written `SUMMARY`. The file still parses. That is exactly the kind of damage only a byte-level
comparison catches.

## Challenge 3: Injection

Change `escape_text` to leave `\n` alone and call `add_event` with the summary
`x\r\nATTENDEE:mailto:evil@x.org`. Parse the result and list the attendees.

**Hint:** A newline in a value is a new content line. Whoever controls the title controls the
event.

## Challenge 4: The race

Open `data/apple.ics`, call `add_event`, then (before `commit`) append a line to the file from
another process. Call `commit(..., in_place=True)`. What happens with the stale-write check removed?

**Hint:** Your edit was computed from the old text, so it silently erases the other process's
change.

## Challenge 5: Overwrite

Remove the `"xb"` mode (use `"wb"`) and call `commit` twice. What does the second call do to the
first call's output? Why is the real tool strict about this when the agent will "just retry"?

**Hint:** Retrying a write is the moment an agent is most likely to be confused about what exists.
