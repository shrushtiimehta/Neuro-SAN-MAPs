"""The terminal step's auto-reset must not overwrite the episode's end state."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.maps_park.runner import build_run_row  # noqa: E402


def _envelope(step, done, obs):
    return {"episode": 1, "step": step, "done": done, "reward": 1668.0,
            "cumulative_reward": 86258.0, "observation": obs}


# The env hands back a FRESH park on the terminal step: $500, nothing built.
RESET_OBS = {"money": 500, "value": 500, "park_rating": 20.0, "research_speed": "none",
             "rides": {"total_rides": 0}, "shops": {"total_shops": 0}, "staff": {}}
LIVE_OBS = {"money": 43084, "value": 85090, "park_rating": 33.24, "research_speed": "medium",
            "rides": {"total_rides": 15, "min_uptime": 1.0}, "shops": {"total_shops": 6},
            "staff": {"staff_list": [{}] * 10}}


def demo():
    prev = build_run_row({"action": "wait"}, _envelope(99, False, LIVE_OBS))
    assert prev["park_value"] == 85090 and prev["num_rides"] == 15

    final = build_run_row({"action": "wait"}, _envelope(100, True, RESET_OBS), prev)
    # Park state carried from step 99, NOT the reset park.
    assert final["park_value"] == 85090, final["park_value"]
    assert final["cash"] == 43084
    assert final["park_rating"] == 33.24
    assert final["num_rides"] == 15 and final["num_shops"] == 6 and final["num_staff"] == 10
    assert final["research_speed"] == "medium"
    # The step's OWN outcome still comes from the env.
    assert final["reward"] == 1668.0 and final["cumulative_reward"] == 86258.0
    assert final["done"] is True and final["step"] == 100

    # Mid-episode rows are untouched, and a prev from another episode is ignored.
    mid = build_run_row({"action": "wait"}, _envelope(50, False, RESET_OBS), prev)
    assert mid["park_value"] == 500
    other = build_run_row({"action": "wait"}, _envelope(100, True, RESET_OBS),
                          {**prev, "episode": 0})
    assert other["park_value"] == 500

    print("terminal row keeps the episode's real end state: OK")


if __name__ == "__main__":
    demo()
