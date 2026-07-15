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


class SeedPlaybooks(CodedTool):
    """Copy config strategy seeds into the working playbook files."""

    SEED_DIR: ClassVar[str] = "coded_tools/config_files"
    STATE_DIR: ClassVar[str] = "coded_tools/state"

    # playbook name -> config seed filename. Mirrors the seed_playbook_* ->
    # playbook_* map in the agent HOCONs' state_read/state_write config.
    PLAYBOOKS: ClassVar[dict[str, str]] = {
        "playbook_coordinator": "coordinator_strategy.md",
        "playbook_rides":       "rides_strategy.md",
        "playbook_shops":       "shops_strategy.md",
        "playbook_staff":       "staff_strategy.md",
        "playbook_survey":      "survey_strategy.md",
        "playbook_research":    "research_strategy.md",
        "playbook_layout":      "layout_strategy.md",
    }

    # Trial-ledger files the consultant networks read via state_read every
    # episode. Unlike the playbooks these are NOT seeded from config — they
    # accumulate trial state across runs — but state_read errors on a missing
    # file, so a brand-new run/state dir leaves the analyzers reading a file
    # that does not exist yet (the macro close-out then errors with
    # "trial_strategies_outcome.md missing"). Ensure each one EXISTS (empty),
    # creating it only when absent so accumulated content is never clobbered.
    TRIAL_LEDGERS: ClassVar[tuple[str, ...]] = (
        "trial_strategies.md",
        "trial_strategies_criteria.md",
        "trial_strategies_outcome.md",
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

        for name, seed_file in self.PLAYBOOKS.items():
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

        # Ensure the trial-ledger files exist so the consultant networks'
        # state_read never errors on a missing file. Create-if-absent only:
        # an existing ledger (with accumulated cross-run content) is left as-is
        # regardless of ``overwrite`` — those lessons must survive a fresh run.
        ledgers_created: list[str] = []
        for fname in self.TRIAL_LEDGERS:
            target = os.path.join(self.STATE_DIR, fname)
            if os.path.exists(target):
                continue
            write_err = FileIO.write_guarded(target, "", self.logger)
            if write_err is not None:
                errors.append(f"{fname}: {write_err}")
                continue
            ledgers_created.append(fname)

        return {"status": "ok", "seeded": seeded, "skipped": skipped,
                "errors": errors, "trial_ledgers_created": ledgers_created}

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        """Delegate to the synchronous invoke."""
        return self.invoke(args, sly_data)
