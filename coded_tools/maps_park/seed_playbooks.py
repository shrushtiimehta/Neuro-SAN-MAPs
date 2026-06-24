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

from coded_tools.common.file_io import FileIO


class SeedPlaybooks(CodedTool):
    """Copy config strategy seeds into the working playbook files."""

    SEED_DIR: ClassVar[str] = "coded_tools/maps_park/config_files"
    STATE_DIR: ClassVar[str] = "coded_tools/maps_park/state"

    # playbook name -> config seed filename. Mirrors the seed_playbook_* ->
    # playbook_* map in the agent HOCONs' state_read/state_write config.
    PLAYBOOKS: ClassVar[dict[str, str]] = {
        "playbook_coordinator": "coordinator_strategy.md",
        "playbook_rides":       "rides_strategy.md",
        "playbook_shops":       "shops_strategy.md",
        "playbook_staff":       "staff_strategy.md",
        "playbook_research":    "research_strategy.md",
        "playbook_layout":      "layout_strategy.md",
    }

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

        return {"status": "ok", "seeded": seeded, "skipped": skipped, "errors": errors}

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any]:
        """Delegate to the synchronous invoke."""
        return self.invoke(args, sly_data)
