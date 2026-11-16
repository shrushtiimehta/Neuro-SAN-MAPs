"""Save the unchanged planning payload in live GMemory state."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from coded_tools.ablations.g_memory_player_planner_watcher.g_memory_store import GMemoryStore
from coded_tools.episode_phases import validate_phase_items
from coded_tools.write_episode_plan import WriteEpisodePlan


class GMemoryWriteEpisodePlan(WriteEpisodePlan):
    """Validate the full checklist and domain strategies before replacing them."""

    # Preserve the canonical per-field retryable validation errors.
    # pylint: disable=too-many-return-statements
    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """Store the complete episode plan without creating plan or playbook files."""
        del sly_data
        raw_items = args.get("checklist_items")
        if isinstance(raw_items, str):
            raw_items = raw_items.splitlines()
        if not isinstance(raw_items, list):
            return f"{self.RETRYABLE_VALIDATION_ERROR} checklist_items is required and must be a list of strings"
        items = [str(item).strip() for item in raw_items if str(item).strip()]
        if not items:
            return f"{self.RETRYABLE_VALIDATION_ERROR} checklist_items must contain at least one non-empty line"
        error = validate_phase_items(items)
        if error:
            return f"{self.RETRYABLE_VALIDATION_ERROR} {error}"
        strategy, error = self._validated_strategy_text(args.get("strategy_summary"), "strategy_summary")
        if error:
            return error
        summaries = args.get("playbook_summaries")
        if not isinstance(summaries, dict):
            return f"{self.RETRYABLE_VALIDATION_ERROR} playbook_summaries is required"
        if set(summaries) != set(self.DOMAIN_PLAYBOOKS):
            return f"{self.RETRYABLE_VALIDATION_ERROR} playbook_summaries requires all six domains"
        checked: dict[str, str] = {}
        for domain in self.DOMAIN_PLAYBOOKS:
            text, error = self._validated_strategy_text(summaries.get(domain), f"playbook_summaries.{domain}")
            if error:
                return error
            checked[domain] = text
        plan = {"checklist_items": items, "strategy_summary": strategy, "playbook_summaries": checked}
        store = GMemoryStore()
        store.put("plan_current", json.dumps(plan))
        store.put("episode_checklist", "# Episode Strategy Plan\n" + "\n".join(items) + "\n")
        store.put("strategy_coordinator", strategy)
        for domain, text in checked.items():
            store.put(f"strategy_{domain}", text)
        return {
            "checklist_items_written": len(items),
            "strategy_summary_written": True,
            "strategy_written": True,
            "checklist_path": "gmemory:episode_checklist",
            "playbook_coordinator_path": "gmemory:playbook_coordinator",
            "summary_action": "replaced",
            "playbook_summaries_written": list(checked),
            "plan_snapshot_written": True,
        }

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """Execute the same plan validation for asynchronous tool calls."""
        return await asyncio.to_thread(self.invoke, args, sly_data)
