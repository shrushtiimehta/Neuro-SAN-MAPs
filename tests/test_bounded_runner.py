"""Guards for the optional completed-episode runner limit."""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.maps_park import bounded_runner


def test_stops_before_episode_eleven(monkeypatch) -> None:
    monkeypatch.setattr(bounded_runner, "EPISODE_LIMIT", 10)
    monkeypatch.setattr(bounded_runner, "_completed", 9)
    monkeypatch.setattr(
        bounded_runner,
        "_base_write_episode_cost",
        lambda episode, reward: {"episode": episode, "final_reward": reward},
    )

    bounded_runner._write_cost_and_count(9, 1234)
    assert bounded_runner._completed == 10
    with pytest.raises(KeyboardInterrupt) as _raised_error:
        bounded_runner._BoundedSeedPlaybooks().invoke({"overwrite": False}, {})


def test_unlimited_mode_never_stops_at_seed_boundary(monkeypatch) -> None:
    monkeypatch.setattr(bounded_runner, "EPISODE_LIMIT", None)
    monkeypatch.setattr(bounded_runner, "_completed", 10_000)
    monkeypatch.setattr(
        bounded_runner._BaseSeedPlaybooks,
        "invoke",
        lambda _self, _args, _sly_data: {"seeded": 0},
    )

    assert bounded_runner._BoundedSeedPlaybooks().invoke({}, {}) == {"seeded": 0}


@pytest.mark.parametrize("value", ["0", "none", "unlimited", "infinite", "inf"])
def test_unlimited_limit_values(value, monkeypatch) -> None:
    monkeypatch.setenv("MAPS_EPISODE_LIMIT", value)
    assert bounded_runner._episode_limit() is None


def test_resume_counts_completed_episodes_once(tmp_path, monkeypatch) -> None:
    ledger = tmp_path / "episode_cost.jsonl"
    ledger.write_text(
        '{"episode":0,"cost_usd":1}\n{"episode":1,"cost_usd":2}\n{"episode":1,"cost_usd":2}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(bounded_runner.sys, "argv", ["bounded_runner", "--resume"])
    monkeypatch.setattr(bounded_runner.runner, "EPISODE_COST_PATH", str(ledger))
    monkeypatch.setattr(
        bounded_runner.runner.wandb_telemetry,
        "completed_episode_count",
        lambda: (_ for _ in ()).throw(AssertionError("resume count must come from the local ledger")),
    )
    assert bounded_runner._resume_completed_count() == 2


def test_baseline_launcher_uses_bounded_runner() -> None:
    source = (Path(__file__).resolve().parents[1] / "apps/maps_park/run_baseline_services.sh").read_text()
    assert 'MAPS_EPISODE_LIMIT="${MAPS_EPISODE_LIMIT:-10}"' in source
    assert "apps.maps_park.bounded_runner" in source
    assert "MAPS_USE_LAST_REWARD=0" in source
    assert "run_ablation_services.sh" in source
    assert "run_all.sh" not in source


def test_replica_launcher_preserves_explicit_episode_limit() -> None:
    source = (Path(__file__).resolve().parents[1] / "apps/maps_park/run_replica_ablation.sh").read_text()
    assert 'episode_limit_override="${MAPS_EPISODE_LIMIT-}"' in source
    assert 'export MAPS_EPISODE_LIMIT="$episode_limit_override"' in source
