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
ActiveTrials: return the active trials, joined across trial_strategies (the
rule body) and trial_strategies_criteria (the metadata), optionally filtered
to one domain.

Replaces the per-turn hand-parse every specialist used to do (read both
files, filter criteria by domain, join trial_ids back to rule bodies). The
specialists call ActiveTrials(domain='rides'); the trial_analyst/curator call
it with no domain to get every active trial.

AGE LIMIT: a trial is only meant to live until the episode-end close-out
resolves it, but a close-out that errors out (or never runs) leaves it in the
ledger forever. Since every trial's window is written in episode-relative steps
("from steps 91-100"), a stranded trial re-arms every episode and stacks
contradictory instructions on the same turn. So trials more than
MAX_CARRYOVER_EPISODES behind the current episode are withheld here, in the one
place every reader goes through, rather than trusted to be cleaned up.
"""

from __future__ import annotations

import json
import os
from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.latest_observation import LatestObservation
from coded_tools.trial_parsing import CRITERIA_PATH
from coded_tools.trial_parsing import STRATEGIES_PATH
from coded_tools.trial_parsing import parse_criteria
from coded_tools.trial_parsing import parse_strategies
from coded_tools.trial_parsing import read_text


def _current_episode() -> int | None:
    """Episode number from the observation cache, or None if unavailable.

    None means "cannot tell", and every caller then treats age as unknown and
    withholds nothing — a missing cache must never blank the learning loop.
    """
    path = LatestObservation.DEFAULT_PATH
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            cache = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(cache, dict):
        return None
    for entries in cache.values():
        last = entries[-1] if isinstance(entries, list) and entries else entries
        if isinstance(last, dict) and isinstance(last.get("episode"), int):
            return last["episode"]
    return None


class ActiveTrials(CodedTool):
    """Return active trials (rule + criteria, joined by trial_id), optionally by domain."""

    # 0 = this episode's trials only. 1 lets a macro trial the close-out judged
    # inconclusive run one more episode, which is the intended carry-over.
    MAX_CARRYOVER_EPISODES: ClassVar[int] = 1

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        """
        :param args: optional 'domain' (rides/shops/staff/research/layout/
            coordinator) and/or 'trial_origin' ('micro'|'macro') to filter to;
            omit for all active trials. (The filter is 'trial_origin', not
            'origin' — 'origin' is a reserved framework-injected key.)
        :return: {domain, origin, count, trials:[{trial_id, rule, domain,
            origin, section, edit_type, find_text, step_start, ep,
            success_criterion, failure_criterion, rationale}]}.
        """
        del sly_data
        domain = args.get("domain")
        domain = str(domain).strip().lower() if domain else None
        # NOT 'origin': the AAOSA framework injects a reserved 'origin' key (the
        # agent call-chain) into every tool call, which clobbered this filter and
        # silently dropped every trial (count=0 forever, killing the learning
        # loop). Take the filter from 'trial_origin', and ignore anything that
        # isn't a real origin so a stray value can never nuke the result again.
        origin = args.get("trial_origin")
        origin = str(origin).strip().lower() if origin else None
        if origin not in ("micro", "macro"):
            origin = None

        strategies = parse_strategies(read_text(STRATEGIES_PATH))
        criteria = parse_criteria(read_text(CRITERIA_PATH))

        current_ep = _current_episode()
        oldest_kept = (current_ep - self.MAX_CARRYOVER_EPISODES) if current_ep is not None else None

        trials: list[dict[str, Any]] = []
        stale: list[str] = []
        for trial_id, rule in strategies.items():
            crit = criteria.get(trial_id, {})
            trial_domain = crit.get("domain")
            if domain is not None and trial_domain != domain:
                continue
            if origin is not None and crit.get("origin") != origin:
                continue
            # `ep` is parsed as a string; an unparseable or missing one is treated
            # as current so a malformed criteria line is never silently withheld.
            if oldest_kept is not None:
                try:
                    trial_ep = int(crit.get("ep"))
                except (TypeError, ValueError):
                    trial_ep = current_ep
                if trial_ep < oldest_kept:
                    stale.append(trial_id)
                    continue
            trials.append({
                "trial_id": trial_id,
                "rule": rule,
                "domain": trial_domain,
                "origin": crit.get("origin"),
                "section": crit.get("section"),
                "edit_type": crit.get("edit"),
                "find_text": crit.get("find"),
                "step_start": crit.get("step_start"),
                "ep": crit.get("ep"),
                "success_criterion": crit.get("success"),
                "failure_criterion": crit.get("failure"),
                "rationale": crit.get("rationale"),
            })

        # `withheld_stale` is reported, not hidden: a silently shrinking trial list
        # would look like the learning loop simply stopped producing.
        result: dict[str, Any] = {
            "domain": domain, "origin": origin, "count": len(trials), "trials": trials,
        }
        if stale:
            result["withheld_stale"] = stale
            result["withheld_reason"] = (
                f"logged before episode {oldest_kept} and never resolved by an "
                f"episode-end close-out; their step windows no longer apply"
            )
        return result

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        return self.invoke(args, sly_data)
