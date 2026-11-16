"""Read the live plan and upstream recall without runtime Markdown files."""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

from coded_tools.ablations.g_memory_player_planner_watcher.g_memory_backend import GMemoryBackend
from coded_tools.ablations.g_memory_player_planner_watcher.g_memory_store import GMemoryStore
from coded_tools.name_map import NameMap
from coded_tools.state_read import StateRead


class GMemoryStateRead(StateRead):
    """Serve logical playbooks, checklist, and outcomes from GMemory state."""

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """Resolve one logical name and append relevant upstream memories."""
        requested = args.get("name")
        name_map = args.get("name_map")
        canonical = NameMap.resolve_alias(requested, name_map) if isinstance(name_map, dict) else requested
        validated = {**args, "name": canonical}
        error = NameMap.validate(validated)
        if error:
            return error
        if not isinstance(canonical, str):
            return "ERROR: name must be a string"
        if canonical.startswith("playbook_"):
            return self._playbook(canonical)
        if canonical == "episode_checklist":
            return self._response(canonical, GMemoryStore().get("episode_checklist") or "")
        if canonical == "trial_strategies_outcome":
            return self._outcomes()
        return super().invoke(validated, sly_data)

    def _playbook(self, name: str) -> dict[str, Any]:
        """Compose the baseline, current plan, promotions, and GMemory recall."""
        domain = name.removeprefix("playbook_")
        store = GMemoryStore()
        baseline = store.get(f"baseline_{domain}") or ""
        strategy = store.get(f"strategy_{domain}") or ""
        suppressed = json.loads(store.get(f"suppressed_{domain}") or "[]")
        baseline = "\n".join(line for line in baseline.splitlines() if line not in suppressed)
        promoted = json.loads(store.get(f"promoted_{domain}") or "[]")
        content = f"## Current strategy\n{strategy}\n\n{baseline}".strip()
        if promoted:
            content += "\n\n## Confirmed strategies\n" + "\n".join(f"- {item}" for item in promoted)
        recall = self._recall(f"{domain} MAPS park strategy {strategy}", store)
        if recall:
            content += "\n\n## GMemory recalled experience\n" + recall
        return self._response(name, content)

    def _outcomes(self) -> dict[str, Any]:
        """Expose verdicts and prior task lessons for the planner."""
        store = GMemoryStore()
        outcomes = store.outcomes()
        content = "\n".join(json.dumps(row, sort_keys=True) for row in outcomes)
        recall = self._recall("MAPS park strategy outcomes and failed approaches", store)
        if recall:
            content += "\n\n## GMemory recalled experience\n" + recall
        return self._response("trial_strategies_outcome", content.strip())

    @staticmethod
    def _recall(query: str, store: GMemoryStore) -> str:
        """Query upstream GMemory only after a completed task has been saved."""
        revision = store.get("upstream_episode_count")
        if not revision:
            return ""
        cache_key = "recall:" + revision + ":" + hashlib.sha256(query.encode("utf-8")).hexdigest()
        cached = store.get(cache_key)
        if cached is not None:
            return cached
        recalled = GMemoryBackend().retrieve(query)
        parts = [f"Successful: {item}" for item in recalled.get("successful", [])]
        parts.extend(f"Failed: {item}" for item in recalled.get("failed", []))
        parts.extend(f"Insight: {item}" for item in recalled.get("insights", []))
        rendered = "\n".join(parts)
        store.put(cache_key, rendered)
        return rendered

    @staticmethod
    def _response(name: str, content: str) -> dict[str, Any]:
        """Keep the canonical StateRead response shape."""
        return {
            "status": "ok",
            "name": name,
            "file_path": f"gmemory:{name}",
            "content": content,
            "line_count": len(content.splitlines()),
            "truncated": False,
        }

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """Execute the same state lookup for asynchronous tool calls."""
        return await asyncio.to_thread(self.invoke, args, sly_data)
