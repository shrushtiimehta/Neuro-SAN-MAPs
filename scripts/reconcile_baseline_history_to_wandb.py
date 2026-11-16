#!/usr/bin/env python3
# Local imports must follow the repo-root bootstrap when run as a script.
# ruff: noqa: E402
"""Make W&B baseline history exactly match the retained primary archives."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any
from typing import Iterable

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
from scripts.import_all_ablation_history_to_wandb import SnapshotFile
from scripts.import_all_ablation_history_to_wandb import _display_name
from scripts.import_all_ablation_history_to_wandb import _episode_number
from scripts.import_all_ablation_history_to_wandb import _fingerprint
from scripts.import_all_ablation_history_to_wandb import _run_id
from scripts.import_all_ablation_history_to_wandb import _snapshot_file
from scripts.import_all_ablation_history_to_wandb import _source_key
from scripts.import_all_ablation_history_to_wandb import all_records
from scripts.import_all_ablation_history_to_wandb import discover
from scripts.import_all_ablation_history_to_wandb import publish_weave
from scripts.import_all_ablation_history_to_wandb import trace_arm_label
from scripts.import_all_ablation_history_to_wandb import upload_run


def _rows_snapshot(name: str, rows: Iterable[dict[str, Any]]) -> SnapshotFile:
    materialized = tuple(rows)
    data = "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in materialized).encode(
        "utf-8"
    )
    return SnapshotFile(name=name, data=data, rows=materialized)


def _completed_signature(run: RawRun) -> tuple[tuple[int, float], ...]:
    signature: list[tuple[int, float]] = []
    file: Any
    for file in run.episode_files:
        if not file.rows:
            continue
        last = file.rows[-1]
        if bool(last.get("done")) or int(last.get("step") or 0) >= 100:
            reward = last.get("cumulative_reward")
            if reward is None:
                raise ValueError(f"completed {run.directory / file.name} has no reward")
            signature.append((_episode_number(file.name), float(reward)))
    return tuple(signature)


def authoritative_baseline_runs(repo_root: Path = ROOT) -> tuple[RawRun, ...]:
    """Build baseline runs and attach only ledger rows proven to belong to each."""
    log_root = repo_root / "logs" / "maps_park"
    prior_root = log_root / "prior-runs"
    if not prior_root.is_dir():
        raise FileNotFoundError(prior_root)

    base_runs: list[RawRun] = []
    directory: Any
    for directory in sorted(path for path in prior_root.iterdir() if path.is_dir()):
        episode_paths = sorted(directory.glob("run.ep*.jsonl"), key=lambda path: _episode_number(path.name))
        if len(episode_paths) <= 1:
            continue
        expected_numbers = list(range(len(episode_paths)))
        actual_numbers = [_episode_number(path.name) for path in episode_paths]
        if actual_numbers != expected_numbers:
            raise ValueError(f"non-contiguous episode files in {directory}: {actual_numbers}")
        paths = episode_paths
        turns = directory / "turns.jsonl"
        if turns.is_file():
            paths.append(turns)
        files = tuple(_snapshot_file(path) for path in paths)
        base_runs.append(
            RawRun(
                key=_source_key(directory),
                name=_display_name(directory),
                arm="baseline",
                directory=directory.resolve(),
                files=files,
                fingerprint=_fingerprint(files),
            )
        )
    if not base_runs:
        raise ValueError(f"no retained multi-episode baselines found in {prior_root}")

    # Park IDs have an exact identity key in each retained TSV filename.
    park_file = _snapshot_file(log_root / "park_ids.jsonl")
    park_by_id: dict[str, dict[str, Any]] = {}
    row: Any
    for row in park_file.rows:
        park_id = str(row.get("park_id") or "")
        if not park_id or park_id in park_by_id:
            raise ValueError(f"missing or duplicate park ID in {log_root / 'park_ids.jsonl'}")
        park_by_id[park_id] = row

    run_park_rows: dict[str, tuple[dict[str, Any], ...]] = {}
    retained_ids: set[str] = set()
    run: Any
    for run in base_runs:
        ids = [path.stem.rsplit("_", 1)[0] for path in sorted(run.directory.glob("*.tsv"))]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate TSV park IDs in {run.directory}")
        unknown = sorted(set(ids) - set(park_by_id))
        if unknown:
            raise ValueError(f"TSV park IDs missing from ledger in {run.directory}: {unknown}")
        rows = tuple(row for row in park_file.rows if row.get("park_id") in set(ids))
        run_episodes = [int(row.get("run_episode", -1)) for row in rows]
        if run_episodes != list(range(len(rows))):
            raise ValueError(f"park ledger order mismatch in {run.directory}: {run_episodes}")
        run_park_rows[run.key] = rows
        retained_ids.update(ids)
    if retained_ids != set(park_by_id):
        raise ValueError(
            "park ledger does not exactly equal retained baseline TSVs: "
            f"unmatched={sorted(set(park_by_id) - retained_ids)}"
        )

    # Cost rows lack a run ID, so match each reset-delimited sequence to the
    # unique retained run with identical completed episode endpoints.
    cost_file = _snapshot_file(log_root / "episode_cost.jsonl")
    cost_groups: list[list[dict[str, Any]]] = []
    row: Any
    for row in cost_file.rows:
        if not cost_groups or int(row.get("episode", -1)) == 0:
            cost_groups.append([])
        cost_groups[-1].append(row)
    costs_by_key: dict[str, tuple[dict[str, Any], ...]] = {}
    signatures = {run.key: _completed_signature(run) for run in base_runs}
    group: Any
    for group in cost_groups:
        signature = tuple((int(row["episode"]), float(row["final_reward"])) for row in group)
        matches = [key for key, candidate in signatures.items() if candidate == signature]
        if len(matches) != 1:
            raise ValueError(f"cost sequence has {len(matches)} retained matches: {signature} -> {matches}")
        key = matches[0]
        if key in costs_by_key:
            raise ValueError(f"multiple cost sequences matched {key}")
        costs_by_key[key] = tuple(group)

    enriched: list[RawRun] = []
    run: Any
    for run in base_runs:
        files = list(run.files)
        if rows := costs_by_key.get(run.key):
            files.append(_rows_snapshot("episode_cost.jsonl", rows))
        files.append(_rows_snapshot("park_ids.jsonl", run_park_rows[run.key]))
        frozen_files = tuple(files)
        enriched.append(
            RawRun(
                key=run.key,
                name=run.name,
                arm=run.arm,
                directory=run.directory,
                files=frozen_files,
                fingerprint=_fingerprint(frozen_files),
            )
        )
    return tuple(enriched)


def _is_baseline_api_run(run: Any) -> bool:
    if run.job_type == "episode":
        return False
    config = dict(run.config or {})
    ablation = str(config.get("Ablation") or config.get("ablation_arm") or "")
    return ablation.casefold() == "baseline" or str(run.group).casefold() == "baseline"


def _is_baseline_root(call: Any) -> bool:
    attributes = dict(call.attributes or {})
    maps = dict(attributes.get("maps") or {})
    source_path = str(maps.get("source_path") or "")
    return (
        maps.get("ablation_arm") in {"baseline", "state"}
        or maps.get("trace_label") == "Baseline"
        or "/logs/maps_park/" in source_path
    )


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
        expected: dict[str, str] = {}
        episode: Any
        for episode in episode_traces(run):
            expected[_call_id(run, episode.episode_index)] = (
                f"Baseline • Run {numbers[run.key]} • Episode {episode.episode_index + 1}"
            )
        correct = len(actual) == len(expected)
        call: Any
        for call in actual:
            attributes = dict(call.attributes or {})
            maps = dict(attributes.get("maps") or {})
            correct = correct and (
                call.id in expected
                and call.display_name == expected.get(call.id)
                and maps.get("source_fingerprint") == run.fingerprint
                and int(maps.get("run_number") or 0) == numbers[run.key]
            )
        if not correct:
            stale.extend(actual)
            rebuild.append(run)
    # Preserve order while removing any overlap from malformed groups.
    stale_by_id = {call.id: call for call in stale}
    return list(stale_by_id.values()), tuple(rebuild)


def _chunks(values: list[str], size: int = 100) -> Iterable[list[str]]:
    index: Any
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--search-root", type=Path, default=DEFAULT_SEARCH_ROOT)
    parser.add_argument("--entity")
    parser.add_argument("--project", default=os.environ.get("WANDB_PROJECT", DEFAULT_PROJECT))
    parser.add_argument("--apply", action="store_true", help="perform the planned changes")
    parser.add_argument("--skip-datasets", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    runs = authoritative_baseline_runs(args.repo_root.resolve())
    numbers = {run.key: number for number, run in enumerate(runs, start=1)}
    if runs[-1].directory.name != "20260820-234115":
        raise ValueError(f"unexpected final retained baseline: {runs[-1].directory}; expected 20260820-234115")

    import wandb
    import weave

    entity = args.entity or os.environ.get("WANDB_ENTITY") or wandb.Api().default_entity
    if not entity:
        raise RuntimeError("could not determine W&B entity; pass --entity")
    os.environ.setdefault("WANDB_SILENT", "true")
    project_path = f"{entity}/{args.project}"

    api = wandb.Api(timeout=60)
    remote_baselines = [run for run in api.runs(project_path) if _is_baseline_api_run(run)]
    expected_ids = {_run_id(run) for run in runs}
    obsolete_runs = [run for run in remote_baselines if run.id not in expected_ids]

    client = weave.init(project_path)
    baseline_roots = [
        call for call in client.get_calls(filter={"trace_roots_only": True}, page_size=1000) if _is_baseline_root(call)
    ]
    stale_roots, rebuild_runs = _trace_reconciliation(baseline_roots, runs, numbers)
    client.finish(use_progress_bar=False)

    print(f"Authoritative baselines: {len(runs)}")
    run: Any
    for run in runs:
        counts = {file.name: len(file.rows) for file in run.files}
        print(
            f"  Run {numbers[run.key]}: {run.directory.name}: "
            f"episodes={len(run.episode_files)}, costs={counts.get('episode_cost.jsonl', 0)}, "
            f"parks={counts.get('park_ids.jsonl', 0)}"
        )
    print(f"Obsolete W&B baseline runs to delete: {len(obsolete_runs)}")
    run: Any
    for run in obsolete_runs:
        print(f"  {run.id}: {run.name}: {dict(run.config or {}).get('source_path')}")
    print(f"Stale baseline trace roots to delete: {len(stale_roots)}; retained runs to rebuild: {len(rebuild_runs)}")
    if not args.apply:
        print("Dry run only; pass --apply to reconcile W&B.")
        return 0

    if stale_roots:
        client = weave.init(project_path)
        chunk: Any
        for chunk in _chunks([call.id for call in stale_roots]):
            client.delete_calls(chunk)
        client.finish(use_progress_bar=False)
        print(f"Deleted {len(stale_roots)} stale baseline trace roots and their children")

    run: Any
    for run in obsolete_runs:
        run.delete(delete_artifacts=True)
        print(f"Deleted obsolete W&B baseline: {run.id} ({run.name})")

    changed = 0
    index: Any
    run: Any
    for index, run in enumerate(runs, start=1):
        url, uploaded = upload_run(run, entity=entity, project=args.project, run_number=numbers[run.key])
        changed += int(uploaded)
        print(f"W&B baseline [{index}/{len(runs)}]: {url}")

    if not args.skip_datasets:
        discovery = discover(args.search_root.resolve())
        non_baselines = tuple(run for run in discovery.runs if run.arm != "baseline")
        records = all_records(non_baselines + runs)
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
                print(f"Traces Run {numbers[run.key]}: roots={root_count}, children={child_count}")
            finally:
                wb_run.finish()
        client.finish(use_progress_bar=False)

    # Verify the externally visible W&B run set and every baseline trace title.
    verify_api = wandb.Api(timeout=60)
    actual_runs = [run for run in verify_api.runs(project_path) if _is_baseline_api_run(run)]
    actual_ids = {run.id for run in actual_runs}
    if actual_ids != expected_ids:
        raise RuntimeError(f"post-sync W&B baseline mismatch: expected={expected_ids}, actual={actual_ids}")
    by_id = {run.id: run for run in actual_runs}
    run: Any
    for run in runs:
        expected_name = f"{trace_arm_label(run)} • Run {numbers[run.key]}"
        actual = by_id[_run_id(run)]
        if actual.name != expected_name:
            raise RuntimeError(f"post-sync run name mismatch for {run.directory}: {actual.name!r}")

    verify_client = weave.init(project_path)
    verify_roots = [
        call
        for call in verify_client.get_calls(filter={"trace_roots_only": True}, page_size=1000)
        if _is_baseline_root(call)
    ]
    remaining_stale, remaining_rebuild = _trace_reconciliation(verify_roots, runs, numbers)
    verify_client.finish(use_progress_bar=False)
    if remaining_stale or remaining_rebuild:
        raise RuntimeError(
            f"post-sync baseline trace mismatch: stale={len(remaining_stale)}, rebuild={len(remaining_rebuild)}"
        )
    print(f"Verified: {len(actual_runs)} baseline W&B runs and {len(verify_roots)} correctly numbered episode traces")
    print(f"Runs: https://wandb.ai/{entity}/{args.project}")
    print(f"Traces: https://wandb.ai/{entity}/{args.project}/weave/traces")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
