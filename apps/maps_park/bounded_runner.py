"""Optional completed-episode limit for the canonical MAPs runner.

This adapter changes no agent or game-loop behavior. It stops immediately
before episode N+1 when bounded, and supports an explicit unlimited mode.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from apps.maps_park import runner


def _episode_limit() -> int | None:
    raw = os.environ.get("MAPS_EPISODE_LIMIT", "10").strip()
    if raw.lower() in {"0", "none", "unlimited", "infinite", "inf"}:
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit(f"MAPS_EPISODE_LIMIT must be a positive integer or 'unlimited', got {raw!r}") from exc
    if value < 1:
        raise SystemExit("MAPS_EPISODE_LIMIT must be at least 1, or use 'unlimited'")
    return value


def _resume_completed_count() -> int:
    """Count locally ledgered episodes when continuing an existing run."""
    if "--resume" not in sys.argv:
        return 0

    episodes: set[Any] = set()
    try:
        with open(runner.EPISODE_COST_PATH, encoding="utf-8") as handle:
            line: Any
            for line in handle:
                if not line.strip():
                    continue
                row = json.loads(line)
                if row.get("episode") is not None:
                    episodes.add(row["episode"])
    except FileNotFoundError:
        return 0
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot establish completed-episode count for resume: {exc}") from exc
    return len(episodes)


EPISODE_LIMIT = _episode_limit()
_completed = _resume_completed_count()
_BaseSeedPlaybooks = runner.SeedPlaybooks
_base_write_episode_cost = runner.write_episode_cost


class _BoundedSeedPlaybooks(_BaseSeedPlaybooks):
    """Stop before the first action of episode N+1."""

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        if EPISODE_LIMIT is not None and _completed >= EPISODE_LIMIT:
            print(f"[runner] Completed exactly {EPISODE_LIMIT} episode(s); stopping.")
            raise KeyboardInterrupt
        return super().invoke(args, sly_data)


def _write_cost_and_count(episode: Any, reward: Any) -> dict[str, Any]:
    """Close the episode normally, then advance the bounded-run counter."""
    global _completed
    row = _base_write_episode_cost(episode, reward)
    _completed += 1
    return row


def main() -> None:
    runner.SeedPlaybooks = _BoundedSeedPlaybooks
    runner.write_episode_cost = _write_cost_and_count
    runner.main()


if __name__ == "__main__":
    main()
