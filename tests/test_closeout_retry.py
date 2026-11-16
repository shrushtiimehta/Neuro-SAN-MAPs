"""The runner treats episode close-out as a receipt-backed transaction."""

from __future__ import annotations

import json

import pytest

from apps.maps_park import runner
from coded_tools.advance_episode import AdvanceEpisode
from coded_tools.file_io import FileIO
from coded_tools.promote_trial import PromoteTrial


def _terminal() -> dict:
    return {
        "episode": 7,
        "step": 100,
        "cumulative_reward": 1_500_000.0,
        "done": True,
    }


def test_closeout_automatically_retries_until_receipt(tmp_path, monkeypatch):
    receipt_path = tmp_path / "closeout_receipt.json"
    monkeypatch.setattr(runner, "CLOSEOUT_RECEIPT_PATH", str(receipt_path))
    calls: list[str] = []

    def fake_consult(_session, _thread, _kind, verified, label="macro", extra=""):
        del label
        calls.append(extra)
        if len(calls) == 1:
            return "ERROR: simulated ResolveTrials failure"
        receipt_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "episode": verified["episode"],
                    "final_reward": verified["cumulative_reward"],
                }
            )
        )
        return "1 promoted, 0 falsified, final=1500000"

    monkeypatch.setattr(runner, "consult", fake_consult)
    response = runner.close_episode_with_retry(object(), {}, _terminal(), max_retries=2)

    assert response == "1 promoted, 0 falsified, final=1500000"
    assert len(calls) == 2
    assert "retry=false" in calls[0]
    assert "retry=true" in calls[1]


def test_closeout_stops_instead_of_advancing_after_exhaustion(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "CLOSEOUT_RECEIPT_PATH", str(tmp_path / "missing_receipt.json"))
    calls = 0

    def failed_consult(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return "ERROR: still broken"

    monkeypatch.setattr(runner, "consult", failed_consult)
    with pytest.raises(RuntimeError, match="stopped before advancing"):
        runner.close_episode_with_retry(object(), {}, _terminal(), max_retries=2)
    assert calls == 3


def test_committed_closeout_is_not_repeated(tmp_path, monkeypatch):
    receipt_path = tmp_path / "closeout_receipt.json"
    receipt_path.write_text(
        json.dumps(
            {
                "version": 1,
                "episode": 7,
                "final_reward": 1_500_000.0,
            }
        )
    )
    monkeypatch.setattr(runner, "CLOSEOUT_RECEIPT_PATH", str(receipt_path))

    def should_not_run(*_args, **_kwargs):
        raise AssertionError("committed close-out was invoked again")

    monkeypatch.setattr(runner, "consult", should_not_run)
    assert runner.close_episode_with_retry(object(), {}, _terminal(), max_retries=2) is None


def test_baseline_closeout_does_not_write_last_reward(tmp_path, monkeypatch):
    reward_path = tmp_path / "last_reward.md"
    receipt_path = tmp_path / "closeout_receipt.json"
    pending_path = tmp_path / ".advance_episode.pending.json"
    observation_path = tmp_path / "latest_observations.json"
    monkeypatch.setattr(AdvanceEpisode, "WRITE_LAST_REWARD", False)
    monkeypatch.setattr(AdvanceEpisode, "LAST_REWARD_PATH", str(reward_path))
    monkeypatch.setattr(AdvanceEpisode, "CLOSEOUT_RECEIPT_PATH", str(receipt_path))
    monkeypatch.setattr(AdvanceEpisode, "PENDING_PATH", str(pending_path))
    monkeypatch.setattr(AdvanceEpisode, "LATEST_OBS_PATH", str(observation_path))

    result = AdvanceEpisode().invoke({"episode": 7, "final_reward": 1_500_000}, {})

    assert result["status"] == "ok"
    assert "last_reward_written" not in result
    assert not reward_path.exists()
    assert receipt_path.exists()


def test_retried_promotion_does_not_duplicate_rule(tmp_path, monkeypatch):
    state_dir = tmp_path / "state"
    seed_dir = tmp_path / "seeds"
    state_dir.mkdir()
    seed_dir.mkdir()
    (state_dir / "playbook_rides.md").write_text("# Rides\n## Timing\n")
    (seed_dir / "seed_playbook_rides.md").write_text("# Rides\n## Learned rules (promoted from prior runs)\n")
    monkeypatch.setattr(PromoteTrial, "STATE_DIR", str(state_dir))
    monkeypatch.setattr(PromoteTrial, "SEED_DIR", str(seed_dir))
    monkeypatch.setattr(PromoteTrial, "MERGED", False)

    args = {
        "domain": "rides",
        "edit_type": "add_line",
        "section": "## Timing",
        "new_text": "- Open the anchor ride first.",
        "episode": 7,
    }
    first = PromoteTrial().invoke(args, {})
    second = PromoteTrial().invoke(args, {})

    assert first["action_taken"] == "promoted"
    assert second["action_taken"] == "already_promoted"
    learned = "- Open the anchor ride first. (learned ep7)"
    assert (state_dir / "playbook_rides.md").read_text().count(learned) == 1
    assert (seed_dir / "seed_playbook_rides.md").read_text().count(learned) == 1


def test_advance_failure_restores_prior_reward_before_retry(tmp_path, monkeypatch):
    reward_path = tmp_path / "last_reward.md"
    receipt_path = tmp_path / "closeout_receipt.json"
    pending_path = tmp_path / ".advance_episode.pending.json"
    reward_path.write_text("cumulative_reward: 900\n")
    monkeypatch.setattr(AdvanceEpisode, "LAST_REWARD_PATH", str(reward_path))
    monkeypatch.setattr(AdvanceEpisode, "CLOSEOUT_RECEIPT_PATH", str(receipt_path))
    monkeypatch.setattr(AdvanceEpisode, "PENDING_PATH", str(pending_path))
    monkeypatch.setattr(AdvanceEpisode, "LATEST_OBS_PATH", str(tmp_path / "latest.json"))

    real_write = FileIO.write_text_atomic
    failed_once = False

    def fail_receipt_once(path, content):
        nonlocal failed_once
        if path == str(receipt_path) and not failed_once:
            failed_once = True
            raise OSError("simulated receipt failure")
        return real_write(path, content)

    monkeypatch.setattr(FileIO, "write_text_atomic", fail_receipt_once)
    first = AdvanceEpisode().invoke({"episode": 7, "final_reward": 1_500_000}, {})
    assert str(first).startswith("ERROR:")
    assert reward_path.read_text() == "cumulative_reward: 900\n"
    assert not pending_path.exists()

    second = AdvanceEpisode().invoke({"episode": 7, "final_reward": 1_500_000}, {})
    assert second["status"] == "ok"
    assert reward_path.read_text() == "cumulative_reward: 1500000\n"
    assert json.loads(receipt_path.read_text())["episode"] == 7
