"""MAPs runtime telemetry is mirrored to both local files and W&B."""

from __future__ import annotations

import os

import pytest
import wandb

from apps.maps_park import runner
from coded_tools import wandb_telemetry
from coded_tools.episode_telemetry import EpisodeTelemetry
from coded_tools.run_telemetry import RunTelemetry


class FakeRun:
    def __init__(
        self,
        *,
        run_id: str = "run-123",
        name: str = "",
        group: str = "",
        job_type: str = "",
        config: dict | None = None,
    ) -> None:
        self.entity = "test-entity"
        self.project = "test-project"
        self.id = run_id
        self.name = name
        self.group = group
        self.job_type = job_type
        self.config = config or {}
        self.url = f"https://wandb.example/test-project/{run_id}"
        self.summary: dict = {}
        self.logged: list[dict] = []
        self.metrics: list[tuple[tuple, dict]] = []
        self.finished: int | None = None

    def define_metric(self, *args, **kwargs) -> None:
        self.metrics.append((args, kwargs))

    def log(self, values: dict) -> None:
        self.logged.append(values)

    def finish(self, exit_code: int = 0) -> None:
        self.finished = exit_code


def _rows() -> list[dict]:
    return [
        {
            "episode": 0,
            "step": 1,
            "action": "place",
            "reward": 10.0,
            "cumulative_reward": 10.0,
            "park_value": 510,
            "done": False,
        },
        {
            "episode": 0,
            "step": 100,
            "action": "wait",
            "reward": 20.0,
            "cumulative_reward": 1000.0,
            "park_value": 900,
            "done": True,
        },
    ]


def _install_failing_mirror(monkeypatch, operation: str) -> None:
    """Make one strict mirror operation fail behind its fail-open wrapper."""
    monkeypatch.setattr(wandb_telemetry, "_mirror_disabled_reason", None)
    monkeypatch.setattr(wandb_telemetry, "_run", FakeRun())
    monkeypatch.setattr(wandb_telemetry, "_episode_runs", {})
    monkeypatch.setattr(wandb_telemetry, "_defined_episode_metrics", {})
    monkeypatch.setattr(wandb_telemetry, "_latest_steps", {})
    monkeypatch.setattr(wandb_telemetry, "_history_cache", {})
    monkeypatch.setattr(wandb_telemetry, "_step_cache", {})
    monkeypatch.setattr(wandb_telemetry.weave_telemetry, "disable", lambda: None)

    def fail(*_args, **_kwargs):
        raise RuntimeError(f"simulated {operation} outage")

    monkeypatch.setattr(wandb_telemetry, operation, fail)


def test_initialization_failure_disables_optional_mirror(monkeypatch) -> None:
    monkeypatch.setattr(wandb_telemetry, "_mirror_disabled_reason", None)
    monkeypatch.setattr(wandb_telemetry, "_run", None)
    monkeypatch.setattr(wandb_telemetry.weave_telemetry, "disable", lambda: None)

    def fail(*_args, **_kwargs):
        raise RuntimeError("simulated initialization outage")

    monkeypatch.setattr(wandb_telemetry, "initialize_run", fail)

    result = wandb_telemetry.try_initialize_run(resume=False, config={})

    assert result is None
    assert not wandb_telemetry.writer_active()
    assert "initialization outage" in str(wandb_telemetry.mirror_disabled_reason())


def test_required_initialization_failure_stops_experiment(monkeypatch) -> None:
    """Study arms must never continue after losing their required W&B sink."""
    monkeypatch.setenv(wandb_telemetry.REQUIRED_ENV, "1")
    monkeypatch.setattr(wandb_telemetry, "_run", None)

    def fail(*_args, **_kwargs):
        raise RuntimeError("simulated required outage")

    monkeypatch.setattr(wandb_telemetry, "initialize_run", fail)

    with pytest.raises(RuntimeError, match="required outage"):
        wandb_telemetry.try_initialize_run(resume=False, config={})


def test_step_mirror_failure_preserves_local_log(tmp_path, monkeypatch) -> None:
    _install_failing_mirror(monkeypatch, "log_step")
    log_dir = tmp_path / "logs"
    monkeypatch.setattr(runner, "RUN_LOG_DIR", str(log_dir))

    runner.write_run_log_row(_rows()[0], 0)

    saved = (log_dir / "run.ep000.jsonl").read_text(encoding="utf-8")
    assert '"cumulative_reward": 10.0' in saved
    assert not wandb_telemetry.writer_active()
    assert "step logging failed" in str(wandb_telemetry.mirror_disabled_reason())


