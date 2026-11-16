"""Regression guards for the baseline episode-start planner's evidence surface."""

from __future__ import annotations

from pathlib import Path

from apps.maps_park.validate_ablations import _load

ROOT = Path(__file__).resolve().parents[1]


def test_baseline_episode_start_reads_champion_status_and_full_economics() -> None:
    config = _load(ROOT / "registries" / "planner.hocon")
    tools = {tool["name"]: tool for tool in config["tools"]}
    instructions = tools["episode_start"]["instructions"]

    required_reads = {
        "status_champion",
        "economics_all",
    }
    for logical_name in required_reads:
        assert f"state_read(name='{logical_name}')" in instructions

    reader = tools["state_read"]
    allowed_names = set(reader["function"]["parameters"]["properties"]["name"]["enum"])
    name_map = reader["args"]["name_map"]
    assert required_reads <= allowed_names
    assert required_reads <= set(name_map)
    assert "last_reward" not in allowed_names
    assert "last_reward" not in name_map
    assert "state_read('last_reward')" not in instructions
    assert name_map["status_champion"].endswith("/status_champion.json")
    unused_status_aliases = {
        "status_layout",
        "status_layout_champion",
        "status_research",
        "status_rides",
        "status_shops",
        "status_staff",
        "status_survey",
    }
    assert unused_status_aliases.isdisjoint(allowed_names)
    assert unused_status_aliases.isdisjoint(name_map)
    assert "restored champion episode’s domain strategy at the top" in instructions
    assert "learned rules promoted from confirmed trials" in instructions


def test_baseline_planner_uses_short_unnamespaced_tool_names() -> None:
    config = _load(ROOT / "registries" / "planner.hocon")
    tools = {tool["name"]: tool for tool in config["tools"]}

    assert {"state_read", "scratchpad", "ActiveTrials"} <= set(tools)
    assert not {"planner_state_read", "planner_scratchpad", "PlannerActiveTrials"} & set(tools)
    all_instructions = "\n".join(str(tool.get("instructions", "")) for tool in config["tools"])
    assert "planner_state_read" not in all_instructions
    assert "planner_scratchpad" not in all_instructions
    assert "PlannerActiveTrials" not in all_instructions


def test_baseline_plan_contract_requires_a_granular_complete_strategy() -> None:
    config = _load(ROOT / "registries" / "planner.hocon")
    tools = {tool["name"]: tool for tool in config["tools"]}
    writer = tools["WriteEpisodePlan"]
    properties = writer["function"]["parameters"]["properties"]

    strategy_description = properties["strategy_summary"]["description"]
    checklist_description = properties["checklist_items"]["description"]
    summaries_description = properties["playbook_summaries"]["description"]
    assert "COORDINATOR STRATEGY" in strategy_description
    assert "complete phase-independent policy" in strategy_description
    assert "Do not repeat temporal plan details" in strategy_description
    assert "status_full.current_phase" not in strategy_description
    assert "turns 1..100" not in strategy_description
    assert "TEMPORAL EXECUTION PLAN" in checklist_description
    assert "only place for phase-specific instructions" in checklist_description
    assert "corresponding phase instructions and the complete next phase" in checklist_description
    assert "physical" not in checklist_description
    assert "SIX DOMAIN STRATEGIES" in summaries_description
    assert "complete phase-independent strategies" in summaries_description
    assert "Do not repeat temporal plan details" in summaries_description
    assert "Never omit a domain" in summaries_description
    assert writer["function"]["parameters"]["required"] == [
        "checklist_items",
        "strategy_summary",
        "playbook_summaries",
    ]
    assert properties["playbook_summaries"]["required"] == [
        "rides",
        "shops",
        "staff",
        "research",
        "layout",
        "survey",
    ]

    start_instructions = tools["episode_start"]["instructions"]
    assert "exactly these three" in start_instructions
    assert 'formatted as "turns A-B: <goal and complete phase instructions>"' in start_instructions
    assert "corresponding phase" in start_instructions
    assert "instructions and the complete next phase" in start_instructions
    assert "physical" not in start_instructions


def test_baseline_player_gets_phase_only_from_middleware() -> None:
    config = _load(ROOT / "registries" / "player.hocon")
    tools = {tool["name"]: tool for tool in config["tools"]}
    instructions = tools["strategy_coordinator"]["instructions"]

    assert "full phase-independent policy" in instructions
    assert "<RUNTIME_EPISODE_PHASE>" in instructions
    assert "current_phase" not in instructions

    player_agents = {
        "strategy_coordinator",
        "rides_manager",
        "shops_manager",
        "staffing_manager",
        "park_layout_planner",
        "research_manager",
        "guest_analyst",
    }
    for name in player_agents:
        middleware = {item["class"] for item in tools[name].get("middleware", [])}
        assert "middleware.episode_phase_middleware.EpisodePhaseMiddleware" in middleware


def test_baseline_plan_validation_can_be_corrected_and_retried() -> None:
    config = _load(ROOT / "registries" / "planner.hocon")
    tools = {tool["name"]: tool for tool in config["tools"]}
    instructions = tools["episode_start"]["instructions"]

    assert "retry only that call, up to twice" in instructions
    assert "After it succeeds, continue with step 6" in instructions
    assert "filesystem/runtime error" in instructions
