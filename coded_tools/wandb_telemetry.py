"""Live W&B telemetry mirroring the MAPs JSONL/TSV experiment logs.

The runner remains the sole JSONL writer. This module mirrors those same
records to one episode-summary parent run and one step-wise child run per
episode, matching the layout used by the historical W&B imports.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from collections.abc import Callable
from glob import glob
from pathlib import Path
from typing import Any

from coded_tools import weave_telemetry
from coded_tools.state_dir import STATE_DIR

BACKEND_ENV = "MAPS_TELEMETRY_BACKEND"
WANDB_BACKEND = "wandb"
REQUIRED_ENV = "MAPS_WANDB_REQUIRED"
DEFAULT_PROJECT = "maps-park-ablations"
RUN_POINTER = Path(STATE_DIR) / ".wandb_run_path"
RECORD_TYPE_KEY = "maps/record_type"  # Read-only compatibility with old runs.
RECORD_PAYLOAD_KEY = "maps/payload"  # Read-only compatibility with old runs.
TOKEN_KEYS = {"total_tokens", "prompt_tokens", "completion_tokens"}
ARM_LABELS = {
    "baseline": "Baseline",
    "state": "Baseline",
    "maps_park": "Baseline",
    "player": "Baseline",
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
    "qwen4b_multi": "Qwen 4B • Multi Agent",
    "qwen4b_single": "Qwen 4B • Single Agent",
    "qwen4b_strong_planner_multi": "Qwen 4B + 30B Planner • Multi Agent",
    "qwen4b_strong_planner_single": "Qwen 4B + 30B Planner • Single Agent",
    "no_self_improvement_multi": "No Self Improvement • Multi Agent",
    "no_self_improvement_single": "No Self Improvement • Single Agent",
    "baseline_gpt5_mini": "GPT-5 Mini • Multi Agent",
    "single_agent_gpt5_mini": "GPT-5 Mini • Single Agent",
}
LIVE_EPISODE_SCHEMA = "live-episode-v1"

_run: Any | None = None
_episode_runs: dict[int, Any] = {}
_defined_episode_metrics: dict[int, set[str]] = {}
_latest_step: dict[str, Any] | None = None
_latest_steps: dict[int, dict[str, Any]] = {}
_history_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_step_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_ablation_label = "Baseline"
_arm_key = "baseline"
_run_number = 1
_run_group = "Baseline • Run 1"
_resume_parent_id: str | None = None
_existing_child_ids: dict[int, str] = {}
_existing_children_loaded = False
_mirror_disabled_reason: str | None = None


def enabled() -> bool:
    """Whether this process was configured to use W&B telemetry."""
    return os.environ.get(BACKEND_ENV, "").strip().lower() == WANDB_BACKEND


def required() -> bool:
    """Whether telemetry failure must stop an experiment arm."""
    return os.environ.get(REQUIRED_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def writer_active() -> bool:
    return _run is not None and _mirror_disabled_reason is None


def mirror_disabled_reason() -> str | None:
    """Why this process stopped mirroring, or ``None`` while it is healthy."""
    return _mirror_disabled_reason


def disable_writer(reason: str) -> None:
    """Disable the optional mirror without disturbing authoritative local logs.

    Do not attempt a remote flush here: this function is normally reached
    because W&B or Weave has already failed, and retrying network cleanup could
    block the game loop. Normal process shutdown still uses ``finish_run``.
    """
    global _run, _latest_step, _mirror_disabled_reason

    if _mirror_disabled_reason is None:
        _mirror_disabled_reason = reason
        print(f"[wandb] WARN: {reason}; disabling optional mirror and continuing locally.")

    try:
        weave_telemetry.disable()
    except Exception:  # noqa: BLE001 - optional telemetry must fail open
        pass

    _episode_runs.clear()
    _defined_episode_metrics.clear()
    _run = None
    _latest_step = None
    _latest_steps.clear()
    _history_cache.clear()
    _step_cache.clear()


def _optional_call(
    operation: str,
    callback: Callable[..., Any],
    *args: Any,
    **kwargs: Any,
) -> Any | None:
    """Run one mirror operation, failing open unless telemetry is required."""
    if required():
        return callback(*args, **kwargs)
    if _mirror_disabled_reason is not None:
        return None
    try:
        return callback(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - W&B is never authoritative
        disable_writer(f"{operation} failed: {type(exc).__name__}: {exc}")
        return None


def current_run_path() -> str | None:
    """Return ``entity/project/run_id`` for the active experiment."""
    if _run is not None:
        return f"{_run.entity}/{_run.project}/{_run.id}"
    configured = os.environ.get("MAPS_WANDB_RUN_PATH", "").strip()
    if configured:
        return configured
    try:
        value = RUN_POINTER.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def reader_enabled() -> bool:
    """Use cloud reads only when the launcher enabled them and a run exists."""
    return enabled() and current_run_path() is not None


def _identity(config: dict[str, Any]) -> tuple[str, str]:
    raw = str(
        os.environ.get("MAPS_ABLATION_ARM")
        or os.environ.get("MAPS_ARM_NAME")
        or os.environ.get("WANDB_RUN_GROUP")
        or config.get("ablation_arm")
        or config.get("runner_agent")
        or "baseline"
    ).strip()
    if raw == "player_solo":
        raw = "state_solo"
    label = ARM_LABELS.get(raw, raw.replace("_", " ").title())
    return raw, label


def _next_run_number(entity: str | None, project: str, label: str) -> int:
    configured = os.environ.get("MAPS_RUN_NUMBER", "").strip()
    if configured:
        number = int(configured)
        if number < 1:
            raise ValueError("MAPS_RUN_NUMBER must be at least 1")
        return number

    import wandb

    api = wandb.Api(timeout=60)
    resolved_entity = entity or api.default_entity
    if not resolved_entity:
        raise RuntimeError("could not determine W&B entity; set WANDB_ENTITY")
    numbers = [
        int(api_run.config.get("Run"))
        for api_run in api.runs(f"{resolved_entity}/{project}", filters={"jobType": "ablation"})
        if api_run.config.get("Ablation") == label and str(api_run.config.get("Run", "")).isdigit()
    ]
    return max(numbers, default=0) + 1


def _child_run_id(parent_run_id: str, episode_index: int) -> str:
    identity = f"{LIVE_EPISODE_SCHEMA}:{parent_run_id}:{episode_index + 1}"
    return "liveep" + hashlib.sha256(identity.encode()).hexdigest()[:10]


def _sync_dir() -> Path:
    path = Path(
        os.environ.get(
            "WANDB_DIR",
            str(Path(tempfile.gettempdir()) / "maps-wandb"),
        )
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def initialize_run(*, resume: bool, config: dict[str, Any]) -> Any | None:
    """Open the experiment's W&B run, creating or resuming as requested."""
    global _run, _latest_step, _ablation_label, _arm_key, _run_number, _run_group
    global _resume_parent_id, _existing_children_loaded
    if not enabled():
        return None
    if _run is not None:
        return _run

    try:
        import wandb
    except ImportError as exc:
        raise RuntimeError(
            "W&B telemetry is enabled but wandb is not installed; run `python -m pip install -r requirements.txt`"
        ) from exc

    pointer = current_run_path() if resume else None
    project = os.environ.get("WANDB_PROJECT", DEFAULT_PROJECT)
    entity = os.environ.get("WANDB_ENTITY") or None
    run_id = None
    if pointer:
        pointer_parts = pointer.split("/")
        if len(pointer_parts) == 3:
            entity, project, run_id = pointer_parts
        else:
            run_id = pointer.rsplit("/", 1)[-1]
    _arm_key, _ablation_label = _identity(config)
    _run_number = _next_run_number(entity, project, _ablation_label) if not run_id else 1
    _run_group = f"{_ablation_label} • Run {_run_number}"
    mode = os.environ.get("WANDB_MODE", "online").strip().lower()
    if mode != "online":
        raise RuntimeError(f"WANDB_MODE={mode!r} would not push telemetry; set WANDB_MODE=online")

    run_config = dict(config)
    if not run_id:
        run_config.update({"Ablation": _ablation_label, "Run": _run_number})
    _run = wandb.init(
        project=project,
        entity=entity,
        id=run_id,
        resume="allow" if resume and run_id else None,
        reinit="create_new",
        name=None if run_id else _run_group,
        group=None if run_id else _run_group,
        job_type="ablation",
        tags=["maps-park", "ablation", _arm_key],
        config=run_config,
        mode="online",
        force=True,
        dir=str(_sync_dir()),
        save_code=False,
    )
    if _run is None:
        raise RuntimeError("wandb.init() did not return a run")

    _resume_parent_id = str(run_id) if run_id else None
    _existing_child_ids.clear()
    _existing_children_loaded = False

    if run_id:
        _ablation_label = str(_run.config.get("Ablation") or _ablation_label)
        existing_number = _run.config.get("Run")
        _run_number = (
            int(existing_number) if existing_number is not None else _next_run_number(entity, project, _ablation_label)
        )
        _run.config["Ablation"] = _ablation_label
        _run.config["Run"] = _run_number
        _run_group = f"{_ablation_label} • Run {_run_number}"
        if _run.name != _run_group:
            _run.name = _run_group
    os.environ["MAPS_RUN_NUMBER"] = str(_run_number)

    _run.define_metric("run/episode", hidden=True, summary="none")

    RUN_POINTER.parent.mkdir(parents=True, exist_ok=True)
    path = f"{_run.entity}/{_run.project}/{_run.id}"
    RUN_POINTER.write_text(path + "\n", encoding="utf-8")
    os.environ["MAPS_WANDB_RUN_PATH"] = path
    _latest_step = None
    _latest_steps.clear()
    print(f"[wandb] Streaming MAPs telemetry to {_run.url}")
    weave_telemetry.initialize(
        path,
        run_name=getattr(_run, "name", _run_group),
        group=_arm_key,
    )
    return _run


