"""Validate and merge completed MAPs ablation replicas without losing provenance."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any
from typing import Iterable

DEFAULT_LOG_DIR = "logs/maps_ablation_player_with_watcher"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        line_number: Any
        line: Any
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON: {exc}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_number}: expected a JSON object")
            rows.append(row)
    return rows


def _instance_values(repo: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    path = repo / ".ablation-instance.env"
    if not path.exists():
        return values
    raw: Any
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'\"")
    return values


def _label(repo: Path) -> str:
    return _instance_values(repo).get("MAPS_REPLICA_ID", repo.name)


def _annotated(rows: Iterable[dict[str, Any]], label: str, arm: str, source: Path) -> Iterable[dict[str, Any]]:
    row: Any
    for row in rows:
        yield {**row, "replicate": label, "arm": arm, "source_file": str(source)}


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        row: Any
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")
            count += 1
    return count


def _current_park_rows(log_dir: Path) -> list[dict[str, Any]]:
    trajectory_ids = {path.stem.rsplit("_", 1)[0] for path in log_dir.glob("*.tsv")}
    ledger = log_dir / "park_ids.jsonl"
    return [
        row for row in (_read_jsonl(ledger) if ledger.exists() else []) if str(row.get("park_id")) in trajectory_ids
    ]


def _validate_complete(log_dir: Path, expected_episodes: int) -> dict[str, Any]:
    episode_files = sorted(log_dir.glob("run.ep*.jsonl"))
    if len(episode_files) != expected_episodes:
        raise ValueError(f"{log_dir}: expected {expected_episodes} episode logs, found {len(episode_files)}")
    step_count = 0
    path: Any
    for path in episode_files:
        rows = _read_jsonl(path)
        if len(rows) != 100 or not rows[-1].get("done") or rows[-1].get("step") != 100:
            raise ValueError(f"{path}: episode is incomplete (rows={len(rows)})")
        step_count += len(rows)

    cost_path = log_dir / "episode_cost.jsonl"
    cost_rows = _read_jsonl(cost_path) if cost_path.exists() else []
    cost_count = len(cost_rows)
    if cost_count != expected_episodes:
        raise ValueError(f"{cost_path}: expected {expected_episodes} rows, found {cost_count}")

    trajectories = sorted(log_dir.glob("*.tsv"))
    if len(trajectories) != expected_episodes:
        raise ValueError(f"{log_dir}: expected {expected_episodes} trajectory TSVs, found {len(trajectories)}")
    current_parks = _current_park_rows(log_dir)
    if len(current_parks) != expected_episodes:
        raise ValueError(
            f"{log_dir / 'park_ids.jsonl'}: expected {expected_episodes} IDs matching "
            f"the current trajectory files, found {len(current_parks)}"
        )
    incomplete_cost_episodes = [row.get("episode") for row in cost_rows if row.get("cost_complete") is False]
    return {
        "episodes": len(episode_files),
        "steps": step_count,
        "trajectories": len(trajectories),
        "incomplete_cost_episodes": incomplete_cost_episodes,
    }


def merge(repos: list[Path], output: Path, log_relative: str | None, expected_episodes: int) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"output already exists: {output}")
    output.mkdir(parents=True)
    trajectory_root = output / "trajectories"
    trajectory_root.mkdir()

    merged: dict[str, list[dict[str, Any]]] = {
        "steps.jsonl": [],
        "turns.jsonl": [],
        "episode_cost.jsonl": [],
        "park_ids.jsonl": [],
    }
    manifest: dict[str, Any] = {
        "log_relative_override": log_relative,
        "expected_episodes_per_replicate": expected_episodes,
        "replicates": [],
    }

    repo: Any
    for repo in repos:
        repo = repo.resolve()
        instance = _instance_values(repo)
        source_log_relative = log_relative or instance.get("MAPS_LOG_RELATIVE") or DEFAULT_LOG_DIR
        log_dir = repo / source_log_relative
        if not log_dir.is_dir():
            raise FileNotFoundError(f"missing log directory: {log_dir}")
        label = _label(repo)
        arm = instance.get("MAPS_ABLATION_ARM", label)
        validation = _validate_complete(log_dir, expected_episodes)

        episode_file: Any
        for episode_file in sorted(log_dir.glob("run.ep*.jsonl")):
            merged["steps.jsonl"].extend(
                _annotated(_read_jsonl(episode_file), label, arm, episode_file.relative_to(repo))
            )
        source_name: Any
        output_name: Any
        for source_name, output_name in (
            ("turns.jsonl", "turns.jsonl"),
            ("episode_cost.jsonl", "episode_cost.jsonl"),
        ):
            source = log_dir / source_name
            if source.exists():
                merged[output_name].extend(_annotated(_read_jsonl(source), label, arm, source.relative_to(repo)))
        park_source = log_dir / "park_ids.jsonl"
        merged["park_ids.jsonl"].extend(
            _annotated(_current_park_rows(log_dir), label, arm, park_source.relative_to(repo))
        )

        target_trajectories = trajectory_root / label
        target_trajectories.mkdir()
        trajectory: Any
        for trajectory in sorted(log_dir.glob("*.tsv")):
            shutil.copy2(trajectory, target_trajectories / trajectory.name)

        manifest["replicates"].append(
            {
                "id": label,
                "arm": arm,
                "repo": str(repo),
                "log_relative": source_log_relative,
                "ports": {key: value for key, value in instance.items() if key.endswith("_PORT")},
                **validation,
            }
        )

    manifest["merged_counts"] = {filename: _write_jsonl(output / filename, rows) for filename, rows in merged.items()}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repos", nargs="+", type=Path, help="Repository replica roots")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--log-relative",
        default=None,
        help="Override every source log directory; otherwise read MAPS_LOG_RELATIVE per replica",
    )
    parser.add_argument("--expected-episodes", type=int, default=7)
    args = parser.parse_args()
    manifest = merge(args.repos, args.output, args.log_relative, args.expected_episodes)
    print(
        f"Merged {len(manifest['replicates'])} complete replicas into {args.output}: "
        f"{manifest['merged_counts']['steps.jsonl']} steps"
    )


if __name__ == "__main__":
    main()
