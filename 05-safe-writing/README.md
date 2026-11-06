# Module 05: Safe Writing

## The Concept

Reading a calendar is harmless. Writing one is how an agent loses a year of your events. The
obvious implementation of "add an event" is: parse the file into objects, append one, serialise
everything back. It looks fine on the test file and then, on a real export, it:

- drops `X-APPLE-TRAVEL-ADVISORY-BEHAVIOR` and every other property you did not model;
- loses `VALARM` reminders, or reorders them;
- re-folds every long line, and changes CRLF to LF;
- writes `TZID` blocks differently, or not at all;
- turns a recurring event's `EXDATE` list into something almost equivalent.

Every one of those is "almost equivalent" until it is your calendar. The rule for this module:

> **Never re-serialise a file you only mean to change. Parse it to learn which physical lines
> to touch, then splice lines.**

That is why Module 01 recorded `first` and `last` for every property and component. The code is
[`minical/writer.py`](../minical/writer.py).

## Line surgery

```python
def splice(lines, remove, insert):
    skip = {i for a, b in remove for i in range(a, b + 1)}
    out = []
    for i, ln in enumerate(lines):
        out.extend(insert.get(i, []))     # new lines go BEFORE original line i
        if i not in skip:
            out.append(ln)
    return out
```

- **Add**: insert the new `BEGIN:VEVENT ... END:VEVENT` before the `END:VCALENDAR` line.
- **Change a field**: remove the property's whole line span (a folded property spans several
  physical lines; `Prop.first..last` covers them) and insert the replacement at the same place.
  Bump `SEQUENCE` the same way, as calendar clients expect when an event changes.
- **Delete**: remove the `VEVENT`'s span.

Everything else is never touched, because it is never re-generated. The check in `main.py` is
blunt and strong: after `add_event`, the list of raw top-level blocks starts with the old list,
unchanged; after `set_summary`, exactly one block differs; and `delete_event(add_event(x))`
returns `x` **byte for byte**. If any line were normalised along the way, that last assert would
fail.

New lines use the file's own line ending (`detect_newline`), are folded at 75 *octets* without
splitting a UTF-8 character, and escape TEXT. Because we escape, newlines in a summary become
`\n` and cannot start a new property:

```
summary = "x\nATTENDEE:mailto:evil@x.org"   ->   SUMMARY:x\nATTENDEE:mailto:evil@x.org
```

Control characters (`\x00`...) are refused outright.

## Don't write a lie

If an agent asks for 02:30 in Berlin on 2026-03-29, that time does not exist. We could write it
and let some client guess; instead `add_event` raises "does not exist in Europe/Berlin (clocks go
forward over it)". Writing is where errors become permanent.

## Defaults that protect you

`commit()` is where the policy lives:

| You pass | Result |
|----------|--------|
| nothing | a **new** file `<name>.new` next to the original (opened with mode `"x"`: if it exists, fail, never overwrite) |
| `dry_run=True` | nothing written; you get a unified diff |
| `in_place=True` | the original is replaced **atomically** (write a temp file, `os.replace`) |

and every path does these first:

1. `parse(new)`: refuse to write anything that no longer parses (a bug in the editor must not
   produce a corrupt calendar);
2. for `in_place`, compare the file on disk with what we read; if someone else changed it in
   between, stop;
3. return the diff so the agent (and you) see exactly what changed.

The default is a *copy* because an agent is allowed to be wrong and you are allowed to look first.
In the real icskit-mcp the copy is `<file>.ics.new`, which is not picked up as a second calendar
(that would show every event twice).

## Run It

```bash
python 05-safe-writing/main.py
```

## Takeaways

- Splice lines; never regenerate.
- A round trip (add then delete) that is byte-identical is the best test you can write.
- Escape on the way out, refuse control characters, refuse times that do not exist.
- Default to the least destructive action, show the diff, and validate before writing.