def _json_payload(record: dict[str, Any]) -> str:
    return json.dumps(record, default=str, separators=(",", ":"), sort_keys=True)


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool):
        return None
    return value if isinstance(value, (int, float)) else None


def _flatten(target: dict[str, Any], key: str, value: Any) -> None:
    if isinstance(value, dict):
        child_key: Any
        child_value: Any
        for child_key, child_value in value.items():
            _flatten(target, f"{key}/{child_key}", child_value)
    elif isinstance(value, (list, tuple)):
        target[key] = _json_payload(list(value))
    else:
        target[key] = value


def _step_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {"episode": int(row.get("episode") or 0) + 1}
    key: Any
    value: Any
    for key, value in row.items():
        if key != "episode":
            _flatten(payload, key, value)
    return payload


def _turn_payload(record: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    verified = record.get("verified_after") or {}
    episode_index = int(verified.get("episode") or 0)
    payload: dict[str, Any] = {"episode": episode_index + 1}
    key: Any
    value: Any
    for key, value in record.items():
        column = "turn/number" if key == "turn" else f"turn/{key}"
        _flatten(payload, column, value)
    payload.pop("turn/verified_after/episode", None)
    token_name: Any
    for token_name in TOKEN_KEYS:
        source_key = f"turn/tokens/{token_name}"
        if source_key in payload:
            payload[token_name] = payload.pop(source_key)
    return episode_index, payload


def _prefixed_payload(
    prefix: str,
    row: dict[str, Any],
    *,
    episode: int,
    excluded: set[str],
) -> dict[str, Any]:
    payload: dict[str, Any] = {"episode": episode}
    key: Any
    value: Any
    for key, value in row.items():
        if key not in excluded:
            _flatten(payload, f"{prefix}/{key}", value)
    return payload


def _define_episode_metrics(episode_index: int, run: Any, payload: dict[str, Any]) -> None:
    defined = _defined_episode_metrics.setdefault(episode_index, set())
    key: Any
    for key in sorted(payload):
        if key in defined:
            continue
        if key in {"episode", "step", "turn/number"}:
            run.define_metric(key, hidden=True, summary="none")
        elif key in TOKEN_KEYS or key.startswith("turn/"):
            run.define_metric(key, step_metric="turn/number", summary="none")
        elif key.startswith(("episode_cost/", "park/")):
            run.define_metric(key, step_metric="episode", summary="none")
        else:
            run.define_metric(key, step_metric="step", summary="none")
        defined.add(key)


def _existing_child_run_id(episode_index: int) -> str | None:
    """Find the existing episode child when reopening an imported/live run."""
    global _existing_children_loaded
    if _run is None or _resume_parent_id != str(_run.id):
        return None
    if not _existing_children_loaded:
        import wandb

        candidate: Any
        for candidate in wandb.Api(timeout=60).runs(
            f"{_run.entity}/{_run.project}",
            filters={"group": _run_group, "jobType": "episode"},
        ):
            try:
                candidate_index = int(candidate.config.get("Episode")) - 1
            except (TypeError, ValueError):
                continue
            _existing_child_ids.setdefault(candidate_index, str(candidate.id))
        _existing_children_loaded = True
    return _existing_child_ids.get(episode_index)


def _episode_run(episode_index: int) -> Any:
    if _run is None:
        raise RuntimeError("W&B episode logging attempted before initialize_run()")
    if episode_index in _episode_runs:
        return _episode_runs[episode_index]

    import wandb

    episode = episode_index + 1
    child_id = _existing_child_run_id(episode_index) or _child_run_id(_run.id, episode_index)
    child = wandb.init(
        project=_run.project,
        entity=_run.entity,
        id=child_id,
        resume="allow",
        reinit="create_new",
        name=f"{_run_group} • Episode {episode}",
        group=_run_group,
        job_type="episode",
        tags=["maps-park", "ablation", _arm_key],
        config={"Ablation": _ablation_label, "Run": _run_number, "Episode": episode},
        mode="online",
        force=True,
        dir=str(_sync_dir()),
        save_code=False,
    )
    if child is None:
        raise RuntimeError(f"wandb.init() did not return Episode {episode}")
    _episode_runs[episode_index] = child
    return child


def log_step(row: dict[str, Any]) -> None:
    """Mirror one authoritative post-action row to its W&B episode child."""
    global _latest_step
    _latest_step = dict(row)
    episode_index = int(row.get("episode") or 0)
    _latest_steps[episode_index] = dict(row)
    child = _episode_run(episode_index)
    payload = _step_payload(row)
    _define_episode_metrics(episode_index, child, payload)
    child.log(payload)
    weave_telemetry.log_step(row)
    _history_cache.clear()
    _step_cache.clear()


def log_turn(record: dict[str, Any]) -> None:
    """Mirror a full turn ledger row to its W&B episode child."""
    episode_index, payload = _turn_payload(record)
    child = _episode_run(episode_index)
    _define_episode_metrics(episode_index, child, payload)
    child.log(payload)
    weave_telemetry.log_turn(record)


def log_episode_summary(row: dict[str, Any], park: dict[str, Any] | None = None) -> None:
    """Mirror episode costs to the child and episode outcomes to the parent."""
    if _run is None:
        raise RuntimeError("W&B episode logging attempted before initialize_run()")
    episode_index = int(row.get("episode") or 0)
    episode = episode_index + 1
    child = _episode_run(episode_index)
    cost_payload = _prefixed_payload(
        "episode_cost",
        row,
        episode=episode,
        excluded={"episode"},
    )
    _define_episode_metrics(episode_index, child, cost_payload)
    child.log(cost_payload)

    if park:
        park_payload = _prefixed_payload(
            "park",
            park,
            episode=episode,
            excluded={"episode", "run_episode"},
        )
        _define_episode_metrics(episode_index, child, park_payload)
        child.log(park_payload)

    score = _number(row.get("final_reward"))
    if score is not None:
        child.summary["cumulative_reward"] = score
    source: Any
    target: Any
    for source, target in (
        ("tokens", "episode_cost/tokens"),
        ("llm_calls", "episode_cost/llm_calls"),
        ("llm_seconds", "episode_cost/llm_seconds"),
    ):
        if row.get(source) is not None:
            child.summary[target] = row[source]
    final_step = _latest_steps.get(episode_index)
    final_value = (park or {}).get("final_value")
    if final_value is None and final_step:
        final_value = final_step.get("park_value")
    if final_value is not None:
        child.summary["park/final_value"] = final_value

    parent_payload: dict[str, Any] = {"run/episode": episode}
    if final_step:
        step = int(final_step.get("step") or 0)
        complete = bool(final_step.get("done")) or step >= 100
        parent_payload["run/episode_steps"] = step
        parent_payload["run/episode_complete"] = complete
        if complete and score is not None:
            parent_payload["run/cumulative_reward"] = score
        key: Any
        value: Any
        for key, value in final_step.items():
            if key not in {"episode", "step", "cumulative_reward"}:
                _flatten(parent_payload, f"run/episode_final/{key}", value)
    key: Any
    value: Any
    for key, value in row.items():
        if key not in {"episode", "final_reward"}:
            _flatten(parent_payload, f"run/episode_cost/{key}", value)
    if park:
        key: Any
        value: Any
        for key, value in park.items():
            if key not in {"episode", "run_episode"}:
                _flatten(parent_payload, f"run/park/{key}", value)
    key: Any
    for key in sorted(parent_payload):
        if key != "run/episode":
            _run.define_metric(key, step_metric="run/episode", summary="none")

    previous_count = int(_run.summary.get("completed_episodes") or 0)
    if episode > previous_count:
        _run.log(parent_payload)
        if score is not None:
            previous_mean = float(_run.summary.get("run/cumulative_reward.mean") or 0.0)
            count = previous_count + 1
            _run.summary["run/cumulative_reward.mean"] = ((previous_mean * previous_count) + score) / count
            previous_max = _number(_run.summary.get("run/cumulative_reward.max"))
            _run.summary["run/cumulative_reward.max"] = score if previous_max is None else max(previous_max, score)
        _run.summary["completed_episodes"] = previous_count + 1
    _run.summary["episodes"] = max(int(_run.summary.get("episodes") or 0), episode)
    weave_telemetry.log_episode_summary(row)
    _history_cache.clear()
    _step_cache.clear()
    child.finish()
    _episode_runs.pop(episode_index, None)
    _defined_episode_metrics.pop(episode_index, None)


def latest_step_row() -> dict[str, Any] | None:
    """Return the writer's latest row, or recover it from W&B after a restart."""
    if _latest_step is not None:
        return dict(_latest_step)
    path = current_run_path()
    if not path:
        return None
    rows = read_step_rows(path, use_cache=False)
    if not rows:
        return None
    return max(rows, key=lambda row: (int(row.get("episode") or 0), int(row.get("step") or 0)))


def _api_run(path: str) -> Any:
    import wandb

    last_error: Exception | None = None
    _attempt: Any
    for _attempt in range(5):
        try:
            return wandb.Api().run(path)
        except Exception as exc:  # noqa: BLE001 - SDK exception types vary
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"could not load W&B run {path}: {last_error}") from last_error


