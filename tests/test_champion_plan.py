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
"""Self-check for the champion-plan cycle: save -> restore.

Exercises the runner's two deterministic helpers against a throwaway temp dir
(real state untouched): a best-so-far run promotes plan_current -> plan_last_good;
a worse one leaves it; the next start restores the last good plan.
Run: `python tests/test_champion_plan.py`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import json
import os
import tempfile

from coded_tools import champion_plan
from coded_tools.write_episode_plan import WriteEpisodePlan


def _plan(tag: str) -> dict:
    return {
        "checklist_items": [f"turns 1-100: {tag}"],
        "strategy_summary": f"summary-{tag}",
        "playbook_summaries": {
            domain: f"Complete executable {domain} strategy for {tag}." for domain in WriteEpisodePlan.DOMAIN_PLAYBOOKS
        },
    }


def _read(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def test_incomplete_domain_strategies_are_rejected_before_any_write(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(WriteEpisodePlan, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(WriteEpisodePlan, "MERGED", False)
    monkeypatch.setattr(WriteEpisodePlan, "REQUIRE_DOMAIN_STRATEGIES", True)

    protected_files = [
        WriteEpisodePlan.CHECKLIST_FILE,
        WriteEpisodePlan.PLAYBOOK_COORDINATOR_FILE,
        WriteEpisodePlan.PLAN_CURRENT_FILE,
        *WriteEpisodePlan.DOMAIN_PLAYBOOKS.values(),
    ]
    for filename in protected_files:
        (tmp_path / filename).write_text(f"sentinel:{filename}\n", encoding="utf-8")

    valid = _plan("validation")
    null_survey = {
        **valid,
        "playbook_summaries": {
            **valid["playbook_summaries"],
            "survey": None,
        },
    }
    literal_none_survey = {
        **valid,
        "playbook_summaries": {
            **valid["playbook_summaries"],
            "survey": "None",
        },
    }
    missing_survey = {
        **valid,
        "playbook_summaries": {
            domain: text for domain, text in valid["playbook_summaries"].items() if domain != "survey"
        },
    }

    for invalid_plan in (null_survey, literal_none_survey, missing_survey):
        result = WriteEpisodePlan().invoke(invalid_plan, {})
        assert isinstance(result, str) and result.startswith("ERROR:"), result
        assert "retryable_validation" in result
        for filename in protected_files:
            assert (tmp_path / filename).read_text(encoding="utf-8") == (f"sentinel:{filename}\n")

    corrected = WriteEpisodePlan().invoke(valid, {})
    assert isinstance(corrected, dict), corrected
    assert corrected["playbook_summaries_written"] == list(WriteEpisodePlan.DOMAIN_PLAYBOOKS)


def test_invalid_phase_coverage_is_rejected_before_any_write(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(WriteEpisodePlan, "STATE_DIR", str(tmp_path))
    monkeypatch.setattr(WriteEpisodePlan, "MERGED", False)
    monkeypatch.setattr(WriteEpisodePlan, "REQUIRE_DOMAIN_STRATEGIES", True)

    invalid_checklists = [
        ["turns 1-9: first", "turns 11-100: gap"],
        ["turns 1-20: first", "turns 20-100: overlap"],
        ["turns 1-99: incomplete"],
        ["phase one: malformed"],
    ]
    for checklist in invalid_checklists:
        result = WriteEpisodePlan().invoke({**_plan("invalid-checklist"), "checklist_items": checklist}, {})
        assert isinstance(result, str) and result.startswith("ERROR: retryable_validation:")
        assert not list(tmp_path.iterdir())


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
        assert champion_plan.promote_plan(reward=250000, min_reward=FLOOR) is False
        assert not os.path.exists(champ), "sub-floor run must not create a champion"

        # 2. Clean run B ABOVE the floor (350k) -> first champion.
        WriteEpisodePlan().invoke(_plan("B"), {})
        assert champion_plan.promote_plan(reward=350000, min_reward=FLOOR) is True
        assert _read(champ)["strategy_summary"] == "summary-B"

        # 3. Clean run C above floor but WORSE than champion (320k) -> not promoted.
        WriteEpisodePlan().invoke(_plan("C"), {})
        assert champion_plan.promote_plan(reward=320000, min_reward=FLOOR) is False
        assert _read(champ)["strategy_summary"] == "summary-B"

        # 4. Clean run D, new best (400k) -> promoted; champion = D.
        WriteEpisodePlan().invoke(_plan("D"), {})
        assert champion_plan.promote_plan(reward=400000, min_reward=FLOOR) is True
        assert _read(champ)["strategy_summary"] == "summary-D"

        # 5. Restore: the champion (D) is re-applied over the current plan.
        WriteEpisodePlan().invoke(_plan("E"), {})
        assert champion_plan.restore_last_good() is True
        assert _read(cur)["strategy_summary"] == "summary-D", "plan_current not reverted"

        # 6. best_reward() is the rising bar: it tracks the current champion (D=400k).
        assert champion_plan.best_reward() == 400000

    # 8. With no min_reward passed, the default CHAMPION_MIN_REWARD bar applies;
    #    best_reward() is 0.0 before any champion.
    with tempfile.TemporaryDirectory() as tmp0:
        WriteEpisodePlan.STATE_DIR = tmp0
        champion_plan.PLAN_CURRENT_PATH = os.path.join(tmp0, "plan_current.json")
        champion_plan.PLAN_LAST_GOOD_PATH = os.path.join(tmp0, "plan_last_good.json")
        champion_plan.CHAMPION_REWARD_PATH = os.path.join(tmp0, "champion_reward.json")
        assert champion_plan.best_reward() == 0.0, "no champion -> bar 0"
        WriteEpisodePlan().invoke(_plan("F"), {})
        assert champion_plan.promote_plan(reward=100) is False, "below the default bar"
        assert champion_plan.promote_plan(reward=champion_plan.CHAMPION_MIN_REWARD) is True
        assert champion_plan.best_reward() == champion_plan.CHAMPION_MIN_REWARD

    # 8. No saved champion -> restore is a safe no-op.
    with tempfile.TemporaryDirectory() as tmp2:
        WriteEpisodePlan.STATE_DIR = tmp2
        champion_plan.PLAN_LAST_GOOD_PATH = os.path.join(tmp2, "plan_last_good.json")
        assert champion_plan.restore_last_good() is False

    print("champion-plan cycle OK: floor-gated best-reward promote + restore verified")


if __name__ == "__main__":
    test_champion_cycle()