def test_turn_mirror_failure_preserves_local_log(tmp_path, monkeypatch) -> None:
    _install_failing_mirror(monkeypatch, "log_turn")
    turns_path = tmp_path / "turns.jsonl"
    monkeypatch.setattr(runner, "TURNS_LOG_PATH", str(turns_path))

    runner.write_turn_log_record({"turn": 1, "verified_after": _rows()[0]})

    assert '"turn": 1' in turns_path.read_text(encoding="utf-8")
    assert not wandb_telemetry.writer_active()
    assert "turn logging failed" in str(wandb_telemetry.mirror_disabled_reason())


def test_summary_mirror_failure_preserves_local_cost(tmp_path, monkeypatch) -> None:
    _install_failing_mirror(monkeypatch, "log_episode_summary")
    cost_path = tmp_path / "episode_cost.jsonl"
    monkeypatch.setattr(runner, "EPISODE_COST_PATH", str(cost_path))
    monkeypatch.setattr(runner, "PARK_IDS_PATH", str(tmp_path / "park_ids.jsonl"))
    runner._EPISODE_SPEND.update(cost_usd=1.0, tokens=10, llm_calls=1, seconds=2.0)
    runner._EPISODE_COST_COMPLETE = True
    runner._EPISODE_COST_INCOMPLETE_REASON = None

    runner.write_episode_cost(0, reward=1000.0)

    assert '"final_reward": 1000.0' in cost_path.read_text(encoding="utf-8")
    assert not wandb_telemetry.writer_active()
    assert "episode-summary logging failed" in str(wandb_telemetry.mirror_disabled_reason())


def test_final_flush_failure_never_escapes(monkeypatch) -> None:
    _install_failing_mirror(monkeypatch, "finish_run")

    wandb_telemetry.try_finish_run()

    assert not wandb_telemetry.writer_active()
    assert "final flush failed" in str(wandb_telemetry.mirror_disabled_reason())


