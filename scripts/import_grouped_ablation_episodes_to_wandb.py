#!/usr/bin/env python3
# Local imports must follow the repo-root bootstrap when run as a script.
# ruff: noqa: E402
"""Create one W&B child run per episode, grouped by experimental run."""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from scripts.import_all_ablation_history_to_wandb import DEFAULT_PROJECT
from scripts.import_all_ablation_history_to_wandb import _api_run
from scripts.import_all_ablation_history_to_wandb import _history_rows
from scripts.import_all_ablation_history_to_wandb import authoritative_runs
from scripts.import_all_ablation_history_to_wandb import run_numbers
from scripts.import_all_ablation_history_to_wandb import trace_arm_label

EPISODE_RUN_SCHEMA = "episode-child-v5"
LEGACY_EPISODE_RUN_SCHEMAS = (
    "episode-child-v1",
    "episode-child-v2",
    "episode-child-v3",
    "episode-child-v4",
)
TURN_TOKEN_KEYS = {"total_tokens", "prompt_tokens", "completion_tokens"}
EPISODE_SCALAR_KEYS = (
    "cumulative_reward",
    "episode_cost/tokens",
    "episode_cost/llm_calls",
    "episode_cost/llm_seconds",
    "park/final_value",
)


def episode_run_id(run_key: str, episode: int, schema: str = EPISODE_RUN_SCHEMA) -> str:
    identity = f"{schema}:{run_key}:{episode}"
    return "ep" + hashlib.sha256(identity.encode()).hexdigest()[:14]


def episode_history(run: Any) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    expected = {int(file.name.removeprefix("run.ep").removesuffix(".jsonl")) + 1 for file in run.episode_files}
    row: Any
    for row in _history_rows(run):
        episode = row.get("episode")
        if episode is None:
            raise ValueError(f"history row without an episode in {run.directory}: {row}")
        grouped[int(episode)].append(row)
    if set(grouped) != expected:
        raise ValueError(
            f"episode partition mismatch for {run.directory}: expected={sorted(expected)}, actual={sorted(grouped)}"
        )
    return dict(sorted(grouped.items()))


