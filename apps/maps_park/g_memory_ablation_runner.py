"""Run the unchanged bounded MAPS loop with GMemory state and episode memory."""

from __future__ import annotations

import json
import re
from typing import Any

from apps.maps_park import runner
from coded_tools.ablations.g_memory_player_planner_watcher import g_memory_interaction_processor
from coded_tools.ablations.g_memory_player_planner_watcher.g_memory_carryover_trials import GMemoryCarryoverTrials
from coded_tools.ablations.g_memory_player_planner_watcher.g_memory_clear_micro import GMemoryClearMicro
from coded_tools.ablations.g_memory_player_planner_watcher.g_memory_seed import GMemorySeed
from coded_tools.ablations.g_memory_player_planner_watcher.g_memory_store import GMemoryStore
from coded_tools.ablations.g_memory_player_planner_watcher.g_memory_write_episode_plan import GMemoryWriteEpisodePlan


class GMemoryAblationRunner:
    """Bind the canonical runner's storage callbacks to GMemory live state."""

    BASE_CHAT = runner.chat

    @staticmethod
    def chat(session: Any, thread: dict[str, Any], message: str) -> tuple[Any, Any, Any]:
        """Tag every streamed internal agent event with its episode and turn."""
        match = re.search(r"\bkind=(episode_start|episode_end|periodic)\s+episode=(\d+)\s+step=(\d+)", message)
        if match:
            chat_kind, episode, step = match.groups()
            turn = int(step) if chat_kind == "episode_end" else int(step) + 1
            g_memory_interaction_processor.GMemoryInteractionProcessor.set_context(int(episode), turn, chat_kind)
        else:
            verified = runner.read_last_verified() or {}
            try:
                episode = int(verified.get("episode") or 0)
                turn = int(verified.get("step") or 0) + 1
            except (TypeError, ValueError):
                episode, turn = 0, 1
            g_memory_interaction_processor.GMemoryInteractionProcessor.set_context(episode, turn, "player")
        return GMemoryAblationRunner.BASE_CHAT(session, thread, message)

    @staticmethod
    def snapshot_micro_strategies() -> list[dict[str, Any]]:
        """Capture only the watcher rules present before a check-in."""
        return [trial for trial in GMemoryStore().trials() if trial.get("origin") == "micro"]

    @staticmethod
    def retire_watched_micro_strategies(trial_ids: set[str]) -> list[str]:
        """Retire the captured IDs, preserving new watcher guidance."""
        store = GMemoryStore()
        eligible = [
            str(trial.get("trial_id"))
            for trial in store.trials()
            if trial.get("origin") == "micro" and trial.get("trial_id") in trial_ids
        ]
        return store.retire(eligible)

    @staticmethod
    def snapshot_playbooks(tag: str, stats: dict[str, Any] | None = None) -> str | None:
        """Return the durable GMemory state location after a champion episode."""
        del tag, stats
        return GMemoryStore().path

    @staticmethod
    def restore_champion_playbooks() -> str | None:
        """The champion plan is already durable in the live database."""
        store = GMemoryStore()
        return store.path if store.get("plan_champion") else None

    @staticmethod
    def strip_learned_from_seeds() -> int:
        """Keep shared static seed files untouched by this isolated ablation."""
        return 0

    @staticmethod
    def best_reward() -> float:
        """Return the rising champion bar from structured state."""
        try:
            return float(GMemoryStore().get("champion_reward") or 0)
        except ValueError:
            return 0.0

    @staticmethod
    def promote_plan(reward: float, min_reward: float = 350000) -> bool:
        """Checkpoint only a plan that beats both the floor and current best."""
        store = GMemoryStore()
        plan = store.get("plan_current")
        if not plan:
            return False
        try:
            numeric = float(reward)
        except (TypeError, ValueError):
            return False
        if numeric < min_reward or numeric <= GMemoryAblationRunner.best_reward():
            return False
        store.put("plan_champion", plan)
        store.put("champion_reward", str(numeric))
        return True

    @staticmethod
    def restore_last_good() -> bool:
        """Reapply the champion plan before the planner revises it."""
        plan = GMemoryStore().get("plan_champion")
        if not plan:
            return False
        result = GMemoryWriteEpisodePlan().invoke(json.loads(plan), {})
        return isinstance(result, dict)

    @staticmethod
    def main() -> None:
        """Apply arm-local hooks and execute the bounded canonical loop."""
        runner.SeedPlaybooks = GMemorySeed
        runner.ConversationThinkingFileMessageProcessor = g_memory_interaction_processor.GMemoryInteractionProcessor
        runner.chat = GMemoryAblationRunner.chat
        runner.CarryoverTrials = GMemoryCarryoverTrials
        runner.snapshot_playbooks = GMemoryAblationRunner.snapshot_playbooks
        runner.restore_champion_playbooks = GMemoryAblationRunner.restore_champion_playbooks
        runner.strip_learned_from_seeds = GMemoryAblationRunner.strip_learned_from_seeds
        runner.champion_plan.best_reward = GMemoryAblationRunner.best_reward
        runner.champion_plan.promote_plan = GMemoryAblationRunner.promote_plan
        runner.champion_plan.restore_last_good = GMemoryAblationRunner.restore_last_good

        # The shared adapter captures runner.SeedPlaybooks at import time.
        # pylint: disable=import-outside-toplevel
        from apps.maps_park import ablation_runner

        # These shared hooks are intentionally replaced only for this arm.
        # pylint: disable=protected-access
        ablation_runner._snapshot_micro_strategies = GMemoryAblationRunner.snapshot_micro_strategies
        ablation_runner._retire_watched_micro_strategies = GMemoryAblationRunner.retire_watched_micro_strategies
        ablation_runner.ClearEpisodeMicroStrategies = GMemoryClearMicro
        ablation_runner.main()


if __name__ == "__main__":
    GMemoryAblationRunner.main()
