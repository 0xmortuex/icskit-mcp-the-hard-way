# Break It: The MCP Wrapper

## Challenge 1: Print to stdout

Add `print("loading", path)` inside `_load_all`, then run `python 06-the-mcp-wrapper/main.py`.
What does the client do? Change it to `print(..., file=sys.stderr)`.

**Hint:** stdout carries JSON-RPC. A stray line is not JSON; depending on the SDK version the
client skips it, errors or desynchronises.

## Challenge 2: Hide the error

Remove the `tool` decorator's `try/except` and call `agenda` with `tz="CEST"`. What text does the
client's `res.content[0].text` contain now?

**Hint:** `Error executing tool agenda`. Nothing tells the agent what to fix, so it retries the same
call.

## Challenge 3: Swallow too much

Change the `except` to `except Exception`. Now add `1 / 0` to `find_conflicts`. What does the agent
see? What does the *developer* see?

**Hint:** The agent gets a calm message about a "division by zero" it cannot act on, and you lose
the traceback. Only catch what an agent can do something about.

## Challenge 4: Escape the sandbox

Call `add_event` with `calendar="../../etc/passwd"` and with an absolute path. Then remove the
`is_relative_to` check in `_target`. What changes?

**Hint:** Without the check, the tool will happily open any file the server's user can read and,
with `in_place`, write it.

## Challenge 5: No tz

Change `tz: str = "UTC"` on `agenda` so that it has no default and read the generated schema with
`list_tools`. What happens to an agent that forgets it? Which is friendlier: a required argument,
or a default that is printed in the answer?

**Hint:** There is no single right answer. The finished icskit-mcp defaults to UTC *and prints the
zone in every line*, so a wrong guess is visible rather than silent.
