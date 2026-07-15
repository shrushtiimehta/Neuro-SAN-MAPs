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
WriteEpisodePlan: the deterministic write side of the macro start-of-episode
pass. The macro analyzes the best + last episodes and produces these artifacts;
this tool persists them so the game-runner network can read them on turn 1:

  1. episode_checklist.md  — the turn-phased plan, one literal
     "turns A-B: <goal>" line per item, consumed VERBATIM by park_director
     (it seeds these straight into create_checklist; no re-derivation).
  2. The STRATEGY SUMMARY block inside playbook_coordinator.md — a freeform
     "best way to go about things" brief. It is NOT a separate file: it is
     written into the coordinator's own playbook (which strategy_coordinator
     already reads every turn) between fixed BEGIN/END markers at the TOP of
     the file, and is REPLACED WHOLESALE every episode.
  3. (optional) Per-domain PLAYBOOK SUMMARIES — a short 2-3 line summary for
     each specialist playbook (rides/shops/staff/research/layout/survey), written
     between PLAYBOOK_SUMMARY markers at the TOP of playbook_<domain>.md, the
     same way the coordinator summary is handled. Each specialist reads its own
     summary every consultation. Replaced wholesale every episode.

For every marked block the hand-authored baseline and the '## Learned rules'
below it are left untouched — only the marked block is rewritten — so promotion/
demotion of learned rules and the per-episode summaries never collide.

