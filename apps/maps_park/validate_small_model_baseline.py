"""Zero-cost preflight for the baseline GPT-5 Mini model ablation."""

from __future__ import annotations

import os
from pathlib import Path

from neuro_san_studio.commands.check_config import extract_llm_configs_from_agent_network
from neuro_san_studio.commands.check_config import load_agent_network

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "registries" / "ablations" / "baseline_gpt5_mini"
EXPECTED_AGENTS = {
    "player.hocon": {
        "strategy_coordinator",
        "rides_manager",
        "shops_manager",
        "staffing_manager",
        "park_layout_planner",
        "research_manager",
        "guest_analyst",
    },
    "planner.hocon": {"macro_orchestrator", "episode_start", "episode_end"},
    "watcher.hocon": {"mid_episode_analyst"},
}


def main() -> None:
    """Assert that the isolated baseline graph uses GPT-5 Mini everywhere."""
    prior_cwd = Path.cwd()
    prior_state = os.environ.get("MAPS_STATE_DIR")
    prior_seed = os.environ.get("MAPS_SEED_DIR")
    try:
        os.chdir(ROOT)
        os.environ["MAPS_STATE_DIR"] = "__small_model_state__"
        os.environ["MAPS_SEED_DIR"] = "__small_model_seeds__"
        for filename, expected_names in EXPECTED_AGENTS.items():
            path = REGISTRY / filename
            network = load_agent_network(str(path.relative_to(ROOT)))
            configs = dict(extract_llm_configs_from_agent_network(network))
            missing = expected_names - set(configs)
            assert not missing, f"{filename} missing LLM agents: {sorted(missing)}"
            for name in expected_names:
                config = configs[name]
                assert config.get("model_name") == "gpt-5-mini", f"{filename}:{name} uses {config.get('model_name')!r}"
                if filename != "player.hocon":
                    assert config.get("reasoning_effort") == "high"
                    assert config.get("use_responses_api") is True
        print("Small-model baseline preflight passed: all 11 LLM agents use gpt-5-mini.")
    finally:
        os.chdir(prior_cwd)
        if prior_state is None:
            os.environ.pop("MAPS_STATE_DIR", None)
        else:
            os.environ["MAPS_STATE_DIR"] = prior_state
        if prior_seed is None:
            os.environ.pop("MAPS_SEED_DIR", None)
        else:
            os.environ["MAPS_SEED_DIR"] = prior_seed


if __name__ == "__main__":
    main()
