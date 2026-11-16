"""Parse and validate the planner's turn-ranged episode phases."""

from __future__ import annotations

import re
from typing import Any
from typing import Iterable

from coded_tools.episode_phase import EpisodePhase


class EpisodePhases:
    """Parse, validate, and select planner episode phases."""

    _PHASE_RE = re.compile(
        r"^\s*(?:[-*+]\s*)?turns?\s+(\d+)\s*(?:[-–—]\s*(\d+))?\s*:\s*(\S.*)\s*$",
        re.IGNORECASE,
    )

    @staticmethod
    def parse_phase_line(line: str) -> EpisodePhase | None:
        """Parse one ``turns A-B: instructions`` line."""
        match = EpisodePhases._PHASE_RE.fullmatch(line)
        if match is None:
            return None
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else start
        return EpisodePhase(start=start, end=end, text=line.strip())

    @staticmethod
    def parse_episode_phases(checklist: str) -> list[EpisodePhase]:
        """Return all parseable phases in their file order."""
        phases: list[EpisodePhase] = []
        for line in checklist.splitlines():
            phase = EpisodePhases.parse_phase_line(line)
            if phase is not None:
                phases.append(phase)
        return phases

    @staticmethod
    def validate_phase_items(
        items: Iterable[Any],
        *,
        first_turn: int = 1,
        last_turn: int = 100,
    ) -> str | None:
        """Return an error when phase items are malformed, unordered, or not gap-free."""
        expected_start = first_turn
        saw_phase = False
        for index, raw_item in enumerate(items):
            phase = EpisodePhases.parse_phase_line(str(raw_item).strip())
            error = EpisodePhases._phase_error(phase, index, expected_start, last_turn)
            if error is not None:
                return error
            saw_phase = True
            assert phase is not None
            expected_start = phase.end + 1

        if not saw_phase:
            return "checklist_items must contain at least one phase"
        if expected_start != last_turn + 1:
            return (
                f"checklist_items must cover through turn {last_turn}; "
                f"coverage currently ends at turn {expected_start - 1}"
            )
        return None

    @staticmethod
    def _phase_error(
        phase: EpisodePhase | None,
        index: int,
        expected_start: int,
        last_turn: int,
    ) -> str | None:
        """Return the validation error for one phase, if present."""
        if phase is None:
            return f"checklist_items[{index}] must use 'turns A-B: <goal and complete phase instructions>'"
        if phase.end < phase.start:
            return f"checklist_items[{index}] has an inverted range: turns {phase.start}-{phase.end}"
        if phase.start != expected_start:
            return (
                f"checklist_items[{index}] must start at turn {expected_start}; "
                f"got turn {phase.start} (phases must be ordered and gap-free)"
            )
        if phase.end > last_turn:
            return f"checklist_items[{index}] ends at turn {phase.end}; the final turn is {last_turn}"
        return None

    @staticmethod
    def phases_for_turn(checklist: str, turn: Any) -> tuple[EpisodePhase, EpisodePhase | None] | None:
        """Return the exact active phase and the immediately following phase."""
        try:
            action_turn = int(turn)
        except (TypeError, ValueError):
            return None

        phases = EpisodePhases.parse_episode_phases(checklist)
        if EpisodePhases.validate_phase_items(phase.text for phase in phases) is not None:
            return None
        for index, phase in enumerate(phases):
            if phase.start <= action_turn <= phase.end:
                next_phase = phases[index + 1] if index + 1 < len(phases) else None
                return phase, next_phase
        return None


# Keep the established function API while the implementation lives in one class.
parse_phase_line = EpisodePhases.parse_phase_line
parse_episode_phases = EpisodePhases.parse_episode_phases
validate_phase_items = EpisodePhases.validate_phase_items
phases_for_turn = EpisodePhases.phases_for_turn