def read_records(path: str, *, use_cache: bool = True) -> list[dict[str, Any]]:
    """Read all MAPs records from a W&B run without sampling."""
    cached = _history_cache.get(path)
    if use_cache and cached and time.monotonic() - cached[0] < 2.0:
        return [dict(record) for record in cached[1]]
    api_run = _api_run(path)
    records: list[dict[str, Any]] = []
    history_row: Any
    for history_row in api_run.scan_history(keys=[RECORD_TYPE_KEY, RECORD_PAYLOAD_KEY], page_size=1000):
        kind = history_row.get(RECORD_TYPE_KEY)
        raw = history_row.get(RECORD_PAYLOAD_KEY)
        if not kind or not isinstance(raw, str):
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append({"record_type": kind, "payload": payload})
    _history_cache[path] = (time.monotonic(), records)
    return [dict(record) for record in records]


def read_step_rows(path: str | None = None, *, use_cache: bool = True) -> list[dict[str, Any]]:
    import wandb

    run_path = path or current_run_path()
    if not run_path:
        return []
    cached = _step_cache.get(run_path)
    if use_cache and cached and time.monotonic() - cached[0] < 2.0:
        return [dict(row) for row in cached[1]]

    legacy = [
        record["payload"]
        for record in read_records(run_path, use_cache=use_cache)
        if record.get("record_type") == "step"
    ]
    if legacy:
        _step_cache[run_path] = (time.monotonic(), legacy)
        return [dict(row) for row in legacy]

    parent = _api_run(run_path)
    entity, project, _parent_id = run_path.split("/", 2)
    parent_config = getattr(parent, "config", {}) or {}
    label = parent_config.get("Ablation")
    run_number = parent_config.get("Run")
    expected_group = f"{label} • Run {run_number}" if label and run_number is not None else None
    groups = list(dict.fromkeys(group for group in (expected_group, parent.group) if group))
    children_by_id: dict[str, Any] = {}
    group: Any
    for group in groups:
        api_run: Any
        for api_run in wandb.Api(timeout=60).runs(f"{entity}/{project}", filters={"group": group}):
            if api_run.job_type == "episode":
                child_id = getattr(api_run, "id", None)
                child_key = str(child_id) if child_id is not None else str(id(api_run))
                children_by_id[child_key] = api_run
    children = list(children_by_id.values())
    children.sort(key=lambda api_run: int(api_run.config.get("Episode") or 0))
    rows: list[dict[str, Any]] = []
    child: Any
    for child in children:
        history_row: Any
        for history_row in child.scan_history(page_size=1000):
            if history_row.get("step") is None:
                continue
            row = {
                key: value
                for key, value in history_row.items()
                if not key.startswith("_")
                and key != "episode"
                and not key.startswith(("turn/", "episode_cost/", "park/"))
                and key not in TOKEN_KEYS
            }
            row["episode"] = int(history_row.get("episode") or 1) - 1
            rows.append(row)
    _step_cache[run_path] = (time.monotonic(), rows)
    return [dict(row) for row in rows]


