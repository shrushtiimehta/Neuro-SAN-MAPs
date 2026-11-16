from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.merge_ablation_replicates import merge


def _jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_merge_preserves_replicate_identity(tmp_path: Path) -> None:
    repos = []
    number: Any
    for number in (2, 3):
        repo = tmp_path / f"repo-{number}"
        repo.mkdir()
        (repo / ".ablation-instance.env").write_text(
            f"MAPS_REPLICA_ID=r{number}\n"
            f"MAPS_ABLATION_ARM=arm-{number}\n"
            "MAPS_LOG_RELATIVE=logs/arm\n"
            f"MAPS_NODE_PORT=30{number}0\n",
            encoding="utf-8",
        )
        logs = repo / "logs/arm"
        rows = [{"episode": 0, "step": step, "done": step == 100} for step in range(1, 101)]
        _jsonl(logs / "run.ep000.jsonl", rows)
        _jsonl(logs / "turns.jsonl", [{"turn": 1}])
        _jsonl(logs / "episode_cost.jsonl", [{"episode": 0, "cost_usd": number}])
        _jsonl(
            logs / "park_ids.jsonl",
            [
                {"episode": 99, "park_id": "stale-park"},
                {"episode": 0, "park_id": f"park-{number}"},
            ],
        )
        (logs / f"park-{number}.tsv").write_text("step\taction\n", encoding="utf-8")
        repos.append(repo)

    output = tmp_path / "merged"
    manifest = merge(repos, output, None, expected_episodes=1)

    assert manifest["merged_counts"]["steps.jsonl"] == 200
    costs = [json.loads(line) for line in (output / "episode_cost.jsonl").read_text().splitlines()]
    assert {row["replicate"] for row in costs} == {"r2", "r3"}
    assert {row["arm"] for row in costs} == {"arm-2", "arm-3"}
    park_rows = [json.loads(line) for line in (output / "park_ids.jsonl").read_text().splitlines()]
    assert {row["park_id"] for row in park_rows} == {"park-2", "park-3"}
    assert (output / "trajectories/r2/park-2.tsv").is_file()
