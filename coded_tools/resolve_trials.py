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
ResolveTrials: apply the curator's per-trial report to the trial files at
episode end, deterministically.

Policy (per active trial):
  - confirmed / falsified -> REMOVE from trial_strategies + trial_strategies_criteria
  - not_applied / inconclusive -> KEEP
  - an active trial absent from the report -> KEEP, outcome 'inconclusive' note 'no_report'
  - origin=micro -> REMOVE regardless of outcome (micro trials are episode-scoped;
    a confirmed one was already promoted to the playbook by the curator), so the
    next episode starts back at just the persisted macro trials.
  - a macro trial older than ActiveTrials still serves, absent from the report
    -> REMOVE as 'expired'. It cannot be reported on, because ActiveTrials no
    longer shows it to the close-out; keeping it as 'inconclusive' would leave a
    trial that is both invisible and undeletable.
For every MACRO trial (never micro — those are written for one episode's exact
state and teach the next planner nothing) append one line to
trial_strategies_outcome, carrying the rule TEXT as well as its id (the id's
rule is deleted from trial_strategies in the same call, so this line is the only
surviving record of what was tried):
  "- OUTCOME ep=<N> trial_id=<id> domain=<D> origin=<O> outcome=<O> note='<note>' rule='<text>'"
"""

from __future__ import annotations

import json
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.active_trials import ActiveTrials
from coded_tools.file_io import FileIO
from coded_tools.trial_parsing import CRITERIA_PATH
from coded_tools.trial_parsing import OUTCOME_PATH
from coded_tools.trial_parsing import STRATEGIES_PATH
from coded_tools.trial_parsing import filter_lines
from coded_tools.trial_parsing import parse_criteria
from coded_tools.trial_parsing import parse_strategies
from coded_tools.trial_parsing import read_text


class ResolveTrials(CodedTool):
    """Trim trial_strategies + criteria and append outcomes from the curator report."""

    REMOVE_OUTCOMES = frozenset({"confirmed", "falsified"})

    @staticmethod
    def _too_old(crit: dict[str, Any], episode: int) -> bool:
        """True when ActiveTrials would no longer serve this trial.

        Deliberately reads the SAME constant ActiveTrials filters on: if the two
        rules ever drift apart, trials reappear in the gap between them —
        withheld from every reader, yet never resolved away.
        """
        try:
            return int(crit.get("ep")) < episode - ActiveTrials.MAX_CARRYOVER_EPISODES
        except (TypeError, ValueError):
            return False        # unparseable ep -> treat as current, never expire blind

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """
        :param args: episode (int); report (JSON list of
            {trial_id, domain, outcome, note}).
        :return: {kept:[...], removed:[...], outcomes_appended:N} or "ERROR: ...".
        """
        del sly_data
        try:
            episode = int(args.get("episode"))
        except (TypeError, ValueError):
            return "ERROR: episode is required and must be an integer"

        report = args.get("report") or []
        if isinstance(report, str):
            try:
                report = json.loads(report)
            except json.JSONDecodeError:
                return "ERROR: report must be a JSON list of per-trial objects"
        report_map = {
            str(r["trial_id"]): r for r in report
            if isinstance(r, dict) and r.get("trial_id")
        }

        strat_text = read_text(STRATEGIES_PATH)
        crit_text = read_text(CRITERIA_PATH)
        strategies = parse_strategies(strat_text)
        active_ids = list(strategies.keys())
        criteria = parse_criteria(crit_text)

        keep_ids: set[str] = set()
        kept: list[str] = []
        removed: list[str] = []
        outcome_lines: list[str] = []

        for trial_id in active_ids:
            entry = report_map.get(trial_id)
            crit = criteria.get(trial_id, {})
            origin = crit.get("origin", "")
            if entry:
                outcome = str(entry.get("outcome", "inconclusive")).strip() or "inconclusive"
                note = str(entry.get("note", "")).strip()
                domain = entry.get("domain") or crit.get("domain", "")
            else:
                outcome, note = "inconclusive", "no_report"
                domain = crit.get("domain", "")

            # micro trials are episode-scoped — drop every one regardless of
            # outcome (a confirmed one was already promoted by the curator) so the
            # next episode starts back at just the persisted macro trials.
            if origin == "micro" and outcome not in self.REMOVE_OUTCOMES:
                note = (f"{note}; " if note else "") + "micro_episode_scoped"

            # A macro trial too old to still be served is unreportable: ActiveTrials
            # withholds it, so the close-out never sees it, so it is never confirmed
            # or falsified — and "inconclusive" would KEEP it. Left alone that is a
            # trial which is both invisible and undeletable. Expire it here, where
            # the raw ledger is still in view.
            if not entry and origin != "micro" and self._too_old(crit, episode):
                outcome = "expired"
                note = (f"{note}; " if note else "") + (
                    f"stranded since ep{crit.get('ep')} — no close-out ever resolved it"
                )

            if outcome in self.REMOVE_OUTCOMES or origin == "micro" or outcome == "expired":
                removed.append(trial_id)
            else:
                keep_ids.add(trial_id)
                kept.append(trial_id)
            # MACRO ONLY. A micro rule is written for one episode's exact state
            # ("from steps 61-70, if cash is at least 8500 and num_rides is 13...")
            # and is meaningless once that park is gone, so its outcome is not
            # ledgered — it would only teach the next planner about a park that
            # no longer exists. The removal above still happens either way.
            if origin == "micro":
                continue
            # The rule TEXT goes in the line, not just its id. The next episode's
            # planner reads this ledger to avoid re-proposing a falsified idea —
            # and "t1_1 falsified" tells it nothing, because the id's rule is
            # deleted from trial_strategies.md in the same call.
            rule = (strategies.get(trial_id) or "").replace("'", "").strip()
            outcome_lines.append(
                f"- OUTCOME ep={episode} trial_id={trial_id} domain={domain} "
                f"origin={origin} outcome={outcome} note='{note}' rule='{rule}'\n"
            )

        try:
            FileIO.write_text(STRATEGIES_PATH, filter_lines(strat_text, keep_ids))
            FileIO.write_text(CRITERIA_PATH, filter_lines(crit_text, keep_ids))
            FileIO.append_text(OUTCOME_PATH, "".join(outcome_lines))
        except OSError as err:
            return f"ERROR: could not write trial files: {err}"

        return {"kept": kept, "removed": removed, "outcomes_appended": len(outcome_lines)}

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return self.invoke(args, sly_data)
