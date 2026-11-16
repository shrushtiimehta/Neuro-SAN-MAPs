"""Keep the same phase schedule while loading it from live GMemory state."""

from __future__ import annotations

from middleware.episode_phase_middleware import EpisodePhaseMiddleware

from coded_tools.ablations.g_memory_player_planner_watcher.g_memory_store import GMemoryStore


class GMemoryPhaseMiddleware(EpisodePhaseMiddleware):
    """Inject current and next plan phases from the structured live store."""

    def _load_checklist(self) -> str:
        """Return the exact planner checklist body without reading Markdown."""
        checklist = GMemoryStore().get("episode_checklist")
        if not checklist:
            raise FileNotFoundError("GMemory episode checklist is missing")
        return checklist
