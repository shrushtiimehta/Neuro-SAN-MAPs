"""Zero-cost structural preflight for the MAPs ablation arms."""

from __future__ import annotations

import importlib
import os
from pathlib import Path
from typing import Any

from neuro_san.internals.run_context.langchain.core.langchain_openai_function_tool import LangChainOpenAIFunctionTool
from pyhocon import ConfigFactory

from coded_tools.name_map import SAFE_READ_ALIASES
from neuro_san_studio.commands.check_config import extract_llm_configs_from_agent_network
from neuro_san_studio.commands.check_config import load_agent_network

ROOT = Path(__file__).resolve().parents[2]
REG = ROOT / "registries"
ABLATION_REG = REG / "ablations"
SHARED_REG = ABLATION_REG / "shared"

CONFIGS = {
    "player": ABLATION_REG / "player_with_watcher" / "player_ablation.hocon",
    "watcher": ABLATION_REG / "player_with_watcher" / "watcher_ablation.hocon",
    "planner": ABLATION_REG / "player_with_planner" / "planner_ablation.hocon",
    "embedded": (ABLATION_REG / "embedded_player_planner_watcher" / "player_planner_watcher_embedded.hocon"),
    "unstructured": (ABLATION_REG / "unstructured_player_planner_watcher" / "planner_unstructured_learning.hocon"),
}

HYBRID_CONFIGS = {
    "single_planner": (ABLATION_REG / "multi_player_single_planner" / "planner_single.hocon"),
    "single_player": (ABLATION_REG / "single_player_multi_planner_watcher" / "player_single.hocon"),
}

G_MEMORY_CONFIGS = {
    "player": ABLATION_REG / "g_memory_player_planner_watcher" / "player_g_memory.hocon",
    "watcher": ABLATION_REG / "g_memory_player_planner_watcher" / "watcher_g_memory.hocon",
    "planner": ABLATION_REG / "g_memory_player_planner_watcher" / "planner_g_memory.hocon",
}

MANIFESTS = {
    "player_with_watcher": ("player_ablation.hocon", "watcher_ablation.hocon"),
    "player_with_planner": ("player_ablation.hocon", "planner_ablation.hocon"),
    "embedded_player_planner_watcher": ("player_planner_watcher_embedded.hocon",),
    "unstructured_player_planner_watcher": (
        "player_ablation.hocon",
        "watcher_ablation.hocon",
        "planner_unstructured_learning.hocon",
    ),
    "g_memory_player_planner_watcher": (
        "player_g_memory.hocon",
        "watcher_g_memory.hocon",
        "planner_g_memory.hocon",
    ),
    "single_agent": ("player_solo.hocon", "planner_solo.hocon"),
    "multi_player_single_planner": ("player_ablation.hocon", "planner_single.hocon"),
    "single_player_multi_planner_watcher": (
        "player_single.hocon",
        "planner_ablation.hocon",
        "watcher_ablation.hocon",
    ),
    "qwen4b_multi": ("player.hocon", "planner.hocon", "watcher.hocon"),
    "qwen4b_single": ("player_solo.hocon", "planner_solo.hocon"),
    "qwen4b_strong_planner_multi": ("player.hocon", "planner.hocon", "watcher.hocon"),
    "qwen4b_strong_planner_single": ("player_solo.hocon", "planner_solo.hocon"),
    "no_self_improvement_multi": ("player.hocon", "planner.hocon", "watcher.hocon"),
    "no_self_improvement_single": ("player_solo.hocon", "planner_solo.hocon"),
}

PLAYER_LLM_AGENTS = {
    "strategy_coordinator",
    "rides_manager",
    "shops_manager",
    "staffing_manager",
    "park_layout_planner",
    "research_manager",
    "guest_analyst",
}
PLANNER_LLM_AGENTS = {"macro_orchestrator", "episode_start", "episode_end"}
WATCHER_LLM_AGENTS = {"mid_episode_analyst"}


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _load(path: Path) -> dict[str, Any]:
    prior_state = os.environ.get("MAPS_STATE_DIR")
    prior_seed = os.environ.get("MAPS_SEED_DIR")
    os.environ["MAPS_STATE_DIR"] = "__ablation_state__"
    os.environ["MAPS_SEED_DIR"] = "__ablation_seed__"
    try:
        return _plain(ConfigFactory.parse_string(path.read_text(encoding="utf-8"), basedir=str(ROOT)))
    finally:
        if prior_state is None:
            os.environ.pop("MAPS_STATE_DIR", None)
        else:
            os.environ["MAPS_STATE_DIR"] = prior_state
        if prior_seed is None:
            os.environ.pop("MAPS_SEED_DIR", None)
        else:
            os.environ["MAPS_SEED_DIR"] = prior_seed


