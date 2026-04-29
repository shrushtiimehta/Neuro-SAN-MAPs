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
Base class for typed MAPs action tools.

Each concrete subclass corresponds to one MAPs action (place, move,
set_research, ...). The base class
1. validates required args,
2. formats the MAPs DSL string the simulator expects,
3. forwards the call over MCP to the running maps_mcp_server,
4. returns the observation envelope as JSON.
"""

from __future__ import annotations

import json
import os
from typing import Any
from typing import ClassVar

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from neuro_san.interfaces.coded_tool import CodedTool


_DEFAULT_MCP_URL = os.environ.get("MAPS_MCP_URL", "http://localhost:8765/mcp")
_TOOL_NAME = "world_server"


class MapsActionBase(CodedTool):
    """Base class for typed MAPs action tools."""

    ACTION_NAME: ClassVar[str] = ""  # set by subclass
    DSL_PARAM_ORDER: ClassVar[tuple[str, ...]] = ()  # MAPs param order (for readability only)
    OPTIONAL_PARAMS: ClassVar[set[str]] = set()  # params that may be omitted

    # The HOCON tool schemas declare all numeric MAPs params as "string" so the
    # LLM doesn't trip over int/integer coercion. We coerce them back to int here
    # before building the DSL string. Any arg whose key appears in INT_PARAMS is
    # passed through int(...). Add new int param names here when new actions land.
    INT_PARAMS: ClassVar[set[str]] = {
        "park",
        "x",
        "y",
        "new_x",
        "new_y",
        "price",
        "order_quantity",
        "num_guests",
    }

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        if not self.ACTION_NAME:
            return {"error": f"{self.__class__.__name__} did not set ACTION_NAME"}

        park = args.get("park")
        if park is None:
            return {"error": "park is required (slot 0..4)"}
        try:
            park = self._coerce_int(park)
        except (TypeError, ValueError):
            return {"error": f"park must be an integer, got {park!r}"}

        action_str = self._format_dsl(args)
        payload = json.dumps({"park": park, "action": action_str})

        try:
            response = await self._call_mcp(payload)
        except Exception as err:  # noqa: BLE001 — surface MCP failures to the LLM
            return {"error": f"MCP call failed: {err}", "park": park, "action": action_str}
        return response

    def _format_dsl(self, args: dict[str, Any]) -> str:
        """Build the MAPs DSL string `name(k=v, k=v, ...)`.

        Only keys listed in DSL_PARAM_ORDER are emitted. We must NOT fall back
        to args.keys(), because the framework injects routing metadata
        (e.g. ``origin``) into args and the MAPs DSL parser rejects unknown
        kwargs as ``invalid syntax``. An empty DSL_PARAM_ORDER (e.g. for
        ``wait``) correctly produces a parameterless call.
        """
        kv_parts: list[str] = []
        order = self.DSL_PARAM_ORDER
        for key in order:
            if key == "park":
                continue
            if key not in args or args[key] is None:
                if key in self.OPTIONAL_PARAMS:
                    continue
                # Required-but-missing params still pass through as Python None;
                # let the simulator reject with a clear error.
                kv_parts.append(f"{key}=None")
                continue
            value = args[key]
            if key in self.INT_PARAMS:
                try:
                    value = self._coerce_int(value)
                except (TypeError, ValueError):
                    # Fall through and let _format_value emit the raw value;
                    # the simulator will reject with a clear parse error.
                    pass
            kv_parts.append(f"{key}={self._format_value(value)}")
        return f"{self.ACTION_NAME}({', '.join(kv_parts)})"

    def _coerce_int(self, value: Any) -> int:
        """Convert HOCON-string numeric params back to int.

        The HOCON tool schemas declare numeric params as "string" so the LLM
        doesn't fight over int/integer naming. Inputs may arrive as ``"7"``,
        ``7``, ``7.0``, etc. — normalize to int here.
        """
        if isinstance(value, bool):
            # bool is an int subclass in Python; reject it explicitly so
            # True/False can't masquerade as 1/0.
            raise TypeError(f"expected int, got bool: {value!r}")
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            if not value.is_integer():
                raise ValueError(f"expected int, got non-integer float: {value!r}")
            return int(value)
        if isinstance(value, str):
            return int(value.strip())
        raise TypeError(f"expected int-coercible value, got {type(value).__name__}: {value!r}")

    def _format_value(self, value: Any) -> str:
        if isinstance(value, bool):
            return "True" if value else "False"
        if isinstance(value, (int, float)):
            return str(value)
        if isinstance(value, list):
            return "[" + ", ".join(self._format_value(v) for v in value) + "]"
        if isinstance(value, str):
            escaped = value.replace("'", "\\'")
            return f"'{escaped}'"
        return repr(value)

    async def _call_mcp(self, payload: str) -> dict[str, Any]:
        async with streamablehttp_client(_DEFAULT_MCP_URL) as (read, write, _meta):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    _TOOL_NAME,
                    arguments={"user_message": {"text": payload}},
                )
                return self._unwrap_tool_result(result)

    def _unwrap_tool_result(self, result: Any) -> dict[str, Any]:
        """MCP returns CallToolResult with content blocks; extract first JSON text."""
        content = getattr(result, "content", None) or []
        for block in content:
            text = getattr(block, "text", None) or (block.get("text") if isinstance(block, dict) else None)
            if isinstance(text, str):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    return {"raw": text}
        return {"error": "empty MCP response"}
