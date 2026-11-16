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
SeedPlaybooks: copy the six config_files strategy seeds into the six
state/playbook_*.md files (deterministic file mechanics, not LLM logic).

Each playbook starts as a verbatim copy of its config seed; the consultant
later edits the state copy with confirmed-rule promotions. The config seed
is the read-only source of truth, the state file is the working copy.

Modes (via the ``overwrite`` arg):
  - overwrite=True  (a fresh, from-scratch run): reset every playbook to its
    config seed, discarding any prior working copy.
  - overwrite=False (a resume, or a mid-run new episode): only create
    playbooks that are missing or empty, so learned edits survive.

Returns ``{"status": "ok", "seeded": [...], "skipped": [...], "errors": [...]}``.
"""

from __future__ import annotations

import logging
import os
from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool

from coded_tools.file_io import FileIO
from coded_tools.state_dir import MERGED_CONTEXT as _MERGED
from coded_tools.state_dir import SEED_DIR as _SEED_DIR
from coded_tools.state_dir import STATE_DIR as _STATE_DIR
from coded_tools.state_dir import USE_LAST_REWARD as _USE_LAST_REWARD


class SeedPlaybooks(CodedTool):
    """Copy config strategy seeds into the working playbook files."""

    SEED_DIR: ClassVar[str] = _SEED_DIR
    STATE_DIR: ClassVar[str] = _STATE_DIR

    # playbook name -> config seed filename. Mirrors the seed_playbook_* ->
    # playbook_* map in the agent HOCONs' state_read/state_write config.
    PLAYBOOKS: ClassVar[dict[str, str]] = {
        "playbook_coordinator": "seed_playbook_coordinator.md",
        "playbook_rides": "seed_playbook_rides.md",
        "playbook_shops": "seed_playbook_shops.md",
        "playbook_staff": "seed_playbook_staff.md",
        "playbook_survey": "seed_playbook_survey.md",
        "playbook_research": "seed_playbook_research.md",
        "playbook_layout": "seed_playbook_layout.md",
    }

    # The solo arm's single merged playbook: seed_playbook_all.md -> playbook_all.md.
    # It sits in the same seed dir as the seven; the arm is told which layout it
    # is by MAPS_MERGED_CONTEXT, never by what happens to be on disk.
    MERGED_SEED: ClassVar[str] = "seed_playbook_all.md"
    MERGED: ClassVar[bool] = _MERGED
    USE_LAST_REWARD: ClassVar[bool] = _USE_LAST_REWARD

    # State files the existing planner/watcher trial flow reads every episode.
    # Create-if-absent only so accumulated content is never clobbered.
    ENSURED_STATE_FILES: ClassVar[tuple[str, ...]] = (
        "trial_strategies.md",
        "trial_strategies_criteria.md",
        "trial_strategies_outcome.md",
        "last_reward.md",
        "episode_checklist.md",
    )

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        """
        :param args: dict with optional key
            - ``overwrite`` (bool, default False): reset existing playbooks
              to their config seed. False only fills missing/empty ones.
        :param sly_data: ignored.
        :return: dict ``{"status", "seeded", "skipped", "errors"}``.
        """
        del sly_data
        overwrite = bool(args.get("overwrite", False))

        seeded: list[str] = []
        skipped: list[str] = []
        errors: list[str] = []

        # The solo arm lays down the checked-in merged playbook instead of the
        # seven. No runner generates or rewrites that frozen source.
        playbooks = {"playbook_all": self.MERGED_SEED} if self.MERGED else self.PLAYBOOKS

        name: Any
        seed_file: Any
        for name, seed_file in playbooks.items():
            target = os.path.join(self.STATE_DIR, f"{name}.md")
            if not overwrite and os.path.exists(target) and os.path.getsize(target) > 0:
                skipped.append(name)
                continue
            source = os.path.join(self.SEED_DIR, seed_file)
            if not os.path.exists(source):
                errors.append(f"{name}: seed not found at {source}")
                continue
            body = FileIO.read_text(source)
            write_err = FileIO.write_guarded(target, body, self.logger)
            if write_err is not None:
                errors.append(f"{name}: {write_err}")
                continue
            seeded.append(name)

        # Ensure these exist so the consultant networks' state_read never errors
        # on a missing file. Create-if-absent only: an existing file (with
        # accumulated cross-run content) is left as-is regardless of
        # ``overwrite`` — those lessons must survive a fresh run.
        ledgers_created: list[str] = []
        fname: Any
        ensured_state_files = tuple(
            fname for fname in self.ENSURED_STATE_FILES if self.USE_LAST_REWARD or fname != "last_reward.md"
        )
        for fname in ensured_state_files:
            target = os.path.join(self.STATE_DIR, fname)
            if os.path.exists(target):
                continue
            # last_reward is read as "cumulative_reward: <N>"; seed it at 0 so the
            # first close-out computes a real delta instead of parsing an empty file.
            if fname == "last_reward.md":
                body = "cumulative_reward: 0\n"
            else:
                body = ""
            write_err = FileIO.write_guarded(target, body, self.logger)
            if write_err is not None:
                errors.append(f"{fname}: {write_err}")
                continue
            ledgers_created.append(fname)

        return {
            "status": "ok",
            "seeded": seeded,
            "skipped": skipped,
            "errors": errors,
            "trial_ledgers_created": ledgers_created,
        }

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        """Delegate to the synchronous invoke."""
        return self.invoke(args, sly_data)
