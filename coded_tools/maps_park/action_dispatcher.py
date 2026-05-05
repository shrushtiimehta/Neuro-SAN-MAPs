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
Deterministic action-name → typed-MAPs-tool dispatcher.

Replaces the former ``action_executor`` LLM agent. Routing is a constant
dict lookup — no LLM call needed. ``strategy_coordinator`` picks an action,
calls this tool, gets the post-step observation envelope back.
"""

from __future__ import annotations

from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.maps_park.latest_observation import LatestObservation
from coded_tools.maps_park.maps_action_base import MapsActionBase
from coded_tools.maps_park.maps_add_path import MapsAddPath
from coded_tools.maps_park.maps_add_water import MapsAddWater
from coded_tools.maps_park.maps_modify import MapsModify
from coded_tools.maps_park.maps_move import MapsMove
from coded_tools.maps_park.maps_place import MapsPlace
from coded_tools.maps_park.maps_remove import MapsRemove
from coded_tools.maps_park.maps_remove_path import MapsRemovePath
from coded_tools.maps_park.maps_remove_water import MapsRemoveWater
from coded_tools.maps_park.maps_set_research import MapsSetResearch
from coded_tools.maps_park.maps_survey_guests import MapsSurveyGuests
from coded_tools.maps_park.maps_wait import MapsWait


class ActionDispatcher(CodedTool):
    """Map an action name + args dict to the matching typed Maps* tool."""

    ACTION_TABLE: ClassVar[dict[str, type[MapsActionBase]]] = {
        "wait": MapsWait,
        "place": MapsPlace,
        "move": MapsMove,
        "remove": MapsRemove,
        "modify": MapsModify,
        "set_research": MapsSetResearch,
        "survey_guests": MapsSurveyGuests,
        "add_path": MapsAddPath,
        "remove_path": MapsRemovePath,
        "add_water": MapsAddWater,
        "remove_water": MapsRemoveWater,
    }

    async def async_invoke(
        self, args: dict[str, Any], sly_data: dict[str, Any]
    ) -> dict[str, Any] | str:
        park = args.get("park")
        if park is None:
            return {"error": "park is required (slot 0..4)"}

        action = args.get("action")
        if not isinstance(action, str) or not action:
            return {"error": f"action is required and must be a non-empty string, got {action!r}"}

        tool_cls = self.ACTION_TABLE.get(action)
        if tool_cls is None:
            return {
                "error": f"unknown action {action!r}",
                "valid_actions": sorted(self.ACTION_TABLE.keys()),
            }

        action_args = args.get("args") or {}
        if not isinstance(action_args, dict):
            return {
                "error": f"args must be an object/dict, got {type(action_args).__name__}",
            }

        merged: dict[str, Any] = {"park": park, **action_args}
        tool = tool_cls()
        response = await tool.async_invoke(merged, sly_data)

        # Persist the full envelope verbatim. We do this here — not in
        # park_director's instructions — because routing the write through
        # the LLM was dropping the nested 'observation' payload (LLM
        # paraphrasing). Doing it in Python guarantees nothing is stripped.
        if isinstance(response, dict) and not response.get("error"):
            try:
                await LatestObservation().async_invoke(
                    {"mode": "write", "park": park, "observation": response},
                    sly_data,
                )
            except Exception:  # noqa: BLE001 — never let a cache-write failure mask the action result
                pass
        return response