def _tools(config: dict[str, Any]) -> list[dict[str, Any]]:
    return config.get("tools", [])


def _by_name(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tools = _tools(config)
    names = [tool.get("name") for tool in tools]
    assert all(names), "every tool needs a name"
    assert len(names) == len(set(names)), f"duplicate tool names: {names}"
    return {tool["name"]: tool for tool in tools}


def _validate_functions_and_classes(config: dict[str, Any]) -> None:
    known = set(_by_name(config))
    tool: Any
    for tool in _tools(config):
        function = dict(tool.get("function") or {})
        function["name"] = tool["name"]
        LangChainOpenAIFunctionTool.verify_function_json(function)
        target: Any
        for target in tool.get("tools", []):
            assert target in known, f"{tool['name']} references missing tool {target}"
        class_path = tool.get("class")
        if class_path:
            module_name, class_name = class_path.rsplit(".", 1)
            module = importlib.import_module(module_name)
            assert hasattr(module, class_name), f"missing class {class_path}"


def _assert_read_name_enums(config: dict[str, Any]) -> None:
    """Keep model-visible read names identical to the operator name maps."""
    name: Any
    for name in ("state_read", "planner_state_read", "watcher_state_read"):
        tool = _by_name(config).get(name)
        if not tool:
            continue
        mapped = set(tool["args"]["name_map"])
        exposed = set(tool["function"]["parameters"]["properties"]["name"].get("enum", []))
        assert exposed == mapped, f"{name} enum/name_map mismatch: {exposed ^ mapped}"


def _assert_observed_alias_guards() -> None:
    expected = {
        "economics": "economics_all",
        "map_layout": "status_layout",
        "status_staffing": "status_staff",
    }
    assert SAFE_READ_ALIASES == expected, "observed read-name alias guards changed"


def _assert_shared_read_targets(configs: dict[str, dict[str, Any]]) -> None:
    """Canonical control networks retain their deliberately narrow read surfaces."""
    player_reads = set(_by_name(configs["player"])["state_read"]["args"]["name_map"])
    planner_reads = set(_by_name(configs["planner"])["state_read"]["args"]["name_map"])
    watcher_reads = set(_by_name(configs["watcher"])["state_read"]["args"]["name_map"])
    assert {"status_full", "status_survey", "status_layout", "economics_all"} <= player_reads
    assert {"status_full", "status_champion", "economics_all"} <= planner_reads
    assert watcher_reads == {"status_full", "trial_strategies_outcome"}


def _inlined_dependency(path: Path, *, strip_outer_object: bool = False) -> str:
    """Render a registry dependency exactly as it appears in self-contained arms."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if strip_outer_object:
        open_index = next(i for i, line in enumerate(lines) if line.strip() == "{")
        close_index = max(i for i, line in enumerate(lines) if line.strip() == "}")
        lines = [line for i, line in enumerate(lines) if i not in {open_index, close_index}]
    relative = path.relative_to(ROOT).as_posix()
    return f"# BEGIN INLINED: {relative}\n" + "\n".join(lines) + f"\n# END INLINED: {relative}\n"


def _assert_canonical_copies() -> None:
    """Generated control graphs must expose the exact canonical prompt values."""
    from scripts.sync_baseline_ablation_prompts import DERIVED

    relative: Any
    expected_text: Any
    for relative, expected_text in DERIVED.items():
        actual = (ROOT / relative).read_text(encoding="utf-8")
        assert actual == expected_text, f"{relative} drifted; run the prompt sync script"

    for role in ("player", "planner", "watcher"):
        canonical = _by_name(_load(REG / f"{role}.hocon"))
        derived = _by_name(_load(SHARED_REG / f"{role}_ablation.hocon"))
        assert list(derived) == list(canonical), f"{role} control tool graph drifted"
        name: Any
        for name, canonical_tool in canonical.items():
            assert derived[name].get("instructions") == canonical_tool.get("instructions"), (
                f"{role}.{name} instructions are not verbatim canonical"
            )


def _merged_model(top: dict[str, Any], tool: dict[str, Any]) -> dict[str, Any]:
    merged = dict(top)
    merged.update(tool.get("llm_config") or {})
    return merged


def _assert_models(configs: dict[str, dict[str, Any]]) -> None:
    player_top = configs["player"]["llm_config"]
    assert player_top["model_name"] == "gpt-5.2"
    assert "reasoning_effort" not in player_top
    role: Any
    for role in ("planner", "watcher", "unstructured"):
        top = configs[role]["llm_config"]
        assert top["model_name"] == "gpt-5.5"
        assert top["reasoning_effort"] == "xhigh"
        assert top["use_responses_api"] is True

    embedded = configs["embedded"]
    top = embedded["llm_config"]
    tools = _by_name(embedded)
    name: Any
    for name in PLAYER_LLM_AGENTS:
        model = _merged_model(top, tools[name])
        assert model["model_name"] == "gpt-5.2"
        assert model.get("reasoning_effort") is None
        assert model.get("use_responses_api") is None
    name: Any
    for name in PLANNER_LLM_AGENTS | WATCHER_LLM_AGENTS:
        model = _merged_model(top, tools[name])
        assert model["model_name"] == "gpt-5.5"
        assert model["reasoning_effort"] == "xhigh"


def _assert_framework_models() -> None:
    """Load through Neuro SAN's real filter/overlay chain, without LLM calls."""
    expected = {
        CONFIGS["player"]: {
            "strategy_coordinator": ("gpt-5.2", None, None),
        },
        CONFIGS["planner"]: {
            "macro_orchestrator": ("gpt-5.5", "xhigh", True),
        },
        CONFIGS["watcher"]: {
            "mid_episode_analyst": ("gpt-5.5", "xhigh", True),
        },
        CONFIGS["embedded"]: {
            "strategy_coordinator": ("gpt-5.2", None, None),
            "macro_orchestrator": ("gpt-5.5", "xhigh", True),
            "mid_episode_analyst": ("gpt-5.5", "xhigh", True),
        },
        CONFIGS["unstructured"]: {
            "macro_orchestrator": ("gpt-5.5", "xhigh", True),
        },
        G_MEMORY_CONFIGS["player"]: {
            "strategy_coordinator": ("gpt-5.2", None, None),
        },
        G_MEMORY_CONFIGS["planner"]: {
            "macro_orchestrator": ("gpt-5.5", "xhigh", True),
        },
        G_MEMORY_CONFIGS["watcher"]: {
            "mid_episode_analyst": ("gpt-5.5", "xhigh", True),
        },
    }
    prior_cwd = Path.cwd()
    prior_state = os.environ.get("MAPS_STATE_DIR")
    prior_seed = os.environ.get("MAPS_SEED_DIR")
    try:
        os.chdir(ROOT)
        os.environ["MAPS_STATE_DIR"] = "__ablation_state__"
        os.environ["MAPS_SEED_DIR"] = "__ablation_seed__"
        path: Any
        agents: Any
        for path, agents in expected.items():
            relative_path = path.relative_to(ROOT)
            network = load_agent_network(str(relative_path))
            configs = dict(extract_llm_configs_from_agent_network(network))
            agent: Any
            want: Any
            for agent, want in agents.items():
                got = configs[agent]
                actual = (
                    got.get("model_name"),
                    got.get("reasoning_effort"),
                    got.get("use_responses_api"),
                )
                assert actual == want, f"effective model mismatch for {relative_path}:{agent}: {actual}"
    finally:
        if prior_state is None:
            os.environ.pop("MAPS_STATE_DIR", None)
        else:
            os.environ["MAPS_STATE_DIR"] = prior_state
        if prior_seed is None:
            os.environ.pop("MAPS_SEED_DIR", None)
        else:
            os.environ["MAPS_SEED_DIR"] = prior_seed
        os.chdir(prior_cwd)


def _assert_topologies(configs: dict[str, dict[str, Any]]) -> None:
    assert _tools(configs["player"])[0]["name"] == "strategy_coordinator"
    player_name_map = _by_name(configs["player"])["state_read"]["args"]["name_map"]
    assert "status" not in player_name_map
    player_tools = _by_name(configs["player"])
    agent_status = {
        "strategy_coordinator": "status_full",
        "rides_manager": "status_rides",
        "shops_manager": "status_shops",
        "staffing_manager": "status_staff",
        "park_layout_planner": "status_layout",
        "research_manager": "status_research",
        "guest_analyst": "status_survey",
    }
    for agent_name, logical_name in agent_status.items():
        assert player_name_map[logical_name].endswith(f"/{logical_name}.json")
        assert f"state_read(name='{logical_name}')" in player_tools[agent_name]["instructions"]
    assert _tools(configs["watcher"])[0]["name"] == "mid_episode_analyst"
    watcher_instructions = _by_name(configs["watcher"])["mid_episode_analyst"]["instructions"]
    for required_instruction in (
        "Always cite evidence (step + metric) from telemetry.",
        "`RunTelemetry(select='best')`",
        "there is no fixed numerical cap",
        "`scratchpad(note=...)`",
        "Return a concise actionable advisory for the player's next turn.",
    ):
        assert required_instruction in watcher_instructions
    assert _tools(configs["planner"])[0]["name"] == "macro_orchestrator"

    embedded = configs["embedded"]
    embedded_names = set(_by_name(embedded))
    assert _tools(embedded)[0]["name"] == "strategy_coordinator"
    assert PLAYER_LLM_AGENTS | PLANNER_LLM_AGENTS | WATCHER_LLM_AGENTS <= embedded_names
    assert not any("router" in name.lower() for name in embedded_names)
    coordinator_targets = set(_by_name(embedded)["strategy_coordinator"]["tools"])
    assert {"macro_orchestrator", "mid_episode_analyst"} <= coordinator_targets

    unstructured = configs["unstructured"]
    names = set(_by_name(unstructured))
    forbidden = {
        "LogTrial",
        "PlannerActiveTrials",
        "CarryoverTrials",
        "ResolveTrials",
        "PromoteTrial",
        "WriteEpisodePlan",
    }
    assert not (names & forbidden), f"unstructured planner exposes trial machinery: {names & forbidden}"
    assert {
        "WriteUnstructuredPlan",
        "ReadEpisodeLearningHistory",
        "SaveEpisodeLearningRecord",
        "ClearEpisodeMicroStrategies",
    } <= names
    start_targets = set(_by_name(unstructured)["episode_start"]["tools"])
    end_targets = set(_by_name(unstructured)["episode_end"]["tools"])
    assert "WriteUnstructuredPlan" in start_targets and "SaveEpisodeLearningRecord" in end_targets
    assert "ClearEpisodeMicroStrategies" in end_targets
    start_instructions = _by_name(unstructured)["episode_start"]["instructions"]
    required_start_reads = {
        "maps_game_docs",
        "economics_all",
        "status_coordinator",
        "status_layout",
        "playbook_coordinator",
        "playbook_rides",
        "playbook_shops",
        "playbook_staff",
        "playbook_research",
        "playbook_layout",
        "playbook_survey",
    }
    logical_name: Any
    for logical_name in required_start_reads:
        assert f"planner_state_read('{logical_name}')" in start_instructions, (
            f"unstructured episode_start omits exact read name {logical_name}"
        )


def _assert_embedded_player_fidelity(configs: dict[str, dict[str, Any]]) -> None:
    """The embedded arm retains its intentional single-network composition."""
    embedded = _by_name(configs["embedded"])
    assert _tools(configs["embedded"])[0]["name"] == "strategy_coordinator"
    coordinator_targets = set(embedded["strategy_coordinator"]["tools"])
    assert {"macro_orchestrator", "mid_episode_analyst"} <= coordinator_targets


def _assert_g_memory_fidelity(configs: dict[str, dict[str, Any]]) -> None:
    """The treatment changes persistence classes, never agent behavior."""
    expected_classes = {
        "player": {
            "state_read": "GMemoryStateRead",
            "scratchpad": "GMemoryRuntimeTool",
            "ActiveTrials": "GMemoryRuntimeTool",
        },
        "watcher": {
            "LogTrial": "GMemoryRuntimeTool",
            "DeleteTrial": "GMemoryRuntimeTool",
            "ActiveTrials": "GMemoryRuntimeTool",
            "scratchpad": "GMemoryRuntimeTool",
            "state_read": "GMemoryStateRead",
        },
        "planner": {
            "advance_episode": "GMemoryAdvanceEpisode",
            "WriteEpisodePlan": "GMemoryWriteEpisodePlan",
            "LogTrial": "GMemoryRuntimeTool",
            "ActiveTrials": "GMemoryRuntimeTool",
            "CarryoverTrials": "GMemoryRuntimeTool",
            "ResolveTrials": "GMemoryRuntimeTool",
            "PromoteTrial": "GMemoryRuntimeTool",
            "scratchpad": "GMemoryRuntimeTool",
            "state_read": "GMemoryStateRead",
        },
    }
    for role, config in configs.items():
        canonical = _by_name(_load(SHARED_REG / f"{role}_ablation.hocon"))
        treatment = _by_name(config)
        assert list(treatment) == list(canonical), f"G-Memory {role} topology drifted"
        for name, canonical_tool in canonical.items():
            assert treatment.get(name, {}).get("instructions") == canonical_tool.get("instructions"), (
                f"G-Memory {role}.{name} instructions drifted"
            )
        for name, class_name in expected_classes.get(role, {}).items():
            assert str(treatment.get(name, {}).get("class", "")).endswith(f".{class_name}")
        for name, tool in treatment.items():
            if tool.get("class", "").endswith(".GMemoryStateRead"):
                name_map = tool.get("args", {}).get("name_map", {})
                assert all("/playbook_" not in str(path) and "/episode_checklist.md" not in str(path)
                           and "/trial_strategies_outcome.md" not in str(path) for path in name_map.values())


def _assert_launchers() -> None:
    expected = {
        "run_player_with_watcher.sh": ("player_ablation", "watcher_ablation", "off"),
        "run_player_with_planner.sh": ("player_ablation", "off", "planner_ablation"),
        "run_embedded_player_planner_watcher.sh": (
            "player_planner_watcher_embedded",
            "player_planner_watcher_embedded",
            "player_planner_watcher_embedded",
        ),
        "run_unstructured_player_planner_watcher.sh": (
            "player_ablation",
            "watcher_ablation",
            "planner_unstructured_learning",
        ),
        "run_g_memory_player_planner_watcher.sh": (
            "player_g_memory",
            "watcher_g_memory",
            "planner_g_memory",
        ),
        "run_multi_player_single_planner.sh": ("player_ablation", "planner_single", "planner_single"),
        "run_single_player_multi_planner_watcher.sh": ("player_single", "watcher_ablation", "planner_ablation"),
    }
    app = ROOT / "apps" / "maps_park"
    filename: Any
    networks: Any
    for filename, networks in expected.items():
        body = (app / filename).read_text(encoding="utf-8")
        key: Any
        value: Any
        for key, value in zip(("RUNNER", "MICRO", "MACRO"), networks):
            assert f"MAPS_{key}_AGENT={value}" in body, f"bad {filename} {key} mapping"
        assert "state_ablations/" in body and "logs/maps_ablation_" in body
        assert "MAPS_SEED_DIR=ablation_seeds/" in body
        arm_name = next(
            line.split("=", 1)[1] for line in body.splitlines() if line.startswith("export MAPS_ARM_NAME=")
        )
        assert (ABLATION_REG / arm_name / "manifest.hocon").is_file()
        state_dir = next(
            line.split("=", 1)[1] for line in body.splitlines() if line.startswith("export MAPS_STATE_DIR=")
        )
        seed_dir = next(
            line.split("=", 1)[1] for line in body.splitlines() if line.startswith("export MAPS_SEED_DIR=")
        )
        assert not seed_dir.startswith(state_dir + "/"), f"{filename} nests seeds under archived state"
    batch = (app / "run_all_ablation_arms.sh").read_text(encoding="utf-8")
    positions = [batch.index(filename) for filename in expected]
    assert positions == sorted(positions)
    assert "MAPS_EPISODE_LIMIT=10" in batch and "--fresh" in batch

    port_defaults = {
        "run_baseline_services.sh": (3000, 8765, 8090),
        "run_player_with_planner.sh": (3010, 8775, 8100),
        "run_embedded_player_planner_watcher.sh": (3020, 8785, 8110),
        "run_unstructured_player_planner_watcher.sh": (3030, 8795, 8120),
        "run_player_with_watcher.sh": (3040, 8805, 8130),
        "run_single_agent_ablation.sh": (3050, 8815, 8140),
        "run_multi_player_single_planner.sh": (3060, 8825, 8150),
        "run_single_player_multi_planner_watcher.sh": (3070, 8835, 8160),
        "run_g_memory_player_planner_watcher.sh": (3080, 8845, 8170),
    }
    port_owners: dict[int, str] = {}
    for filename, ports in port_defaults.items():
        body = (app / filename).read_text(encoding="utf-8")
        for kind, port in zip(("NODE", "MCP", "STUDIO"), ports):
            assignment = f'export MAPS_{kind}_PORT="${{MAPS_{kind}_PORT:-{port}}}"'
            assert assignment in body, f"bad {filename} {kind} port default"
            assert port not in port_owners, f"port {port} is shared by {port_owners.get(port)} and {filename}"
            port_owners[port] = filename

    services = (app / "run_ablation_services.sh").read_text(encoding="utf-8")
    assert ': "${MAPS_NODE_PORT:?' in services
    assert ': "${MAPS_MCP_PORT:?' in services
    assert ': "${MAPS_STUDIO_PORT:?' in services
    assert '"$MAPS_NODE_PORT" == "$MAPS_MCP_PORT"' in services
    assert 'for port in "$MAPS_NODE_PORT" "$MAPS_MCP_PORT" "$MAPS_STUDIO_PORT"' in services
    assert '--server-http-port "$MAPS_STUDIO_PORT"' in services
    assert '--port "$MAPS_STUDIO_PORT"' in services


def _assert_arm_manifests() -> None:
    """Each arm serves only the networks declared in its own directory."""
    arm: Any
    filenames: Any
    for arm, filenames in MANIFESTS.items():
        manifest_path = ABLATION_REG / arm / "manifest.hocon"
        manifest = {str(name).strip('"'): enabled for name, enabled in _load(manifest_path).items()}
        assert set(manifest) == set(filenames), f"{arm} manifest mismatch: {set(manifest) ^ set(filenames)}"
        assert all(manifest[name] is True for name in filenames)
        assert all((manifest_path.parent / name).is_file() for name in filenames)


def _assert_hybrid_topologies(configs: dict[str, dict[str, Any]]) -> None:
    """The hybrid side named single must contain exactly one LLM agent."""
    planner = configs["single_planner"]
    player = configs["single_player"]
    planner_agents = [tool for tool in _tools(planner) if tool.get("instructions")]
    player_agents = [tool for tool in _tools(player) if tool.get("instructions")]
    assert [tool["name"] for tool in planner_agents] == ["single_planner"]
    assert [tool["name"] for tool in player_agents] == ["single_player"]

    planner_tools = _by_name(planner)
    write_schema = planner_tools["WriteEpisodePlan"]["function"]["parameters"]
    assert set(write_schema["required"]) == {
        "checklist_items",
        "strategy_summary",
        "playbook_summaries",
    }
    planner_reads = set(planner_tools["state_read"]["args"]["name_map"])
    player_reads = set(_by_name(player)["state_read"]["args"]["name_map"])
    for reads in (planner_reads, player_reads):
        assert {
            f"playbook_{domain}"
            for domain in ("coordinator", "rides", "shops", "staff", "research", "layout", "survey")
        } <= reads
        assert {
            f"status_{domain}" for domain in ("coordinator", "rides", "shops", "staff", "research", "layout", "survey")
        } <= reads


def main() -> None:
    configs = {name: _load(path) for name, path in CONFIGS.items()}
    hybrid_configs = {name: _load(path) for name, path in HYBRID_CONFIGS.items()}
    g_memory_configs = {name: _load(path) for name, path in G_MEMORY_CONFIGS.items()}
    _assert_observed_alias_guards()
    _assert_canonical_copies()
    config: Any
    for config in configs.values():
        _validate_functions_and_classes(config)
        _assert_read_name_enums(config)
    for config in hybrid_configs.values():
        _validate_functions_and_classes(config)
        _assert_read_name_enums(config)
    for config in g_memory_configs.values():
        _validate_functions_and_classes(config)
        _assert_read_name_enums(config)
    _assert_shared_read_targets(configs)
    _assert_models(configs)
    _assert_framework_models()
    _assert_topologies(configs)
    _assert_embedded_player_fidelity(configs)
    _assert_g_memory_fidelity(g_memory_configs)
    _assert_hybrid_topologies(hybrid_configs)
    _assert_launchers()
    _assert_arm_manifests()
    print("[ablation preflight] PASS: configs, schemas, models, topology, isolation, and launchers")


if __name__ == "__main__":
    main()
