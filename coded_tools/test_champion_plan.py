# Copyright © 2025-2026 Cognizant Technology Solutions Corp, www.cognizant.com.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# END COPYRIGHT
"""Self-check for the champion-plan cycle: save -> doom -> restore.

Exercises the runner's two deterministic helpers against a throwaway temp dir
(real state untouched): a clean run promotes plan_current -> plan_last_good; a
doom leaves it; the next start restores the last good plan.
Run: `python -m coded_tools.test_champion_plan`.
"""

from __future__ import annotations

import json
import os
import tempfile

from coded_tools import champion_plan
from coded_tools.write_episode_plan import WriteEpisodePlan


def _plan(tag: str) -> dict:
    return {
        "checklist_items": [f"turns 1-100: {tag}"],
        "strategy_summary": f"summary-{tag}",
        "playbook_summaries": {},
    }


def _read(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def test_champion_cycle() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        WriteEpisodePlan.STATE_DIR = tmp
        champion_plan.PLAN_CURRENT_PATH = os.path.join(tmp, "plan_current.json")
        champion_plan.PLAN_LAST_GOOD_PATH = os.path.join(tmp, "plan_last_good.json")
        champion_plan.CHAMPION_REWARD_PATH = os.path.join(tmp, "champion_reward.json")
        cur = champion_plan.PLAN_CURRENT_PATH
        champ = champion_plan.PLAN_LAST_GOOD_PATH

        FLOOR = 300000

        # 1. Clean run A BELOW the floor (250k) -> NOT promoted (useless fallback).
        WriteEpisodePlan().invoke(_plan("A"), {})
        assert champion_plan.promote_plan(aborted=False, reward=250000, min_reward=FLOOR) is False
        assert not os.path.exists(champ), "sub-floor run must not create a champion"

        # 2. Clean run B ABOVE the floor (350k) -> first champion.
        WriteEpisodePlan().invoke(_plan("B"), {})
        assert champion_plan.promote_plan(aborted=False, reward=350000, min_reward=FLOOR) is True
        assert _read(champ)["strategy_summary"] == "summary-B"

        # 3. Clean run C above floor but WORSE than champion (320k) -> not promoted.
        WriteEpisodePlan().invoke(_plan("C"), {})
        assert champion_plan.promote_plan(aborted=False, reward=320000, min_reward=FLOOR) is False
        assert _read(champ)["strategy_summary"] == "summary-B"

        # 4. Clean run D, new best (400k) -> promoted; champion = D.
        WriteEpisodePlan().invoke(_plan("D"), {})
        assert champion_plan.promote_plan(aborted=False, reward=400000, min_reward=FLOOR) is True
        assert _read(champ)["strategy_summary"] == "summary-D"

        # 5. Doomed run E (reward irrelevant) -> never promoted; champion stays D.
        WriteEpisodePlan().invoke(_plan("E"), {})
        assert champion_plan.promote_plan(aborted=True, reward=999999, min_reward=FLOOR) is False
        assert _read(champ)["strategy_summary"] == "summary-D"

        # 6. Roll back after the doom: restore D over the doomed E.
        assert champion_plan.restore_last_good() is True
        assert _read(cur)["strategy_summary"] == "summary-D", "plan_current not reverted"

    # 7. No saved champion -> restore is a safe no-op.
    with tempfile.TemporaryDirectory() as tmp2:
        WriteEpisodePlan.STATE_DIR = tmp2
        champion_plan.PLAN_LAST_GOOD_PATH = os.path.join(tmp2, "plan_last_good.json")
        assert champion_plan.restore_last_good() is False

    print("champion-plan cycle OK: floor-gated best-reward promote + doom rollback verified")


if __name__ == "__main__":
    test_champion_cycle()
