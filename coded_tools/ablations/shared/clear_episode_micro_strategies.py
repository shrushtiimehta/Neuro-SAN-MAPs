"""Deterministically remove every episode-scoped watcher strategy.

Macro strategies are preserved. No outcome is recorded because watcher guidance
is intentionally temporary and must disappear at the episode boundary.
"""

from __future__ import annotations

from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.file_io import FileIO
from coded_tools.trial_parsing import CRITERIA_PATH
from coded_tools.trial_parsing import STRATEGIES_PATH
from coded_tools.trial_parsing import filter_lines
from coded_tools.trial_parsing import parse_criteria
from coded_tools.trial_parsing import parse_strategies


class ClearEpisodeMicroStrategies(CodedTool):
    """Remove all active criteria rows whose origin is ``micro``."""

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        del sly_data
        try:
            episode = int(args.get("episode"))
        except (TypeError, ValueError):
            return "ERROR: episode is required and must be an integer"

        strategies_text = FileIO.read_text(STRATEGIES_PATH)
        criteria_text = FileIO.read_text(CRITERIA_PATH)
        strategies = parse_strategies(strategies_text)
        criteria = parse_criteria(criteria_text)
        removed = sorted(trial_id for trial_id in strategies if criteria.get(trial_id, {}).get("origin") == "micro")
        keep_ids = set(strategies) - set(removed)
        try:
            FileIO.write_text(STRATEGIES_PATH, filter_lines(strategies_text, keep_ids))
            FileIO.write_text(CRITERIA_PATH, filter_lines(criteria_text, keep_ids))
        except OSError as err:
            return f"ERROR: could not clear micro strategies: {err}"
        return {"episode": episode, "removed": removed, "removed_count": len(removed)}

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return self.invoke(args, sly_data)
