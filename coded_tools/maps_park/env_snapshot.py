# Copyright © 2025-2026 Cognizant Technology Solutions Corp, www.cognizant.com.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# END COPYRIGHT
"""
Runner-side wrapper around the MAPs MCP snapshot/restore tools.

These are NOT agent-facing — only `apps/maps_park/runner.py` calls them, to
roll the MAPs env back to a pre-step state when the post-validator detects
the agent committed a bad action. The MCP tools `snapshot_state` and
`restore_state` are exposed by maps_mcp_server.py on the branch
`maps-park-mcp-snapshot-tools`.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client


_DEFAULT_MCP_URL = os.environ.get("MAPS_MCP_URL", "http://localhost:8765/mcp")


def _unwrap(result: Any) -> dict:
    """MCP returns a CallToolResult; pull the first JSON text block out."""
    content = getattr(result, "content", None) or []
    for block in content:
        text = getattr(block, "text", None) or (block.get("text") if isinstance(block, dict) else None)
        if isinstance(text, str):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
    return {"error": "could not parse MCP response", "raw": str(result)}


async def _call_tool(tool_name: str, arguments: dict) -> dict:
    async with streamablehttp_client(_DEFAULT_MCP_URL) as (read, write, _meta):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=arguments)
            return _unwrap(result)


def take_snapshot(park: int = 0, path: str | None = None) -> dict:
    """Ask the MAPs MCP server to pickle the current state.

    Returns the server's envelope, including {"saved": True, "path": "...",
    "step": N, "episode": E}. On failure returns {"error": "..."}.
    """
    args: dict = {"request": {"park": int(park)}}
    if path:
        args["request"]["path"] = path
    return asyncio.run(_call_tool("snapshot_state", args))


def restore(park: int, snapshot_path: str) -> dict:
    """Ask the MAPs MCP server to load_state from the given pickle.

    Returns the server's envelope, including {"loaded": True, "step": N,
    "episode": E}. On failure returns {"error": "..."}.
    """
    args = {"request": {"park": int(park), "path": snapshot_path}}
    return asyncio.run(_call_tool("restore_state", args))
