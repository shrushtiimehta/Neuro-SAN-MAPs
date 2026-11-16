import json
from typing import Any

from scripts.backfill_ablation_traces_to_weave import episode_traces
from scripts.import_all_ablation_history_to_wandb import _history_rows
from scripts.import_all_ablation_history_to_wandb import _run_history_rows
from scripts.import_all_ablation_history_to_wandb import all_records
from scripts.import_all_ablation_history_to_wandb import discover
from scripts.import_grouped_ablation_episodes_to_wandb import episode_scalar_values
from scripts.reconcile_baseline_history_to_wandb import authoritative_baseline_runs


def _jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_discover_excludes_one_episode_and_keeps_full_records(tmp_path):
    logs = tmp_path / "neuro-san-studio-test" / "logs"
    kept = logs / "maps_ablation_test"
    excluded = logs / "maps_ablation_short"
    _jsonl(kept / "run.ep000.jsonl", [{"episode": 0, "nested": {"x": 1}}])
    _jsonl(kept / "run.ep001.jsonl", [{"episode": 1, "custom": [1, 2]}])
    _jsonl(
        kept / "turns.jsonl",
        [
            {
                "anything": {"is": "preserved"},
                "tokens": {
                    "total_tokens": 12,
                    "prompt_tokens": 7,
                    "completion_tokens": 5,
                },
            }
        ],
    )
    _jsonl(kept / "episode_cost.jsonl", [{"episode": 0, "cost_usd": 1.25}])
    _jsonl(kept / "park_ids.jsonl", [{"park_id": "abc"}])
    _jsonl(excluded / "run.ep000.jsonl", [{"episode": 0}])

    result = discover(tmp_path)
    records = all_records(result.runs)

    assert len(result.runs) == 1
    assert result.excluded_one_episode == (excluded.resolve(),)
    assert records["trajectory"][0]["record"] == {"episode": 0, "nested": {"x": 1}}
    assert records["trajectory"][1]["record"] == {"episode": 1, "custom": [1, 2]}
    assert records["turn"][0]["record"]["anything"] == {"is": "preserved"}
    assert records["episode_cost"][0]["record"]["cost_usd"] == 1.25
    assert records["park_id"][0]["record"]["park_id"] == "abc"

    history = _history_rows(result.runs[0])
    assert history[0]["episode"] == 1
    assert history[0]["nested/x"] == 1
    assert not any(key.startswith("trajectory/") for row in history for key in row)
    turn_row = next(row for row in history if "total_tokens" in row)
    assert turn_row["total_tokens"] == 12
    assert "turn/tokens/total_tokens" not in turn_row
    assert turn_row["prompt_tokens"] == 7
    assert turn_row["completion_tokens"] == 5
    assert "turn/tokens/prompt_tokens" not in turn_row
    assert "turn/tokens/completion_tokens" not in turn_row
    assert "episode_index" not in history[0]
    assert "maps/payload" not in history[0]
    assert any(row.get("episode_cost/cost_usd") == 1.25 for row in history)
    assert any(row.get("park/park_id") == "abc" for row in history)

    run_history = _run_history_rows(result.runs[0])
    assert [row["run/episode"] for row in run_history] == [1, 2]
    assert run_history[0]["run/episode_cost/cost_usd"] == 1.25
    assert run_history[0]["run/park/park_id"] == "abc"
    assert not any(key.startswith(("trajectory/", "turn/")) for row in run_history for key in row)


def test_discover_deduplicates_identical_worktree_copies(tmp_path):
    repo: Any
    for repo in ("neuro-san-studio-a", "neuro-san-studio-b"):
        run = tmp_path / repo / "logs/maps_ablation_same"
        _jsonl(run / "run.ep000.jsonl", [{"episode": 0}])
        _jsonl(run / "run.ep001.jsonl", [{"episode": 1}])

    result = discover(tmp_path)

    assert len(result.runs) == 1
    assert len(result.duplicate_directories) == 1


def test_episode_scalar_values_keeps_only_single_episode_cards():
    rows = [
        {"step": 100, "cash": 100, "done": True},
        {"episode_cost/tokens": 123, "episode_cost/llm_calls": 4},
        {"cumulative_reward": 456, "park/final_value": 789},
    ]

    assert episode_scalar_values(rows) == {
        "cumulative_reward": 456,
        "episode_cost/tokens": 123,
        "episode_cost/llm_calls": 4,
        "park/final_value": 789,
    }


def test_authoritative_baselines_partition_ledgers_and_use_filename_episodes(tmp_path):
    logs = tmp_path / "logs/maps_park"
    first = logs / "prior-runs/20260730-033048"
    second = logs / "prior-runs/20260730-232001"
    directory: Any
    prefix: Any
    rewards: Any
    for directory, prefix, rewards in (
        (first, "11111111-1111-1111-1111-111111111111", (10, 20)),
        (second, "22222222-2222-2222-2222-222222222222", (30, 40)),
    ):
        episode: Any
        reward: Any
        for episode, reward in enumerate(rewards):
            # Deliberately repeat the embedded value: filenames remain canonical.
            _jsonl(
                directory / f"run.ep{episode:03d}.jsonl",
                [{"episode": 0, "step": 100, "done": True, "cumulative_reward": reward}],
            )
        _jsonl(directory / "turns.jsonl", [])
        (directory / f"{prefix}_1.tsv").write_text("x\n", encoding="utf-8")

    _jsonl(
        logs / "park_ids.jsonl",
        [
            {
                "episode": index,
                "run_episode": 0,
                "park_id": park_id,
                "final_value": value,
            }
            for index, (park_id, value) in enumerate(
                (
                    ("11111111-1111-1111-1111-111111111111", 10),
                    ("22222222-2222-2222-2222-222222222222", 30),
                )
            )
        ],
    )
    _jsonl(
        logs / "episode_cost.jsonl",
        [
            {"episode": 0, "final_reward": 10},
            {"episode": 1, "final_reward": 20},
            {"episode": 0, "final_reward": 30},
            {"episode": 1, "final_reward": 40},
        ],
    )

    runs = authoritative_baseline_runs(tmp_path)

    assert [run.directory.name for run in runs] == [
        "20260730-033048",
        "20260730-232001",
    ]
    assert [trace.episode_index for trace in episode_traces(runs[0])] == [0, 1]
    assert [len(next(file for file in run.files if file.name == "park_ids.jsonl").rows) for run in runs] == [1, 1]
    assert [len(next(file for file in run.files if file.name == "episode_cost.jsonl").rows) for run in runs] == [2, 2]
