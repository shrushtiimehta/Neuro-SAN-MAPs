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

Two required side effects, applied as one tool call by ``episode_closer``:

  1. Drop the stale done=true observation envelope MAPs auto-restart leaves
     behind, so the next turn's ParkStatus does not re-trigger episode_closer.
  2. Atomically write ``closeout_receipt.json`` LAST. The runner uses this
     episode/reward receipt as the durable transaction commit marker and will
     retry close-out from local telemetry until it exists.

Arms that still consume the legacy ``last_reward.md`` may opt into writing it.
The canonical baseline does not: its planner reads reward from full status.

trial_strategies_outcome.md is NOT touched here: it is append-only and keeps
every episode's OUTCOME lines for the life of the run. It used to be trimmed to
a 5-episode window, which silently deleted the run's own history — the lines are
macro-only (a handful per episode, ~250 bytes each), so a 100-episode run is a
few hundred KB and worth keeping whole. ResolveTrials and CarryoverTrials append
to it; nothing prunes it. Wiping it is a --fresh run's job, not an episode's.

No LLM prose is stored. An episode summary written by the close-out reads like
"pulled first red carousel to step70 versus ep1 step75" — true of one park that
no longer exists, and worthless to the planner of the next one. The raw OUTCOME
lines are the record: one line per macro trial, carrying the rule text and the
verdict.

Trial strategies + criteria cleanup (removing stale/resolved/unpromatable
trials) is intentionally NOT done here — it happens at the START of the next
episode inside SeedPlaybooks, so the new episode always begins with a clean slate.

Every episode is an exam episode (learning is always active), so there is
no phase to track or advance.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.file_io import FileIO
from coded_tools.state_dir import USE_LAST_REWARD as _USE_LAST_REWARD
from coded_tools.state_dir import state_path


class AdvanceEpisode(CodedTool):
    """Commit episode close-out and clear the observation cache."""

    WRITE_LAST_REWARD: ClassVar[bool] = _USE_LAST_REWARD
    LAST_REWARD_PATH: ClassVar[str] = state_path("last_reward.md")
    CLOSEOUT_RECEIPT_PATH: ClassVar[str] = state_path("closeout_receipt.json")
    PENDING_PATH: ClassVar[str] = state_path(".advance_episode.pending.json")
    LATEST_OBS_PATH: ClassVar[str] = os.environ.get(
        "MAPS_LATEST_OBS_PATH",
        state_path("latest_observations.json"),
    )

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    @classmethod
    def recover_pending(cls) -> str | None:
        """Recover a process interrupted before the close-out receipt write.

        If the receipt landed, the transaction committed and only the journal
        needs removing. For a legacy arm that writes ``last_reward``, otherwise
        restore its exact prior value before retrying.
        """
        if not os.path.exists(cls.PENDING_PATH):
            return None
        try:
            with open(cls.PENDING_PATH, encoding="utf-8") as handle:
                pending = json.load(handle)
            committed = False
            try:
                with open(cls.CLOSEOUT_RECEIPT_PATH, encoding="utf-8") as handle:
                    receipt = json.load(handle)
                committed = int(receipt.get("episode")) == int(pending.get("episode")) and float(
                    receipt.get("final_reward")
                ) == float(pending.get("final_reward"))
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                committed = False

            if not committed and pending.get("write_last_reward", cls.WRITE_LAST_REWARD):
                if pending.get("prior_exists"):
                    FileIO.write_text_atomic(cls.LAST_REWARD_PATH, str(pending.get("prior_body", "")))
                else:
                    try:
                        os.remove(cls.LAST_REWARD_PATH)
                    except FileNotFoundError:
                        pass
            os.remove(cls.PENDING_PATH)
            return None
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as err:
            return f"ERROR: could_not_recover_advance_episode: {err}"

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """
        Apply end-of-episode bookkeeping.

        :param args:
            - ``final_reward`` (int|float, required): this episode's
              cumulative_reward, recorded in the close-out receipt.
            - ``episode`` (int, required): current episode number. Validated
              but not otherwise used here — the close-out contract keeps it so a
              malformed call is caught, and the trial files are owned elsewhere.
        :param sly_data: ignored.
        :return: result dict on success, or an ``"ERROR: ..."`` string.
        """
        del sly_data

        recovery_error = self.recover_pending()
        if recovery_error is not None:
            return recovery_error

        final_reward = args.get("final_reward")
        if final_reward is None:
            return "ERROR: invalid_input: 'final_reward' is required."

        episode = FileIO.to_int(args.get("episode"))
        if episode is None:
            return "ERROR: invalid_input: 'episode' is required and must be an integer."

        try:
            final_reward_number = float(final_reward)
        except (TypeError, ValueError):
            return "ERROR: invalid_input: 'final_reward' must be numeric."

        pending = {
            "version": 1,
            "episode": episode,
            "final_reward": final_reward_number,
            "write_last_reward": self.WRITE_LAST_REWARD,
        }
        if self.WRITE_LAST_REWARD:
            pending["prior_exists"] = os.path.exists(self.LAST_REWARD_PATH)
            pending["prior_body"] = FileIO.read_text(self.LAST_REWARD_PATH)
        try:
            FileIO.write_text_atomic(self.PENDING_PATH, json.dumps(pending, sort_keys=True) + "\n")
            if self.WRITE_LAST_REWARD:
                FileIO.write_text_atomic(self.LAST_REWARD_PATH, f"cumulative_reward: {final_reward}\n")
        except OSError as err:
            recovery_error = self.recover_pending()
            if recovery_error is not None:
                return recovery_error
            return f"ERROR: could_not_write: {self.LAST_REWARD_PATH}: {err}"

        # Drop the stale done=true envelope MAPs auto-restart leaves behind.
        cache_cleared = self._clear_observation_cache()

        # Written LAST: this is the close-out transaction's durable commit
        # marker.  The runner advances only after this exact episode/reward pair
        # exists.  Repeating the write is safe, so a failed close-out can retry.
        receipt = {
            "version": 1,
            "episode": episode,
            "final_reward": final_reward_number,
        }
        try:
            FileIO.write_text_atomic(
                self.CLOSEOUT_RECEIPT_PATH,
                json.dumps(receipt, sort_keys=True) + "\n",
            )
        except OSError as err:
            self.logger.error("Could not write %s: %s", self.CLOSEOUT_RECEIPT_PATH, err)
            recovery_error = self.recover_pending()
            if recovery_error is not None:
                return recovery_error
            return f"ERROR: could_not_write: {self.CLOSEOUT_RECEIPT_PATH}: {err}"

        try:
            os.remove(self.PENDING_PATH)
        except OSError as err:
            # The receipt is authoritative and already committed. A later call
            # to recover_pending sees the matching receipt and only removes the
            # stale journal; never report a false close-out failure here.
            self.logger.warning("Could not clear %s: %s", self.PENDING_PATH, err)

        result = {
            "status": "ok",
            "episode": episode,
            "observation_cache_cleared": cache_cleared,
            "closeout_receipt_written": True,
        }
        if self.WRITE_LAST_REWARD:
            result["last_reward_written"] = final_reward_number
        return result

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