def completed_episode_count(path: str | None = None) -> int:
    """Count unique episodes that reached a terminal step in a W&B run."""
    run_path = path or current_run_path()
    if not run_path:
        return 0

    # The parent summary is updated only after an episode closes successfully.
    # Prefer it on resume: it remains authoritative even for older parent runs
    # whose immutable W&B group differs from their episode-child group.
    parent = _api_run(run_path)
    parent_summary = getattr(parent, "summary", {}) or {}
    summary_count = parent_summary.get("completed_episodes")
    try:
        if summary_count is not None and int(summary_count) >= 0:
            return int(summary_count)
    except (TypeError, ValueError):
        pass

    episodes = {
        row.get("episode")
        for row in read_step_rows(run_path, use_cache=False)
        if row.get("done") and row.get("episode") is not None
    }
    return len(episodes)


def migrate_legacy_jsonl(run_log_dir: str, episode_cost_path: str, turns_log_path: str) -> dict[str, int]:
    """Mirror a legacy local run when its first W&B launch uses ``--resume``."""
    counts = {"steps": 0, "turns": 0, "episodes": 0}
    parks: dict[int, dict[str, Any]] = {}
    park_path = os.path.join(run_log_dir, "park_ids.jsonl")
    if os.path.exists(park_path):
        try:
            with open(park_path, encoding="utf-8") as handle:
                line: Any
                for line in handle:
                    if not line.strip():
                        continue
                    park = json.loads(line)
                    episode = int(park.get("run_episode", park.get("episode", 0)))
                    parks[episode] = park
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"cannot migrate legacy park telemetry {park_path}: {exc}") from exc
    weave_telemetry.suspend()
    try:
        path: Any
        for path in sorted(glob(os.path.join(run_log_dir, "run.ep*.jsonl"))):
            try:
                with open(path, encoding="utf-8") as handle:
                    line: Any
                    for line in handle:
                        if not line.strip():
                            continue
                        row = json.loads(line)
                        if row.get("step") is not None:
                            log_step(row)
                            counts["steps"] += 1
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"cannot migrate legacy telemetry {path}: {exc}") from exc

        if os.path.exists(turns_log_path):
            try:
                with open(turns_log_path, encoding="utf-8") as handle:
                    line: Any
                    for line in handle:
                        if not line.strip():
                            continue
                        log_turn(json.loads(line))
                        counts["turns"] += 1
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"cannot migrate legacy turn telemetry {turns_log_path}: {exc}") from exc

        if os.path.exists(episode_cost_path):
            try:
                with open(episode_cost_path, encoding="utf-8") as handle:
                    line: Any
                    for line in handle:
                        if not line.strip():
                            continue
                        summary = json.loads(line)
                        episode = int(summary.get("episode") or 0)
                        log_episode_summary(summary, parks.get(episode))
                        counts["episodes"] += 1
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError(f"cannot migrate legacy episode telemetry {episode_cost_path}: {exc}") from exc
    finally:
        weave_telemetry.resume()
    print(
        "[wandb] Migrated legacy resume telemetry: "
        f"{counts['steps']} steps, {counts['turns']} turns, "
        f"{counts['episodes']} episode summaries"
    )
    return counts


