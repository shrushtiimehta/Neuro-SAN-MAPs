"""Full-strategy MAPS runner with no information carried across episodes."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from typing import ClassVar

from apps.maps_park import runner
from coded_tools.seed_playbooks import SeedPlaybooks


class NoSelfImprovementRunner:
    """Keep planner/watcher strategy within an episode, then erase its effects."""

    _base_write_episode_cost: ClassVar[Any] = runner.write_episode_cost
    _reset_patterns: ClassVar[tuple[str, ...]] = (
        "scratchpad_*.md",
        "trial_strategies*.md",
        "episode_checklist.md",
        "last_reward.md",
        "plan_current.json",
        "plan_last_good.json",
        "champion_reward.json",
        "status*.json",
        "latest_observations.json",
        "proposed_action.json",
    )
    _episode_marker = "no_carry_episode.txt"

    @staticmethod
    def _never_promote(_reward: Any, _minimum: Any = None) -> bool:
        """Prevent deterministic champion state from becoming a learning channel."""
        return False

    @staticmethod
    def _never_restore() -> bool:
        """Prevent a prior episode plan from being restored."""
        return False

    @staticmethod
    def _never_restore_archive() -> None:
        """Prevent default-mode startup from loading a prior champion archive."""
        return None

    @classmethod
    def _reset_fixed_policy(cls, completed_episode: Any) -> None:
        """Restore seeds and make prior-episode telemetry invisible to agents."""
        state_dir = Path(runner.PLAYBOOK_STATE_DIR)
        pattern: Any
        path: Any
        for pattern in cls._reset_patterns:
            for path in state_dir.glob(pattern):
                path.unlink(missing_ok=True)
        seeded = SeedPlaybooks().invoke({"overwrite": True}, {})
        errors = seeded.get("errors", [])
        if errors:
            raise RuntimeError("no-carryover reset failed: " + "; ".join(errors))
        try:
            next_episode = int(completed_episode) + 1
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"invalid completed episode: {completed_episode!r}") from exc
        (state_dir / cls._episode_marker).write_text(f"{next_episode}\n", encoding="utf-8")

    @classmethod
    def write_episode_cost(cls, episode: Any, reward: Any) -> dict[str, Any]:
        """Record the episode, then erase every strategy it could carry forward."""
        row = cls._base_write_episode_cost(episode, reward)
        cls._reset_fixed_policy(episode)
        print(f"[no-self-improvement] episode={episode} cleared all cross-episode strategy state")
        return row

    @classmethod
    def main(cls) -> None:
        """Apply no-carryover guards and run the shared ten-episode adapter."""
        if os.environ.get("MAPS_SELF_IMPROVEMENT") != "0":
            raise RuntimeError("no-self-improvement runner requires MAPS_SELF_IMPROVEMENT=0")
        if os.environ.get("MAPS_NO_CROSS_EPISODE") != "1":
            raise RuntimeError("no-self-improvement runner requires MAPS_NO_CROSS_EPISODE=1")
        if os.environ.get("MAPS_SKIP_MACRO_CLOSEOUT") != "1":
            raise RuntimeError("no-self-improvement runner requires MAPS_SKIP_MACRO_CLOSEOUT=1")
        runner.champion_plan.promote_plan = cls._never_promote
        runner.champion_plan.restore_last_good = cls._never_restore
        runner.restore_champion_playbooks = cls._never_restore_archive
        runner.write_episode_cost = cls.write_episode_cost

        # Import only after patching write_episode_cost so the bounded adapter
        # counts the no-carryover wrapper rather than bypassing it.
        from apps.maps_park import bounded_runner

        bounded_runner.main()


if __name__ == "__main__":
    NoSelfImprovementRunner.main()
