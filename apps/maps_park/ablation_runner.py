"""Bounded experiment adapter around the canonical MAPs runner.

No game-loop behavior is forked here. The adapter adds only experiment
invariants: exactly N completed episodes and watcher-origin micro strategies
are deleted at every episode boundary. Player retry behavior stays canonical.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from apps.maps_park import runner
from coded_tools.ablations.shared.clear_episode_micro_strategies import ClearEpisodeMicroStrategies
from coded_tools.file_io import FileIO
from coded_tools.trial_parsing import CRITERIA_PATH
from coded_tools.trial_parsing import STRATEGIES_PATH
from coded_tools.trial_parsing import filter_lines
from coded_tools.trial_parsing import parse_criteria
from coded_tools.trial_parsing import parse_strategies


def _positive_limit() -> int:
    raw = os.environ.get("MAPS_EPISODE_LIMIT", "10")
    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit(f"MAPS_EPISODE_LIMIT must be an integer, got {raw!r}") from exc
    if value < 1:
        raise SystemExit("MAPS_EPISODE_LIMIT must be at least 1")
    return value


EPISODE_LIMIT = _positive_limit()


def _resume_completed_count() -> int:
    """Count distinct locally ledgered episodes for a resumed arm."""
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


_completed = _resume_completed_count()
_BaseSeedPlaybooks = runner.SeedPlaybooks
_base_consult = runner.consult
_base_write_episode_cost = runner.write_episode_cost


class _BoundedSeedPlaybooks(_BaseSeedPlaybooks):
    """Stop before the first action of episode N+1."""

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        if _completed >= EPISODE_LIMIT:
            print(f"[ablation] Completed exactly {EPISODE_LIMIT} episode(s); stopping.")
            raise KeyboardInterrupt
        result = super().invoke(args, sly_data)
        errors = result.get("errors", [])
        if errors:
            raise RuntimeError("playbook seeding failed before the first LLM turn: " + "; ".join(errors))
        return result


def _snapshot_micro_strategies() -> list[dict[str, Any]]:
    """Capture the micro guidance that must expire after the next watching."""
    strategies = parse_strategies(FileIO.read_text(STRATEGIES_PATH))
    criteria = parse_criteria(FileIO.read_text(CRITERIA_PATH))
    return [
        {"trial_id": trial_id, "rule": rule, **criteria.get(trial_id, {})}
        for trial_id, rule in strategies.items()
        if criteria.get(trial_id, {}).get("origin") == "micro"
    ]


def _retire_watched_micro_strategies(trial_ids: set[str]) -> list[str]:
    """Delete only the strategies present before watching; preserve new ones."""
    if not trial_ids:
        return []
    strategies_text = FileIO.read_text(STRATEGIES_PATH)
    criteria_text = FileIO.read_text(CRITERIA_PATH)
    strategies = parse_strategies(strategies_text)
    criteria = parse_criteria(criteria_text)
    removed = sorted(
        trial_id
        for trial_id in trial_ids
        if trial_id in strategies and criteria.get(trial_id, {}).get("origin") == "micro"
    )
    if not removed:
        return []
    keep_ids = set(strategies) - set(removed)
    try:
        FileIO.write_text(STRATEGIES_PATH, filter_lines(strategies_text, keep_ids))
        FileIO.write_text(CRITERIA_PATH, filter_lines(criteria_text, keep_ids))
    except OSError as exc:
        raise RuntimeError(f"could not retire watched micro strategies: {exc}") from exc
    return removed


def _ablation_consult(
    session: Any, thread: Any, kind: str, verified: dict | None, label: str = "consultant", extra: str = ""
) -> str:
    incoming: list[dict[str, Any]] = []
    if kind == "periodic":
        incoming = _snapshot_micro_strategies()
        lifecycle = (
            "expiring_micro_strategies_json="
            + json.dumps(incoming, separators=(",", ":"), sort_keys=True)
            + " Evaluate every strategy in this snapshot during this watching. "
            "After your response, the runner will delete exactly these incoming strategies; "
            "strategies you create during this watching remain active until the next watching."
        )
        extra = f"{extra} {lifecycle}".strip()

    response = _base_consult(session, thread, kind, verified, label=label, extra=extra)
    if kind == "periodic":
        removed = _retire_watched_micro_strategies({str(trial["trial_id"]) for trial in incoming})
        print(
            f"[ablation] watching retired {len(removed)} prior micro strategy(s); new watcher strategies remain active"
        )
    return response


def _write_cost_and_close(episode: Any, reward: Any) -> dict[str, Any]:
    global _completed
    row = _base_write_episode_cost(episode, reward)
    cleared = ClearEpisodeMicroStrategies().invoke({"episode": episode}, {})
    if isinstance(cleared, str):
        raise RuntimeError(cleared)
    print(f"[ablation] episode={episode} removed {cleared['removed_count']} temporary micro strategy(s)")
    _completed += 1
    return row


def main() -> None:
    runner.SeedPlaybooks = _BoundedSeedPlaybooks
    runner.consult = _ablation_consult
    runner.write_episode_cost = _write_cost_and_close
    runner.main()


if __name__ == "__main__":
    main()
