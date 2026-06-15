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
In all cases append one line to trial_strategies_outcome:
  "- OUTCOME ep=<N> trial_id=<id> domain=<D> outcome=<O> note='<note>'"
"""

from __future__ import annotations

import json
import re
from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.common.file_io import FileIO
from coded_tools.maps_park.trial_parsing import CRITERIA_PATH
from coded_tools.maps_park.trial_parsing import OUTCOME_PATH
from coded_tools.maps_park.trial_parsing import STRATEGIES_PATH
from coded_tools.maps_park.trial_parsing import parse_criteria
from coded_tools.maps_park.trial_parsing import parse_strategies
from coded_tools.maps_park.trial_parsing import read_text

_LINE_TID_RE = re.compile(r"^-\s+(\S+?):?\s")  # trial_id at the start of a strategy or criteria line


class ResolveTrials(CodedTool):
    """Trim trial_strategies + criteria and append outcomes from the curator report."""

    REMOVE_OUTCOMES = frozenset({"confirmed", "falsified"})

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
        active_ids = list(parse_strategies(strat_text).keys())
        criteria = parse_criteria(crit_text)

        keep_ids: set[str] = set()
        kept: list[str] = []
        removed: list[str] = []
        outcome_lines: list[str] = []

        for trial_id in active_ids:
            entry = report_map.get(trial_id)
            if entry:
                outcome = str(entry.get("outcome", "inconclusive")).strip() or "inconclusive"
                note = str(entry.get("note", "")).strip()
                domain = entry.get("domain") or criteria.get(trial_id, {}).get("domain", "")
            else:
                outcome, note = "inconclusive", "no_report"
                domain = criteria.get(trial_id, {}).get("domain", "")

            if outcome in self.REMOVE_OUTCOMES:
                removed.append(trial_id)
            else:
                keep_ids.add(trial_id)
                kept.append(trial_id)
            outcome_lines.append(
                f"- OUTCOME ep={episode} trial_id={trial_id} domain={domain} "
                f"outcome={outcome} note='{note}'\n"
            )

        try:
            FileIO.write_text(STRATEGIES_PATH, self._filter_lines(strat_text, keep_ids))
            FileIO.write_text(CRITERIA_PATH, self._filter_lines(crit_text, keep_ids))
            FileIO.append_text(OUTCOME_PATH, "".join(outcome_lines))
        except OSError as err:
            return f"ERROR: could not write trial files: {err}"

        return {"kept": kept, "removed": removed, "outcomes_appended": len(outcome_lines)}

    @staticmethod
    def _filter_lines(text: str, keep_ids: set[str]) -> str:
        """Keep every line whose trial_id is in keep_ids; preserve non-trial lines."""
        out: list[str] = []
        for line in text.splitlines():
            match = _LINE_TID_RE.match(line.strip())
            if match is None:
                out.append(line)  # blank/header/other — preserve
            elif match.group(1) in keep_ids:
                out.append(line)
            # else: a trial line whose id was removed -> drop
        body = "\n".join(out).strip("\n")
        return body + "\n" if body else ""

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return self.invoke(args, sly_data)
