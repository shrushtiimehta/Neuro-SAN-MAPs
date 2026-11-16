"""Structural guards for the two mixed single/multi-agent repository arms."""

from __future__ import annotations

import re
from pathlib import Path

from apps.maps_park import single_planner_ablation_runner
from apps.maps_park import validate_ablations

ROOT = Path(__file__).resolve().parents[1]
REGISTRIES = ROOT / "registries" / "ablations"


def _llm_agents(path: Path) -> list[str]:
    config = validate_ablations._load(path)
    return [tool["name"] for tool in config["tools"] if tool.get("instructions")]


def test_multi_player_single_planner_topology() -> None:
    arm = REGISTRIES / "multi_player_single_planner"
    assert _llm_agents(arm / "planner_single.hocon") == ["single_planner"]
    player = validate_ablations._load(arm / "player_ablation.hocon")
    assert len([tool for tool in player["tools"] if tool.get("instructions")]) == 7

    launcher = (ROOT / "apps/maps_park/run_multi_player_single_planner.sh").read_text()
    assert "MAPS_RUNNER_AGENT=player_ablation" in launcher
    assert "MAPS_MICRO_AGENT=planner_single" in launcher
    assert "MAPS_MACRO_AGENT=planner_single" in launcher
    assert "single_planner_ablation_runner" in launcher


def test_single_player_multi_planner_watcher_topology() -> None:
    arm = REGISTRIES / "single_player_multi_planner_watcher"
    assert _llm_agents(arm / "player_single.hocon") == ["single_player"]
    planner = validate_ablations._load(arm / "planner_ablation.hocon")
    watcher = validate_ablations._load(arm / "watcher_ablation.hocon")
    assert len([tool for tool in planner["tools"] if tool.get("instructions")]) == 3
    assert len([tool for tool in watcher["tools"] if tool.get("instructions")]) == 1

    launcher = (ROOT / "apps/maps_park/run_single_player_multi_planner_watcher.sh").read_text()
    assert "MAPS_RUNNER_AGENT=player_single" in launcher
    assert "MAPS_MICRO_AGENT=watcher_ablation" in launcher
    assert "MAPS_MACRO_AGENT=planner_ablation" in launcher


def test_hybrid_contexts_use_split_domain_state() -> None:
    paths = (
        REGISTRIES / "multi_player_single_planner/planner_single.hocon",
        REGISTRIES / "single_player_multi_planner_watcher/player_single.hocon",
    )
    for path in paths:
        config = validate_ablations._load(path)
        state_read = next(tool for tool in config["tools"] if tool["name"] == "state_read")
        names = set(state_read["args"]["name_map"])
        for domain in ("coordinator", "rides", "shops", "staff", "research", "layout", "survey"):
            assert f"playbook_{domain}" in names
            assert f"status_{domain}" in names
        assert not any(
            re.search(r"state_solo|playbook_all", str(value)) for value in state_read["args"]["name_map"].values()
        )


def test_single_planner_reuses_one_session(monkeypatch) -> None:
    opened: list[str] = []

    def fake_open(agent_name: str, host: str, port: int):
        del host, port
        opened.append(agent_name)
        return object(), {}

    monkeypatch.setenv("MAPS_MICRO_AGENT", "planner_single")
    monkeypatch.setenv("MAPS_MACRO_AGENT", "planner_single")
    monkeypatch.setattr(single_planner_ablation_runner, "_base_open_session", fake_open)
    monkeypatch.setattr(single_planner_ablation_runner, "_planner_connection", None)
    first = single_planner_ablation_runner._open_session("planner_single", "localhost", 8090)
    second = single_planner_ablation_runner._open_session("planner_single", "localhost", 8090)
    assert first is second
    assert opened == ["planner_single"]
