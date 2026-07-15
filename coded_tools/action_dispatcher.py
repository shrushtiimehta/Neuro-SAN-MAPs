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

from coded_tools.latest_observation import LatestObservation
from coded_tools.maps_action_base import MapsActionBase
from coded_tools.maps_modify import MapsModify
from coded_tools.maps_move import MapsMove
from coded_tools.maps_place import MapsPlace
from coded_tools.maps_remove import MapsRemove
from coded_tools.maps_set_research import MapsSetResearch
from coded_tools.maps_survey_guests import MapsSurveyGuests
from coded_tools.maps_wait import MapsWait


class ActionDispatcher(CodedTool):
    """Map an action name + args dict to the matching typed Maps* tool."""

    # Only the actions available in easy/medium difficulty (MAPs
    # ACTIONS_BY_DIFFICULTY). The hard-only terraform actions (add_path,
    # remove_path, add_water, remove_water) are intentionally not exposed here.
    ACTION_TABLE: ClassVar[dict[str, type[MapsActionBase]]] = {
        "wait": MapsWait,
        "place": MapsPlace,
        "move": MapsMove,
        "remove": MapsRemove,
        "modify": MapsModify,
        "set_research": MapsSetResearch,
        "survey_guests": MapsSurveyGuests,
    }

    async def async_invoke(
        self, args: dict[str, Any], sly_data: dict[str, Any]
    ) -> dict[str, Any] | str:
        park = args.get("park", 0)

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

        # Normalize the special episode_complete envelope MAPs returns when a
        # horizon is reached. It uses a different shape (final_step/total_reward
        # /new_park_observation, no top-level done/step/observation), which
        # otherwise causes ParkStatus to report done=false and skip the
        # episode_closer flow. We graft the standard fields onto it so
        # parkstatus_reader.preflight triggers end-of-episode bookkeeping.
        if isinstance(response, dict) and response.get("episode_complete"):
            new_obs = response.get("new_park_observation") or {}
            response = {
                **response,
                "episode": response.get("completed_episode"),
                "step": response.get("final_step"),
                "horizon": new_obs.get("horizon"),
                "cumulative_reward": response.get("total_reward"),
                "done": True,
                "observation": new_obs,
            }

        # Persist the full envelope verbatim. We do this here — not in the
        # coordinator's instructions — because routing the write through
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
