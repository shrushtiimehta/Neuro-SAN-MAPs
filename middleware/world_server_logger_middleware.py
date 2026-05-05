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
Captures every world_server (MAPs MCP) tool result and appends a row to a
JSONL file. Source-of-truth telemetry: numbers come straight from the
simulator, not the LLM's narration.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import time
from logging import Logger
from typing import Any
from typing import Awaitable
from typing import Callable
from typing import ClassVar
from typing import override

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage
from langchain_core.messages.tool import ToolCall
from langgraph.prebuilt.tool_node import ToolCallRequest
from langgraph.types import Command


class WorldServerLoggerMiddleware(AgentMiddleware):
    """Append one JSONL row per MAPs world-step tool call.

    Supports both the legacy single-tool ``world_server`` shape (the agent
    calls one MCP tool with a JSON-string payload) and the new typed
    ``maps_*`` coded_tools (one per MAPs action with structured args).
    """

    DEFAULT_LOG_PATH: ClassVar[str] = "logs/maps_park/run.jsonl"
    DEFAULT_TOOL_NAME: ClassVar[str] = "world_server"

    def __init__(
        self,
        log_path: str = DEFAULT_LOG_PATH,
        tool_name: str | None = None,
        tool_names: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.log_path: str = log_path
        if tool_names:
            self.tool_names: list[str] = list(tool_names)
        elif tool_name:
            self.tool_names = [tool_name]
        else:
            self.tool_names = [self.DEFAULT_TOOL_NAME]
        self.logger: Logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._ensure_log_dir()

    def _ensure_log_dir(self) -> None:
        directory: str = os.path.dirname(self.log_path)
        if directory:
            os.makedirs(directory, exist_ok=True)

    @override
    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        tool_call: ToolCall = request.tool_call
        name: str = tool_call.get("name", "")
        args: dict[str, Any] = tool_call.get("args", {})

        result: ToolMessage | Command[Any] = await handler(request)

        if name in self.tool_names and isinstance(result, ToolMessage):
            flat_args: dict[str, Any] = self._unwrap_args(args)
            park: str = str(flat_args.get("park", "0"))
            envelope: dict[str, Any] = await self._read_latest_observation(park)
            if not envelope:
                envelope = self._parse_content(result.content)
            self._record(name, args, envelope)

        return result

    async def _read_latest_observation(self, park: str) -> dict[str, Any]:
        """Read the freshest observation envelope from LatestObservation.

        ActionDispatcher writes to LatestObservation before returning, so
        the window always holds the just-completed step. Reading here gives
        us a clean Python dict without any serialisation wrapper to strip.
        """
        try:
            from coded_tools.maps_park.latest_observation import LatestObservation  # noqa: PLC0415
            window = await LatestObservation().async_invoke(
                {"mode": "read", "park": park}, {}
            )
            if isinstance(window, dict) and window.get("window_size", 0) > 0:
                return window.get("latest") or {}
        except Exception as exc:  # noqa: BLE001
            self.logger.debug("LatestObservation read failed: %s", exc)
        return {}

    def _record(self, tool_name: str, args: dict[str, Any], envelope: dict[str, Any]) -> None:
        flat_args: dict[str, Any] = self._unwrap_args(args)
        observation: dict[str, Any] = envelope.get("observation") or {}
        action_label: Any = flat_args.get("action") or self._synthesize_action(tool_name, flat_args)
        row: dict[str, Any] = {
            "wall_time": time.time(),
            "tool": tool_name,
            "park": flat_args.get("park"),
            "action": action_label,
            "episode": envelope.get("episode"),
            "step": envelope.get("step", observation.get("step")),
            "horizon": envelope.get("horizon"),
            "cash": observation.get("money", observation.get("cash")),
            "park_value": observation.get("value"),
            "park_rating": observation.get("park_rating"),
            "research_speed": observation.get("research_speed"),
            "cumulative_reward": envelope.get("cumulative_reward"),
            "reward": envelope.get("reward"),
            "done": envelope.get("done"),
            "error": envelope.get("error"),
            "num_rides": self._dict_get(observation.get("rides"), "total_rides"),
            "num_shops": self._dict_get(observation.get("shops"), "total_shops"),
            "num_staff": self._sum_staff(observation.get("staff")),
            "min_uptime": self._dict_get(observation.get("rides"), "min_uptime"),
            "min_cleanliness": observation.get("min_cleanliness"),
            "shop_revenue": self._dict_get(observation.get("shops"), "total_revenue_generated"),
            "ride_op_cost": self._dict_get(observation.get("rides"), "total_operating_cost"),
        }
        if all(row.get(k) is None for k in ("step", "cash", "cumulative_reward")):
            row["_raw_args"] = args
            row["_envelope_preview"] = repr(envelope)[:500]
        self._append(row)

    @staticmethod
    def _synthesize_action(tool_name: str, flat_args: dict[str, Any]) -> str | None:
        """Build a human-readable action label from a typed maps_* call.

        For the legacy single-tool path, the LLM already supplies an
        ``action`` string. For the typed coded_tools we reconstruct one
        like ``place(x=8, y=7, type='ride', ...)`` for log readability.
        """
        if not tool_name.startswith("maps_"):
            return None
        action_name: str = tool_name[len("maps_"):]
        kv_parts: list[str] = []
        for key, value in flat_args.items():
            if key == "park":
                continue
            kv_parts.append(f"{key}={value!r}")
        return f"{action_name}({', '.join(kv_parts)})"

    @staticmethod
    def _unwrap_args(args: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(args, dict):
            return {}
        if "park" in args or "action" in args:
            return args
        for nest_key in ("user_message", "input", "request", "payload"):
            inner: Any = args.get(nest_key)
            if isinstance(inner, dict):
                text: Any = inner.get("text")
                if isinstance(text, str):
                    try:
                        parsed_text: Any = json.loads(text)
                        if isinstance(parsed_text, dict):
                            return parsed_text
                    except json.JSONDecodeError:
                        pass
                if "park" in inner or "action" in inner:
                    return inner
            if isinstance(inner, str):
                try:
                    parsed: Any = json.loads(inner)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    continue
        return args

    def _parse_content(self, raw_content: Any) -> dict[str, Any]:
        if isinstance(raw_content, dict):
            return raw_content
        if isinstance(raw_content, list):
            for block in raw_content:
                text: Any = None
                if isinstance(block, dict):
                    text = block.get("text")
                elif hasattr(block, "text"):
                    text = getattr(block, "text", None)
                if isinstance(text, str):
                    parsed: dict[str, Any] = self._try_json(text)
                    if parsed:
                        return parsed
            return {}
        if isinstance(raw_content, str):
            return self._try_json(raw_content)
        return {}

    @staticmethod
    def _strip_content_wrapper(text: str) -> str:
        """Strip ToolMessage repr wrapper: content="<dict>" → <dict>.

        When neuro-san serialises a coded-tool dict result into a ToolMessage,
        the `.content` attribute sometimes arrives as the Python repr of the
        whole message rather than just the payload, e.g.:
            content="{'park_index': 0, 'step': 1, ...}"
        Stripping the wrapper exposes the inner Python-repr dict so that
        ast.literal_eval can parse it correctly.
        """
        for prefix, suffix in (('content="', '"'), ("content='", "'")):
            if text.startswith(prefix) and text.endswith(suffix) and len(text) > len(prefix) + len(suffix):
                inner = text[len(prefix):-len(suffix)]
                # Unescape any escaped quotes that were part of the wrapper encoding
                inner = inner.replace(f"\\{suffix}", suffix)
                return inner
        return text

    @staticmethod
    def _try_json(text: str) -> dict[str, Any]:
        # Strip ToolMessage repr wrapper before attempting to parse
        text = WorldServerLoggerMiddleware._strip_content_wrapper(text)
        try:
            parsed: Any = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            pass
        try:
            parsed = ast.literal_eval(text)
            return parsed if isinstance(parsed, dict) else {}
        except (ValueError, SyntaxError):
            return {}

    @staticmethod
    def _dict_get(container: Any, key: str) -> Any:
        if isinstance(container, dict):
            return container.get(key)
        return None

    @staticmethod
    def _sum_staff(staff: Any) -> int | None:
        """Sum staff across roles and tiers.

        ``total_janitors``/``total_mechanics``/``total_specialists`` are each
        a length-4 list of tier counts ``[yellow, blue, green, red]``.
        We want the grand total of actual staff, so sum every element.
        """
        if not isinstance(staff, dict):
            return None
        total: int = 0
        seen: bool = False
        for key in ("total_janitors", "total_mechanics", "total_specialists"):
            value: Any = staff.get(key)
            if isinstance(value, list):
                for entry in value:
                    if isinstance(entry, int):
                        total += entry
                seen = True
            elif isinstance(value, int):
                total += value
                seen = True
        return total if seen else None

    @staticmethod
    def _safe_len(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return len(value)
        except TypeError:
            return None

    def _append(self, row: dict[str, Any]) -> None:
        try:
            with open(self.log_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(row) + "\n")
        except OSError as err:
            self.logger.warning("Failed to write run.jsonl row: %s", err)
