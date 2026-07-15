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
"""
Champion-plan checkpoint — deterministic, driven by the runner (no LLM).

WriteEpisodePlan dumps each episode's plan args to plan_current.json. The runner
calls these two functions directly:
  - promote_plan(aborted, reward, min_reward): after a CLEAN episode, copy
    plan_current -> plan_last_good ONLY if its reward clears min_reward AND beats
    the current champion (best-so-far, above the floor).
  - restore_last_good(): before the next episode start, if the prior one doomed,
    re-apply plan_last_good via WriteEpisodePlan instead of re-deriving off the
    doomed run.
"""

from __future__ import annotations

import json
import os
import shutil

from coded_tools.write_episode_plan import WriteEpisodePlan

_STATE_DIR = "coded_tools/state"
PLAN_CURRENT_PATH = os.path.join(_STATE_DIR, "plan_current.json")
PLAN_LAST_GOOD_PATH = os.path.join(_STATE_DIR, "plan_last_good.json")
CHAMPION_REWARD_PATH = os.path.join(_STATE_DIR, "champion_reward.json")

# A champion below the doom floor is a useless fallback, so it must clear this to
# be promoted. Matches the runner's DEFAULT_REWARD_FLOOR; the runner passes its
# actual --reward-floor as min_reward, this is just the default.
CHAMPION_MIN_REWARD = 300000


def _champion_reward() -> float | None:
    """The reward the current champion earned, or None if there is no champion."""
    try:
        with open(CHAMPION_REWARD_PATH, encoding="utf-8") as fh:
            return float(json.load(fh)["reward"])
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def promote_plan(aborted: bool, reward: float, min_reward: float = CHAMPION_MIN_REWARD) -> bool:
    """On a clean run, promote the current plan to the champion ONLY if its reward
    clears min_reward (the doom floor) AND beats the current champion (or there is
    no champion yet). Returns True if the champion was updated."""
    if aborted or not os.path.exists(PLAN_CURRENT_PATH):
        return False
    try:
        reward = float(reward)
    except (TypeError, ValueError):
        return False  # no usable reward -> don't touch the champion
    if reward < min_reward:
        return False  # below the floor -> not a worthy fallback
    champ = _champion_reward()
    if champ is not None and reward <= champ:
        return False  # not better -> keep the existing champion
    try:
        shutil.copyfile(PLAN_CURRENT_PATH, PLAN_LAST_GOOD_PATH)
        with open(CHAMPION_REWARD_PATH, "w", encoding="utf-8") as fh:
            json.dump({"reward": reward}, fh)
        return True
    except OSError:
        return False


def restore_last_good() -> bool:
    """Re-apply the champion plan (checklist + coordinator/specialist summaries)
    via WriteEpisodePlan. Returns True if a good plan was restored."""
    try:
        with open(PLAN_LAST_GOOD_PATH, encoding="utf-8") as fh:
            plan = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(plan, dict) or not plan.get("checklist_items") or not plan.get("strategy_summary"):
        return False
    result = WriteEpisodePlan().invoke(plan, {})
    return not isinstance(result, str)  # WriteEpisodePlan returns "ERROR: ..." on failure
