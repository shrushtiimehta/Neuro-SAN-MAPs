"""The OUTCOME ledger is append-only: closing an episode never deletes a line.

AdvanceEpisode used to trim trial_strategies_outcome.md to a 5-episode window,
so a long run quietly lost its own history — by ep17 everything before ep12 was
gone. The lines are macro-only (a handful per episode), so the whole run's
ledger is kept and only a --fresh run wipes it.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coded_tools.advance_episode import AdvanceEpisode  # noqa: E402
from coded_tools.trial_parsing import OUTCOME_PATH      # noqa: E402

LEDGER = "".join(
    f"- OUTCOME ep={ep} trial_id=t{ep}_1 domain=rides origin=macro "
    f"outcome=confirmed note='n' rule='r'\n"
    for ep in range(0, 10)
)


def test_close_out_keeps_every_episode():
    with tempfile.TemporaryDirectory() as tmp:
        cwd = os.getcwd()
        os.chdir(tmp)
        try:
            Path(OUTCOME_PATH).parent.mkdir(parents=True, exist_ok=True)
            Path(OUTCOME_PATH).write_text(LEDGER, encoding="utf-8")

            # Episode 20 closing: the old window would have kept ep16+ only.
            result = AdvanceEpisode().invoke({"final_reward": 123.0, "episode": 20}, {})
            assert result["status"] == "ok", result
            assert Path(OUTCOME_PATH).read_text(encoding="utf-8") == LEDGER

            # The reward it DOES own is still written.
            assert "123.0" in Path(AdvanceEpisode.LAST_REWARD_PATH).read_text(encoding="utf-8")
        finally:
            os.chdir(cwd)


def test_episode_is_still_required():
    assert str(AdvanceEpisode().invoke({"final_reward": 1}, {})).startswith("ERROR")


if __name__ == "__main__":
    test_close_out_keeps_every_episode()
    test_episode_is_still_required()
    print("ok")
