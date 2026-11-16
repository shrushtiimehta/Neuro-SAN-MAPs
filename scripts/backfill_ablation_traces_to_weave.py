#!/usr/bin/env python3
# Local imports must follow the repo-root bootstrap when run as a script.
# ruff: noqa: E402
"""Backfill live-shaped episode/turn trace trees for historical MAPs runs."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import os
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.import_all_ablation_history_to_wandb import DEFAULT_PROJECT
from scripts.import_all_ablation_history_to_wandb import DEFAULT_SEARCH_ROOT
from scripts.import_all_ablation_history_to_wandb import RawRun
from scripts.import_all_ablation_history_to_wandb import _episode_number
from scripts.import_all_ablation_history_to_wandb import _run_id
from scripts.import_all_ablation_history_to_wandb import discover
from scripts.import_all_ablation_history_to_wandb import run_numbers
from scripts.import_all_ablation_history_to_wandb import trace_arm_label

from coded_tools import weave_telemetry

TRACE_V2_RUN_KEYS = frozenset(
    {
        "baseline-original",
        "embedded-player-planner-watcher",
        "planner-only",
        "watcher-only",
        "unstructured-planning",
        "solo-1",
        "solo-2",
        "solo-3",
    }
)


@dataclass(frozen=True)
class EpisodeTrace:
    episode_index: int
    trajectory_file: str
    trajectory: tuple[dict[str, Any], ...]
    turns: tuple[tuple[int, dict[str, Any]], ...]
    episode_cost: dict[str, Any] | None
    park_id: dict[str, Any] | None

    @property
    def complete(self) -> bool:
        if not self.trajectory:
            return False
        last = self.trajectory[-1]
        return bool(last.get("done")) or int(last.get("step") or 0) >= 100


def episode_traces(run: RawRun) -> tuple[EpisodeTrace, ...]:
    """Join raw trajectory, turn, cost, and park-ID rows by episode."""
    turns: dict[int, list[tuple[int, dict[str, Any]]]] = {}
    costs: dict[int, list[dict[str, Any]]] = {}
    parks: dict[int, list[dict[str, Any]]] = {}
    file: Any
    for file in run.files:
        if file.name == "turns.jsonl":
            line_number: Any
            row: Any
            for line_number, row in enumerate(file.rows, start=1):
                verified = row.get("verified_after") or {}
                if isinstance(verified, dict) and verified.get("episode") is not None:
                    turns.setdefault(int(verified["episode"]), []).append((line_number, row))
        elif file.name == "episode_cost.jsonl":
            row: Any
            for row in file.rows:
                if row.get("episode") is not None:
                    costs.setdefault(int(row["episode"]), []).append(row)
        elif file.name == "park_ids.jsonl":
            row: Any
            for row in file.rows:
                value = row.get("run_episode", row.get("episode"))
                if value is not None:
                    parks.setdefault(int(value), []).append(row)

    result: list[EpisodeTrace] = []
    file: Any
    for file in run.episode_files:
        fallback = _episode_number(file.name)
        # The filename is authoritative within a run. Trusting an embedded
        # legacy episode value can collapse several files into Episode 1.
        episode_index = fallback
        result.append(
            EpisodeTrace(
                episode_index=episode_index,
                trajectory_file=file.name,
                trajectory=file.rows,
                turns=tuple(turns.get(episode_index, [])),
                # Current sidecars can contain archived rows followed by the
                # current run. The latest matching row is the relevant one.
                episode_cost=costs.get(episode_index, [None])[-1],
                park_id=parks.get(episode_index, [None])[-1],
            )
        )
    return tuple(sorted(result, key=lambda episode: episode.episode_index))


def _call_id(run: RawRun, episode_index: int, child: str = "root") -> str:
    identity = (
        f"wandb://maps-park/{run.key}/{run.fingerprint}/episode/{episode_index}/{child}/{weave_telemetry.TRACE_SCHEMA}"
    )
    if run.key in TRACE_V2_RUN_KEYS:
        legacy_run_id = "hist" + hashlib.sha256(f"history-v2:{run.key}".encode()).hexdigest()[:12]
        identity += f"/history-v2/{legacy_run_id}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, identity))


def _trace_times(episode: EpisodeTrace) -> tuple[dt.datetime, dt.datetime]:
    if episode.turns:
        pairs = [weave_telemetry.turn_times(row) for _line, row in episode.turns]
        started_at = min(pair[0] for pair in pairs)
        ended_at = max(pair[1] for pair in pairs)
    else:
        started_at = ended_at = dt.datetime.now(tz=dt.timezone.utc)
    if episode.episode_cost:
        cost_time = weave_telemetry.utc_timestamp(episode.episode_cost.get("wall_time"), ended_at)
        ended_at = max(ended_at, cost_time)
    return started_at, ended_at


def backfill_run(client: Any, run: RawRun, *, entity: str, project: str, run_number: int) -> tuple[int, int]:
    """Create all episode roots and turn children for one raw run snapshot."""
    metadata = {
        "source_run_key": run.key,
        "source_run_name": run.name,
        "source_path": str(run.directory),
        "source_fingerprint": run.fingerprint,
        "wandb_run_id": _run_id(run),
        "wandb_run_path": f"{entity}/{project}/{_run_id(run)}",
        "ablation_arm": run.arm,
        "trace_label": trace_arm_label(run),
        "run_number": run_number,
    }
    roots = 0
    children = 0
    episode: Any
    for episode in episode_traces(run):
        started_at, ended_at = _trace_times(episode)
        parent = weave_telemetry.create_episode_call(
            client,
            run_metadata=metadata,
            episode_index=episode.episode_index,
            started_at=started_at,
            historical=True,
            call_id=_call_id(run, episode.episode_index),
            display_name=weave_telemetry.episode_display_name(metadata, episode.episode_index),
            episode_inputs={
                "trajectory_file": episode.trajectory_file,
                "park": episode.park_id,
            },
        )
        roots += 1
        source_line: Any
        turn: Any
        for source_line, turn in episode.turns:
            weave_telemetry.create_turn_call(
                client,
                parent=parent,
                run_metadata=metadata,
                episode_index=episode.episode_index,
                record=turn,
                historical=True,
                call_id=_call_id(run, episode.episode_index, f"turn-{source_line}"),
            )
            children += 1
        last_step = episode.trajectory[-1] if episode.trajectory else None
        weave_telemetry.finish_episode_call(
            client,
            parent,
            last_step=last_step,
            episode_summary=episode.episode_cost,
            complete=episode.complete,
            turn_count=len(episode.turns),
            ended_at=ended_at,
        )
    return roots, children


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search-root", type=Path, default=DEFAULT_SEARCH_ROOT)
    parser.add_argument("--entity", help="W&B entity; defaults to the authenticated account")
    parser.add_argument("--project", default=os.environ.get("WANDB_PROJECT", DEFAULT_PROJECT))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    discovery = discover(args.search_root.resolve())
    total_roots = sum(len(episode_traces(run)) for run in discovery.runs)
    total_children = sum(len(episode.turns) for run in discovery.runs for episode in episode_traces(run))
    print(
        f"Trace plan: runs={len(discovery.runs)}, episode_roots={total_roots}, "
        f"turn_children={total_children}, total_calls={total_roots + total_children}"
    )
    if args.dry_run:
        return 0

    import wandb
    import weave

    entity = args.entity or os.environ.get("WANDB_ENTITY") or wandb.Api().default_entity
    if not entity:
        raise RuntimeError("could not determine W&B entity; pass --entity")
    os.environ.setdefault("WANDB_SILENT", "true")
    client = weave.init(f"{entity}/{args.project}")
    api = wandb.Api(timeout=60)
    uploaded_roots = 0
    uploaded_children = 0
    skipped = 0
    existing_root_ids = {call.id for call in client.get_calls(filter={"trace_roots_only": True}, page_size=1000)}
    numbers = run_numbers(discovery.runs)
    index: Any
    run: Any
    for index, run in enumerate(discovery.runs, start=1):
        api.run(f"{entity}/{args.project}/{_run_id(run)}")
        expected_root_ids = {_call_id(run, episode.episode_index) for episode in episode_traces(run)}
        if expected_root_ids.issubset(existing_root_ids):
            skipped += 1
            print(f"Trace [{index}/{len(discovery.runs)}] already current: {run.name}")
            continue
        roots, children = backfill_run(
            client,
            run,
            entity=entity,
            project=args.project,
            run_number=numbers[run.key],
        )
        client.flush()
        existing_root_ids.update(expected_root_ids)
        uploaded_roots += roots
        uploaded_children += children
        print(f"Trace [{index}/{len(discovery.runs)}] uploaded: {run.name}: roots={roots}, children={children}")
    client.finish(use_progress_bar=False)
    print(f"Backfill complete: roots={uploaded_roots}, children={uploaded_children}, runs_skipped={skipped}")
    print(f"Traces: https://wandb.ai/{entity}/{args.project}/weave/traces")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
