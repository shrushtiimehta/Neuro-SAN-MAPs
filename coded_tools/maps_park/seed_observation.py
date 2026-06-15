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
SeedObservation: fetch a park's initial (step 0) observation from the MAPs
server WITHOUT stepping, and write it to the latest-observation cache.

The runner calls this once at startup so the very first turn's ParkStatus
returns real park state instead of "No observation stored yet, call wait()".
That removes the throwaway first-turn wait — turn 1 becomes a real build.

Talks to the same maps_mcp_server as the action tools, but calls the
``world_observe`` tool (no step) instead of ``world_server`` (steps).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.maps_park.latest_observation import LatestObservation

_MCP_URL = os.environ.get("MAPS_MCP_URL", "http://localhost:8765/mcp")
_OBSERVE_TOOL = "world_observe"


class SeedObservation(CodedTool):
    """Seed the obs cache with the env's current (unstepped) observation."""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        """
        :param args: dict with optional key
            - ``park`` (int, default 0): the park slot to seed.
        :param sly_data: passed through to LatestObservation.
        :return: dict ``{"status": "ok", "park", "step"}`` on success, or
            ``{"status": "error", "error": <msg>}``.
        """
        park = int(args.get("park", 0))

        envelope = await self._fetch_observation(park)
        if "error" in envelope:
            return {"status": "error", "error": envelope["error"]}

        write_result = await LatestObservation().async_invoke(
            {"mode": "write", "park": park, "observation": envelope}, sly_data
        )
        if isinstance(write_result, dict) and write_result.get("error"):
            return {"status": "error", "error": write_result["error"]}

        return {"status": "ok", "park": park, "step": envelope.get("step")}

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        """Synchronous entry point for non-async callers (e.g. the runner)."""
        import asyncio
        return asyncio.run(self.async_invoke(args, sly_data))

    async def _fetch_observation(self, park: int) -> dict[str, Any]:
        """Call the MCP world_observe tool and return the observation envelope."""
        try:
            async with streamablehttp_client(_MCP_URL) as (read, write, _meta):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(
                        _OBSERVE_TOOL, arguments={"request": {"park": park}}
                    )
                    return self._unwrap(result)
        except Exception as exc:  # noqa: BLE001 — surface to caller
            return {"error": f"world_observe call failed: {exc}"}

    @staticmethod
    def _unwrap(result: Any) -> dict[str, Any]:
        """Extract the first JSON object from an MCP CallToolResult."""
        content = getattr(result, "content", None) or []
        for block in content:
            text = getattr(block, "text", None) or (block.get("text") if isinstance(block, dict) else None)
            if isinstance(text, str):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    return {"error": f"non-JSON MCP response: {text[:200]}"}
        return {"error": "empty MCP response"}
