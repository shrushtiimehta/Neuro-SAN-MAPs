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
PromoteTrial: the deterministic playbook editor. The curator/analyst DECIDES
what to change (judgment); this tool performs the file edit and mirrors it into
the config seed so it survives fresh runs.

  - add_line: append the line at the end (section 'end'/'new'/empty), or
    insert it immediately after the named section header line; tags it
    '(learned ep<N>)'.
  - replace_line: replace the unique occurrence of find_text with the new line
    (also tagged).
  - remove_line: DEMOTION — remove a previously-learned line so the loop can
    SELF-CORRECT a rule that was promoted on a lucky episode but correlates with
    regressions. SAFETY: only lines tagged '(learned ep<N>)' are removable, so
    the hand-authored baseline can never be deleted (worst case: a no-op
    skipped_not_learned). The same line is removed from the seed mirror too.
    Needs only find_text (a substring of the learned line); new_text/episode are
    ignored.

When a live-playbook edit succeeds, the learned line is ALSO mirrored into the
read-only config seed (config_files/<domain>_strategy.md) under its dedicated
"## Learned rules" section, leaving the hand-authored baseline above it intact.
This is what carries confirmed rules across fresh, from-scratch runs (where
SeedPlaybooks resets each working playbook to its seed): the next run starts
from baseline + everything learned so far. The mirror is APPEND-ONLY — the seed
must already carry the section header (all seeds are pre-seeded with it); the
code never creates it. Best-effort: a missing seed, missing section, or a line
already present never fails the promotion.

Returns {action_taken, playbook, line, seed_mirror} where action_taken is one of:
  promoted, skipped_section_missing, skipped_not_found, skipped_ambiguous,
  skipped_playbook_missing; and seed_mirror is one of:
  appended, duplicate_skipped, section_missing, seed_missing, not_attempted (when
  the live edit did not promote).
"""

from __future__ import annotations

import os
from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool


class PromoteTrial(CodedTool):
    """Apply a confirmed trial's add_line/replace_line edit to playbook_<domain>.md."""

    STATE_DIR: ClassVar[str] = "coded_tools/state"
    SEED_DIR: ClassVar[str] = "coded_tools/config_files"
    # domain -> config seed filename. Mirrors SeedPlaybooks.PLAYBOOKS;
    # every domain maps to <domain>_strategy.md.
    SEED_FILES: ClassVar[dict[str, str]] = {
        "coordinator": "coordinator_strategy.md",
        "rides":       "rides_strategy.md",
        "shops":       "shops_strategy.md",
        "staff":       "staff_strategy.md",
        "research":    "research_strategy.md",
        "layout":      "layout_strategy.md",
        "survey":      "survey_strategy.md",
    }
    # Header under which mirrored learned rules accumulate in the seed file.
    LEARNED_SECTION: ClassVar[str] = "## Learned rules (promoted from prior runs)"
    # Marker that tags a promoted line; remove_line only touches lines carrying
    # it, protecting the hand-authored baseline from demotion.
    LEARNED_MARKER: ClassVar[str] = "(learned ep"
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
        if edit_type not in ("add_line", "replace_line", "remove_line"):
            return "ERROR: edit_type must be 'add_line', 'replace_line', or 'remove_line'"
        # remove_line (demotion) needs only find_text; add/replace need new_text + episode.
        new_text = str(args.get("new_text", "")).strip()
        if edit_type != "remove_line" and not new_text:
            return "ERROR: new_text is required and must be non-empty"
        episode = None
        if edit_type != "remove_line":
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

        if edit_type == "remove_line":
            find_text = str(args.get("find_text", "")).strip()
            if not find_text:
                return "ERROR: remove_line requires find_text"
            return self._remove_line(domain, playbook, path, text, find_text)

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

    def _remove_line(
        self, domain: str, playbook: str, path: str, text: str, find_text: str
    ) -> dict[str, Any] | str:
        """Demotion: remove the unique learned line containing find_text from the
        playbook and its seed mirror. Only '(learned ep<N>)'-tagged lines qualify,
        so the hand-authored baseline is never removed.

        :return: {action_taken, playbook, line, seed_mirror}; action_taken is
            demoted / skipped_not_found / skipped_ambiguous / skipped_not_learned.
        """
        lines = text.splitlines()
        matched = [ln for ln in lines if find_text in ln]
        if not matched:
            return {"action_taken": "skipped_not_found", "playbook": playbook,
                    "line": "", "seed_mirror": "not_attempted"}
        if len(matched) > 1:
            return {"action_taken": "skipped_ambiguous", "playbook": playbook,
                    "line": "", "seed_mirror": "not_attempted"}
        target = matched[0]
        if self.LEARNED_MARKER not in target:
            # Baseline protection — never demote a hand-authored rule.
            return {"action_taken": "skipped_not_learned", "playbook": playbook,
                    "line": target, "seed_mirror": "not_attempted"}

        new_body = "\n".join(ln for ln in lines if ln != target)
        if new_body:
            new_body += "\n"
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(new_body)
        except OSError as err:
            return f"ERROR: could not write {path}: {err}"

        return {"action_taken": "demoted", "playbook": playbook,
                "line": target, "seed_mirror": self._remove_from_seed(domain, target)}

    def _remove_from_seed(self, domain: str, target_line: str) -> str:
        """Remove the same learned line from the config seed mirror. Best-effort.

        :return: 'removed' | 'not_found' | 'seed_missing'.
        """
        seed_path = os.path.join(self.SEED_DIR, self.SEED_FILES[domain])
        if not os.path.exists(seed_path):
            return "seed_missing"
        try:
            with open(seed_path, encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except OSError:
            return "seed_missing"
        if target_line not in lines:
            return "not_found"
        new_body = "\n".join(ln for ln in lines if ln != target_line)
        if new_body:
            new_body += "\n"
        try:
            with open(seed_path, "w", encoding="utf-8") as fh:
                fh.write(new_body)
        except OSError:
            return "seed_missing"
        return "removed"

    def _mirror_to_seed(self, domain: str, final_line: str) -> str:
        """Append the learned line to the config seed under LEARNED_SECTION.

        Append-only: the seed must already carry the LEARNED_SECTION header (all
        seeds are pre-seeded with it); this NEVER creates it. Best-effort — a
        missing seed, missing section, or duplicate line is reported, never raised,
        so a seed problem cannot undo the (already-written) live playbook edit.
        :return: 'appended' | 'duplicate_skipped' | 'section_missing' | 'seed_missing'.
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
        if anchor not in text:
            # Append-only: the seed must already carry the LEARNED_SECTION header
            # (all seeds are pre-seeded with it). Never create it here.
            return "section_missing"
        # Insert directly beneath the existing section header.
        new_text = text.replace(anchor, anchor + final_line + "\n", 1)

        try:
            with open(seed_path, "w", encoding="utf-8") as fh:
                fh.write(new_text)
        except OSError:
            return "seed_missing"
        return "appended"

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return self.invoke(args, sly_data)
