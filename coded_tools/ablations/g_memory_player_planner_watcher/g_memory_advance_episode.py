"""Commit each completed MAPS episode to the actual upstream GMemory class."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from openai import OpenAIError

from coded_tools.ablations.g_memory_player_planner_watcher.g_memory_backend import GMemoryBackend
from coded_tools.ablations.g_memory_player_planner_watcher.g_memory_store import GMemoryStore
from coded_tools.advance_episode import AdvanceEpisode
from coded_tools.episode_telemetry import EpisodeTelemetry


class GMemoryAdvanceEpisode(AdvanceEpisode):
    """Save the full episode trajectory before the normal closeout receipt."""

    WRITE_LAST_REWARD = False

    def invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """Persist an upstream MASMessage, then commit the canonical receipt."""
        try:
            episode = int(args.get("episode"))
            final_reward = float(args.get("final_reward"))
        except (TypeError, ValueError):
            return "ERROR: episode and final_reward are required numbers"
        telemetry = EpisodeTelemetry().invoke({"episode": episode}, {})
        if not telemetry.get("exists"):
            return f"ERROR: cannot save episode {episode} to GMemory: {telemetry.get('error')}"
        store = GMemoryStore()
        plan = json.loads(store.get("plan_current") or "{}")
        plan["promoted_rules"] = {
            domain: json.loads(store.get(f"promoted_{domain}") or "[]")
            for domain in ("coordinator", "rides", "shops", "staff", "research", "layout", "survey")
        }
        plan["suppressed_rules"] = {
            domain: json.loads(store.get(f"suppressed_{domain}") or "[]")
            for domain in ("coordinator", "rides", "shops", "staff", "research", "layout", "survey")
        }
        interactions = store.interactions(episode)
        try:
            saved = GMemoryBackend().add_episode(
                episode=episode,
                final_reward=final_reward,
                telemetry=telemetry,
                plan=plan,
                outcomes=store.outcomes(),
                interactions=interactions,
            )
        except (RuntimeError, ValueError, OSError, ImportError, OpenAIError) as error:
            return f"ERROR: could not save episode to upstream GMemory: {error}"
        store.put("upstream_episode_count", str(episode + 1))
        store.commit_interactions(episode, [int(event.get("event_id")) for event in interactions])
        result = super().invoke(args, sly_data)
        if isinstance(result, str):
            return result
        result["g_memory"] = saved
        return result

    async def async_invoke(self, args: dict[str, Any], sly_data: dict[str, Any]) -> dict[str, Any] | str:
        """Execute the same closeout for asynchronous tool calls."""
        return await asyncio.to_thread(self.invoke, args, sly_data)