Returns {checklist_items_written, strategy_summary_written, checklist_path,
playbook_coordinator_path, summary_action, playbook_summaries_written} where
summary_action is 'replaced' (markers existed) or 'inserted' (markers added at
top), and playbook_summaries_written is the list of domains whose summary block
was written this call.
"""

from __future__ import annotations

import json
import os
from typing import Any
from typing import ClassVar

from neuro_san.interfaces.coded_tool import CodedTool


class WriteEpisodePlan(CodedTool):
    """Persist the episode checklist plus the per-episode coordinator and specialist summaries."""

    STATE_DIR: ClassVar[str] = "coded_tools/state"
    CHECKLIST_FILE: ClassVar[str] = "episode_checklist.md"
    # Raw plan args, dumped on every write so the runner's champion mechanism
    # (coded_tools/champion_plan.py: promote on a clean run, restore on a doom)
    # can re-apply this exact plan later.
    PLAN_CURRENT_FILE: ClassVar[str] = "plan_current.json"
    CHECKLIST_TITLE: ClassVar[str] = "# Episode Strategy Plan"
    PLAYBOOK_COORDINATOR_FILE: ClassVar[str] = "playbook_coordinator.md"

    # The coordinator strategy summary lives between these markers inside
    # playbook_coordinator.md so it can be replaced every episode.
    SUMMARY_BEGIN: ClassVar[str] = "<!-- STRATEGY_SUMMARY:BEGIN -->"
    SUMMARY_END: ClassVar[str] = "<!-- STRATEGY_SUMMARY:END -->"
    SUMMARY_HEADER: ClassVar[str] = (
        "## Current strategy summary (regenerated every episode — top priority this run)"
    )

    # Each specialist playbook carries its own per-episode summary between these
    # markers at the top of playbook_<domain>.md.
    PLAYBOOK_SUMMARY_BEGIN: ClassVar[str] = "<!-- PLAYBOOK_SUMMARY:BEGIN -->"
    PLAYBOOK_SUMMARY_END: ClassVar[str] = "<!-- PLAYBOOK_SUMMARY:END -->"
    PLAYBOOK_SUMMARY_HEADER: ClassVar[str] = "## Summary (regenerated every episode)"

    # domain -> its working playbook file. Mirrors SeedPlaybooks.PLAYBOOKS.
    DOMAIN_PLAYBOOKS: ClassVar[dict[str, str]] = {
        "rides":    "playbook_rides.md",
        "shops":    "playbook_shops.md",
        "staff":    "playbook_staff.md",
        "research": "playbook_research.md",
        "layout":   "playbook_layout.md",
        "survey":   "playbook_survey.md",
    }

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """
        :param args:
            checklist_items: list of "turns A-B: <goal>" strings (the full
                100-turn plan, ordered by turn). Required, non-empty.
            strategy_summary: freeform prose brief written into
                playbook_coordinator.md for strategy_coordinator. Required.
            playbook_summaries: optional dict {domain: summary_text} for any of
                rides/shops/staff/research/layout/survey. Each is written between
                PLAYBOOK_SUMMARY markers at the top of playbook_<domain>.md.
                Unknown domains and empty summaries are skipped.
        :return: result dict or "ERROR: ...".
        """
        del sly_data

        raw_items = args.get("checklist_items")
        if isinstance(raw_items, str):
            # Tolerate a newline-delimited blob if the caller didn't pass a list.
            raw_items = raw_items.splitlines()
        if not isinstance(raw_items, list):
            return "ERROR: checklist_items is required and must be a list of strings"
        items = [str(it).strip() for it in raw_items if str(it).strip()]
        if not items:
            return "ERROR: checklist_items must contain at least one non-empty line"

        strategy_summary = str(args.get("strategy_summary", "")).strip()
        if not strategy_summary:
            return "ERROR: strategy_summary is required and must be non-empty"

        try:
            os.makedirs(self.STATE_DIR, exist_ok=True)
        except OSError as err:
            return f"ERROR: could not create {self.STATE_DIR}: {err}"

        # 1. Checklist file (consumed verbatim by park_director).
        checklist_path = os.path.join(self.STATE_DIR, self.CHECKLIST_FILE)
        checklist_body = self.CHECKLIST_TITLE + "\n" + "\n".join(items) + "\n"
        try:
            with open(checklist_path, "w", encoding="utf-8") as fh:
                fh.write(checklist_body)
        except OSError as err:
            return f"ERROR: could not write {checklist_path}: {err}"

        # 2. Strategy summary block inside playbook_coordinator.md.
        coord_path = os.path.join(self.STATE_DIR, self.PLAYBOOK_COORDINATOR_FILE)
        coord_block = self._build_block(self.SUMMARY_BEGIN, self.SUMMARY_HEADER,
                                        strategy_summary, self.SUMMARY_END)
        summary_action, err = self._write_marked_block(
            coord_path, self.SUMMARY_BEGIN, self.SUMMARY_END, coord_block
        )
        if err:
            return err

        # 3. Optional per-domain specialist summaries.
        playbook_summaries = args.get("playbook_summaries") or {}
        summaries_written: list[str] = []
        if isinstance(playbook_summaries, dict):
            for domain, filename in self.DOMAIN_PLAYBOOKS.items():
                text = str(playbook_summaries.get(domain, "")).strip()
                if not text:
                    continue
                path = os.path.join(self.STATE_DIR, filename)
                block = self._build_block(self.PLAYBOOK_SUMMARY_BEGIN,
                                          self.PLAYBOOK_SUMMARY_HEADER, text,
                                          self.PLAYBOOK_SUMMARY_END)
                _, derr = self._write_marked_block(
                    path, self.PLAYBOOK_SUMMARY_BEGIN, self.PLAYBOOK_SUMMARY_END, block
                )
                if derr:
                    return derr
                summaries_written.append(domain)

        # Snapshot the raw plan so the champion mechanism can restore it verbatim.
        plan_snapshot = self._snapshot_plan(items, strategy_summary, playbook_summaries)

        return {
            "checklist_items_written": len(items),
            "strategy_summary_written": True,
            "checklist_path": checklist_path,
            "playbook_coordinator_path": coord_path,
            "summary_action": summary_action,
            "playbook_summaries_written": summaries_written,
            "plan_snapshot_written": plan_snapshot,
        }

    def _snapshot_plan(self, items: list, strategy_summary: str, playbook_summaries: Any) -> bool:
        """Dump the plan args to plan_current.json (best-effort). The runner's
        champion_plan promotes this to plan_last_good on a clean run and
        re-applies it after a doom."""
        summaries = {}
        if hasattr(playbook_summaries, "items"):
            summaries = {str(k): str(v) for k, v in playbook_summaries.items()}
        snapshot = {
            "checklist_items": list(items),
            "strategy_summary": strategy_summary,
            "playbook_summaries": summaries,
        }
        try:
            with open(os.path.join(self.STATE_DIR, self.PLAN_CURRENT_FILE), "w", encoding="utf-8") as fh:
                json.dump(snapshot, fh, indent=2)
            return True
        except OSError:
            return False

    def _build_block(self, begin: str, header: str, body: str, end: str) -> str:
        """The full marked block, header + body, ready to embed."""
        return (
            f"{begin}\n"
            f"{header}\n"
            f"{body.rstrip(chr(10))}\n"
            f"{end}\n"
        )

    def _write_marked_block(
        self, path: str, begin: str, end: str, block: str
    ) -> tuple[str, str | None]:
        """Replace the begin..end marked block in `path`, or insert it at the top
        if no markers exist yet. Returns (action, error_or_None).

        SeedPlaybooks resets a playbook to its seed on a fresh run; as long as the
        seed carries the markers they persist and the block is replaced in place.
        If a playbook somehow lacks markers, the block is prepended at the top.
        """
        existing = ""
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    existing = fh.read()
            except OSError as err:
                return "", f"ERROR: could not read {path}: {err}"

        begin_idx = existing.find(begin)
        end_idx = existing.find(end)
        if begin_idx != -1 and end_idx != -1 and end_idx > begin_idx:
            # Replace the existing block (inclusive of both markers).
            end_after = end_idx + len(end)
            new_text = existing[:begin_idx] + block.rstrip("\n") + existing[end_after:]
            action = "replaced"
        else:
            # Prepend the block at the top, then the existing content.
            new_text = block + "\n" + existing if existing else block
            action = "inserted"

        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(new_text)
        except OSError as err:
            return "", f"ERROR: could not write {path}: {err}"
        return action, None

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        return self.invoke(args, sly_data)
