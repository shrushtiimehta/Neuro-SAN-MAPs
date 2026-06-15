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
specialists call ActiveTrials(domain='rides'); the anthropologist/curator call
it with no domain to get every active trial.
"""

from __future__ import annotations

from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.maps_park.trial_parsing import CRITERIA_PATH
from coded_tools.maps_park.trial_parsing import STRATEGIES_PATH
from coded_tools.maps_park.trial_parsing import parse_criteria
from coded_tools.maps_park.trial_parsing import parse_strategies
from coded_tools.maps_park.trial_parsing import read_text


class ActiveTrials(CodedTool):
    """Return active trials (rule + criteria, joined by trial_id), optionally by domain."""

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        """
        :param args: optional 'domain' (rides/shops/staff/research/layout/
            director/coordinator) to filter to; omit for all active trials.
        :return: {domain, count, trials:[{trial_id, rule, domain, section,
            edit_type, find_text, step_start, ep, success_criterion,
            failure_criterion, rationale}]}.
        """
        del sly_data
        domain = args.get("domain")
        domain = str(domain).strip().lower() if domain else None

        strategies = parse_strategies(read_text(STRATEGIES_PATH))
        criteria = parse_criteria(read_text(CRITERIA_PATH))

        trials: list[dict[str, Any]] = []
        for trial_id, rule in strategies.items():
            crit = criteria.get(trial_id, {})
            trial_domain = crit.get("domain")
            if domain is not None and trial_domain != domain:
                continue
            trials.append({
                "trial_id": trial_id,
                "rule": rule,
                "domain": trial_domain,
                "section": crit.get("section"),
                "edit_type": crit.get("edit"),
                "find_text": crit.get("find"),
                "step_start": crit.get("step_start"),
                "ep": crit.get("ep"),
                "success_criterion": crit.get("success"),
                "failure_criterion": crit.get("failure"),
                "rationale": crit.get("rationale"),
            })

        return {"domain": domain, "count": len(trials), "trials": trials}

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        return self.invoke(args, sly_data)
