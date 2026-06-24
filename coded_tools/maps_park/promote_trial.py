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
PromoteTrial: apply ONE confirmed trial's edit to its playbook, tagging the
new line '(learned ep<N>)'. The curator DECIDES which trials are confirmed
(judgment); this tool performs the deterministic playbook edit.

  - add_line: append the line at the end (section 'end'/'new'/empty), or
    insert it immediately after the named section header line.
  - replace_line: replace the unique occurrence of find_text with the new line.

When a live-playbook edit succeeds, the learned line is ALSO mirrored into the
read-only config seed (config_files/<domain>_strategy.md) under a dedicated
"## Learned rules" section, leaving the hand-authored baseline above it intact.
This is what carries confirmed rules across fresh, from-scratch runs (where
SeedPlaybooks resets each working playbook to its seed): the next run starts
from baseline + everything learned so far. The mirror is best-effort — a seed
that is missing or already contains the exact line never fails the promotion.

Returns {action_taken, playbook, line, seed_mirror} where action_taken is one of:
  promoted, skipped_section_missing, skipped_not_found, skipped_ambiguous,
  skipped_playbook_missing; and seed_mirror is one of:
  appended, duplicate_skipped, seed_missing, not_attempted (when the live edit
  did not promote).
"""

from __future__ import annotations

import os
from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool


class PromoteTrial(CodedTool):
    """Apply a confirmed trial's add_line/replace_line edit to playbook_<domain>.md."""

    STATE_DIR: ClassVar[str] = "coded_tools/maps_park/state"
    SEED_DIR: ClassVar[str] = "coded_tools/maps_park/config_files"
    # domain -> config seed filename. Mirrors SeedPlaybooks.PLAYBOOKS;
    # every domain maps to <domain>_strategy.md.
    SEED_FILES: ClassVar[dict[str, str]] = {
        "coordinator": "coordinator_strategy.md",
        "rides":       "rides_strategy.md",
        "shops":       "shops_strategy.md",
        "staff":       "staff_strategy.md",
        "research":    "research_strategy.md",
        "layout":      "layout_strategy.md",
    }
    # Header under which mirrored learned rules accumulate in the seed file.
    LEARNED_SECTION: ClassVar[str] = "## Learned rules (promoted from prior runs)"
    DOMAINS: ClassVar[frozenset[str]] = frozenset(SEED_FILES)
    END_SECTIONS: ClassVar[frozenset[str]] = frozenset({"", "end", "new"})

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """
        :param args: domain, edit_type ('add_line'|'replace_line'), new_text,
            episode (int), section (for add_line), find_text (for replace_line).
        :return: {action_taken, playbook, line} or "ERROR: ...".
        """
        del sly_data
        domain = str(args.get("domain", "")).strip().lower()
        if domain not in self.DOMAINS:
            return f"ERROR: domain must be one of {sorted(self.DOMAINS)}"
        edit_type = str(args.get("edit_type", "")).strip()
        if edit_type not in ("add_line", "replace_line"):
            return "ERROR: edit_type must be 'add_line' or 'replace_line'"
        new_text = str(args.get("new_text", "")).strip()
        if not new_text:
            return "ERROR: new_text is required and must be non-empty"
        try:
            episode = int(args.get("episode"))
        except (TypeError, ValueError):
            return "ERROR: episode is required and must be an integer"

        playbook = f"playbook_{domain}"
        path = os.path.join(self.STATE_DIR, f"{playbook}.md")
        if not os.path.exists(path):
            return {
                "action_taken": "skipped_playbook_missing",
                "playbook": playbook,
                "line": "",
                "seed_mirror": "not_attempted",
            }

        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError as err:
            return f"ERROR: could not read {path}: {err}"

        final_line = f"{new_text} (learned ep{episode})"

        if edit_type == "add_line":
            section = str(args.get("section", "")).strip()
            if section.lower() in self.END_SECTIONS:
                new_body = text.rstrip("\n") + "\n" + final_line + "\n"
                action = "promoted"
            else:
                anchor = section + "\n"
                if anchor in text:
                    new_body = text.replace(anchor, anchor + final_line + "\n", 1)
                    action = "promoted"
                else:
                    return {
                        "action_taken": "skipped_section_missing",
                        "playbook": playbook,
                        "line": final_line,
                        "seed_mirror": "not_attempted",
                    }
        else:  # replace_line
            find_text = str(args.get("find_text", "")).strip()
            if not find_text:
                return "ERROR: replace_line requires find_text"
            occurrences = text.count(find_text)
            if occurrences == 0:
                return {
                    "action_taken": "skipped_not_found",
                    "playbook": playbook,
                    "line": final_line,
                    "seed_mirror": "not_attempted",
                }
            if occurrences > 1:
                return {
                    "action_taken": "skipped_ambiguous",
                    "playbook": playbook,
                    "line": final_line,
                    "seed_mirror": "not_attempted",
                }
            new_body = text.replace(find_text, final_line, 1)
            action = "promoted"

        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(new_body)
        except OSError as err:
            return f"ERROR: could not write {path}: {err}"

        seed_mirror = self._mirror_to_seed(domain, final_line)
        return {
            "action_taken": action,
            "playbook": playbook,
            "line": final_line,
            "seed_mirror": seed_mirror,
        }

    def _mirror_to_seed(self, domain: str, final_line: str) -> str:
        """Append the learned line to the config seed under LEARNED_SECTION.

        Best-effort: a missing seed or a duplicate line is reported, never raised,
        so a seed problem cannot undo the (already-written) live playbook edit.
        :return: 'appended' | 'duplicate_skipped' | 'seed_missing'.
        """
        seed_path = os.path.join(self.SEED_DIR, self.SEED_FILES[domain])
        if not os.path.exists(seed_path):
            return "seed_missing"
        try:
            with open(seed_path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            return "seed_missing"

        # Dedup on the exact learned line so repeated promotions don't bloat the seed.
        if final_line in text:
            return "duplicate_skipped"

        anchor = self.LEARNED_SECTION + "\n"
        if anchor in text:
            # Insert directly beneath the existing section header.
            new_text = text.replace(anchor, anchor + final_line + "\n", 1)
        else:
            # Create the section once, at the end, after the hand-authored baseline.
            new_text = text.rstrip("\n") + "\n\n" + self.LEARNED_SECTION + "\n" + final_line + "\n"

        try:
            with open(seed_path, "w", encoding="utf-8") as fh:
                fh.write(new_text)
        except OSError:
            return "seed_missing"
        return "appended"

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return self.invoke(args, sly_data)
