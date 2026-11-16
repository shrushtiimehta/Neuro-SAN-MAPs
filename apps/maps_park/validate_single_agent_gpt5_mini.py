"""Zero-cost preflight for the single-agent GPT-5 Mini ablation."""

from __future__ import annotations

import os
from pathlib import Path

from neuro_san_studio.commands.check_config import extract_llm_configs_from_agent_network
from neuro_san_studio.commands.check_config import load_agent_network

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "registries" / "ablations" / "single_agent_gpt5_mini"
EXPECTED = {
    "player_solo.hocon": "solo_player",
    "planner_solo.hocon": "solo_planner",
}


def main() -> None:
    """Assert that the two active solo agents use GPT-5 Mini."""
    prior_cwd = Path.cwd()
    prior_state = os.environ.get("MAPS_STATE_DIR")
    prior_seed = os.environ.get("MAPS_SEED_DIR")
    try:
        os.chdir(ROOT)
        os.environ["MAPS_STATE_DIR"] = "state_solo"
        os.environ["MAPS_SEED_DIR"] = "__single_agent_mini_seeds__"
        for filename, expected_agent in EXPECTED.items():
            path = REGISTRY / filename
            network = load_agent_network(str(path.relative_to(ROOT)))
            configs = dict(extract_llm_configs_from_agent_network(network))
            assert set(configs) == {expected_agent}, f"{filename} must expose only {expected_agent}: {sorted(configs)}"
            config = configs[expected_agent]
            assert config.get("model_name") == "gpt-5-mini", (
                f"{filename}:{expected_agent} uses {config.get('model_name')!r}"
            )
            if filename == "planner_solo.hocon":
                assert config.get("reasoning_effort") == "high"
                assert config.get("use_responses_api") is True
        print("Single-agent model preflight passed: both LLM agents use gpt-5-mini.")
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
