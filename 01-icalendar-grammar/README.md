# Module 01: iCalendar Grammar

## The Concept

A calendar export looks like this:

```
BEGIN:VEVENT
DTSTART;TZID=Europe/Istanbul:20260302T100000
SUMMARY:Call with the London office, a very long title that has to be folded across
 several physical lines
ATTENDEE;CN="Doe\, Jane";PARTSTAT=ACCEPTED:mailto:jane@example.com
DESCRIPTION:Agenda: blockers\, plans\; notes.\nSecond line
END:VEVENT
```

It looks like `KEY:VALUE` lines. It is not, quite. RFC 5545 stacks four small grammars on top of
each other, and a parser that skips one of them works on your test file and fails on a stranger's.

```
 bytes -> physical lines -> logical lines -> content lines -> component tree
          (CRLF/LF/CR)      (unfolding)      (name;params:value)   (BEGIN/END)
```

### 1. Physical lines

Files in the wild end lines with CRLF (the standard), LF (most hand-edited files) or a lone CR
(very old exports). Split with a regex that keeps the line ending:

```python
_LINE_RE = re.compile(r"[^\r\n]*(?:\r\n|\n|\r)|[^\r\n]+")
```

**Do not use `str.splitlines()`.** It also splits on form feed, vertical tab, U+0085, U+2028 and
U+2029. All of those are legal characters inside a value, and an event title containing U+2028
would be cut in half. Keeping the ending matters too: Module 05 writes new lines with the file's
own ending.

### 2. Unfolding

Lines are limited to 75 octets, so a longer one is *folded*: a CRLF followed by a space or tab.
Unfold by removing the line break and **exactly one** whitespace character:

```python
parts = [body]
while next line starts with " " or "\t":
    parts.append(next_line[1:])      # ONE character, not lstrip()
```

`lstrip()` would eat real leading spaces of the continued text. The folding position is arbitrary
(it may fall inside a word, or inside a UTF-8 character's *bytes* in sloppy exporters - we work
on decoded text, so characters are intact).

### 3. Content lines

`NAME;PARAM=value;PARAM="quoted, with ; and :":VALUE`. The first colon *outside quotes* ends
the name and parameters. Parameter values may be quoted and may be comma lists. That is why a
`str.split(":")` is wrong for `ATTENDEE;CN="Doe; Jane: Jr.":mailto:j@x`. See
`parse_content_line` in [`minical/parse.py`](../minical/parse.py).

TEXT values have their own escaping: `\n` newline, `\,` comma, `\;` semicolon, `\\` backslash.
Escape on write, unescape on read, and do it **after** you have split lists on commas
(`CATEGORIES:a\,b,c` is two items).

### 4. The tree - and why it keeps line numbers

`BEGIN:X` pushes, `END:X` pops, and a mismatch is an error with a line number. Every `Component`
and `Prop` records `first` and `last`, its physical line range. That looks like bookkeeping for
error messages. The real reason is Module 05: to edit one event without disturbing the rest of
the file we must know exactly which physical lines belong to it.

### What to do with damage

Two kinds, treated differently:

- **Structural** damage (never closed, `END` mismatch, no `VCALENDAR`) means we cannot trust any
  of the tree: raise `ICalError` with the line number.
- **A single malformed line** (no colon, unterminated quote) is recorded in `Parsed.warnings` and
  skipped. The agent will see it. It is never dropped silently.

## Run It

```bash
python 01-icalendar-grammar/main.py
```

It asserts, against `data/google.ics`: the escaped description decodes to
`Daily sync.\nAgenda: blockers, plans; notes.`, a folded title spans more than one physical line,
a quoted `CN` containing `;` and `:` survives, and the hostile file's garbage line is reported
with its line number.

## Takeaways

- Physical line, logical line, content line, component: four layers, each trivially small.
- Keep spans. They cost nothing and the writer will need them.
- Report damage; never swallow it.
