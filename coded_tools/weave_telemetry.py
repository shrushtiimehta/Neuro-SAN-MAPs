"""Episode/turn trace trees shared by live MAPs runs and history backfills."""

from __future__ import annotations

import datetime as dt
import os
from typing import Any

TRACE_SCHEMA = "maps-park-episode-turn-v1"
EPISODE_OP = "maps_park.episode"
TURN_OP = "maps_park.turn"

_client: Any | None = None
_run_metadata: dict[str, Any] = {}
_episode_call: Any | None = None
_episode_index: int | None = None
_last_step: dict[str, Any] | None = None
_turn_count = 0
_suspended = False


def episode_display_name(run_metadata: dict[str, Any], episode_index: int) -> str:
    """Return the concise title shared by live and historical episode calls."""
    label = run_metadata.get("trace_label")
    if not label:
        arm = str(run_metadata.get("ablation_arm") or "MAPs Park")
        label = {
            "embedded_player_planner_watcher": "Embedded",
            "planner_only": "Planner",
            "player_with_planner": "Planner",
            "watcher_only": "Watcher",
            "player_with_watcher": "Watcher",
            "solo_ablation": "Single Agent",
            "state_solo": "Single Agent",
            "state_single_agent": "Single Agent",
            "unstructured_planning": "Unstructured",
            "unstructured_player_planner_watcher": "Unstructured",
            "baseline": "Baseline",
            "state": "Baseline",
        }.get(arm, arm.replace("_", " ").title())
    run_number = int(run_metadata.get("run_number") or 1)
    return f"{label} • Run {run_number} • Episode {episode_index + 1}"


def utc_timestamp(value: Any, fallback: dt.datetime | None = None) -> dt.datetime:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        try:
            return dt.datetime.fromtimestamp(float(value), tz=dt.timezone.utc)
        except (OverflowError, OSError, ValueError):
            pass
    return fallback or dt.datetime.now(tz=dt.timezone.utc)


def turn_times(record: dict[str, Any]) -> tuple[dt.datetime, dt.datetime]:
    """Return a best-effort start/end pair from a legacy or live turn row."""
    ended_at = utc_timestamp(record.get("wall_time"))
    tokens = record.get("tokens") or {}
    seconds = tokens.get("time_taken_in_seconds") if isinstance(tokens, dict) else 0
    try:
        duration = max(0.0, float(seconds or 0.0))
    except (TypeError, ValueError):
        duration = 0.0
    return ended_at - dt.timedelta(seconds=duration), ended_at


def _attributes(run_metadata: dict[str, Any], episode_index: int, *, historical: bool) -> dict[str, Any]:
    return {
        "maps": {
            "trace_schema": TRACE_SCHEMA,
            "historical_import": historical,
            "episode": episode_index + 1,
            "episode_index": episode_index,
            **run_metadata,
        }
    }


def create_episode_call(
    client: Any,
    *,
    run_metadata: dict[str, Any],
    episode_index: int,
    started_at: dt.datetime,
    historical: bool,
    call_id: str | None = None,
    display_name: str | None = None,
    episode_inputs: dict[str, Any] | None = None,
) -> Any:
    """Create an episode root call using the common trace schema."""
    return client.create_call(
        op=EPISODE_OP,
        inputs={
            "episode": episode_index + 1,
            "episode_index": episode_index,
            "run": run_metadata,
            **(episode_inputs or {}),
        },
        attributes=_attributes(run_metadata, episode_index, historical=historical),
        display_name=display_name or episode_display_name(run_metadata, episode_index),
        use_stack=False,
        _call_id_override=call_id,
        started_at=started_at,
    )


def create_turn_call(
    client: Any,
    *,
    parent: Any,
    run_metadata: dict[str, Any],
    episode_index: int,
    record: dict[str, Any],
    historical: bool,
    call_id: str | None = None,
) -> Any:
    """Create and finish one child turn call, preserving its full record."""
    started_at, ended_at = turn_times(record)
    turn = record.get("turn")
    verified = record.get("verified_after") or {}
    step = verified.get("step") if isinstance(verified, dict) else None
    child = client.create_call(
        op=TURN_OP,
        inputs={"turn_record": record},
        parent=parent,
        attributes=_attributes(run_metadata, episode_index, historical=historical),
        display_name=f"Turn {turn or step or '?'} · Step {step or '?'}",
        use_stack=False,
        _call_id_override=call_id,
        started_at=started_at,
    )
    tokens = record.get("tokens") or {}
    if not isinstance(tokens, dict):
        tokens = {}
    child.summary = {
        "maps": {
            "turn_count": 1,
            "attempts": int(record.get("attempts") or 0),
            "succeeded": int(bool(record.get("turn_done"))),
            "tokens": int(tokens.get("total_tokens") or 0),
            "llm_calls": int(tokens.get("successful_requests") or 0),
            "llm_seconds": float(tokens.get("time_taken_in_seconds") or 0.0),
            "estimated_cost_usd": float(tokens.get("total_cost") or 0.0),
        }
    }
    client.finish_call(
        child,
        output={
            "turn_done": bool(record.get("turn_done")),
            "proposed": record.get("proposed"),
            "verified_after": record.get("verified_after"),
        },
        ended_at=ended_at,
    )
    return child