def episode_scalar_values(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Return the useful one-value summary fields for an episode child."""
    values: dict[str, Any] = {}
    complete = any(bool(row.get("done")) or int(row.get("step") or 0) >= 100 for row in rows)
    row: Any
    for row in rows:
        key: Any
        for key in EPISODE_SCALAR_KEYS:
            if key == "cumulative_reward" and not complete:
                continue
            if row.get(key) is not None:
                values[key] = row[key]
    return values


def _define_metrics(wb_run: Any, rows: list[dict[str, Any]]) -> None:
    columns = {key for row in rows for key in row} - {"episode", "cumulative_reward"}
    wb_run.define_metric("episode", hidden=True, summary="none")
    wb_run.define_metric("step", hidden=True, summary="none")
    wb_run.define_metric("cumulative_reward", step_metric="step", summary="none")
    wb_run.define_metric("turn/number", hidden=True, summary="none")
    column: Any
    for column in sorted(columns):
        if column in {"step", "turn/number"}:
            continue
        if column in TURN_TOKEN_KEYS or column.startswith("turn/"):
            step_metric = "turn/number"
        elif column.startswith(("episode_cost/", "park/")):
            step_metric = "episode"
        else:
            step_metric = "step"
        wb_run.define_metric(column, step_metric=step_metric, summary="none")


def upload_episode(
    source: Any,
    *,
    episode: int,
    rows: list[dict[str, Any]],
    run_number: int,
    entity: str,
    project: str,
) -> tuple[str, bool]:
    import wandb

    label = trace_arm_label(source)
    group = f"{label} • Run {run_number}"
    name = f"{group} • Episode {episode}"
    run_id = episode_run_id(source.key, episode)
    path = f"{entity}/{project}/{run_id}"
    api_run = _api_run(wandb.Api(timeout=60), path)
    if api_run is not None:
        score_rows = list(api_run.scan_history(keys=["episode", "cumulative_reward"], page_size=1000))
        expected_scores = [
            (row["episode"], row["cumulative_reward"]) for row in rows if row.get("cumulative_reward") is not None
        ]
        actual_scores = [(row.get("episode"), row.get("cumulative_reward")) for row in score_rows]
        line_count = int(api_run._attrs.get("historyLineCount") or 0)
        if line_count != len(rows) or actual_scores != expected_scores:
            raise RuntimeError(f"episode history differs for {path}")
        changed = False
        if api_run.name != name or api_run.group != group:
            api_run.name = name
            api_run.group = group
            changed = True
        if api_run.config.get("Ablation") != label:
            api_run.config["Ablation"] = label
            changed = True
        if api_run.config.get("Run") != run_number:
            api_run.config["Run"] = run_number
            changed = True
        if api_run.config.get("Episode") != episode:
            api_run.config["Episode"] = episode
            changed = True
        key: Any
        value: Any
        for key, value in episode_scalar_values(rows).items():
            if api_run.summary.get(key) != value:
                api_run.summary[key] = value
                changed = True
        if changed:
            api_run.update()
        return api_run.url, changed

    sync_dir = Path(tempfile.gettempdir()) / "maps-wandb-history"
    sync_dir.mkdir(parents=True, exist_ok=True)
    complete = any(bool(row.get("done")) or int(row.get("step") or 0) >= 100 for row in rows)
    wb_run = wandb.init(
        entity=entity,
        project=project,
        id=run_id,
        resume="allow",
        name=name,
        group=group,
        job_type="episode",
        tags=[
            "maps-park",
            "ablation",
            source.arm,
            "complete" if complete else "partial",
        ],
        config={"Ablation": label, "Run": run_number, "Episode": episode},
        dir=str(sync_dir),
        mode="online",
        force=True,
        save_code=False,
    )
    if wb_run is None:
        raise RuntimeError(f"wandb.init returned no run for {name}")
    _define_metrics(wb_run, rows)
    row: Any
    for row in rows:
        wb_run.log(row)
    key: Any
    value: Any
    for key, value in episode_scalar_values(rows).items():
        wb_run.summary[key] = value
    trajectory_columns = {
        key
        for row in rows
        for key in row
        if key not in {"episode", *EPISODE_SCALAR_KEYS} and not key.startswith(("turn/", "episode_cost/", "park/"))
    }
    key: Any
    for key in list(dict(wb_run.summary)):
        if key in EPISODE_SCALAR_KEYS:
            continue
        if key in trajectory_columns or key.startswith(("turn/", "episode_cost/", "park/")):
            del wb_run.summary[key]
    url = wb_run.url
    wb_run.finish()
    return url, True


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entity")
    parser.add_argument("--project", default=os.environ.get("WANDB_PROJECT", DEFAULT_PROJECT))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    sources = authoritative_runs()
    numbers = run_numbers(sources)
    plan = [(source, episode, rows) for source in sources for episode, rows in episode_history(source).items()]
    print(
        f"Grouped episode plan: groups={len(sources)}, child_runs={len(plan)}, "
        f"history_rows={sum(len(rows) for _source, _episode, rows in plan)}"
    )
    if args.dry_run:
        return 0

    import wandb

    entity = args.entity or os.environ.get("WANDB_ENTITY") or wandb.Api().default_entity
    if not entity:
        raise RuntimeError("could not determine W&B entity; pass --entity")
    os.environ.setdefault("WANDB_SILENT", "true")
    index: Any
    source: Any
    episode: Any
    rows: Any
    for index, (source, episode, rows) in enumerate(plan, 1):
        url, changed = upload_episode(
            source,
            episode=episode,
            rows=rows,
            run_number=numbers[source.key],
            entity=entity,
            project=args.project,
        )
        action = "uploaded" if changed else "verified"
        print(f"[{index}/{len(plan)}] {action}: {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
