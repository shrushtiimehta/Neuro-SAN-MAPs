"""Regression tests for the corrected four-arm MAPs ablation pipeline."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from apps.maps_park import ablation_runner
from apps.maps_park import runner as maps_runner
from apps.maps_park import validate_ablations
from coded_tools.ablations.shared.clear_episode_micro_strategies import ClearEpisodeMicroStrategies
from coded_tools.ablations.unstructured_player_planner_watcher.read_episode_learning_history import (
    ReadEpisodeLearningHistory,
)
from coded_tools.ablations.unstructured_player_planner_watcher.save_episode_learning_record import (
    SaveEpisodeLearningRecord,
)
from coded_tools.ablations.unstructured_player_planner_watcher.write_unstructured_plan import WriteUnstructuredPlan
from coded_tools.seed_playbooks import SeedPlaybooks
from coded_tools.write_episode_plan import WriteEpisodePlan

ROOT = Path(__file__).resolve().parents[1]


def test_full_zero_cost_preflight() -> None:
    validate_ablations.main()


def test_micro_strategies_are_deleted_but_macro_is_preserved(tmp_path, monkeypatch) -> None:
    strategies = tmp_path / "trial_strategies.md"
    criteria = tmp_path / "trial_strategies_criteria.md"
    strategies.write_text("- t2_1: macro rule\n- t2_2: watcher rule\n", encoding="utf-8")
    criteria.write_text(
        "- t2_1 ep=2 step_start=1 domain=rides origin=macro section='new' edit=add_line "
        "rationale='r' success='s' failure='f'\n"
        "- t2_2 ep=2 step_start=20 domain=shops origin=micro section='new' edit=add_line "
        "rationale='r' success='s' failure='f'\n",
        encoding="utf-8",
    )
    import coded_tools.ablations.shared.clear_episode_micro_strategies as module

    monkeypatch.setattr(module, "STRATEGIES_PATH", str(strategies))
    monkeypatch.setattr(module, "CRITERIA_PATH", str(criteria))
    result = ClearEpisodeMicroStrategies().invoke({"episode": 2}, {})
    assert result["removed"] == ["t2_2"]
    assert "t2_1" in strategies.read_text(encoding="utf-8")
    assert "t2_2" not in strategies.read_text(encoding="utf-8")
    assert "t2_2" not in criteria.read_text(encoding="utf-8")


def test_next_watching_reads_then_retires_old_micro_and_preserves_new(tmp_path, monkeypatch) -> None:
    strategies = tmp_path / "trial_strategies.md"
    criteria = tmp_path / "trial_strategies_criteria.md"
    strategies.write_text(
        "- t2_1: persistent macro\n- t2_2: previous watcher guidance\n",
        encoding="utf-8",
    )
    criteria.write_text(
        "- t2_1 ep=2 step_start=1 domain=rides origin=macro section='new' edit=add_line "
        "rationale='r' success='s' failure='f'\n"
        "- t2_2 ep=2 step_start=20 domain=shops origin=micro section='new' edit=add_line "
        "rationale='r' success='s' failure='f'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ablation_runner, "STRATEGIES_PATH", str(strategies))
    monkeypatch.setattr(ablation_runner, "CRITERIA_PATH", str(criteria))

    def fake_consult(session, thread, kind, verified, label="consultant", extra=""):
        del session, thread, verified, label
        assert kind == "periodic"
        assert '"trial_id":"t2_2"' in extra
        assert "previous watcher guidance" in extra
        # Simulate a strategy created during this watching. The post-watch
        # retirement must not confuse it with the incoming snapshot.
        with strategies.open("a", encoding="utf-8") as handle:
            handle.write("- t2_3: new watcher guidance\n")
        with criteria.open("a", encoding="utf-8") as handle:
            handle.write(
                "- t2_3 ep=2 step_start=30 domain=staff origin=micro section='new' "
                "edit=add_line rationale='r' success='s' failure='f'\n"
            )
        return "VERDICT: underperforming | refreshed guidance"

    monkeypatch.setattr(ablation_runner, "_base_consult", fake_consult)
    ablation_runner._ablation_consult(None, None, "periodic", {"episode": 2, "step": 30}, label="micro")

    strategy_text = strategies.read_text(encoding="utf-8")
    criteria_text = criteria.read_text(encoding="utf-8")
    assert "t2_1" in strategy_text and "t2_1" in criteria_text
    assert "t2_2" not in strategy_text and "t2_2" not in criteria_text
    assert "t2_3" in strategy_text and "t2_3" in criteria_text


def test_episode_learning_journal_is_idempotent_and_readable(tmp_path, monkeypatch) -> None:
    journal = tmp_path / "episode_learnings.md"
    monkeypatch.setattr(SaveEpisodeLearningRecord, "PATH", str(journal))
    monkeypatch.setattr(ReadEpisodeLearningHistory, "PATH", str(journal))
    tool = SaveEpisodeLearningRecord()
    base = {
        "episode": 3,
        "final_reward": 1200,
        "worked": ["step 10: ride revenue rose"],
        "did_not_work": ["step 40: rejected placement wasted one action"],
        "summary": "Build reachable earning assets before speculative spending.",
    }
    assert tool.invoke(base, {})["action"] == "appended"
    revised = dict(base, summary="Keep the reachable ride sequence; remove the rejected placement.")
    assert tool.invoke(revised, {})["action"] == "replaced"
    text = journal.read_text(encoding="utf-8")
    assert text.count("## Episode 3") == 1
    assert "What did not work / ruined the run" in text
    read = ReadEpisodeLearningHistory().invoke({"scope": "all"}, {})
    assert read["exists"] is True and "reachable ride sequence" in read["content"]


def test_unstructured_writer_creates_one_complete_plan_only(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(WriteEpisodePlan, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(WriteEpisodePlan, "MERGED", False)
    (tmp_path / "playbook_coordinator.md").write_text("# Coordinator\n", encoding="utf-8")
    result = WriteUnstructuredPlan().invoke(
        {
            "strategy": (
                "One complete plan covering rides, shops, staff, research, layout, surveys, cash, and adaptation."
            )
        },
        {},
    )
    assert result["strategy_written"] is True
    plan = json.loads((tmp_path / "plan_current.json").read_text(encoding="utf-8"))
    assert list(plan) == ["checklist_items", "strategy_summary", "playbook_summaries"]
    assert plan["playbook_summaries"] == {}
    assert len(plan["checklist_items"]) == 1
    assert "One complete plan" in plan["strategy_summary"]


def test_all_new_shell_runners_are_valid_bash() -> None:
    names = [
        "run_ablation_services.sh",
        "run_player_with_watcher.sh",
        "run_player_with_planner.sh",
        "run_embedded_player_planner_watcher.sh",
        "run_unstructured_player_planner_watcher.sh",
        "run_g_memory_player_planner_watcher.sh",
        "run_single_agent_ablation.sh",
        "run_multi_player_single_planner.sh",
        "run_single_player_multi_planner_watcher.sh",
        "run_all_ablation_arms.sh",
    ]
    name: Any
    for name in names:
        path = ROOT / "apps" / "maps_park" / name
        subprocess.run(["bash", "-n", str(path)], check=True)
        assert path.stat().st_mode & 0o111


def test_ablation_services_default_openai_to_responses_api() -> None:
    source = (ROOT / "apps/maps_park/run_ablation_services.sh").read_text()
    assert 'export LC_OUTPUT_VERSION="${LC_OUTPUT_VERSION:-responses/v1}"' in source


def test_ablation_services_exclude_archived_telemetry_by_default() -> None:
    source = (ROOT / "apps/maps_park/run_ablation_services.sh").read_text()
    assert 'export MAPS_INCLUDE_ARCHIVED="${MAPS_INCLUDE_ARCHIVED:-0}"' in source
    assert "--include-archived" in source


def test_single_agent_ablation_resets_inherited_archived_telemetry() -> None:
    source = (ROOT / "apps/maps_park/run_single_agent_ablation.sh").read_text()
    assert "export MAPS_INCLUDE_ARCHIVED=0" in source


def test_bounded_runner_stops_before_episode_eleven(monkeypatch) -> None:
    monkeypatch.setattr(ablation_runner, "EPISODE_LIMIT", 10)
    monkeypatch.setattr(ablation_runner, "_completed", 9)
    monkeypatch.setattr(
        ablation_runner,
        "_base_write_episode_cost",
        lambda episode, reward: {"episode": episode, "final_reward": reward},
    )

    class FakeClear:
        def invoke(self, args, sly_data):
            return {"removed": [], "removed_count": 0}

    monkeypatch.setattr(ablation_runner, "ClearEpisodeMicroStrategies", FakeClear)
    ablation_runner._write_cost_and_close(9, 1234)
    assert ablation_runner._completed == 10
    with pytest.raises(KeyboardInterrupt) as _raised_error:
        ablation_runner._BoundedSeedPlaybooks().invoke({"overwrite": False}, {})


def test_resume_counts_prior_completed_episodes(tmp_path, monkeypatch) -> None:
    ledger = tmp_path / "episode_cost.jsonl"
    ledger.write_text(
        '{"episode":0,"cost_usd":1}\n{"episode":1,"cost_usd":2}\n{"episode":1,"cost_usd":2}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(ablation_runner.sys, "argv", ["ablation_runner", "--resume"])
    monkeypatch.setattr(ablation_runner.runner, "EPISODE_COST_PATH", str(ledger))
    assert ablation_runner._resume_completed_count() == 2


def test_external_seed_mirror_survives_fresh_archive(tmp_path, monkeypatch) -> None:
    state_dir = tmp_path / "state"
    seed_dir = tmp_path / "seeds"
    state_dir.mkdir()
    seed_dir.mkdir()
    (state_dir / "stale_runtime_file.md").write_text("old run", encoding="utf-8")
    source: Any
    for source in (ROOT / "coded_tools" / "config_files").glob("seed_playbook_*.md"):
        shutil.copy2(source, seed_dir / source.name)

    monkeypatch.setattr(maps_runner, "PLAYBOOK_STATE_DIR", str(state_dir))
    monkeypatch.setattr(maps_runner, "PLAYBOOK_HISTORY_DIR", str(state_dir / "playbook_history"))
    monkeypatch.setattr(SeedPlaybooks, "STATE_DIR", str(state_dir))
    monkeypatch.setattr(SeedPlaybooks, "SEED_DIR", str(seed_dir))
    monkeypatch.setattr(SeedPlaybooks, "MERGED", False)

    maps_runner.archive_state()
    result = SeedPlaybooks().invoke({"overwrite": True}, {})
    assert result["errors"] == []
    assert len(result["seeded"]) == 7
    assert (state_dir / "playbook_coordinator.md").is_file()
    assert (seed_dir / "seed_playbook_coordinator.md").is_file()


def test_seed_error_stops_before_any_llm_turn(monkeypatch) -> None:
    monkeypatch.setattr(ablation_runner, "_completed", 0)
    monkeypatch.setattr(
        ablation_runner._BaseSeedPlaybooks,
        "invoke",
        lambda self, args, sly_data: {"errors": ["playbook_coordinator: missing seed"]},
    )
    with pytest.raises(RuntimeError, match="before the first LLM turn") as _raised_error:
        ablation_runner._BoundedSeedPlaybooks().invoke({"overwrite": True}, {})


def test_ablation_adapter_preserves_canonical_player_retry_loop() -> None:
    source = (ROOT / "apps" / "maps_park" / "ablation_runner.py").read_text(encoding="utf-8")
    assert "def _strict_chat" not in source
    assert "runner.chat =" not in source


@pytest.mark.skip(reason="strict chat adapter removed; canonical retry loop is used")
def test_explicit_agent_error_is_never_retried(monkeypatch) -> None:
    monkeypatch.setattr(
        ablation_runner,
        "_base_chat",
        lambda *args, **kwargs: (
            "ERROR: file_not_found: playbook_coordinator.md",
            {"thread": "unused"},
            {"total_cost": 0.01},
        ),
    )
    with pytest.raises(RuntimeError, match="refusing retries") as _raised_error:
        ablation_runner._strict_chat(None, None, "one turn")


@pytest.mark.skip(reason="special layout recovery removed; canonical retry loop is used")
@pytest.mark.parametrize(
    "error",
    [
        "ERROR: 'reachable_tiles'",
        "ERROR: No tool/state provided for the map layout (reachable_tiles); "
        "ProposeAction failed with an invalid coordinate.",
    ],
)
def test_scoped_layout_error_allows_one_canonical_correction(monkeypatch, error) -> None:
    monkeypatch.setattr(
        ablation_runner,
        "_base_chat",
        lambda *args, **kwargs: (error, {"thread": "kept"}, {"total_cost": 0.1}),
    )
    response, thread, accounting = ablation_runner._strict_chat(
        None, None, "[PREFLIGHT MODE] continue\n\nTake one action on park 0."
    )
    assert response == error
    assert thread == {"thread": "kept"}
    assert accounting["total_cost"] == 0.1


@pytest.mark.skip(reason="strict chat adapter removed; canonical retry loop is used")
def test_repeated_scoped_layout_error_remains_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr(
        ablation_runner,
        "_base_chat",
        lambda *args, **kwargs: ("ERROR: 'reachable_tiles'", {}, {"total_cost": 0.1}),
    )
    with pytest.raises(RuntimeError, match="refusing retries") as _raised_error:
        ablation_runner._strict_chat(
            None,
            None,
            "[PREFLIGHT MODE] continue\n\nERROR: no action was proposed this turn. Re-run your per-turn sequence.",
        )


@pytest.mark.skip(reason="strict chat adapter removed; canonical retry loop is used")
def test_missing_first_episode_reference_uses_deterministic_fallback(monkeypatch) -> None:
    error = (
        "ERROR: required best-run telemetry contained no step rows/reference episode, "
        "so a metric gap vs best cannot be computed."
    )
    monkeypatch.setattr(
        ablation_runner,
        "_base_chat",
        lambda *args, **kwargs: (error, {"thread": "kept"}, {"total_cost": 0.25}),
    )
    monkeypatch.setattr(
        ablation_runner.RunTelemetry,
        "invoke",
        lambda self, args, sly_data: {
            "scope": "select",
            "exists": False,
            "reference_available": False,
            "reference_episode": None,
        },
    )

    response, thread, accounting = ablation_runner._strict_chat(None, None, "kind=periodic episode=0 step=30")

    assert response.startswith("VERDICT: on_track")
    assert thread == {"thread": "kept"}
    assert accounting["total_cost"] == 0.25


@pytest.mark.skip(reason="strict chat adapter removed; canonical retry loop is used")
def test_missing_reference_error_still_fails_when_reference_exists(monkeypatch) -> None:
    error = "ERROR: best-run reference episode has no step rows"
    monkeypatch.setattr(
        ablation_runner,
        "_base_chat",
        lambda *args, **kwargs: (error, {}, {"total_cost": 0.25}),
    )
    monkeypatch.setattr(
        ablation_runner.RunTelemetry,
        "invoke",
        lambda self, args, sly_data: {
            "scope": "select",
            "exists": True,
            "reference_available": True,
            "reference_episode": {"steps": [{"step": 30}]},
        },
    )

    with pytest.raises(RuntimeError, match="refusing retries") as _raised_error:
        ablation_runner._strict_chat(None, None, "kind=periodic episode=1 step=30")


@pytest.mark.skip(reason="strict chat adapter removed; canonical retry loop is used")
def test_empty_scratchpad_serialization_error_does_not_kill_watcher(monkeypatch) -> None:
    monkeypatch.setattr(
        ablation_runner,
        "_base_chat",
        lambda *args, **kwargs: (
            "ERROR: scratchpad was read with a note argument instead of no args; procedure violated.",
            {"thread": "kept"},
            {"total_cost": 1.25},
        ),
    )

    response, thread, accounting = ablation_runner._strict_chat(None, None, "kind=periodic episode=2 step=20")

    assert response.startswith("VERDICT: underperforming")
    assert thread == {"thread": "kept"}
    assert accounting["total_cost"] == 1.25


@pytest.mark.skip(reason="strict chat adapter removed; canonical retry loop is used")
def test_omitted_scratchpad_note_serialized_empty_does_not_kill_watcher(monkeypatch) -> None:
    monkeypatch.setattr(
        ablation_runner,
        "_base_chat",
        lambda *args, **kwargs: (
            "ERROR: scratchpad was called with an empty note argument instead of being omitted; stop instantly.",
            {"thread": "kept"},
            {"total_cost": 1.5},
        ),
    )

    response, thread, accounting = ablation_runner._strict_chat(None, None, "kind=periodic episode=2 step=30")

    assert response.startswith("VERDICT: underperforming")
    assert thread == {"thread": "kept"}
    assert accounting["total_cost"] == 1.5


@pytest.mark.skip(reason="strict chat adapter removed; canonical retry loop is used")
def test_incomplete_optional_watcher_cycle_continues_without_retry(monkeypatch) -> None:
    monkeypatch.setattr(
        ablation_runner,
        "_base_chat",
        lambda *args, **kwargs: (
            "ERROR: incomplete live-correction cycle before final response",
            {"thread": "kept"},
            {"total_cost": 1.40702225},
        ),
    )

    response, thread, accounting = ablation_runner._strict_chat(None, None, "kind=periodic episode=0 step=50")

    assert response.startswith("WATCHER NOTICE:")
    assert "without a paid retry" not in response
    assert thread == {"thread": "kept"}
    assert accounting["total_cost"] == 1.40702225