def finish_episode_call(
    client: Any,
    call: Any,
    *,
    last_step: dict[str, Any] | None,
    episode_summary: dict[str, Any] | None,
    complete: bool,
    turn_count: int,
    ended_at: dt.datetime | None = None,
) -> None:
    """Finish an episode root with the live/backfill-compatible output."""
    final_score = None
    if last_step:
        final_score = last_step.get("cumulative_reward")
    if episode_summary and episode_summary.get("final_reward") is not None:
        final_score = episode_summary.get("final_reward")
    call.summary = {
        "maps": {
            "complete": int(complete),
            "partial": int(not complete),
            "turn_count": turn_count,
            "final_score": final_score,
            "final_step": last_step.get("step") if last_step else None,
        }
    }
    client.finish_call(
        call,
        output={
            "status": "complete" if complete else "partial",
            "final_state": last_step,
            "episode_summary": episode_summary,
        },
        ended_at=ended_at or dt.datetime.now(tz=dt.timezone.utc),
    )


def initialize(run_path: str, *, run_name: str, group: str) -> None:
    """Initialize live Weave tracing after the associated W&B run starts."""
    global _client, _run_metadata
    if _client is not None:
        return
    import weave

    entity, project, run_id = run_path.split("/", 2)
    _client = weave.init(f"{entity}/{project}")
    _run_metadata = {
        "wandb_run_id": run_id,
        "wandb_run_path": run_path,
        "run_name": run_name,
        "ablation_arm": group,
        "run_number": int(os.environ.get("MAPS_RUN_NUMBER", "1")),
    }


def suspend() -> None:
    """Suppress traces while legacy rows are copied into W&B history."""
    global _suspended
    _suspended = True


def resume() -> None:
    global _suspended
    _suspended = False


def log_step(row: dict[str, Any]) -> None:
    global _last_step
    if _client is None or _suspended:
        return
    _last_step = dict(row)


def _close_live_episode(*, complete: bool, episode_summary: dict[str, Any] | None) -> None:
    global _episode_call, _episode_index, _last_step, _turn_count
    if _client is None or _episode_call is None:
        return
    finish_episode_call(
        _client,
        _episode_call,
        last_step=_last_step,
        episode_summary=episode_summary,
        complete=complete,
        turn_count=_turn_count,
    )
    _client.flush()
    _episode_call = None
    _episode_index = None
    _last_step = None
    _turn_count = 0


def log_turn(record: dict[str, Any]) -> None:
    global _episode_call, _episode_index, _turn_count
    if _client is None or _suspended:
        return
    verified = record.get("verified_after") or {}
    if not isinstance(verified, dict):
        return
    episode_index = int(verified.get("episode") or 0)
    if _episode_call is not None and _episode_index != episode_index:
        _close_live_episode(complete=False, episode_summary=None)
    if _episode_call is None:
        started_at, _ended_at = turn_times(record)
        _episode_call = create_episode_call(
            _client,
            run_metadata=_run_metadata,
            episode_index=episode_index,
            started_at=started_at,
            historical=False,
        )
        _episode_index = episode_index
    create_turn_call(
        _client,
        parent=_episode_call,
        run_metadata=_run_metadata,
        episode_index=episode_index,
        record=record,
        historical=False,
    )
    _turn_count += 1


def log_episode_summary(row: dict[str, Any]) -> None:
    if _client is None or _suspended:
        return
    _close_live_episode(complete=True, episode_summary=dict(row))


def finish() -> None:
    """Flush a partial live episode and close the Weave client."""
    global _client, _run_metadata
    if _client is None:
        return
    _close_live_episode(complete=False, episode_summary=None)
    _client.finish(use_progress_bar=False)
    _client = None
    _run_metadata = {}


def disable() -> None:
    """Drop live tracing state without any remote flush or network cleanup."""
    global _client, _run_metadata, _episode_call, _episode_index
    global _last_step, _turn_count, _suspended
    _client = None
    _run_metadata = {}
    _episode_call = None
    _episode_index = None
    _last_step = None
    _turn_count = 0
    _suspended = True
