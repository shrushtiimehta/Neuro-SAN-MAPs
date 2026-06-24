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
End-of-episode bookkeeping (deterministic, not LLM logic).

Three side effects, applied as one tool call by ``episode_closer``:

  1. Persist this episode's cumulative_reward to ``last_reward.md`` so
     the next episode_closer can compute a real reward_delta.
  2. Drop the stale done=true observation envelope MAPs auto-restart leaves
     behind, so the next turn's ParkStatus does not re-trigger episode_closer.
  3. Update trial_strategies_outcome.md:
       - Insert the LLM-crafted outcome_summary (passed by episode_closer)
         under "## Episode Summaries" so trial_analyst can read what NOT to
         re-propose next episode.
       - Trim raw OUTCOME lines older than the current episode, leaving only
         the current episode's lines plus all summary sections.

Trial strategies + criteria cleanup (removing stale/resolved/unpromatable
trials) is intentionally NOT done here — it happens at the START of the next
episode inside SeedPlaybooks, so the new episode always begins with a clean slate.

Every episode is an exam episode (learning is always active), so there is
no phase to track or advance.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.common.file_io import FileIO
from coded_tools.maps_park.trial_parsing import OUTCOME_PATH
from coded_tools.maps_park.trial_parsing import read_text

_OUTCOME_EP_RE = re.compile(r"^-\s+OUTCOME\s+ep=(\d+)\s")

_SUMMARY_SECTION = "## Episode Summaries"


class AdvanceEpisode(CodedTool):
    """Persist last_reward, clear the observation cache, and update the outcome ledger."""

    LAST_REWARD_PATH: ClassVar[str] = "coded_tools/maps_park/state/last_reward.md"
    LATEST_OBS_PATH: ClassVar[str] = os.environ.get(
        "MAPS_LATEST_OBS_PATH",
        "coded_tools/maps_park/state/latest_observations.json",
    )

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """
        Apply end-of-episode bookkeeping.

        :param args:
            - ``final_reward`` (int|float, required): this episode's
              cumulative_reward. Written to ``last_reward.md`` for the
              next episode's prior_reward.
            - ``episode`` (int, required): current episode number, used to
              age out stale trials and tag the outcome summary.
            - ``outcome_summary`` (str, optional): LLM-crafted one-paragraph
              summary of this episode's confirmed/falsified outcomes — what
              NOT to re-propose next episode. Written under "## Episode
              Summaries" in trial_strategies_outcome.md before the raw OUTCOME
              lines are trimmed.
        :param sly_data: ignored.
        :return: dict with status, last_reward_written, observation_cache_cleared,
            and trial_cleanup summary on success, or an ``"ERROR: ..."`` string.
        """
        del sly_data

        final_reward = args.get("final_reward")
        if final_reward is None:
            return "ERROR: invalid_input: 'final_reward' is required."

        episode = FileIO.to_int(args.get("episode"))
        if episode is None:
            return "ERROR: invalid_input: 'episode' is required and must be an integer."

        outcome_summary = str(args["outcome_summary"]).strip() if args.get("outcome_summary") else None

        last_reward_body = f"cumulative_reward: {final_reward}\n"
        write_reward_err = FileIO.write_guarded(self.LAST_REWARD_PATH, last_reward_body, self.logger)
        if write_reward_err is not None:
            return write_reward_err

        # Drop the stale done=true envelope MAPs auto-restart leaves behind.
        cache_cleared = self._clear_observation_cache()

        # Update the outcome ledger: insert LLM summary and trim old OUTCOME lines.
        outcome_updated = self._update_outcome(episode, outcome_summary)

        return {
            "status": "ok",
            "last_reward_written": float(final_reward),
            "observation_cache_cleared": cache_cleared,
            "outcome_updated": outcome_updated,
        }

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return self.invoke(args, sly_data)

    def _clear_observation_cache(self) -> bool:
        """Remove the latest-observation cache. Returns True if a file existed."""
        try:
            if os.path.exists(self.LATEST_OBS_PATH):
                os.remove(self.LATEST_OBS_PATH)
                return True
        except OSError as err:
            self.logger.warning("Could not clear %s: %s", self.LATEST_OBS_PATH, err)
        return False

    def _update_outcome(self, episode: int, outcome_summary: str | None) -> dict[str, Any]:
        """Insert LLM summary into the outcome ledger and trim old raw OUTCOME lines."""
        try:
            outcome_text = read_text(OUTCOME_PATH)
        except OSError as err:
            return {"error": f"could not read outcome file: {err}"}

        if outcome_summary:
            outcome_text = self._insert_summary(outcome_text, episode, outcome_summary)
        trimmed = self._trim_outcome(outcome_text, episode)

        try:
            FileIO.write_text(OUTCOME_PATH, trimmed)
        except OSError as err:
            return {"error": f"could not write outcome file: {err}"}

        return {"summary_written": outcome_summary is not None}

    @staticmethod
    def _insert_summary(text: str, episode: int, summary: str) -> str:
        """Insert one episode-summary entry under the ## Episode Summaries section.

        Creates the section after the first header line if it doesn't exist yet.
        New entries are prepended (most recent first) under the section header.
        """
        entry = f"### ep={episode}\n{summary.strip()}\n"
        anchor = _SUMMARY_SECTION + "\n"
        if anchor in text:
            return text.replace(anchor, anchor + entry + "\n", 1)
        # Section missing — create it after the first non-blank line (file header).
        lines = text.splitlines(keepends=True)
        insert_at = next((i + 1 for i, ln in enumerate(lines) if ln.strip()), len(lines))
        lines.insert(insert_at, "\n" + _SUMMARY_SECTION + "\n" + entry + "\n")
        return "".join(lines)

    @staticmethod
    def _trim_outcome(text: str, episode: int) -> str:
        """Keep non-OUTCOME lines (headers/summaries) and OUTCOME lines from this episode only."""
        out: list[str] = []
        for line in text.splitlines():
            m = _OUTCOME_EP_RE.match(line.strip())
            if m is None:
                out.append(line)  # header, summary, or section line — always keep
            elif int(m.group(1)) >= episode:
                out.append(line)  # current episode's outcomes — keep
            # else: older raw OUTCOME lines — drop
        body = "\n".join(out).strip("\n")
        return body + "\n" if body else ""
