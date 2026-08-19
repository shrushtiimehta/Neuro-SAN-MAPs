"""Episode cost is the SUM of every LLM call in that episode, and resets after.

The bug this guards against is a leaking tally: if the accumulator is not reset
when an episode closes, episode 2 is billed for episode 1 as well and every
cost-per-reward number after the first is silently wrong.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apps.maps_park import runner  # noqa: E402


def _turn(cost, tokens=1000, calls=26):
    return {"total_cost": cost, "total_tokens": tokens,
            "successful_requests": calls, "time_taken_in_seconds": 1.5}


def test_cost_sums_per_episode_and_resets(tmp_path=None):
    out = Path(tmp_path or ".") / "episode_cost.jsonl"
    runner.EPISODE_COST_PATH = str(out)
    out.unlink(missing_ok=True)
    runner._EPISODE_SPEND.update(cost_usd=0.0, tokens=0, llm_calls=0, seconds=0.0)

    for _ in range(3):                                  # 3 player turns...
        runner._accrue_spend(_turn(0.40))
    runner._accrue_spend(_turn(0.10))                   # ...plus a close-out consult
    ep1 = runner.write_episode_cost(1, reward=1000.0, aborted=False)

    assert round(ep1["cost_usd"], 2) == 1.30            # 3*0.40 + 0.10, consult included
    assert ep1["tokens"] == 4000
    assert ep1["llm_calls"] == 104
    assert ep1["cost_per_reward"] == round(1.30 / 1000.0, 6)

    runner._accrue_spend(_turn(0.25))                   # episode 2 starts clean
    ep2 = runner.write_episode_cost(2, reward=0, aborted=True)
    assert ep2["cost_usd"] == 0.25, "episode 1's spend leaked into episode 2"
    assert ep2["cost_per_reward"] is None               # no divide-by-zero on a 0 run
    assert ep2["aborted"] is True

    rows = [json.loads(ln) for ln in out.read_text().splitlines()]
    assert [r["episode"] for r in rows] == [1, 2]       # one line per episode, appended

    # A call with no accounting (a failed or empty response) must not crash or count.
    runner._accrue_spend(None)
    assert runner._EPISODE_SPEND["cost_usd"] == 0.0
    out.unlink(missing_ok=True)


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        test_cost_sums_per_episode_and_resets(td)
    print("ok")
