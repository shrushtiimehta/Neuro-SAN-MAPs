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
"""TrimOutputMiddleware: suppress everything except the agent's final output text.

Applied to sub-agents (specialists, coordinators). When a model call produces
a *final* response (AIMessage with no tool_calls), the response content is
truncated to `max_chars` characters. Intermediate model calls that produce
tool_calls are passed through unchanged.

This ensures that the ToolMessage seen by the parent agent contains only the
essential output, preventing verbose elaboration from bloating the parent's
within-turn context.

Usage in HOCON:
    middleware = [
        {"class": "middleware.trim_output_middleware.TrimOutputMiddleware",
         "args": {"max_chars": 400}}
    ]
"""

from __future__ import annotations

from logging import getLogger
from typing import Awaitable
from typing import Callable
from typing import override

from langchain.agents.middleware.types import AgentMiddleware
from langchain.agents.middleware.types import ContextT
from langchain.agents.middleware.types import ModelRequest
from langchain.agents.middleware.types import ModelResponse
from langchain.agents.middleware.types import ResponseT
from langchain_core.messages import AIMessage


class TrimOutputMiddleware(AgentMiddleware):
    """Truncate the agent's final text response to ``max_chars`` characters.

    Only the final AIMessage (no tool_calls) is affected. All intermediate
    model calls (those that produce tool_calls) pass through untouched, so
    the agent's internal reasoning and tool use work normally.

    The truncated text is what flows back to the parent as the ToolMessage
    content, keeping the parent's context lean.
    """

    def __init__(self, max_chars: int = 400) -> None:
        super().__init__()
        self._max_chars = max_chars
        self._logger = getLogger(__name__)

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        response = await handler(request)

        new_result = []
        modified = False
        for msg in response.result:
            if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
                raw = msg.content if isinstance(msg.content, str) else ""
                if len(raw) > self._max_chars:
                    trimmed = raw[: self._max_chars]
                    self._logger.debug(
                        "TrimOutputMiddleware: trimmed final response %d → %d chars",
                        len(raw),
                        self._max_chars,
                    )
                    msg = AIMessage(content=trimmed, id=msg.id)
                    modified = True
            new_result.append(msg)

        if not modified:
            return response
        return ModelResponse(result=new_result, structured_response=response.structured_response)
