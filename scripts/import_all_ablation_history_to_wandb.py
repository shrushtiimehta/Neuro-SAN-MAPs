#!/usr/bin/env python3
"""Upload every retained multi-episode MAPs run to W&B and Weave.

Each W&B parent run contains one history row per episode. Per-step trajectory
and turn histories are published by ``import_grouped_ablation_episodes_to_wandb``
as episode children. Identical worktree copies are deduplicated and one-episode
runs are excluded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_SEARCH_ROOT = ROOT.parent
DEFAULT_PROJECT = "maps-park-ablations"
SIDECARS = ("turns.jsonl", "episode_cost.jsonl", "park_ids.jsonl")
DATASET_NAMES = {
    "trajectory": "maps_park_all_ablation_trajectories",
    "turn": "maps_park_all_ablation_turns",
    "episode_cost": "maps_park_all_ablation_episode_costs",
    "park_id": "maps_park_all_ablation_park_ids",
}
# Parent histories contain only episode-wise values. Increment this when their
# immutable W&B history schema must be replaced.
HISTORY_SCHEMA = "run-episode-summary-v2"
LEGACY_HISTORY_SCHEMAS = ("chart-columns-v7", "run-episode-summary-v1")


@dataclass(frozen=True)
class SnapshotFile:
    name: str
    data: bytes
    rows: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class RawRun:
    key: str
    name: str
    arm: str
    directory: Path
    files: tuple[SnapshotFile, ...]
    fingerprint: str

    @property
    def episode_files(self) -> tuple[SnapshotFile, ...]:
        return tuple(file for file in self.files if file.name.startswith("run.ep"))


@dataclass(frozen=True)
class Discovery:
    runs: tuple[RawRun, ...]
    excluded_one_episode: tuple[Path, ...]
    duplicate_directories: tuple[tuple[Path, Path], ...]


def _parse_jsonl(path: Path, data: bytes) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    line_number: Any
    line: Any
    for line_number, line in enumerate(data.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON in {path}:{line_number}: {exc}") from exc
        if not isinstance(row, dict):
            raise ValueError(f"expected a JSON object in {path}:{line_number}")
        rows.append(row)
    return tuple(rows)


def _snapshot_file(path: Path) -> SnapshotFile:
    data = path.read_bytes()
    return SnapshotFile(path.name, data, _parse_jsonl(path, data))


def _episode_number(name: str) -> int:
    match = re.search(r"run\.ep(\d+)\.jsonl$", name)
    if match is None:
        raise ValueError(f"unexpected trajectory filename: {name}")
    return int(match.group(1))


def _arm(directory: Path) -> str:
    part: Any
    for part in reversed(directory.parts):
        if part.startswith("maps_ablation_"):
            raw = part.removeprefix("maps_ablation_")
            return {
                "player_with_planner": "planner_only",
                "player_with_watcher": "watcher_only",
                "unstructured_player_planner_watcher": "unstructured_planning",
            }.get(raw, raw)
        if part == "maps_park_solo":
            return "solo_ablation"
        if part == "maps_park":
            return "baseline"
    return "maps_park"


def _repo_name(directory: Path) -> str:
    parent: Any
    for parent in (directory, *directory.parents):
        if parent.name.startswith("neuro-san-studio"):
            return parent.name
    return "workspace"


def _run_stamp(directory: Path) -> str:
    return directory.name if directory.parent.name == "prior-runs" else "current"


def _known_key(directory: Path, arm: str, stamp: str) -> str | None:
    repo = _repo_name(directory)
    if repo == "neuro-san-studio":
        known = {
            ("baseline", "20260819-233018"): "baseline-original",
            ("solo_ablation", "20260912-153544"): "solo-1",
            ("solo_ablation", "20260912-223114"): "solo-2",
            ("solo_ablation", "current"): "solo-3",
            ("watcher_only", "current"): "watcher-only",
            ("planner_only", "current"): "planner-only",
            ("unstructured_planning", "current"): "unstructured-planning",
        }
        if key := known.get((arm, stamp)):
            return key
    if arm == "embedded_player_planner_watcher" and stamp == "current":
        return "embedded-player-planner-watcher"
    if arm == "planner_only" and stamp == "current":
        return "planner-only"
    if arm == "unstructured_planning" and stamp == "current":
        return "unstructured-planning"
    return None


def _source_key(directory: Path) -> str:
    arm = _arm(directory)
    stamp = _run_stamp(directory)
    known = _known_key(directory, arm, stamp)
    if known:
        return known
    repo = _repo_name(directory)
    repo_suffix = "-studio2" if repo == "neuro-san-studio2" else ""
    return f"{arm.replace('_', '-')}-{stamp}{repo_suffix}"


def _display_name(directory: Path) -> str:
    arm = _arm(directory).replace("_", " ").title()
    stamp = _run_stamp(directory)
    repo = _repo_name(directory)
    suffix = f" ({repo})" if repo == "neuro-san-studio2" else ""
    return f"{arm} — {stamp}{suffix}"


def trace_arm_label(run: RawRun) -> str:
    return {
        "embedded_player_planner_watcher": "Embedded",
        "planner_only": "Planner",
        "watcher_only": "Watcher",
        "unstructured_planning": "Unstructured",
        "solo_ablation": "Single Agent",
        "baseline": "Baseline",
    }.get(run.arm, run.arm.replace("_", " ").title())


def run_numbers(runs: tuple[RawRun, ...]) -> dict[str, int]:
    """Number runs chronologically within each ablation arm."""
    grouped: dict[str, list[RawRun]] = {}
    run: Any
    for run in runs:
        grouped.setdefault(run.arm, []).append(run)
    numbers: dict[str, int] = {}
    arm_runs: Any
    for arm_runs in grouped.values():
        ordered = sorted(
            arm_runs,
            key=lambda run: (
                "99999999-999999" if run.directory.parent.name != "prior-runs" else run.directory.name,
                run.key,
            ),
        )
        number: Any
        run: Any
        for number, run in enumerate(ordered, start=1):
            numbers[run.key] = number
    return numbers


def _fingerprint(files: tuple[SnapshotFile, ...]) -> str:
    digest = hashlib.sha256()
    file: Any
    for file in files:
        digest.update(file.name.encode())
        digest.update(b"\0")
        digest.update(file.data)
    return digest.hexdigest()


def _candidate_priority(path: Path) -> tuple[int, str]:
    # Prefer the primary checkout when an isolated ablation worktree contains
    # an identical copy; embedded data exists only in its isolated worktree.
    try:
        path.relative_to(ROOT)
        priority = 0
    except ValueError:
        priority = 1
    return priority, str(path)


def discover(search_root: Path) -> Discovery:
    directories: set[Path] = set()
    repo: Any
    for repo in sorted(search_root.glob("neuro-san-studio*")):
        logs = repo / "logs"
        if not logs.is_dir():
            continue
        path: Any
        for path in logs.rglob("run.ep*.jsonl"):
            if any(part.startswith("maps_") for part in path.parts):
                directories.add(path.parent.resolve())

    excluded: list[Path] = []
    candidates: list[RawRun] = []
    directory: Any
    for directory in sorted(directories, key=_candidate_priority):
        episode_paths = sorted(directory.glob("run.ep*.jsonl"), key=lambda p: _episode_number(p.name))
        if len(episode_paths) <= 1:
            excluded.append(directory)
            continue
        paths = episode_paths + [directory / name for name in SIDECARS if (directory / name).is_file()]
        files = tuple(_snapshot_file(path) for path in paths)
        arm = _arm(directory)
        if arm == "baseline" and ROOT not in (directory, *directory.parents):
            # Baselines are authoritative only in the primary checkout. Old
            # secondary-checkout folders may still exist after being removed
            # from the retained baseline set.
            continue
        candidates.append(
            RawRun(
                key=_source_key(directory),
                name=_display_name(directory),
                arm=arm,
                directory=directory,
                files=files,
                fingerprint=_fingerprint(files),
            )
        )

    unique: list[RawRun] = []
    by_fingerprint: dict[str, RawRun] = {}
    duplicates: list[tuple[Path, Path]] = []
    candidate: Any
    for candidate in candidates:
        original = by_fingerprint.get(candidate.fingerprint)
        if original is not None:
            duplicates.append((candidate.directory, original.directory))
            continue
        by_fingerprint[candidate.fingerprint] = candidate
        unique.append(candidate)
    return Discovery(tuple(unique), tuple(excluded), tuple(duplicates))


def _kind(file_name: str) -> str:
    if file_name.startswith("run.ep"):
        return "trajectory"
    return {
        "turns.jsonl": "turn",
        "episode_cost.jsonl": "episode_cost",
        "park_ids.jsonl": "park_id",
    }[file_name]


def all_records(runs: tuple[RawRun, ...]) -> dict[str, list[dict[str, Any]]]:
    records: dict[str, list[dict[str, Any]]] = {kind: [] for kind in DATASET_NAMES}
    run: Any
    for run in runs:
        metadata = {
            "source_run_key": run.key,
            "source_run_name": run.name,
            "ablation_arm": run.arm,
            "source_directory": str(run.directory),
            "source_fingerprint": run.fingerprint,
        }
        file: Any
        for file in run.files:
            kind = _kind(file.name)
            line_number: Any
            row: Any
            for line_number, row in enumerate(file.rows, start=1):
                records[kind].append(
                    {
                        **metadata,
                        "source_file": file.name,
                        "source_line": line_number,
                        # Keep the source object nested so no metadata key can
                        # overwrite, rename, or otherwise lose an original field.
                        "record": row,
                    }
                )
    return records


def _history_run_id(key: str, schema: str = HISTORY_SCHEMA) -> str:
    identity = f"{schema}:{key}"
    return "hist" + hashlib.sha256(identity.encode()).hexdigest()[:12]


def _run_id(run: RawRun) -> str:
    return _history_run_id(run.key)


def _api_run(api: Any, path: str) -> Any | None:
    try:
        return api.run(path)
    except Exception as exc:  # SDK exception classes vary by W&B version.
        message = str(exc).lower()
        if "not found" in message or "could not find" in message:
            return None
        raise


def _completed_episodes(run: RawRun) -> list[tuple[int, dict[str, Any]]]:
    completed: list[tuple[int, dict[str, Any]]] = []
    file: Any
    for file in run.episode_files:
        if not file.rows:
            continue
        last = file.rows[-1]
        if bool(last.get("done")) or int(last.get("step") or 0) >= 100:
            # The archive filename is the canonical per-run episode index.
            # Some legacy payloads reused a global or stale ``episode`` value.
            episode_index = _episode_number(file.name)
            completed.append((episode_index, last))
    return sorted(completed)


def _record_counts(run: RawRun) -> dict[str, int]:
    counts = {kind: 0 for kind in DATASET_NAMES}
    file: Any
    for file in run.files:
        counts[_kind(file.name)] += len(file.rows)
    return counts


def _flatten_history_value(target: dict[str, Any], key: str, value: Any) -> None:
    """Flatten nested objects into W&B columns without metadata envelopes."""
    if isinstance(value, dict):
        child_key: Any
        child_value: Any
        for child_key, child_value in value.items():
            _flatten_history_value(target, f"{key}/{child_key}", child_value)
        return
    if isinstance(value, (list, tuple)):
        target[key] = json.dumps(value, default=str, separators=(",", ":"), sort_keys=True)
        return
    target[key] = value


def _prefixed_history_row(
    prefix: str,
    source: dict[str, Any],
    *,
    episode: int | None,
    excluded: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    if episode is not None:
        result["episode"] = episode
    key: Any
    value: Any
    for key, value in source.items():
        if key in excluded:
            continue
        column = f"{prefix}/{key}"
        if prefix == "turn" and key == "turn":
            column = "turn/number"
        _flatten_history_value(result, column, value)
    return result


def _history_rows(run: RawRun) -> list[dict[str, Any]]:
    """Build chartable history rows while keeping episode labels one-based."""
    rows: list[dict[str, Any]] = []
    file: Any
    for file in run.episode_files:
        episode = _episode_number(file.name) + 1
        source: Any
        for source in file.rows:
            row: dict[str, Any] = {"episode": episode}
            key: Any
            value: Any
            for key, value in source.items():
                if key != "episode":
                    _flatten_history_value(row, key, value)
            rows.append(row)

    file: Any
    for file in run.files:
        if file.name == "turns.jsonl":
            source: Any
            for source in file.rows:
                verified = source.get("verified_after") or {}
                episode_index = verified.get("episode") if isinstance(verified, dict) else None
                episode = int(episode_index) + 1 if episode_index is not None else None
                row = _prefixed_history_row("turn", source, episode=episode)
                row.pop("turn/verified_after/episode", None)
                token_name: Any
                for token_name in (
                    "total_tokens",
                    "prompt_tokens",
                    "completion_tokens",
                ):
                    source_key = f"turn/tokens/{token_name}"
                    if source_key in row:
                        row[token_name] = row.pop(source_key)
                rows.append(row)
        elif file.name == "episode_cost.jsonl":
            source: Any
            for source in file.rows:
                episode_index = source.get("episode")
                episode = int(episode_index) + 1 if episode_index is not None else None
                rows.append(
                    _prefixed_history_row(
                        "episode_cost",
                        source,
                        episode=episode,
                        excluded=frozenset({"episode"}),
                    )
                )
        elif file.name == "park_ids.jsonl":
            source: Any
            for source in file.rows:
                episode_index = source.get("run_episode", source.get("episode"))
                episode = int(episode_index) + 1 if episode_index is not None else None
                rows.append(
                    _prefixed_history_row(
                        "park",
                        source,
                        episode=episode,
                        excluded=frozenset({"episode", "run_episode"}),
                    )
                )

    return rows


def _run_history_rows(run: RawRun) -> list[dict[str, Any]]:
    """Build one parent-run history row for every one-based episode."""
    rows_by_episode: dict[int, dict[str, Any]] = {}
    file: Any
    for file in run.episode_files:
        episode = _episode_number(file.name) + 1
        row: dict[str, Any] = {"run/episode": episode}
        if file.rows:
            last = file.rows[-1]
            step = int(last.get("step") or len(file.rows))
            complete = bool(last.get("done")) or step >= 100
            row["run/episode_steps"] = step
            row["run/episode_complete"] = complete
            if complete and last.get("cumulative_reward") is not None:
                row["run/cumulative_reward"] = last["cumulative_reward"]
            final_state = _prefixed_history_row(
                "run/episode_final",
                last,
                episode=None,
                excluded=frozenset({"episode", "step", "cumulative_reward"}),
            )
            row.update(final_state)
        rows_by_episode[episode] = row

    file: Any
    for file in run.files:
        if file.name not in {"episode_cost.jsonl", "park_ids.jsonl"}:
            continue
        position: Any
        source: Any
        for position, source in enumerate(file.rows):
            if file.name == "episode_cost.jsonl":
                episode_index = source.get("episode", position)
                prefix = "run/episode_cost"
                excluded = frozenset({"episode", "final_reward"})
            else:
                episode_index = source.get("run_episode", position)
                prefix = "run/park"
                excluded = frozenset({"episode", "run_episode"})
            episode = int(episode_index) + 1
            if episode not in rows_by_episode:
                raise ValueError(f"{file.name} refers to missing episode {episode} in {run.directory}")
            rows_by_episode[episode].update(
                _prefixed_history_row(
                    prefix,
                    source,
                    episode=None,
                    excluded=excluded,
                )
            )

    return [rows_by_episode[episode] for episode in sorted(rows_by_episode)]


def authoritative_runs(search_root: Path = DEFAULT_SEARCH_ROOT) -> tuple[RawRun, ...]:
    """Return only the retained runs with their correctly partitioned ledgers."""
    from scripts.reconcile_baseline_history_to_wandb import authoritative_baseline_runs
    from scripts.reconcile_cleaned_ablations_to_wandb import TARGET_ARMS
    from scripts.reconcile_cleaned_ablations_to_wandb import authoritative_ablation_runs

    baselines = authoritative_baseline_runs(ROOT)
    ablations = authoritative_ablation_runs(ROOT)
    discovered = discover(search_root.resolve()).runs
    embedded = tuple(
        run
        for run in discovered
        if run.arm != "baseline" and run.arm not in TARGET_ARMS and run.key == "embedded-player-planner-watcher"
    )
    runs = (*baselines, *ablations, *embedded)
    keys = [run.key for run in runs]
    if len(runs) != 26 or len(keys) != len(set(keys)):
        raise ValueError(f"expected 26 unique authoritative runs, found {len(runs)}: {keys}")
    return tuple(runs)


def upload_run(run_data: RawRun, *, entity: str, project: str, run_number: int) -> tuple[str, bool]:
    import wandb

    run_id = _run_id(run_data)
    path = f"{entity}/{project}/{run_id}"
    api_run = _api_run(wandb.Api(timeout=60), path)
    arm_label = trace_arm_label(run_data)
    desired_name = f"{arm_label} • Run {run_number}"
    desired_group = desired_name
    renamed = False
    if api_run is not None:
        if api_run.name != desired_name or api_run.group != desired_group:
            api_run.name = desired_name
            api_run.group = desired_group
            renamed = True
        if api_run.config.get("Ablation") != arm_label:
            api_run.config["Ablation"] = arm_label
            renamed = True
        if api_run.config.get("Run") != run_number:
            api_run.config["Run"] = run_number
            renamed = True
        if renamed:
            api_run.update()
    completed = _completed_episodes(run_data)
    desired_scores = [
        {
            "run/episode": episode_index + 1,
            "run/cumulative_reward": last.get("cumulative_reward"),
        }
        for episode_index, last in completed
    ]
    if api_run is not None:
        current_history = [
            {
                "run/episode": row.get("run/episode"),
                "run/cumulative_reward": row.get("run/cumulative_reward"),
            }
            for row in api_run.scan_history(keys=["run/episode", "run/cumulative_reward"], page_size=1000)
        ]
        expected_row_count = len(_run_history_rows(run_data))
        current_row_count = int(api_run.summary._json_dict.get("_step", -1)) + 1
        if current_history != desired_scores or current_row_count != expected_row_count:
            raise RuntimeError(f"clean W&B history differs for {path}; create a new history schema")
        return api_run.url, renamed

    sync_dir = Path(tempfile.gettempdir()) / "maps-wandb-history"
    sync_dir.mkdir(parents=True, exist_ok=True)
    wb_run = wandb.init(
        entity=entity,
        project=project,
        id=run_id,
        resume="allow",
        name=desired_name,
        group=desired_group,
        job_type="ablation",
        tags=["maps-park", "ablation", run_data.arm],
        config={"Ablation": arm_label, "Run": run_number},
        dir=str(sync_dir),
        mode="online",
        force=True,
        save_code=False,
    )
    if wb_run is None:
        raise RuntimeError(f"wandb.init returned no run for {run_data.name}")
    wb_run.define_metric("run/episode", hidden=True, summary="none")
    wb_run.define_metric("run/cumulative_reward", step_metric="run/episode", summary="mean")
    wb_run.define_metric("run/cumulative_reward", step_metric="run/episode", summary="max")
    history_rows = _run_history_rows(run_data)
    history_columns = {key for history_row in history_rows for key in history_row} - {
        "run/episode",
        "run/cumulative_reward",
    }
    column: Any
    for column in sorted(history_columns):
        wb_run.define_metric(column, step_metric="run/episode", summary="none")
    history_row: Any
    for history_row in history_rows:
        wb_run.log(history_row)

    wb_run.summary["completed_episodes"] = len(completed)
    wb_run.summary["episodes"] = len(history_rows)
    key: Any
    for key in list(dict(wb_run.summary)):
        if key.startswith(("run/episode_final/", "run/episode_cost/", "run/park/")):
            del wb_run.summary[key]
    wb_run.finish()
    return wb_run.url, True


def publish_weave(records: dict[str, list[dict[str, Any]]], *, entity: str, project: str) -> dict[str, str]:
    import weave

    weave.init(f"{entity}/{project}")
    refs: dict[str, str] = {}
    descriptions = {
        "trajectory": "Every JSON object from every run.ep*.jsonl in all unique multi-episode MAPs runs.",
        "turn": "Every JSON object from turns.jsonl in all unique multi-episode MAPs runs.",
        "episode_cost": "Every JSON object from episode_cost.jsonl in all unique multi-episode MAPs runs.",
        "park_id": "Every JSON object from park_ids.jsonl in all unique multi-episode MAPs runs.",
    }
    kind: Any
    name: Any
    for kind, name in DATASET_NAMES.items():
        rows = records[kind]
        if not rows:
            continue
        dataset = weave.Dataset(name=name, description=descriptions[kind], rows=rows)
        refs[name] = str(weave.publish(dataset))
    weave.finish()
    return refs


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search-root", type=Path, default=DEFAULT_SEARCH_ROOT)
    parser.add_argument("--entity", help="W&B entity; defaults to the authenticated account")
    parser.add_argument("--project", default=os.environ.get("WANDB_PROJECT", DEFAULT_PROJECT))
    parser.add_argument("--dry-run", action="store_true", help="inventory without uploading")
    parser.add_argument("--skip-runs", action="store_true", help="publish Weave datasets only")
    parser.add_argument("--skip-weave", action="store_true", help="create W&B runs/artifacts only")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    discovery = discover(args.search_root.resolve())
    runs = authoritative_runs(args.search_root.resolve())
    records = all_records(runs)
    print(
        f"Unique multi-episode runs: {len(runs)}; "
        f"excluded one-episode runs: {len(discovery.excluded_one_episode)}; "
        f"deduplicated worktree copies: {len(discovery.duplicate_directories)}"
    )
    print("Records: " + ", ".join(f"{kind}={len(rows)}" for kind, rows in records.items()))
    run: Any
    for run in runs:
        counts = _record_counts(run)
        print(
            f"{run.name}: episode_files={len(run.episode_files)}, "
            + ", ".join(f"{kind}={count}" for kind, count in counts.items())
        )
    directory: Any
    for directory in discovery.excluded_one_episode:
        print(f"Excluded one-episode run: {directory}")
    duplicate: Any
    original: Any
    for duplicate, original in discovery.duplicate_directories:
        print(f"Deduplicated identical copy: {duplicate} -> {original}")
    if args.dry_run:
        return 0

    import wandb

    entity = args.entity or os.environ.get("WANDB_ENTITY") or wandb.Api().default_entity
    if not entity:
        raise RuntimeError("could not determine W&B entity; pass --entity")
    os.environ.setdefault("WANDB_SILENT", "true")

    if not args.skip_runs:
        numbers = run_numbers(runs)
        index: Any
        run: Any
        for index, run in enumerate(runs, start=1):
            url, changed = upload_run(
                run,
                entity=entity,
                project=args.project,
                run_number=numbers[run.key],
            )
            action = "uploaded" if changed else "already current"
            print(f"W&B [{index}/{len(runs)}] {action}: {run.name} -> {url}")
    if not args.skip_weave:
        refs = publish_weave(records, entity=entity, project=args.project)
        name: Any
        ref: Any
        for name, ref in refs.items():
            print(
                f"Weave: {name} ({len(records[next(k for k, v in DATASET_NAMES.items() if v == name)])} rows) -> {ref}"
            )
    print(f"Project: https://wandb.ai/{entity}/{args.project}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
