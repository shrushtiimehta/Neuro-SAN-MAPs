"""Runner-side carryover adapter for the GMemory live state."""

from __future__ import annotations

from typing import Any

from coded_tools.ablations.g_memory_player_planner_watcher.g_memory_runtime_tool import GMemoryRuntimeTool


class GMemoryCarryoverTrials(GMemoryRuntimeTool):
    """Use the same carryover semantics as the planner tool."""

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """Bind the live carryover operation."""
        return super().invoke({**args, "memory_operation": "carryover_trials"}, sly_data)
