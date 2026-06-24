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
LogTrial: mint a collision-free trial_id and append the matching pair of
lines to trial_strategies + trial_strategies_criteria, atomically.

This replaces the hand-rolled "read the file, count the lines whose id
starts with t<episode>_, increment, then format the criteria line"
procedure that was duplicated across consultant_director (periodic),
episode_closer, and parkstatus_reader. The LLM only supplies the suggestion
fields; the deterministic id-minting and exact line formatting happen here.

Files written (one appended line each):
  - trial_strategies.md           "- <trial_id>: <new_text>"
  - trial_strategies_criteria.md  "- <trial_id> ep=<E> step_start=<S>
                                    domain=<D> section='<X>' edit=<...>
                                    [find='<F>'] rationale='<R>'
                                    success='<SC>' failure='<FC>'"
"""

from __future__ import annotations

from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.common.file_io import FileIO
from coded_tools.maps_park.trial_parsing import CRITERIA_PATH
from coded_tools.maps_park.trial_parsing import STRATEGIES_PATH


class LogTrial(CodedTool):
    """Mint a trial_id and append the strategy + criteria lines for one trial."""

    STRATEGIES_PATH: ClassVar[str] = STRATEGIES_PATH
    CRITERIA_PATH: ClassVar[str] = CRITERIA_PATH

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """
        :param args: episode (int), domain, edit_type ('add_line'|'replace_line'),
            new_text, section, rationale, success_criterion, failure_criterion,
            step_start (int step, or the literal 'end_of_episode'),
            find_text (required only for replace_line).
        :return: {"trial_id": <id>} or an "ERROR: ..." string.
        """
        del sly_data

        episode = FileIO.to_int(args.get("episode"))
        if episode is None:
            return "ERROR: episode is required and must be an integer"

        edit_type = str(args.get("edit_type", "")).strip()
        if edit_type not in ("add_line", "replace_line"):
            return "ERROR: edit_type must be 'add_line' or 'replace_line'"

        new_text = str(args.get("new_text", "")).strip()
        domain = str(args.get("domain", "")).strip()
        section = str(args.get("section", "")).strip()
        rationale = str(args.get("rationale", "")).strip()
        success = str(args.get("success_criterion", "")).strip()
        failure = str(args.get("failure_criterion", "")).strip()
        find_text = str(args.get("find_text", "")).strip()

        for name, value in (("new_text", new_text), ("domain", domain),
                            ("section", section), ("rationale", rationale),
                            ("success_criterion", success), ("failure_criterion", failure)):
            if not value:
                return f"ERROR: {name} is required and must be non-empty"
        if edit_type == "replace_line" and not find_text:
            return "ERROR: replace_line requires find_text"

        # step_start: an integer step, or the literal 'end_of_episode'.
        raw_step = args.get("step_start")
        if isinstance(raw_step, str) and raw_step.strip() == "end_of_episode":
            step_start: Any = "end_of_episode"
        else:
            step_start = FileIO.to_int(raw_step)
            if step_start is None:
                return "ERROR: step_start must be an integer or 'end_of_episode'"

        trial_id = self._next_trial_id(episode)

        strategy_line = f"- {trial_id}: {new_text}\n"
        if edit_type == "replace_line":
            criteria_line = (
                f"- {trial_id} ep={episode} step_start={step_start} domain={domain} "
                f"section='{section}' edit=replace_line find='{find_text}' "
                f"rationale='{rationale}' success='{success}' failure='{failure}'\n"
            )
        else:
            criteria_line = (
                f"- {trial_id} ep={episode} step_start={step_start} domain={domain} "
                f"section='{section}' edit=add_line "
                f"rationale='{rationale}' success='{success}' failure='{failure}'\n"
            )

        try:
            FileIO.append_text(self.STRATEGIES_PATH, strategy_line)
            FileIO.append_text(self.CRITERIA_PATH, criteria_line)
        except OSError as err:
            return f"ERROR: could not write trial files: {err}"

        return {"trial_id": trial_id}

    def _next_trial_id(self, episode: int) -> str:
        """Next collision-free id for this episode: t<episode>_<N+1>."""
        prefix = f"- t{episode}_"
        count = sum(
            1 for line in FileIO.read_text(self.STRATEGIES_PATH).splitlines()
            if line.startswith(prefix)
        )
        return f"t{episode}_{count + 1}"

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return self.invoke(args, sly_data)
