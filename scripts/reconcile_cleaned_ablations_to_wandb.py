#!/usr/bin/env python3
# Local imports must follow the repo-root bootstrap when run as a script.
# ruff: noqa: E402
"""Reconcile cleaned Planner, Watcher, Unstructured, and Solo runs to W&B."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from scripts.backfill_ablation_traces_to_weave import _call_id
from scripts.backfill_ablation_traces_to_weave import backfill_run
from scripts.backfill_ablation_traces_to_weave import episode_traces
from scripts.import_all_ablation_history_to_wandb import DEFAULT_PROJECT
from scripts.import_all_ablation_history_to_wandb import DEFAULT_SEARCH_ROOT
from scripts.import_all_ablation_history_to_wandb import ROOT
from scripts.import_all_ablation_history_to_wandb import RawRun
from scripts.import_all_ablation_history_to_wandb import _display_name
from scripts.import_all_ablation_history_to_wandb import _episode_number
from scripts.import_all_ablation_history_to_wandb import _fingerprint
from scripts.import_all_ablation_history_to_wandb import _run_id
from scripts.import_all_ablation_history_to_wandb import _snapshot_file
from scripts.import_all_ablation_history_to_wandb import _source_key
from scripts.import_all_ablation_history_to_wandb import all_records
from scripts.import_all_ablation_history_to_wandb import discover
from scripts.import_all_ablation_history_to_wandb import publish_weave
from scripts.import_all_ablation_history_to_wandb import run_numbers
from scripts.import_all_ablation_history_to_wandb import trace_arm_label
from scripts.import_all_ablation_history_to_wandb import upload_run
from scripts.reconcile_baseline_history_to_wandb import _chunks
from scripts.reconcile_baseline_history_to_wandb import _completed_signature
from scripts.reconcile_baseline_history_to_wandb import _rows_snapshot
from scripts.reconcile_baseline_history_to_wandb import authoritative_baseline_runs

ARM_ROOTS = {
    "planner_only": "logs/maps_ablation_player_with_planner",
    "watcher_only": "logs/maps_ablation_player_with_watcher",
    "unstructured_planning": "logs/maps_ablation_unstructured_player_planner_watcher",
    "solo_ablation": "logs/maps_park_solo",
}
ARM_ALIASES = {
    "player_with_planner": "planner_only",
    "player_with_watcher": "watcher_only",
    "unstructured_player_planner_watcher": "unstructured_planning",
    "state_solo": "solo_ablation",
    "state_single_agent": "solo_ablation",
    "Planner": "planner_only",
    "Watcher": "watcher_only",
    "Unstructured": "unstructured_planning",
    "Single Agent": "solo_ablation",
}
TARGET_ARMS = frozenset(ARM_ROOTS)


def _canonical_arm(value: Any) -> str:
    arm = str(value or "")
    return ARM_ALIASES.get(arm, arm)


def _retained_directories(root: Path) -> tuple[Path, ...]:
    directories: list[Path] = []
    prior = root / "prior-runs"
    if prior.is_dir():
        directories.extend(sorted(path for path in prior.iterdir() if path.is_dir()))
    directories.append(root)
    return tuple(directory for directory in directories if len(tuple(directory.glob("run.ep*.jsonl"))) > 1)


def _base_run(directory: Path, arm: str) -> RawRun:
    episode_paths = sorted(directory.glob("run.ep*.jsonl"), key=lambda path: _episode_number(path.name))
    numbers = [_episode_number(path.name) for path in episode_paths]
    if numbers != list(range(len(numbers))):
        raise ValueError(f"non-contiguous episode files in {directory}: {numbers}")
    turns = directory / "turns.jsonl"
    if not turns.is_file():
        raise ValueError(f"retained run has no turns.jsonl: {directory}")
    files = tuple(_snapshot_file(path) for path in [*episode_paths, turns])
    return RawRun(
        key=_source_key(directory),
        name=_display_name(directory),
        arm=arm,
        directory=directory.resolve(),
        files=files,
        fingerprint=_fingerprint(files),
    )


def _enrich_arm(root: Path, arm: str) -> tuple[RawRun, ...]:
    runs = tuple(_base_run(directory, arm) for directory in _retained_directories(root))
    if not runs:
        raise ValueError(f"no retained multi-episode runs in {root}")

    park_file = _snapshot_file(root / "park_ids.jsonl")
    park_by_id: dict[str, dict[str, Any]] = {}
    row: Any
    for row in park_file.rows:
        park_id = str(row.get("park_id") or "")
        if not park_id or park_id in park_by_id:
            raise ValueError(f"missing or duplicate park ID in {root / 'park_ids.jsonl'}")
        park_by_id[park_id] = row

    parks_by_key: dict[str, tuple[dict[str, Any], ...]] = {}
    retained_ids: set[str] = set()
    run: Any
    for run in runs:
        ids = [path.stem.rsplit("_", 1)[0] for path in sorted(run.directory.glob("*.tsv"))]
        unknown = sorted(set(ids) - set(park_by_id))
        if len(ids) != len(set(ids)) or unknown:
            raise ValueError(f"invalid TSV-to-park mapping in {run.directory}: {unknown}")
        id_set = set(ids)
        rows = tuple(row for row in park_file.rows if row.get("park_id") in id_set)
        run_episodes = [int(row.get("run_episode", -1)) for row in rows]
        if run_episodes != list(range(len(rows))):
            raise ValueError(f"park ledger order mismatch in {run.directory}: {run_episodes}")
        parks_by_key[run.key] = rows
        retained_ids.update(ids)
    if retained_ids != set(park_by_id):
        raise ValueError(
            f"park ledger does not equal retained TSVs in {root}: unmatched={sorted(set(park_by_id) - retained_ids)}"
        )

    cost_file = _snapshot_file(root / "episode_cost.jsonl")
    cost_groups: list[list[dict[str, Any]]] = []
    row: Any
    for row in cost_file.rows:
        if not cost_groups or int(row.get("episode", -1)) == 0:
            cost_groups.append([])
        cost_groups[-1].append(row)
    signatures = {run.key: _completed_signature(run) for run in runs}
    costs_by_key: dict[str, tuple[dict[str, Any], ...]] = {}
    group: Any
    for group in cost_groups:
        signature = tuple((int(row["episode"]), float(row["final_reward"])) for row in group)
        matches = [key for key, candidate in signatures.items() if candidate == signature]
        if len(matches) != 1:
            raise ValueError(f"cost sequence has {len(matches)} retained matches in {root}: {signature} -> {matches}")
        key = matches[0]
        if key in costs_by_key:
            raise ValueError(f"multiple cost groups matched {key}")
        costs_by_key[key] = tuple(group)

    enriched: list[RawRun] = []
    run: Any
    for run in runs:
        files = list(run.files)
        if rows := costs_by_key.get(run.key):
            files.append(_rows_snapshot("episode_cost.jsonl", rows))
        files.append(_rows_snapshot("park_ids.jsonl", parks_by_key[run.key]))
        frozen = tuple(files)
        enriched.append(
            RawRun(
                key=run.key,
                name=run.name,
                arm=run.arm,
                directory=run.directory,
                files=frozen,
                fingerprint=_fingerprint(frozen),
            )
        )
    return tuple(enriched)


def authoritative_ablation_runs(repo_root: Path = ROOT) -> tuple[RawRun, ...]:
    runs: list[RawRun] = []
    arm: Any
    relative_root: Any
    for arm, relative_root in ARM_ROOTS.items():
        runs.extend(_enrich_arm(repo_root / relative_root, arm))
    keys = [run.key for run in runs]
    if len(keys) != len(set(keys)):
        raise ValueError(f"duplicate authoritative run keys: {keys}")
    return tuple(runs)


def _api_arm(run: Any) -> str:
    if run.job_type == "episode":
        return ""
    config = dict(run.config or {})
    return _canonical_arm(config.get("Ablation") or config.get("ablation_arm") or run.group)


def _call_arm(call: Any) -> str:
    attributes = dict(call.attributes or {})
    maps = dict(attributes.get("maps") or {})
    return _canonical_arm(maps.get("ablation_arm"))


def _trace_reconciliation(
    roots: list[Any], runs: tuple[RawRun, ...], numbers: dict[str, int]
) -> tuple[list[Any], tuple[RawRun, ...]]:
    by_path: dict[str | None, list[Any]] = defaultdict(list)
    call: Any
    for call in roots:
        attributes = dict(call.attributes or {})
        maps = dict(attributes.get("maps") or {})
        by_path[maps.get("source_path")].append(call)

    stale: list[Any] = []
    rebuild: list[RawRun] = []
    authoritative_paths = {str(run.directory) for run in runs}
    path: Any
    calls: Any
    for path, calls in by_path.items():
        if path not in authoritative_paths:
            stale.extend(calls)

    run: Any
    for run in runs:
        actual = by_path.get(str(run.directory), [])
        expected = {
            _call_id(run, episode.episode_index): (
                f"{trace_arm_label(run)} • Run {numbers[run.key]} • Episode {episode.episode_index + 1}"
            )
            for episode in episode_traces(run)
        }
        correct = len(actual) == len(expected)
        call: Any
        for call in actual:
            attributes = dict(call.attributes or {})
            maps = dict(attributes.get("maps") or {})
            correct = correct and (
                call.id in expected
                and call.display_name == expected.get(call.id)
                and _call_arm(call) == run.arm
                and maps.get("source_fingerprint") == run.fingerprint
                and int(maps.get("run_number") or 0) == numbers[run.key]
            )
        if not correct:
            stale.extend(actual)
            rebuild.append(run)
    stale_by_id = {call.id: call for call in stale}
    return list(stale_by_id.values()), tuple(rebuild)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--search-root", type=Path, default=DEFAULT_SEARCH_ROOT)
    parser.add_argument("--entity")
    parser.add_argument("--project", default=os.environ.get("WANDB_PROJECT", DEFAULT_PROJECT))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--skip-datasets", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    repo_root = args.repo_root.resolve()
    runs = authoritative_ablation_runs(repo_root)
    numbers = run_numbers(runs)

    import wandb
    import weave

    entity = args.entity or os.environ.get("WANDB_ENTITY") or wandb.Api().default_entity
    if not entity:
        raise RuntimeError("could not determine W&B entity; pass --entity")
    os.environ.setdefault("WANDB_SILENT", "true")
    project_path = f"{entity}/{args.project}"

    api = wandb.Api(timeout=60)
    remote_target = [run for run in api.runs(project_path) if _api_arm(run) in TARGET_ARMS]
    expected_ids = {_run_id(run) for run in runs}
    obsolete_runs = [run for run in remote_target if run.id not in expected_ids]

    client = weave.init(project_path)
    target_roots = [
        call
        for call in client.get_calls(filter={"trace_roots_only": True}, page_size=1000)
        if _call_arm(call) in TARGET_ARMS
    ]
    stale_roots, rebuild_runs = _trace_reconciliation(target_roots, runs, numbers)
    client.finish(use_progress_bar=False)

    print(f"Authoritative target runs: {len(runs)}")
    run: Any
    for run in runs:
        counts = {file.name: len(file.rows) for file in run.files}
        print(
            f"  {trace_arm_label(run)} Run {numbers[run.key]}: {run.directory}: "
            f"episodes={len(run.episode_files)}, costs={counts.get('episode_cost.jsonl', 0)}, "
            f"parks={counts.get('park_ids.jsonl', 0)}, "
            f"turns={counts.get('turns.jsonl', 0)}"
        )
    print(f"Obsolete target W&B runs to delete: {len(obsolete_runs)}")
    run: Any
    for run in obsolete_runs:
        print(f"  {run.id}: {run.name}: {dict(run.config or {}).get('source_path')}")
    print(f"Stale target trace roots to delete: {len(stale_roots)}; retained runs to rebuild: {len(rebuild_runs)}")
    if not args.apply:
        print("Dry run only; pass --apply to reconcile W&B.")
        return 0

    if stale_roots:
        client = weave.init(project_path)
        chunk: Any
        for chunk in _chunks([call.id for call in stale_roots]):
            client.delete_calls(chunk)
        client.finish(use_progress_bar=False)
        print(f"Deleted {len(stale_roots)} stale target trace roots and their children")

    run: Any
    for run in obsolete_runs:
        run.delete(delete_artifacts=True)
        print(f"Deleted obsolete target W&B run: {run.id} ({run.name})")

    index: Any
    run: Any
    for index, run in enumerate(runs, start=1):
        url, changed = upload_run(run, entity=entity, project=args.project, run_number=numbers[run.key])
        action = "updated" if changed else "already current"
        print(f"W&B target [{index}/{len(runs)}] {action}: {url}")

    if not args.skip_datasets:
        baselines = authoritative_baseline_runs(repo_root)
        discovery = discover(args.search_root.resolve())
        others = tuple(run for run in discovery.runs if run.arm != "baseline" and run.arm not in TARGET_ARMS)
        records = all_records(baselines + runs + others)
        refs = publish_weave(records, entity=entity, project=args.project)
        print("Published current datasets: " + ", ".join(f"{name}={ref}" for name, ref in refs.items()))

    if rebuild_runs:
        client = weave.init(project_path)
        sync_dir = Path(tempfile.gettempdir()) / "maps-wandb-history"
        sync_dir.mkdir(parents=True, exist_ok=True)
        run: Any
        for run in rebuild_runs:
            wb_run = wandb.init(
                entity=entity,
                project=args.project,
                id=_run_id(run),
                resume="allow",
                dir=str(sync_dir),
                mode="online",
                force=True,
                save_code=False,
            )
            if wb_run is None:
                raise RuntimeError(f"wandb.init returned no run for {run.name}")
            try:
                root_count, child_count = backfill_run(
                    client,
                    run,
                    entity=entity,
                    project=args.project,
                    run_number=numbers[run.key],
                )
                client.flush()
                print(
                    f"Traces {trace_arm_label(run)} Run {numbers[run.key]}: roots={root_count}, children={child_count}"
                )
            finally:
                wb_run.finish()
        client.finish(use_progress_bar=False)

    verify_api = wandb.Api(timeout=60)
    actual_runs = [run for run in verify_api.runs(project_path) if _api_arm(run) in TARGET_ARMS]
    if {run.id for run in actual_runs} != expected_ids:
        raise RuntimeError("post-sync target W&B run set does not match retained runs")
    by_id = {run.id: run for run in actual_runs}
    run: Any
    for run in runs:
        desired = f"{trace_arm_label(run)} • Run {numbers[run.key]}"
        if by_id[_run_id(run)].name != desired:
            raise RuntimeError(f"post-sync run name mismatch: {run.directory}")

    verify_client = weave.init(project_path)
    verify_roots = [
        call
        for call in verify_client.get_calls(filter={"trace_roots_only": True}, page_size=1000)
        if _call_arm(call) in TARGET_ARMS
    ]
    remaining_stale, remaining_rebuild = _trace_reconciliation(verify_roots, runs, numbers)
    verify_client.finish(use_progress_bar=False)
    if remaining_stale or remaining_rebuild:
        raise RuntimeError(f"post-sync trace mismatch: stale={len(remaining_stale)}, rebuild={len(remaining_rebuild)}")
    print(f"Verified: {len(actual_runs)} target W&B runs and {len(verify_roots)} correctly numbered episode traces")
    print(f"Runs: https://wandb.ai/{entity}/{args.project}")
    print(f"Traces: https://wandb.ai/{entity}/{args.project}/weave/traces")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
