"""Module 06 check: launch the server as a subprocess and talk MCP to it over stdio.

Run:  python 06-the-mcp-wrapper/main.py
This is exactly what Claude does: start a process, send JSON-RPC down stdin, read stdout.
"""

import asyncio
import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from mcp import ClientSession  # noqa: E402
from mcp.client.stdio import StdioServerParameters, stdio_client  # noqa: E402

EXPECTED = {"calendar_overview", "agenda", "find_free_time", "find_conflicts", "add_event", "delete_event"}


async def main(cal_dir: str) -> None:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONPATH": ROOT}
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "minical.server", "--dir", cal_dir], env=env, cwd=ROOT)
    async with stdio_client(params) as (read, write), ClientSession(read, write) as s:
        init = await s.initialize()
        assert init.server_info.name == "minical"
        tools = {t.name: t for t in (await s.list_tools()).tools}
        assert set(tools) == EXPECTED, set(tools) ^ EXPECTED
        assert "never" in tools["add_event"].description or "not modified" in tools["add_event"].description
        print("1. tools:", sorted(tools))

        res = await s.call_tool("agenda", {"start": "2026-03-27", "end": "2026-03-30", "tz": "Europe/Berlin"})
        text = res.content[0].text
        assert not res.is_error and "zone Europe/Berlin" in text
        assert "2026-03-29 01:30 CET -> 04:30" in text, "the night shift over the clock change ends at 04:30 CEST"
        print("2. agenda over the wire ok")

        res = await s.call_tool("find_free_time", {
            "start": "2026-03-09", "end": "2026-03-09", "duration_minutes": 60, "tz": "Europe/Istanbul"})
        assert not res.is_error and "2026-03-09 09:00 +03 -> 14:30" in res.content[0].text, res.content[0].text
        print("3. find_free_time ok")

        # errors arrive as readable messages, not as 'Error executing tool'
        res = await s.call_tool("agenda", {"start": "2026-03-01", "end": "2026-03-02", "tz": "CEST"})
        assert res.is_error and "IANA" in res.content[0].text
        res = await s.call_tool("add_event", {"calendar": "../x.ics", "summary": "x",
                                              "start": "2026-03-01T10:00", "duration_minutes": 30})
        assert res.is_error and "outside the allowed directory" in res.content[0].text, res.content[0].text
        print("4. errors are instructions ok")

        before = hashlib.sha256((Path(cal_dir) / "google.ics").read_bytes()).hexdigest()
        res = await s.call_tool("add_event", {"calendar": "google.ics", "summary": "Over the wire",
                                              "start": "2026-03-10T15:00", "duration_minutes": 30, "tz": "Europe/Istanbul"})
        assert not res.is_error and "google.ics.new" in res.content[0].text
        assert hashlib.sha256((Path(cal_dir) / "google.ics").read_bytes()).hexdigest() == before
        print("5. write tool leaves the original alone ok")


with tempfile.TemporaryDirectory() as tmp:
    for name in ("google.ics", "apple.ics", "outlook.ics"):
        shutil.copy(os.path.join(ROOT, "data", name), tmp)
    asyncio.run(main(tmp))
print("MODULE 06 OK")
