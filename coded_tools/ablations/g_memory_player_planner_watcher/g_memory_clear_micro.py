"""Episode-boundary cleanup of GMemory live watcher rules."""

from __future__ import annotations

import asyncio
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.ablations.g_memory_player_planner_watcher.g_memory_store import GMemoryStore


class GMemoryClearMicro(CodedTool):
    """Retire all temporary watcher rules at the episode boundary."""

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """Return the same cleanup receipt as the shared Markdown tool."""
        del sly_data
        try:
            episode = int(args.get("episode"))
        except (TypeError, ValueError):
            return "ERROR: episode is required and must be an integer"
        store = GMemoryStore()
        ids = [str(trial.get("trial_id")) for trial in store.trials() if trial.get("origin") == "micro"]
        removed = store.retire(ids)
        return {"episode": episode, "removed": removed, "removed_count": len(removed)}

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """Execute the same cleanup for asynchronous tool calls."""
        return await asyncio.to_thread(self.invoke, args, sly_data)
