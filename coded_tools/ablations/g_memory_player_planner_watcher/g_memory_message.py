"""Safe message type for the upstream GMemory import boundary."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GMemoryMessage:
    """Provide the two fields upstream prompts use without importing mas.llm."""

    role: str
    content: str
