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
"""Inject the current planner-authored episode phase into each model call.

Phase timing is execution context, not park state. This middleware reads the
completed simulator step from ``latest_observations.json``, selects the phase
for the action turn being planned plus the immediately following phase from
``episode_checklist.md``, and prefixes both to the latest human message. The
files themselves remain authoritative; nothing is copied into
``status_full.json`` or a specialist status projection.
"""

from __future__ import annotations

import json
import os
from logging import getLogger
from pathlib import Path
from typing import Awaitable
from typing import Callable
from typing import List
from typing import override

from langchain.agents.middleware.types import AgentMiddleware
from langchain.agents.middleware.types import ContextT
from langchain.agents.middleware.types import ModelRequest
from langchain.agents.middleware.types import ModelResponse
from langchain.agents.middleware.types import ResponseT
from langchain_core.messages import BaseMessage
from langchain_core.messages import HumanMessage
from langchain_core.messages.base import merge_content

from coded_tools.episode_phases import phases_for_turn

_PHASE_BEGIN = "<RUNTIME_EPISODE_PHASE>"
_PHASE_END = "</RUNTIME_EPISODE_PHASE>"


class EpisodePhaseMiddleware(AgentMiddleware):
    """Prefix the current episode phase to every LLM call in an agent turn."""

    def __init__(
        self,
        state_dir: str | None = None,
        latest_observation_path: str | None = None,
        park: int | str = 0,
    ) -> None:
        super().__init__()
        active_state_dir = state_dir or os.environ.get("MAPS_STATE_DIR", "state")
        self._checklist_path = Path(active_state_dir) / "episode_checklist.md"
        self._latest_observation_path = Path(
            latest_observation_path
            or os.environ.get(
                "MAPS_LATEST_OBS_PATH",
                str(Path(active_state_dir) / "latest_observations.json"),
            )
        )
        self._park_key = f"park_{int(park)}"
        self._logger = getLogger(__name__)

    def _phase_context(self) -> tuple[int, int, str, str | None] | None:
        try:
            checklist = self._load_checklist()
            observations = json.loads(self._latest_observation_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as err:
            self._logger.warning("EpisodePhaseMiddleware: phase unavailable: %s", err)
            return None

        window = observations.get(self._park_key) if isinstance(observations, dict) else None
        if isinstance(window, list):
            envelope = window[-1] if window else None
        elif isinstance(window, dict):
            envelope = window
        else:
            envelope = None
        if not isinstance(envelope, dict):
            return None

        observation = envelope.get("observation")
        if not isinstance(observation, dict):
            observation = envelope.get("new_park_observation")
        if not isinstance(observation, dict):
            observation = {}

        # The envelope step is maintained by GameManager.step_count and is the
        # authoritative count of completed actions. The nested observation is
        # only a fallback for the episode-reset envelope.
        step = envelope.get("step")
        if step is None:
            step = observation.get("step")
        try:
            current_step = int(step)
        except (TypeError, ValueError):
            return None
        # The cached observation is the state AFTER `current_step` completed
        # actions. The player is choosing the next action, so checklist turn N
        # corresponds to observation step N-1.
        action_turn = current_step + 1
        phase_pair = phases_for_turn(checklist, action_turn)
        if phase_pair is None:
            self._logger.warning(
                "EpisodePhaseMiddleware: no checklist phase covers action turn %d",
                action_turn,
            )
            return None
        current_phase, next_phase = phase_pair
        return (
            current_step,
            action_turn,
            current_phase.text,
            next_phase.text if next_phase is not None else None,
        )

    def _load_checklist(self) -> str:
        """Load the planner checklist from this arm's configured storage."""
        return self._checklist_path.read_text(encoding="utf-8")

    def _current_phase(self) -> str | None:
        """Return only the phase line for callers that do not need the step."""
        context = self._phase_context()
        return context[2] if context is not None else None

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        phase_context = self._phase_context()
        if phase_context is None:
            return await handler(request)
        current_step, action_turn, phase, next_phase = phase_context

        messages: List[BaseMessage] = list(request.messages or [])
        human_index = self._last_human_index(messages)
        if human_index is None:
            return await handler(request)

        human = messages[human_index]
        if _PHASE_BEGIN in str(human.content):
            return await handler(request)

        runtime_context = (
            f"{_PHASE_BEGIN}\n"
            f"Completed simulator step: {current_step}\n"
            f"Action turn being planned: {action_turn}\n"
            "Current phase — execute the parts relevant to your role:\n"
            f"{phase}\n"
            "Next phase you can prepare for:\n"
            f"{next_phase or 'None — this is the final phase.'}\n"
            f"{_PHASE_END}\n\n"
        )
        messages[human_index] = human.model_copy(update={"content": merge_content(runtime_context, human.content)})
        return await handler(request.override(messages=messages))

    @staticmethod
    def _last_human_index(messages: List[BaseMessage]) -> int | None:
        for index in range(len(messages) - 1, -1, -1):
            if isinstance(messages[index], HumanMessage):
                return index
        return None