def list_run_paths(*, include_current_only: bool = False) -> list[str]:
    """Return current and prior cloud runs for the active experiment group."""
    current = current_run_path()
    if not current:
        return []
    if include_current_only:
        return [current]

    import wandb

    entity, project, _run_id = current.split("/", 2)
    current_api_run = _api_run(current)
    label = current_api_run.config.get("Ablation")
    filters = {"config.Ablation": label} if label else None
    paths = [current]
    api_run: Any
    for api_run in wandb.Api().runs(path=f"{entity}/{project}", filters=filters, order="-created_at"):
        if api_run.job_type not in {"ablation", "experiment"}:
            continue
        path = f"{api_run.entity}/{api_run.project}/{api_run.id}"
        if path not in paths:
            paths.append(path)
    return paths


def finish_run(exit_code: int = 0) -> None:
    """Flush queued data and close the W&B run."""
    global _run, _latest_step
    if _run is None:
        return
    weave_telemetry.finish()
    child: Any
    for child in list(_episode_runs.values()):
        child.finish(exit_code=exit_code)
    _episode_runs.clear()
    _defined_episode_metrics.clear()
    _run.finish(exit_code=exit_code)
    _run = None
    _latest_step = None
    _latest_steps.clear()
    _history_cache.clear()
    _step_cache.clear()


