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

Two side effects, applied as one tool call by ``episode_closer``:

  1. Persist this episode's cumulative_reward to ``last_reward.md`` so
     the next episode_closer can compute a real reward_delta.
  2. Drop the stale done=true observation envelope MAPs auto-restart leaves
     behind, so the next turn's ParkStatus does not re-trigger episode_closer.

Every episode is an exam episode (learning is always active), so there is
no phase to track or advance — this tool only persists the reward and clears
the cache.
"""

from __future__ import annotations

import logging
import os
from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.common.file_io import FileIO


class AdvanceEpisode(CodedTool):
    """Persist last_reward + clear the stale observation cache in one shot."""

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

        :param args: dict with key
            - ``final_reward`` (int|float, required): this episode's
              cumulative_reward. Written to ``last_reward.md`` for the
              next episode's prior_reward.
        :param sly_data: ignored.
        :return: dict ``{"status": "ok", "last_reward_written",
            "observation_cache_cleared"}`` on success, or an ``"ERROR: ..."``
            string on failure.
        """
        del sly_data

        final_reward = args.get("final_reward")
        if final_reward is None:
            return "ERROR: invalid_input: 'final_reward' is required."

        last_reward_body = f"cumulative_reward: {final_reward}\n"
        write_reward_err = FileIO.write_guarded(self.LAST_REWARD_PATH, last_reward_body, self.logger)
        if write_reward_err is not None:
            return write_reward_err

        # Drop the stale done=true envelope MAPs auto-restart leaves behind.
        # Without this, the NEXT turn's ParkStatus would still report done=true
        # and re-trigger episode_closer, replaying all bookkeeping.
        cache_cleared = self._clear_observation_cache()

        return {
            "status": "ok",
            "last_reward_written": float(final_reward),
            "observation_cache_cleared": cache_cleared,
        }

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """Delegate to the synchronous invoke."""
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
