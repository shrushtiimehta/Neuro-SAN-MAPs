#!/usr/bin/env python3
"""Import the ablation chart's historical JSONL data into W&B and Weave.

The source files are treated as read-only recovery data.  Completed episodes
become historical W&B runs, while combined step, turn, and episode datasets are
published to Weave.  Stable run IDs and per-record keys make repeat imports
safe, including refreshes while the embedded arm is still running.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from typing import Iterable

try:
    from scripts.render_ablation_result_charts import PROVIDED_BASELINE
    from scripts.render_ablation_result_charts import RUNS
    from scripts.render_ablation_result_charts import SOLO_LOG_DIRS
except ModuleNotFoundError:  # Direct ``python scripts/...`` execution.
    from render_ablation_result_charts import PROVIDED_BASELINE
    from render_ablation_result_charts import RUNS
    from render_ablation_result_charts import SOLO_LOG_DIRS


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROJECT = "maps-park-ablations"
HISTORY_SCHEMA = "clean-v4"


@dataclass(frozen=True)
class Source:
    key: str
    name: str
    arm: str
    replicate: int
    log_dir: Path | None = None
    supplied_scores: dict[int, float] | None = None


@dataclass
class PreparedRun:
    source: Source
    steps: list[dict[str, Any]]
    turns: list[dict[str, Any]]
    episodes: list[dict[str, Any]]
    fingerprint: str


def _episode_number(path: Path) -> int:
    match = re.search(r"run\.ep(\d+)\.jsonl$", path.name)
    if match is None:
        raise ValueError(f"unexpected trajectory filename: {path}")
    return int(match.group(1))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        line_number: Any
        line: Any
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON in {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"expected a JSON object in {path}:{line_number}")
            rows.append(value)
    return rows


def _metadata(source: Source) -> dict[str, Any]:
    return {
        "ablation_arm": source.arm,
        "historical_run": source.name,
        "replicate": source.replicate,
        "source_kind": "supplied_scores" if source.supplied_scores else "legacy_jsonl",
    }


def _dataset_step(source: Source, row: dict[str, Any]) -> dict[str, Any]:
    episode_index = int(row.get("episode") or 0)
    episode_step = int(row.get("step") or 0)
    return {
        **_metadata(source),
        **row,
        "episode": episode_index + 1,
        "episode_index": episode_index,
        "episode_step": episode_step,
    }


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, (int, float)) else None


def _wandb_step(row: dict[str, Any]) -> dict[str, Any]:
    episode_index = int(row["episode_index"])
    episode_step = int(row["episode_step"])
    payload: dict[str, Any] = {
        "maps/record_type": "step",
        "maps/payload": json.dumps(
            {
                key: value
                for key, value in row.items()
                if key not in {"ablation_arm", "historical_run", "replicate", "source_kind"}
            },
            default=str,
            separators=(",", ":"),
            sort_keys=True,
        ),
        "episode": episode_index + 1,
        "episode_index": episode_index,
        "episode_step": episode_step,
        "step/action": row.get("action"),
        "step/rejected_action": row.get("rejected_action"),
        "step/done": bool(row.get("done")),
    }
    scalar_metrics = {
        "step/reward": row.get("reward"),
        "step/cumulative_score": row.get("cumulative_reward"),
        "step/cash": row.get("cash"),
        "step/park_value": row.get("park_value"),
        "step/park_rating": row.get("park_rating"),
        "step/num_rides": row.get("num_rides"),
        "step/num_shops": row.get("num_shops"),
        "step/num_staff": row.get("num_staff"),
        "step/min_uptime": row.get("min_uptime"),
        "step/min_cleanliness": row.get("min_cleanliness"),
        "step/shop_revenue": row.get("shop_revenue"),
        "step/ride_operating_cost": row.get("ride_op_cost"),
    }
    payload.update({key: number for key, raw in scalar_metrics.items() if (number := _number(raw)) is not None})
    return payload


def _normalize_turn(source: Source, row: dict[str, Any], line_index: int) -> dict[str, Any] | None:
    verified = row.get("verified_after") or {}
    if not isinstance(verified, dict) or verified.get("episode") is None:
        return None
    episode_index = int(verified["episode"])
    episode_step = int(verified.get("step") or 0)
    tokens = row.get("tokens") or {}
    if not isinstance(tokens, dict):
        tokens = {}
    return {
        **_metadata(source),
        "source_line": line_index,
        "wall_time": row.get("wall_time"),
        "episode": episode_index + 1,
        "episode_index": episode_index,
        "episode_step": episode_step,
        "turn": row.get("turn"),
        "attempts": row.get("attempts"),
        "succeeded": bool(row.get("turn_done")),
        "tokens": int(tokens.get("total_tokens") or 0),
        "llm_calls": int(tokens.get("successful_requests") or 0),
        "llm_seconds": float(tokens.get("time_taken_in_seconds") or 0.0),
        "estimated_cost_usd": float(tokens.get("total_cost") or 0.0),
    }


def _wandb_turn(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "maps/record_type": "turn",
        "maps/payload": json.dumps(
            {
                "wall_time": row.get("wall_time"),
                "turn": row.get("turn"),
                "attempts": row.get("attempts"),
                "turn_done": row.get("succeeded"),
            },
            default=str,
            separators=(",", ":"),
            sort_keys=True,
        ),
        "episode": row["episode"],
        "episode_index": row["episode_index"],
        "episode_step": row["episode_step"],
        "turn/number": row.get("turn"),
        "turn/attempts": row.get("attempts"),
        "turn/succeeded": row.get("succeeded"),
        "turn/tokens": row.get("tokens"),
        "turn/llm_calls": row.get("llm_calls"),
        "turn/llm_seconds": row.get("llm_seconds"),
        "turn/estimated_cost_usd": row.get("estimated_cost_usd"),
    }


def _wandb_episode(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "episode": row["episode"],
        "cumulative_reward": row["final_score"],
    }


def _fingerprint(events: Iterable[tuple[str, dict[str, Any]]]) -> str:
    digest = hashlib.sha256()
    key: Any
    event: Any
    for key, event in events:
        digest.update(key.encode())
        digest.update(json.dumps(event, default=str, sort_keys=True, separators=(",", ":")).encode())
    return digest.hexdigest()


def prepare(source: Source) -> PreparedRun:
    if source.supplied_scores is not None:
        episodes = [
            {
                **_metadata(source),
                "episode": episode_index + 1,
                "episode_index": episode_index,
                "final_score": float(score),
                "episode_steps": None,
            }
            for episode_index, score in sorted(source.supplied_scores.items())
        ]
        events = [(f"episode_summary:{row['episode_index']}", _wandb_episode(row)) for row in episodes]
        return PreparedRun(source, [], [], episodes, _fingerprint(events))

    if source.log_dir is None or not source.log_dir.is_dir():
        raise FileNotFoundError(f"historical source does not exist: {source.log_dir}")

    trajectory_rows: dict[int, list[dict[str, Any]]] = {}
    path: Any
    for path in sorted(source.log_dir.glob("run.ep*.jsonl"), key=_episode_number):
        rows = _read_jsonl(path)
        if not rows:
            continue
        last = rows[-1]
        complete = bool(last.get("done")) or int(last.get("step") or 0) >= 100
        if complete:
            trajectory_rows[_episode_number(path)] = rows

    completed = set(trajectory_rows)
    costs: dict[int, dict[str, Any]] = {}
    cost_path = source.log_dir / "episode_cost.jsonl"
    if cost_path.exists():
        cost_row: Any
        for cost_row in _read_jsonl(cost_path):
            if cost_row.get("episode") is not None:
                costs[int(cost_row["episode"])] = cost_row

    steps = [
        _dataset_step(source, row)
        for episode_index in sorted(trajectory_rows)
        for row in trajectory_rows[episode_index]
    ]
    episodes: list[dict[str, Any]] = []
    episode_index: Any
    rows: Any
    for episode_index, rows in sorted(trajectory_rows.items()):
        last = rows[-1]
        cost = costs.get(episode_index, {})
        episodes.append(
            {
                **_metadata(source),
                "episode": episode_index + 1,
                "episode_index": episode_index,
                "final_score": float(last.get("cumulative_reward") or 0.0),
                "episode_steps": int(last.get("step") or len(rows)),
                "estimated_cost_usd": cost.get("cost_usd"),
                "cost_is_estimate": cost.get("cost_is_estimate"),
                "cost_complete": cost.get("cost_complete"),
                "tokens": cost.get("tokens"),
                "llm_calls": cost.get("llm_calls"),
                "llm_seconds": cost.get("llm_seconds"),
                "cost_per_score": cost.get("cost_per_reward"),
            }
        )

    turns: list[dict[str, Any]] = []
    turns_path = source.log_dir / "turns.jsonl"
    if turns_path.exists():
        line_index: Any
        turn: Any
        for line_index, turn in enumerate(_read_jsonl(turns_path), start=1):
            normalized = _normalize_turn(source, turn, line_index)
            if normalized is not None and normalized["episode_index"] in completed:
                turns.append(normalized)

    events: list[tuple[str, dict[str, Any]]] = []
    events.extend((f"step:{row['episode_index']}:{row['episode_step']}", _wandb_step(row)) for row in steps)
    events.extend((f"turn:{row['source_line']}", _wandb_turn(row)) for row in turns)
    events.extend((f"episode_summary:{row['episode_index']}", _wandb_episode(row)) for row in episodes)
    return PreparedRun(source, steps, turns, episodes, _fingerprint(events))


def sources() -> list[Source]:
    by_slug = {spec.slug: spec for spec in RUNS}
    result = [
        Source(
            key="baseline-original",
            name="Original baseline (historical)",
            arm="baseline",
            replicate=1,
            log_dir=by_slug["01_baseline"].log_dir,
        ),
        Source(
            key="baseline-provided",
            name="Provided baseline (historical)",
            arm="baseline",
            replicate=2,
            supplied_scores=PROVIDED_BASELINE,
        ),
    ]
    result.extend(
        Source(
            key=f"solo-{index}",
            name=f"Solo ablation run {index} (historical)",
            arm="solo_ablation",
            replicate=index,
            log_dir=log_dir,
        )
        for index, log_dir in enumerate(SOLO_LOG_DIRS, start=1)
    )
    slug: Any
    arm: Any
    name: Any
    for slug, arm, name in (
        ("03_watcher_only", "watcher_only", "Watcher-only ablation (historical)"),
        ("04_planner_only", "planner_only", "Planner-only ablation (historical)"),
        (
            "05_embedded_player_planner_watcher",
            "embedded_player_planner_watcher",
            "Embedded player + planner + watcher (historical)",
        ),
        ("06_unstructured_planning", "unstructured_planning", "Unstructured planning (historical)"),
    ):
        result.append(
            Source(
                key=arm.replace("_", "-"),
                name=name,
                arm=arm,
                replicate=1,
                log_dir=by_slug[slug].log_dir,
            )
        )
    return result


def _run_id(source: Source) -> str:
    identity = f"{HISTORY_SCHEMA}:{source.key}"
    return "hist" + hashlib.sha256(identity.encode()).hexdigest()[:12]


def _existing_run(api: Any, path: str) -> Any | None:
    try:
        return api.run(path)
    except Exception as exc:  # W&B exposes version-specific communication exceptions.
        if "not found" in str(exc).lower() or "could not find" in str(exc).lower():
            return None
        raise


def _existing_record_hashes(api_run: Any | None) -> dict[str, str]:
    if api_run is None:
        return {}
    return {
        str(row["history_import/row_key"]): str(row["history_import/payload_hash"])
        for row in api_run.scan_history(keys=["history_import/row_key", "history_import/payload_hash"], page_size=1000)
        if row.get("history_import/row_key") and row.get("history_import/payload_hash")
    }


def _payload_hash(payload: dict[str, Any]) -> str:
    body = json.dumps(payload, default=str, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


def upload_run(prepared: PreparedRun, *, entity: str, project: str) -> tuple[str, int]:
    import wandb

    source = prepared.source
    run_id = _run_id(source)
    path = f"{entity}/{project}/{run_id}"
    api = wandb.Api(timeout=60)
    api_run = _existing_run(api, path)
    desired_history = [
        {
            "episode": row["episode"],
            "cumulative_reward": row["final_score"],
        }
        for row in prepared.episodes
    ]
    if api_run is not None:
        current_history = [
            {
                "episode": row.get("episode"),
                "cumulative_reward": row.get("cumulative_reward"),
            }
            for row in api_run.scan_history(keys=["episode", "cumulative_reward"], page_size=1000)
        ]
        if current_history != desired_history:
            raise RuntimeError(f"clean W&B history differs for {path}; create a new history schema")
        return api_run.url, 0

    sync_dir = Path(tempfile.gettempdir()) / "maps-wandb-history"
    sync_dir.mkdir(parents=True, exist_ok=True)
    run = wandb.init(
        entity=entity,
        project=project,
        id=run_id,
        resume="allow",
        name=source.name,
        group=source.arm,
        job_type="ablation",
        tags=["maps-park", "ablation", source.arm],
        config={
            "ablation_arm": source.arm,
            "replicate": source.replicate,
        },
        dir=str(sync_dir),
        mode="online",
        force=True,
        save_code=False,
    )
    if run is None:
        raise RuntimeError(f"wandb.init returned no run for {source.name}")
    run.define_metric("episode", hidden=True, summary="none")
    run.define_metric("cumulative_reward", step_metric="episode", summary="mean")
    run.define_metric("cumulative_reward", step_metric="episode", summary="max")
    row: Any
    for row in desired_history:
        run.log(row)

    run.summary["completed_episodes"] = len(prepared.episodes)
    url = run.url
    run.finish()
    return url, len(desired_history)


def publish_weave(prepared_runs: list[PreparedRun], *, entity: str, project: str) -> dict[str, str]:
    import weave

    weave.init(f"{entity}/{project}")
    datasets = {
        "maps_park_historical_ablation_steps": (
            "Completed historical MAPs ablation trajectory steps; episode labels are one-based.",
            [row for prepared in prepared_runs for row in prepared.steps],
        ),
        "maps_park_historical_ablation_turns": (
            "Historical MAPs ablation turn-level execution and LLM accounting summaries.",
            [row for prepared in prepared_runs for row in prepared.turns],
        ),
        "maps_park_historical_ablation_episodes": (
            "Completed MAPs ablation episode outcomes used by the result charts.",
            [row for prepared in prepared_runs for row in prepared.episodes],
        ),
    }
    refs: dict[str, str] = {}
    name: Any
    description: Any
    rows: Any
    for name, (description, rows) in datasets.items():
        if not rows:
            continue
        dataset = weave.Dataset(name=name, description=description, rows=rows)
        refs[name] = str(weave.publish(dataset))
    weave.finish()
    return refs


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entity", help="W&B entity; defaults to the authenticated account")
    parser.add_argument("--project", default=os.environ.get("WANDB_PROJECT", DEFAULT_PROJECT))
    parser.add_argument("--dry-run", action="store_true", help="inventory data without uploading")
    parser.add_argument("--skip-runs", action="store_true", help="publish Weave datasets only")
    parser.add_argument("--skip-weave", action="store_true", help="create W&B runs only")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    prepared_runs = [prepare(source) for source in sources()]
    totals = {
        "runs": len(prepared_runs),
        "steps": sum(len(run.steps) for run in prepared_runs),
        "turns": sum(len(run.turns) for run in prepared_runs),
        "episodes": sum(len(run.episodes) for run in prepared_runs),
    }
    run: Any
    for run in prepared_runs:
        print(
            f"{run.source.name}: {len(run.episodes)} completed episodes, "
            f"{len(run.steps)} steps, {len(run.turns)} turns"
        )
    print("Totals: " + ", ".join(f"{key}={value}" for key, value in totals.items()))
    if args.dry_run:
        return 0

    import wandb

    entity = args.entity or os.environ.get("WANDB_ENTITY") or wandb.Api().default_entity
    if not entity:
        raise RuntimeError("could not determine W&B entity; pass --entity")
    os.environ.setdefault("WANDB_SILENT", "true")

    if not args.skip_runs:
        prepared: Any
        for prepared in prepared_runs:
            url, uploaded = upload_run(prepared, entity=entity, project=args.project)
            print(f"W&B: {prepared.source.name}: {uploaded} new records -> {url}")
    if not args.skip_weave:
        refs = publish_weave(prepared_runs, entity=entity, project=args.project)
        name: Any
        ref: Any
        for name, ref in refs.items():
            print(f"Weave: {name} -> {ref}")
    print(f"Project: https://wandb.ai/{entity}/{args.project}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
