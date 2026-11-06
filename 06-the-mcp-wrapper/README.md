# Module 06: The MCP Wrapper

## The Concept

Modules 01-05 are a library. An MCP server is a thin layer that makes the library usable by an
agent that cannot read your code, cannot see your screen, and only ever sees the text a tool
returns. This module is that layer: [`minical/server.py`](../minical/server.py), about 220 lines.

MCP is JSON-RPC over a pipe. For a local server the client (Claude Desktop, Claude Code) starts
your program as a subprocess and talks to its stdin/stdout:

```
initialize   ->  server name, capabilities, instructions
tools/list   ->  [{name, description, inputSchema}, ...]
tools/call   ->  {content: [{text: ...}], isError: bool}
```

With `MCPServer` from the `mcp` SDK, a tool is a Python function: the name is the tool name, the
type hints become the JSON schema, the docstring becomes the description the agent reads.

```python
@tool
def find_free_time(start: str, end: str, duration_minutes: int, tz: str = "UTC",
                   working_hours: str = "09:00-17:00", buffer_minutes: int = 0) -> str:
    """Free blocks of at least duration_minutes inside working_hours (local wall clock in tz,
    Monday to Friday), across ALL calendars. ..."""
```

**stdout belongs to the protocol.** Never `print()` in a stdio server: your text lands in the
JSON-RPC stream. Log to stderr.

## Tool design: few tools, strong descriptions

Six tools cover the job: an overview, three questions (`agenda`, `find_free_time`,
`find_conflicts`) and two writes. The description is the agent's only documentation, so it states
what the tool does, **every default** (working hours, Mon-Fri, what is ignored), the argument
format, and what the safety behaviour is:

> SAFETY: the original is not modified unless in_place=true; by default an edited copy is
> written as '<file>.new'. dry_run=true writes nothing and shows the patch.

Choices worth copying:

1. **`tz` on every tool, printed in every answer.** The agent cannot know which zone you mean
   unless it asks, and a time without a zone is a guess. Each result starts with `(zone
   Europe/Istanbul)` and each time carries its abbreviation (`+03`, `CET`, `CEST`).
2. **Text out, not JSON.** The consumer is a language model reading prose. Group by day, one
   line per event, UID at the end so it can be passed to the next tool.
3. **Reads before writes, and `calendar_overview` first.** It lists files and *problems*, so the
   agent knows when something was skipped.
4. **Warnings travel with results.** When a file had a broken event, `agenda` appends `Warnings:`
   so a missing meeting is never a silent absence.

## Errors are instructions (and mcp 2.x hides everything else)

In `mcp>=2`, if a tool raises an ordinary exception the client receives only
`Error executing tool X`. The message is hidden. Only a `ToolError`'s message is forwarded. So
the `@tool` decorator catches the failures an agent can act on and re-raises them as `ToolError`:

```python
try:
    return fn(*a, **kw)
except (ICalError, OSError, ValueError) as e:
    raise ToolError(str(e)) from e
```

and everything else, an actual bug, stays hidden and crashes loudly in the server's stderr. Not
swallowing the unexpected is as important as surfacing the expected. Compare:

| Bad | Good |
|-----|------|
| `Error executing tool agenda` | `unknown time zone 'CEST'; use an IANA name like 'Europe/Istanbul' or 'UTC'` |
| `FileNotFoundError` | `'x.ics' not found; call calendar_overview for the file names` |

## The sandbox

`--dir` is required and everything is resolved relative to it, with `Path.resolve()` and
`is_relative_to` so `..`, absolute paths and symlinks cannot escape. The server never opens a
socket and needs no credentials; the only thing it can reach is the folder you named. That
belongs in the README of the finished project too, as a **security** section.

## Testing over the real wire

`main.py` launches the server exactly as Claude would:

```python
params = StdioServerParameters(command=sys.executable, args=["-m", "minical.server", "--dir", tmp])
async with stdio_client(params) as (read, write), ClientSession(read, write) as s:
    await s.initialize()
    tools = await s.list_tools()
    result = await s.call_tool("agenda", {...})
```

Unit tests of the functions would not catch a schema that does not serialise, a stray `print`, or
an exception whose message never reaches the client. This test does. It checks the tool list, a
DST-correct agenda, an exact free-time answer, that errors arrive readable, and that a write
leaves the original file's SHA-256 unchanged.

## Run It

```bash
python 06-the-mcp-wrapper/main.py
# or run the server by hand and point a client at it:
python -m minical.server --dir data
```

To use it with Claude Code: `claude mcp add minical -- python -m minical.server --dir /path/to/calendars`
(from the repository root, with the requirements installed).

## Takeaways

- A tool is a function plus a description the agent will actually read.
- Put the defaults and the safety behaviour in the description.
- Convert expected failures to `ToolError` with an actionable message; let bugs crash.
- Test through a real stdio session, not just function calls.
