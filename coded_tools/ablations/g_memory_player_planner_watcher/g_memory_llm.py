"""LLM callable used by upstream GMemory for extraction and reranking."""

from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI


# Upstream requires this callable signature rather than a policy-rich class.
# pylint: disable=too-few-public-methods
class GMemoryLLM:
    """Use the configured OpenAI-compatible Responses API without logging keys."""

    def __init__(self) -> None:
        load_dotenv()
        self.model = os.environ.get("MAPS_GMEMORY_MODEL", "gpt-5.5")
        base_url = os.environ.get("OPENAI_API_BASE") or None
        self.client = OpenAI(base_url=base_url)

    # Match the upstream LLMCallable protocol exactly.
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def __call__(
        self,
        messages: list[Any],
        temperature: float = 0.1,
        max_tokens: int = 1024,
        stop_strs: list[str] | None = None,
        num_comps: int = 1,
    ) -> str:
        """Answer one upstream prompt; unsupported sampler knobs are ignored."""
        del temperature, stop_strs, num_comps
        response = self.client.responses.create(
            model=self.model,
            input=[{"role": message.role, "content": message.content} for message in messages],
            max_output_tokens=max_tokens,
        )
        answer = str(response.output_text or "").strip()
        if not answer:
            raise RuntimeError("GMemory extraction returned an empty response")
        return answer
