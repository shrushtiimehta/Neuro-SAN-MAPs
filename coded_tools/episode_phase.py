"""One parsed phase from an episode checklist."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EpisodePhase:
    """One parsed checklist phase and its complete original instruction line."""

    start: int
    end: int
    text: str
