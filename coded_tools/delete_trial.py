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
DeleteTrial: prune ONE micro trial mid-episode when it is no longer needed or
isn't working.

The mid_episode_analyst logs its own (origin=micro) trials via LogTrial and, on
a later step, may find one of them unproductive. This removes the paired lines
from trial_strategies + trial_strategies_criteria. Nothing is written to
trial_strategies_outcome: a micro rule is written for one episode's exact state
("from steps 61-70, if cash is at least 8500 and num_rides is 13...") and says
nothing about the next park, so ledgering it would only bury the macro outcomes
that DO carry across episodes.

Micro-only by design: macro trials persist across episodes and are resolved
only at episode close by ResolveTrials, so a macro trial_id is refused. The
line removal mirrors ResolveTrials exactly (both use
coded_tools.trial_parsing.filter_lines).
"""

from __future__ import annotations

from typing import Any

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.file_io import FileIO
from coded_tools.trial_parsing import CRITERIA_PATH
from coded_tools.trial_parsing import STRATEGIES_PATH
from coded_tools.trial_parsing import filter_lines
from coded_tools.trial_parsing import parse_criteria
from coded_tools.trial_parsing import parse_strategies
from coded_tools.trial_parsing import read_text


class DeleteTrial(CodedTool):
    """Remove one micro trial from the active ledger. Writes no outcome line."""

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """
        :param args: trial_id (str) — the micro trial to delete, e.g. 't3_2'.
        :return: {"deleted": <trial_id>} or "ERROR: ...".
        """
        del sly_data

        trial_id = str(args.get("trial_id", "")).strip()
        if not trial_id:
            return "ERROR: trial_id is required and must be non-empty"

        strat_text = read_text(STRATEGIES_PATH)
        crit_text = read_text(CRITERIA_PATH)

        strategies = parse_strategies(strat_text)
        active_ids = strategies.keys()
        if trial_id not in active_ids:
            return f"ERROR: unknown or already-removed trial_id: {trial_id}"

        crit = parse_criteria(crit_text).get(trial_id, {})
        origin = crit.get("origin", "")
        if origin != "micro":
            return (
                f"ERROR: refusing to delete non-micro trial_id: {trial_id} "
                f"(origin={origin or 'unknown'}); only micro trials can be pruned mid-episode"
            )

        keep_ids = {tid for tid in active_ids if tid != trial_id}
        # Nothing is ledgered. This tool only ever deletes MICRO trials (guarded
        # above), and a micro rule is written for one episode's exact state
        # ("from steps 61-70, if cash is at least 8500 and num_rides is 13..."),
        # so its outcome teaches the next planner nothing about a different park.
        # Macro outcomes are the ledger's whole content; ResolveTrials writes those.
        try:
            FileIO.write_text(STRATEGIES_PATH, filter_lines(strat_text, keep_ids))
            FileIO.write_text(CRITERIA_PATH, filter_lines(crit_text, keep_ids))
        except OSError as err:
            return f"ERROR: could not write trial files: {err}"

        return {"deleted": trial_id}

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return self.invoke(args, sly_data)
