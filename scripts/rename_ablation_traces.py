#!/usr/bin/env python3
# Local imports must follow the repo-root bootstrap when run as a script.
# ruff: noqa: E402
"""Apply concise display names to all backfilled MAPs episode traces."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import wandb
import weave
from scripts.backfill_ablation_traces_to_weave import _call_id
from scripts.backfill_ablation_traces_to_weave import episode_traces
from scripts.import_all_ablation_history_to_wandb import DEFAULT_PROJECT
from scripts.import_all_ablation_history_to_wandb import DEFAULT_SEARCH_ROOT
from scripts.import_all_ablation_history_to_wandb import _run_id
from scripts.import_all_ablation_history_to_wandb import discover
from scripts.import_all_ablation_history_to_wandb import run_numbers
from scripts.import_all_ablation_history_to_wandb import trace_arm_label

from coded_tools import weave_telemetry


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search-root", type=Path, default=DEFAULT_SEARCH_ROOT)
    parser.add_argument("--entity")
    parser.add_argument("--project", default=os.environ.get("WANDB_PROJECT", DEFAULT_PROJECT))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    entity = args.entity or os.environ.get("WANDB_ENTITY") or wandb.Api().default_entity
    if not entity:
        raise RuntimeError("could not determine W&B entity; pass --entity")
    runs = discover(args.search_root.resolve()).runs
    numbers = run_numbers(runs)
    planned = sum(len(episode_traces(run)) for run in runs)
    print(f"Episode traces to rename: {planned}")
    if args.dry_run:
        return 0

    client = weave.init(f"{entity}/{args.project}")
    changed = 0
    renamed_runs = 0
    api = wandb.Api(timeout=60)
    run: Any
    for run in runs:
        desired_run_name = f"{trace_arm_label(run)} • Run {numbers[run.key]}"
        wb_run = api.run(f"{entity}/{args.project}/{_run_id(run)}")
        if wb_run.name != desired_run_name:
            wb_run.name = desired_run_name
            wb_run.update()
            renamed_runs += 1
        metadata = {
            "trace_label": trace_arm_label(run),
            "run_number": numbers[run.key],
            "ablation_arm": run.arm,
        }
        episode: Any
        for episode in episode_traces(run):
            call = client.get_call(_call_id(run, episode.episode_index))
            desired = weave_telemetry.episode_display_name(metadata, episode.episode_index)
            if call.display_name != desired:
                call.set_display_name(desired)
                changed += 1
    client.finish(use_progress_bar=False)
    print(f"Renamed {changed} episode traces")
    print(f"Renamed {renamed_runs} W&B runs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
