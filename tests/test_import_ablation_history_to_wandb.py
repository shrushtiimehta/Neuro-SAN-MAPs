import json

from scripts.import_ablation_history_to_wandb import Source
from scripts.import_ablation_history_to_wandb import prepare


def _write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_prepare_excludes_partial_tail_and_uses_one_based_episodes(tmp_path):
    _write_jsonl(
        tmp_path / "run.ep000.jsonl",
        [
            {"episode": 0, "step": 1, "cumulative_reward": 10, "done": False},
            {"episode": 0, "step": 100, "cumulative_reward": 25, "done": True},
        ],
    )
    _write_jsonl(
        tmp_path / "run.ep001.jsonl",
        [{"episode": 1, "step": 12, "cumulative_reward": 4, "done": False}],
    )
    _write_jsonl(
        tmp_path / "turns.jsonl",
        [
            {"verified_after": {"episode": 0, "step": 1}, "tokens": {}},
            {"verified_after": {"episode": 1, "step": 12}, "tokens": {}},
        ],
    )

    run = prepare(Source("test", "Test", "solo", 1, log_dir=tmp_path))

    assert len(run.steps) == 2
    assert len(run.turns) == 1
    assert len(run.episodes) == 1
    assert run.episodes[0]["episode"] == 1
    assert run.episodes[0]["episode_index"] == 0
    assert run.episodes[0]["final_score"] == 25


def test_prepare_accepts_supplied_score_only_run():
    run = prepare(
        Source(
            "provided",
            "Provided",
            "baseline",
            2,
            supplied_scores={0: 100.0, 1: 200.0},
        )
    )

    assert run.steps == []
    assert run.turns == []
    assert [row["episode"] for row in run.episodes] == [1, 2]
    assert [row["final_score"] for row in run.episodes] == [100.0, 200.0]
