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
CarryoverTrials: hand the episode planner every trial left over from earlier
episodes, and clear them in the same call.

The trial lifecycle has exactly one exit for a leftover:

    episode START   design trials                          -> LogTrial
    episode END     evaluate: confirmed -> PromoteTrial
                              falsified -> removed
                              neither   -> LEFT OVER       -> ResolveTrials
    next START      leftovers fed to the planner AND DELETED  <- this tool

READ-AND-CLEAR, like the scratchpad: a leftover informs exactly one planning
pass and then stops existing. Nothing can go stale, because nothing survives a
second episode — which is what went wrong before this tool existed, when a
ledger carried ep0/ep1/ep2 trials into ep3 at once and their episode-relative
step windows ("from steps 91-100") all re-armed together with contradictory
cash floors.

Only trials from EARLIER episodes are cleared. Trials stamped with the current
episode are left alone, so calling this after LogTrial (rather than before)
cannot wipe the plan the planner just wrote — the tool is safe in any order.
"""

from __future__ import annotations

from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.file_io import FileIO
from coded_tools.trial_parsing import CRITERIA_PATH
from coded_tools.trial_parsing import OUTCOME_PATH
from coded_tools.trial_parsing import STRATEGIES_PATH
from coded_tools.trial_parsing import filter_lines
from coded_tools.trial_parsing import parse_criteria
from coded_tools.trial_parsing import parse_strategies
from coded_tools.trial_parsing import read_text


class CarryoverTrials(CodedTool):
    """Return every trial left over from an earlier episode, and delete it."""

    STRATEGIES_PATH: str = STRATEGIES_PATH
    CRITERIA_PATH: str = CRITERIA_PATH
    OUTCOME_PATH: str = OUTCOME_PATH

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """
        :param args: episode (int, required) — the episode being planned. Trials
            stamped with an EARLIER episode are returned and cleared; trials
            stamped with this one are left in place.
        :return: {episode, count, trials:[...], cleared:[trial_id]} or "ERROR: ...".
        """
        del sly_data
        try:
            episode = int(args.get("episode"))
        except (TypeError, ValueError):
            return "ERROR: episode is required and must be an integer"

        strat_text = read_text(self.STRATEGIES_PATH)
        crit_text = read_text(self.CRITERIA_PATH)
        strategies = parse_strategies(strat_text)
        criteria = parse_criteria(crit_text)

        carried: list[dict[str, Any]] = []
        keep_ids: set[str] = set()
        outcome_lines: list[str] = []

        for trial_id, rule in strategies.items():
            crit = criteria.get(trial_id, {})
            try:
                trial_ep = int(crit.get("ep"))
            except (TypeError, ValueError):
                # No parseable episode stamp: keep it rather than delete blind.
                # A malformed criteria line is a bug to fix, not a trial to bin.
                keep_ids.add(trial_id)
                continue

            if trial_ep >= episode:
                keep_ids.add(trial_id)          # logged for the episode being planned
                continue

            carried.append({
                "trial_id": trial_id,
                "rule": rule,
                "domain": crit.get("domain"),
                "origin": crit.get("origin"),
                "ep": crit.get("ep"),
                "step_start": crit.get("step_start"),
                "rationale": crit.get("rationale"),
                "success_criterion": crit.get("success"),
                "failure_criterion": crit.get("failure"),
            })
            # The rule text goes into the outcome ledger before the rule itself is
            # deleted below — otherwise the only record of what was tried is an id.
            # Macro only. A micro rule is written for one episode's exact state
            # ("from steps 61-70, if cash is at least 8500 and num_rides is 13"),
            # so ledgering it just buries the macro outcomes that do carry across
            # episodes. It is still cleared from the active files above.
            if crit.get("origin") == "micro":
                continue
            safe_rule = rule.replace("'", "").strip()
            outcome_lines.append(
                f"- OUTCOME ep={episode} trial_id={trial_id} "
                f"domain={crit.get('domain', '')} origin={crit.get('origin', '')} "
                f"outcome=carried_over note='fed to the episode {episode} planner "
                f"and retired' rule='{safe_rule}'\n"
            )

        if carried:
            try:
                FileIO.write_text(self.STRATEGIES_PATH, filter_lines(strat_text, keep_ids))
                FileIO.write_text(self.CRITERIA_PATH, filter_lines(crit_text, keep_ids))
                FileIO.append_text(self.OUTCOME_PATH, "".join(outcome_lines))
            except OSError as err:
                return f"ERROR: could not write trial files: {err}"

        return {
            "episode": episode,
            "count": len(carried),
            "trials": carried,
            "cleared": [t["trial_id"] for t in carried],
        }

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return self.invoke(args, sly_data)