def test_writer_mirrors_files_to_parent_and_episode_runs(tmp_path, monkeypatch) -> None:
    created: list[FakeRun] = []

    def fake_init(**kwargs) -> FakeRun:
        run = FakeRun(
            run_id=kwargs.get("id") or "run-123",
            name=kwargs.get("name", ""),
            group=kwargs.get("group", ""),
            job_type=kwargs.get("job_type", ""),
            config=dict(kwargs.get("config") or {}),
        )
        created.append(run)
        return run

    monkeypatch.setenv(wandb_telemetry.BACKEND_ENV, "wandb")
    monkeypatch.setenv("WANDB_PROJECT", "test-project")
    monkeypatch.setenv("MAPS_RUN_NUMBER", "20")
    monkeypatch.setattr(wandb_telemetry, "RUN_POINTER", tmp_path / ".wandb_run_path")
    monkeypatch.setattr(wandb, "init", fake_init)
    monkeypatch.setattr(wandb_telemetry, "_run", None)
    monkeypatch.setattr(wandb_telemetry, "_episode_runs", {})
    monkeypatch.setattr(wandb_telemetry, "_defined_episode_metrics", {})
    monkeypatch.setattr(wandb_telemetry, "_latest_step", None)
    monkeypatch.setattr(wandb_telemetry, "_latest_steps", {})
    monkeypatch.setattr(
        wandb_telemetry.weave_telemetry,
        "initialize",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(wandb_telemetry.weave_telemetry, "log_step", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(wandb_telemetry.weave_telemetry, "log_turn", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(wandb_telemetry.weave_telemetry, "log_episode_summary", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(wandb_telemetry.weave_telemetry, "finish", lambda: None)

    log_dir = tmp_path / "logs"
    monkeypatch.setattr(runner, "RUN_LOG_DIR", str(log_dir))
    monkeypatch.setattr(runner, "TURNS_LOG_PATH", str(log_dir / "turns.jsonl"))
    monkeypatch.setattr(runner, "EPISODE_COST_PATH", str(log_dir / "episode_cost.jsonl"))
    monkeypatch.setattr(runner, "PARK_IDS_PATH", str(log_dir / "park_ids.jsonl"))

    parent = wandb_telemetry.initialize_run(
        resume=False,
        config={"runner_agent": "player", "micro_agent": "watcher"},
    )
    runner.write_run_log_row(_rows()[0], 0)
    runner.write_run_log_row(_rows()[1], 0)
    turn = {
        "turn": 1,
        "attempts": 1,
        "turn_done": True,
        "verified_after": _rows()[1],
        "tokens": {
            "total_tokens": 12,
            "prompt_tokens": 7,
            "completion_tokens": 5,
        },
    }
    runner.write_turn_log_record(turn)
    log_dir.mkdir(exist_ok=True)
    (log_dir / "park_ids.jsonl").write_text(
        '{"episode":19,"run_episode":0,"park_id":"park-abc","final_value":900}\n',
        encoding="utf-8",
    )
    runner._EPISODE_SPEND.update(cost_usd=1.25, tokens=100, llm_calls=2, seconds=3.0)
    runner._EPISODE_COST_COMPLETE = True
    runner._EPISODE_COST_INCOMPLETE_REASON = None
    runner.write_episode_cost(0, reward=1000.0)

    assert (tmp_path / ".wandb_run_path").read_text().strip() == ("test-entity/test-project/run-123")
    assert parent is created[0]
    child = created[1]
    assert parent.name == parent.group == "Baseline • Run 20"
    assert parent.config["Ablation"] == "Baseline"
    assert parent.config["Run"] == 20
    assert child.name == "Baseline • Run 20 • Episode 1"
    assert child.group == "Baseline • Run 20"
    assert child.config == {"Ablation": "Baseline", "Run": 20, "Episode": 1}

    first_step, final_step, turn_row, cost_row, park_row = child.logged
    assert first_step["episode"] == 1
    assert first_step["step"] == 1
    assert first_step["cumulative_reward"] == 10.0
    assert final_step["step"] == 100
    assert turn_row["total_tokens"] == 12
    assert turn_row["prompt_tokens"] == 7
    assert turn_row["completion_tokens"] == 5
    assert "turn/tokens/total_tokens" not in turn_row
    assert cost_row["episode_cost/tokens"] == 100
    assert park_row["park/park_id"] == "park-abc"
    assert not any(key.startswith("maps/") or key.startswith("trajectory/") for row in child.logged for key in row)

    assert parent.logged[0]["run/episode"] == 1
    assert parent.logged[0]["run/cumulative_reward"] == 1000.0
    assert parent.logged[0]["run/park/park_id"] == "park-abc"
    assert parent.summary["run/cumulative_reward.mean"] == 1000.0
    assert parent.summary["run/cumulative_reward.max"] == 1000.0
    assert child.summary["cumulative_reward"] == 1000.0

    assert (log_dir / "run.ep000.jsonl").exists()
    assert (log_dir / "turns.jsonl").exists()
    assert (log_dir / "episode_cost.jsonl").exists()
    assert child.finished == 0

    wandb_telemetry.finish_run()
    assert parent.finished == 0


def test_episode_and_run_tools_always_read_local_logs(tmp_path, monkeypatch) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "run.ep000.jsonl").write_text(
        "\n".join(wandb_telemetry._json_payload(row) for row in _rows()) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(EpisodeTelemetry, "RUN_LOG_DIR", str(log_dir))
    monkeypatch.setattr(RunTelemetry, "RUN_LOG_DIR", str(log_dir))
    monkeypatch.setattr(wandb_telemetry, "reader_enabled", lambda: True)
    monkeypatch.setattr(
        wandb_telemetry,
        "read_step_rows",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("operational telemetry must not read W&B")),
    )

    episode = EpisodeTelemetry().invoke({"episode": 0}, {})
    assert episode["exists"] is True
    assert episode["rollup"]["reached_step_100"] is True
    assert episode["rollup"]["cum_end"] == 1000.0

    run = RunTelemetry().invoke({}, {})
    assert "source" not in run
    assert run["run_episode_count"] == 1
    assert run["run_rollup"]["best_episode"] == {
        "episode": 0,
        "cum_end": 1000.0,
    }


def test_episode_tool_prefers_current_local_log_over_cloud(tmp_path, monkeypatch) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "run.ep003.jsonl").write_text(
        '{"episode":3,"step":100,"action":"wait","cumulative_reward":1234,"done":true}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(EpisodeTelemetry, "RUN_LOG_DIR", str(log_dir))
    monkeypatch.setattr(wandb_telemetry, "reader_enabled", lambda: True)
    monkeypatch.setattr(
        wandb_telemetry,
        "read_step_rows",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("cloud should not be read when the local episode exists")
        ),
    )

    episode = EpisodeTelemetry().invoke({"episode": 3}, {})

    assert episode["exists"] is True
    assert episode["rollup"]["cum_end"] == 1234


def test_resume_preserves_parent_identity(tmp_path, monkeypatch) -> None:
    class ImmutableGroupRun(FakeRun):
        @property
        def group(self) -> str:
            return self._group

        @group.setter
        def group(self, value: str) -> None:
            if hasattr(self, "_group"):
                raise AttributeError("group is read-only after initialization")
            self._group = value

    resumed = ImmutableGroupRun(
        run_id="existing",
        name="Unstructured • Run 2",
        group="Unstructured • Run 2",
        job_type="ablation",
        config={"Ablation": "Unstructured", "Run": 2},
    )
    captured = {}

    def fake_init(**kwargs):
        captured.update(kwargs)
        return resumed

    monkeypatch.setenv(wandb_telemetry.BACKEND_ENV, "wandb")
    monkeypatch.setenv("MAPS_WANDB_RUN_PATH", "test-entity/test-project/existing")
    monkeypatch.setenv("MAPS_ABLATION_ARM", "unstructured_player_planner_watcher")
    monkeypatch.delenv("MAPS_RUN_NUMBER", raising=False)
    monkeypatch.setattr(wandb, "init", fake_init)
    monkeypatch.setattr(wandb_telemetry, "RUN_POINTER", tmp_path / ".wandb_run_path")
    monkeypatch.setattr(wandb_telemetry, "_run", None)
    monkeypatch.setattr(wandb_telemetry.weave_telemetry, "initialize", lambda *_args, **_kwargs: None)

    result = wandb_telemetry.initialize_run(resume=True, config={})

    assert result is resumed
    assert captured["name"] is None
    assert captured["group"] is None
    assert "Ablation" not in captured["config"]
    assert resumed.name == resumed.group == "Unstructured • Run 2"
    assert os.environ["MAPS_RUN_NUMBER"] == "2"


def test_resume_reopens_existing_episode_child(monkeypatch) -> None:
    parent = FakeRun(
        run_id="historical-parent",
        name="Embedded • Run 1",
        group="Embedded • Run 1",
        config={"Ablation": "Embedded", "Run": 1},
    )
    existing = FakeRun(
        run_id="existing-episode-7",
        name="Embedded • Run 1 • Episode 7",
        group="Embedded • Run 1",
        job_type="episode",
        config={"Ablation": "Embedded", "Run": 1, "Episode": 7},
    )
    captured: dict = {}

    class Api:
        @staticmethod
        def runs(*_args, **_kwargs):
            return [existing]

    def fake_init(**kwargs):
        captured.update(kwargs)
        return FakeRun(
            run_id=kwargs["id"],
            name=kwargs["name"],
            group=kwargs["group"],
            job_type=kwargs["job_type"],
            config=dict(kwargs["config"]),
        )

    monkeypatch.setattr(wandb, "Api", lambda **_kwargs: Api())
    monkeypatch.setattr(wandb, "init", fake_init)
    monkeypatch.setattr(wandb_telemetry, "_run", parent)
    monkeypatch.setattr(wandb_telemetry, "_run_group", parent.group)
    monkeypatch.setattr(wandb_telemetry, "_run_number", 1)
    monkeypatch.setattr(wandb_telemetry, "_ablation_label", "Embedded")
    monkeypatch.setattr(wandb_telemetry, "_arm_key", "embedded")
    monkeypatch.setattr(wandb_telemetry, "_resume_parent_id", parent.id)
    monkeypatch.setattr(wandb_telemetry, "_existing_child_ids", {})
    monkeypatch.setattr(wandb_telemetry, "_existing_children_loaded", False)
    monkeypatch.setattr(wandb_telemetry, "_episode_runs", {})

    child = wandb_telemetry._episode_run(6)

    assert child.id == "existing-episode-7"
    assert captured["id"] == "existing-episode-7"
    assert captured["resume"] == "allow"


def test_reader_reconstructs_steps_from_episode_children(monkeypatch) -> None:
    class Parent:
        group = "Baseline • Run 20"

        @staticmethod
        def scan_history(**_kwargs):
            return []

    class Child:
        job_type = "episode"
        config = {"Episode": 1}

        @staticmethod
        def scan_history(**_kwargs):
            return [
                {"_step": 0, "episode": 1, "step": 1, "cash": 100},
                {"_step": 1, "episode": 1, "turn/number": 1},
                {"_step": 2, "episode": 1, "step": 2, "cash": 200},
            ]

    class Api:
        @staticmethod
        def runs(*_args, **_kwargs):
            return [Child()]

    monkeypatch.setattr(wandb_telemetry, "_api_run", lambda _path: Parent())
    monkeypatch.setattr(wandb, "Api", lambda **_kwargs: Api())
    monkeypatch.setattr(wandb_telemetry, "_history_cache", {})
    monkeypatch.setattr(wandb_telemetry, "_step_cache", {})

    rows = wandb_telemetry.read_step_rows("test-entity/test-project/parent", use_cache=False)

    assert rows == [
        {"step": 1, "cash": 100, "episode": 0},
        {"step": 2, "cash": 200, "episode": 0},
    ]


def test_reader_finds_children_when_parent_group_is_legacy(monkeypatch) -> None:
    class Parent:
        group = "legacy-parent-group"
        config = {"Ablation": "Single Agent", "Run": 4}

        @staticmethod
        def scan_history(**_kwargs):
            return []

    class Child:
        id = "episode-17"
        job_type = "episode"
        config = {"Episode": 17}

        @staticmethod
        def scan_history(**_kwargs):
            return [{"episode": 17, "step": 100, "done": True}]

    queried_groups: list[str] = []

    class Api:
        @staticmethod
        def runs(*_args, **kwargs):
            group = kwargs["filters"]["group"]
            queried_groups.append(group)
            return [Child()] if group == "Single Agent • Run 4" else []

    monkeypatch.setattr(wandb_telemetry, "_api_run", lambda _path: Parent())
    monkeypatch.setattr(wandb, "Api", lambda **_kwargs: Api())
    monkeypatch.setattr(wandb_telemetry, "_history_cache", {})
    monkeypatch.setattr(wandb_telemetry, "_step_cache", {})

    rows = wandb_telemetry.read_step_rows("test-entity/test-project/parent", use_cache=False)

    assert queried_groups == ["Single Agent • Run 4", "legacy-parent-group"]
    assert rows == [{"step": 100, "done": True, "episode": 16}]


def test_completed_episode_count_prefers_parent_summary(monkeypatch) -> None:
    parent = FakeRun(config={"Ablation": "Single Agent", "Run": 4})
    parent.summary["completed_episodes"] = "17"
    monkeypatch.setattr(wandb_telemetry, "_api_run", lambda _path: parent)
    monkeypatch.setattr(
        wandb_telemetry,
        "read_step_rows",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("child history should not be scanned")),
    )

    assert wandb_telemetry.completed_episode_count("test-entity/test-project/parent") == 17


def test_legacy_resume_is_uploaded_once(tmp_path, monkeypatch) -> None:
    parent = FakeRun(name="Baseline • Run 1", group="Baseline • Run 1")
    children: list[FakeRun] = []

    def fake_init(**kwargs) -> FakeRun:
        child = FakeRun(
            run_id=kwargs["id"],
            name=kwargs["name"],
            group=kwargs["group"],
            job_type=kwargs["job_type"],
            config=dict(kwargs["config"]),
        )
        children.append(child)
        return child

    monkeypatch.setattr(wandb, "init", fake_init)
    monkeypatch.setattr(wandb_telemetry, "_run", parent)
    monkeypatch.setattr(wandb_telemetry, "_episode_runs", {})
    monkeypatch.setattr(wandb_telemetry, "_defined_episode_metrics", {})
    monkeypatch.setattr(wandb_telemetry, "_latest_step", None)
    monkeypatch.setattr(wandb_telemetry, "_latest_steps", {})
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "run.ep000.jsonl").write_text(
        "\n".join(wandb_telemetry._json_payload(row) for row in _rows()) + "\n",
        encoding="utf-8",
    )
    (logs / "turns.jsonl").write_text(
        wandb_telemetry._json_payload(
            {
                "turn": 1,
                "attempts": 1,
                "turn_done": True,
                "verified_after": _rows()[0],
                "tokens": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (logs / "episode_cost.jsonl").write_text(
        wandb_telemetry._json_payload(
            {
                "episode": 0,
                "final_reward": 1000.0,
                "cost_usd": 1.0,
                "tokens": 10,
                "llm_calls": 1,
                "llm_seconds": 2.0,
                "cost_complete": True,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    counts = wandb_telemetry.migrate_legacy_jsonl(
        str(logs),
        str(logs / "episode_cost.jsonl"),
        str(logs / "turns.jsonl"),
    )

    assert counts == {"steps": 2, "turns": 1, "episodes": 1}
    assert wandb_telemetry.latest_step_row()["step"] == 100
    assert len(children) == 1
    child = children[0]
    assert [row.get("step") for row in child.logged[:2]] == [1, 100]
    assert child.logged[2]["turn/number"] == 1
    assert child.logged[3]["episode_cost/tokens"] == 10
    assert parent.logged[0]["run/episode"] == 1
    assert parent.logged[0]["run/episode_steps"] == 100