def try_initialize_run(*, resume: bool, config: dict[str, Any]) -> Any | None:
    """Initialize W&B, raising only when required study telemetry fails."""
    return _optional_call("initialization", initialize_run, resume=resume, config=config)


def try_log_step(row: dict[str, Any]) -> None:
    """Mirror a step, raising only when required study telemetry fails."""
    _optional_call("step logging", log_step, row)


def try_log_turn(record: dict[str, Any]) -> None:
    """Mirror a turn, raising only when required study telemetry fails."""
    _optional_call("turn logging", log_turn, record)


def try_log_episode_summary(row: dict[str, Any], park: dict[str, Any] | None = None) -> None:
    """Mirror an episode, raising only when required study telemetry fails."""
    _optional_call("episode-summary logging", log_episode_summary, row, park)


def try_migrate_legacy_jsonl(run_log_dir: str, episode_cost_path: str, turns_log_path: str) -> Any | None:
    """Best-effort legacy upload used only while resuming a run."""
    return _optional_call(
        "legacy telemetry migration",
        migrate_legacy_jsonl,
        run_log_dir,
        episode_cost_path,
        turns_log_path,
    )


def try_finish_run(exit_code: int = 0) -> None:
    """Flush the optional mirror without masking the runner's real outcome."""
    _optional_call("final flush", finish_run, exit_code=exit_code)
