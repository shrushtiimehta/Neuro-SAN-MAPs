"""Baseline networks expose concise, role-agnostic model-facing tool names."""

from __future__ import annotations

from pathlib import Path

from apps.maps_park.validate_ablations import _load

ROOT = Path(__file__).resolve().parents[1]


def _tools(registry: str) -> dict[str, dict]:
    config = _load(ROOT / "registries" / registry)
    return {tool["name"]: tool for tool in config["tools"]}


def test_watcher_uses_short_unnamespaced_tool_names() -> None:
    tools = _tools("watcher.hocon")
    expected = {
        "state_read",
        "scratchpad",
        "RunTelemetry",
        "EpisodeTelemetry",
        "ActiveTrials",
        "LogTrial",
        "DeleteTrial",
    }
    removed = {
        "watcher_state_read",
        "watcher_scratchpad",
        "WatcherRunTelemetry",
        "WatcherEpisodeTelemetry",
        "WatcherActiveTrials",
        "WatcherLogTrial",
        "WatcherDeleteTrial",
    }

    assert expected <= set(tools)
    assert not removed & set(tools)
    analyst = tools["mid_episode_analyst"]
    assert set(analyst["tools"]) == expected
    assert not any(old in analyst["instructions"] for old in removed)


def test_watcher_exposes_only_used_full_context_aliases() -> None:
    config_path = ROOT / "registries" / "watcher.hocon"
    config_text = config_path.read_text(encoding="utf-8")
    tools = _tools("watcher.hocon")
    analyst = tools["mid_episode_analyst"]
    reader = tools["state_read"]

    expected = ["status_full", "trial_strategies_outcome"]
    assert reader["function"]["parameters"]["properties"]["name"]["enum"] == expected
    assert list(reader["args"]["name_map"]) == expected
    assert reader["args"]["max_content_chars"] == 120000
    assert "watcher_tools" not in config_text
    assert "tools = ${watcher_tools}" not in config_text
    assert "EpisodeTelemetry()" in analyst["instructions"]
    assert "result already gathered above" in analyst["instructions"]
    assert "ActiveTrials(trial_origin='micro')" not in analyst["instructions"]
    assert "VERDICT" not in analyst["function"]["description"]


def test_all_baseline_internal_tool_references_resolve() -> None:
    for registry in ("player.hocon", "planner.hocon", "watcher.hocon"):
        tools = _tools(registry)
        for owner, tool in tools.items():
            missing = set(tool.get("tools", [])) - set(tools)
            assert not missing, f"{registry}:{owner} references {sorted(missing)}"


def test_player_state_read_exposes_only_used_aliases() -> None:
    reader = _tools("player.hocon")["state_read"]
    enum = reader["function"]["parameters"]["properties"]["name"]["enum"]
    name_map = reader["args"]["name_map"]
    expected = [
        "economics_all",
        "economics_research",
        "economics_rides",
        "economics_shops",
        "economics_staff",
        "playbook_coordinator",
        "playbook_layout",
        "playbook_research",
        "playbook_rides",
        "playbook_shops",
        "playbook_staff",
        "playbook_survey",
        "status_full",
        "status_layout",
        "status_research",
        "status_rides",
        "status_shops",
        "status_staff",
        "status_survey",
    ]

    assert enum == expected
    assert list(name_map) == expected
    assert reader["args"]["max_content_chars"] == 120000


def test_baseline_all_economics_contains_operational_constants() -> None:
    economics = (ROOT / "coded_tools" / "config_files" / "economics_all.md").read_text()
    required = {
        "break_even_days",
        "ride_rejection_happiness_penalty",
        "specialty_decay_rate",
        "clean_rate",
        "repair_rate",
        "stocking_rate",
        "speed_progress",
    }

    assert all(field in economics for field in required)
