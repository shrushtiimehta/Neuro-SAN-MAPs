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
"""StaticPromptCachingMiddleware: cache only system message and tools.

Extends AnthropicPromptCachingMiddleware but skips the per-call
model_settings cache_control breakpoint. That breakpoint tags the last
message in the sequence on every LLM call, creating a new cache entry each
time that is never reused in the next turn — pure write waste.

System message and tools are static across all calls within the hour TTL,
so they always hit after the first write. Message-level content is dynamic
and not worth caching.
"""

from __future__ import annotations

from typing import Any

from langchain.agents.middleware.types import ModelRequest
from langchain_anthropic.middleware.prompt_caching import (
    AnthropicPromptCachingMiddleware,
    _tag_system_message,
    _tag_tools,
)


class StaticPromptCachingMiddleware(AnthropicPromptCachingMiddleware):
    """Cache system message and tools only — skip message-prefix cache writes."""

    def _apply_caching(self, request: ModelRequest) -> ModelRequest:
        overrides: dict[str, Any] = {}
        cache_control = self._cache_control

        system_message = _tag_system_message(request.system_message, cache_control)
        if system_message is not request.system_message:
            overrides["system_message"] = system_message

        tools = _tag_tools(request.tools, cache_control)
        if tools is not request.tools:
            overrides["tools"] = tools

        if not overrides:
            return request
        return request.override(**overrides)
