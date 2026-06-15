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
"""TrimHistoryMiddleware: drop all messages from prior turns.

For long-running loop agents (one user message per "turn"), the langgraph
checkpointer accumulates the full message history across turns, which
inflates prompt size and cost over time. This middleware keeps only the
messages from the most recent HumanMessage onwards, so each new user turn
sees a clean chat history. The system message is unaffected (langgraph
keeps it on the side), the checklist middleware re-injects checklist state
from its own slice each turn, and the persistent_memory tool still works.

Anything the agent needs across turns must therefore live in:
  - the system prompt (static instructions),
  - the checklist (AgentChecklistMiddleware),
  - persistent memory (PersistentMemoryMiddleware) — read at episode start,
  - tool calls within the current turn (ParkStatus, read_file, etc.).
"""

from logging import getLogger
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


class TrimHistoryMiddleware(AgentMiddleware):
    """Trim everything before the latest HumanMessage.

    Within a single turn the latest HumanMessage is the anchor — all
    intra-turn AI / Tool messages come after it, so they are preserved.
    Across turns, prior-turn messages sit before the new HumanMessage and
    are dropped. The log line only fires when something is actually
    trimmed (i.e. the first model call of a new turn).
    """

    def __init__(self) -> None:
        super().__init__()
        self._logger = getLogger(__name__)

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        messages: List[BaseMessage] = list(request.messages or [])
        last_human_idx = self._find_last_human_index(messages)
        if last_human_idx is None or last_human_idx == 0:
            return await handler(request)

        trimmed = messages[last_human_idx:]
        self._logger.info(
            "TrimHistoryMiddleware: dropped %d prior-turn message(s), kept %d",
            last_human_idx,
            len(trimmed),
        )
        return await handler(request.override(messages=trimmed))

    @staticmethod
    def _find_last_human_index(messages: List[BaseMessage]) -> int | None:
        for idx in range(len(messages) - 1, -1, -1):
            if isinstance(messages[idx], HumanMessage):
                return idx
        return None
