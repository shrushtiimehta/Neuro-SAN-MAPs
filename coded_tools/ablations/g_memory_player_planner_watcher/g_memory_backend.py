"""Adapter to the pinned upstream GMemory implementation.

The upstream mas.llm module prints API keys when imported. We substitute its
type-only interface before importing GMemory, then supply our safe callable.
"""

from __future__ import annotations

import importlib
import json
import os
import sys
import types
from pathlib import Path
from typing import Any

from langchain_core.documents import Document

from coded_tools.ablations.g_memory_player_planner_watcher.g_memory_llm import GMemoryLLM
from coded_tools.ablations.g_memory_player_planner_watcher.g_memory_message import GMemoryMessage
from coded_tools.state_dir import STATE_DIR


class GMemoryBackend:
    """Persist and retrieve completed MAPS trajectories with upstream GMemory."""

    UPSTREAM_COMMIT = "7b581c51d993bd600df14691d101d7e601040cc6"

    def __init__(
        self, embedding_func: Any | None = None, llm_model: Any | None = None, working_dir: str | None = None
    ) -> None:
        repository = Path(os.environ.get("MAPS_GMEMORY_REPO", str(Path.home() / "GMemory-upstream")))
        source = repository / "mas" / "memory" / "mas_memory" / "GMemory.py"
        if not source.is_file():
            raise RuntimeError(f"upstream GMemory source is missing: {source}")
        if str(repository) not in sys.path:
            sys.path.insert(0, str(repository))
        self._prepare_safe_import(repository)
        try:
            upstream = importlib.import_module("mas.memory.mas_memory.GMemory")
            common = importlib.import_module("mas.memory.common")
            utils = importlib.import_module("mas.utils")
        except ImportError as error:
            raise RuntimeError(f"GMemory optional dependencies are missing: {error}") from error
        self.message_type = common.MASMessage
        self.agent_message_type = common.AgentMessage
        self.memory = upstream.GMemory(
            namespace="maps_episodes",
            global_config={
                "working_dir": working_dir or str(Path(STATE_DIR) / "g_memory_upstream"),
                "start_insights_threshold": 5,
                "rounds_per_insights": 5,
                "insights_point_num": 5,
                "hop": 1,
            },
            llm_model=llm_model or GMemoryLLM(),
            embedding_func=embedding_func or utils.EmbeddingFunc(),
        )

    @staticmethod
    def _prepare_safe_import(repository: Path) -> None:
        """Avoid upstream import side effects and its old Document path."""
        for name, directory in (
            ("mas", repository / "mas"),
            ("mas.memory", repository / "mas" / "memory"),
            ("mas.memory.mas_memory", repository / "mas" / "memory" / "mas_memory"),
        ):
            if name not in sys.modules:
                package = types.ModuleType(name)
                package.__path__ = [str(directory)]
                sys.modules[name] = package
        if "mas.llm" not in sys.modules:
            safe_llm = types.ModuleType("mas.llm")
            safe_llm.Message = GMemoryMessage
            safe_llm.LLMCallable = Any
            sys.modules["mas.llm"] = safe_llm
        if "langchain.docstore.document" not in sys.modules:
            docstore = types.ModuleType("langchain.docstore")
            document = types.ModuleType("langchain.docstore.document")
            document.Document = Document
            sys.modules["langchain.docstore"] = docstore
            sys.modules["langchain.docstore.document"] = document

    # The completed-task boundary carries all evidence tiers in one upstream call.
    # pylint: disable=too-many-arguments,too-many-locals
    def add_episode(
        self,
        *,
        episode: int,
        final_reward: float,
        telemetry: dict[str, Any],
        plan: dict[str, Any],
        outcomes: list[dict[str, Any]],
        interactions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Turn one finished episode into GMemory's MASMessage and save it."""
        if self.memory.memory_size and any(
            doc.get("task_main", "").endswith(f"episode {episode}")
            for doc in self.memory.main_memory.get().get("metadatas", [])
            if isinstance(doc, dict)
        ):
            return {"episode": episode, "already_saved": True, "backend": "upstream-gmemory"}
        rollup = telemetry.get("rollup", {})
        coordination = self._coordination_summary(interactions or [])
        description = json.dumps(
            {
                "objective": "Build the most valuable profitable MAPS park in 100 actions",
                "final_reward": final_reward,
                "plan": plan,
                "rollup": rollup,
                "trial_outcomes": [item for item in outcomes if item.get("episode") == episode],
                "agent_coordination": coordination,
            },
            separators=(",", ":"),
            default=str,
        )
        message = self.message_type(
            task_main=f"MAPS park optimization episode {episode}",
            task_description=description,
            label=final_reward >= 350000,
        )
        message.add_extra_field("agent_coordination", coordination)
        self._attach_interactions(message, interactions or [], coordination)
        steps = telemetry.get("steps", [])
        if isinstance(steps, list):
            selected = steps[:: max(1, len(steps) // 12)]
            if steps and selected[-1] is not steps[-1]:
                selected.append(steps[-1])
            for step in selected:
                if not isinstance(step, dict):
                    continue
                action = json.dumps({key: step.get(key) for key in ("step", "action", "type", "subtype", "price")})
                observation = json.dumps(
                    {key: step.get(key) for key in ("reward", "cash", "park_value", "park_rating", "daily_profit")}
                )
                message.add_message_to_current_state(self.agent_message_type(agent_name="player", message=action), [])
                message.move_state(action, observation)
        self.memory.add_memory(message)
        return {
            "episode": episode,
            "already_saved": False,
            "backend": "upstream-gmemory",
            "memory_size": self.memory.memory_size,
            "agent_interactions": len(interactions or []),
        }

    # Graph node and edge identities must be built in one ordered pass.
    # pylint: disable=too-many-locals
    def _attach_interactions(self, message: Any, interactions: list[dict[str, Any]], summary: str) -> None:
        """Build GMemory's interaction graph with real delegation and reply edges."""
        if not interactions:
            return
        stride = max(1, (len(interactions) + 279) // 280)
        selected = {int(event.get("event_id", index)): event for index, event in enumerate(interactions[::stride])}
        for event in interactions:
            if event.get("chat_kind") in {"episode_start", "episode_end", "periodic"}:
                selected[int(event.get("event_id", 0))] = event
        last_node: dict[str, str] = {}
        pending_delegate: dict[str, str] = {}
        last_advice: str | None = None
        for event in sorted(selected.values(), key=lambda item: int(item.get("event_id", 0))):
            agent = str(event.get("agent_name", ""))
            if not agent:
                continue
            parent = str(event.get("parent_name", ""))
            target = str(event.get("target_name", ""))
            leaf = agent.rsplit(".", 1)[-1]
            upstream = [
                node
                for node in (
                    pending_delegate.pop(leaf, None),
                    last_node.get(parent),
                    last_node.get(agent),
                    last_advice if leaf == "strategy_coordinator" else None,
                )
                if node
            ]
            upstream = list(dict.fromkeys(upstream))
            kind = str(event.get("message_type", ""))
            content = str(event.get("content", ""))[:1200]
            agent_message = self.agent_message_type(
                agent_name=agent,
                user_instruction=content if kind == "HUMAN" else None,
                message=content if kind != "HUMAN" else None,
                extra_fields={
                    "turn": event.get("turn"),
                    "chat_kind": event.get("chat_kind"),
                    "message_type": kind,
                    "target_agent": target,
                },
            )
            node = message.add_message_to_current_state(agent_message, upstream)
            last_node[agent] = node
            if kind == "AGENT" and target:
                pending_delegate[target] = node
            if kind == "AI" and event.get("chat_kind") in {"episode_start", "periodic"}:
                last_advice = node
        message.move_state("multi-agent coordination", summary or "Agent roles and delegations recorded in graph")

    @staticmethod
    def _coordination_summary(interactions: list[dict[str, Any]]) -> str:
        """Select bounded planner, watcher, and specialist decisions for retrieval."""
        selected = [event for event in interactions if event.get("message_type") in {"AI", "AGENT"}]
        if not selected:
            return ""
        priority = [event for event in selected if event.get("chat_kind") != "player"]
        player = [event for event in selected if event.get("chat_kind") == "player"]
        stride = max(1, len(player) // 18)
        priority_stride = max(1, (len(priority) + 11) // 12)
        chosen = priority[::priority_stride][:12] + player[::stride][:18]
        lines = []
        for event in sorted(chosen, key=lambda item: int(item.get("event_id", 0))):
            agent = str(event.get("agent_name", ""))
            target = str(event.get("target_name", ""))
            relationship = f"{agent}->{target}" if target else agent
            lines.append(f"turn {event.get('turn')}: {relationship}: {str(event.get('content', ''))[:280]}")
        return "\n".join(lines)[:9000]

    def retrieve(self, query: str) -> dict[str, Any]:
        """Return GMemory's successful, failed, and insight tiers."""
        if self.memory.memory_size == 0:
            return {"successful": [], "failed": [], "insights": []}
        successes, failures, insights = self.memory.retrieve_memory(
            query_task=query, successful_topk=2, failed_topk=1, insight_topk=8, threshold=0.0
        )
        return {
            "successful": [self._render_task(task) for task in successes],
            "failed": [self._render_task(task) for task in failures],
            "insights": [str(insight) for insight in insights],
        }

    @staticmethod
    def _render_task(task: Any) -> str:
        """Bound retrieved trajectories before they enter a player prompt."""
        key_steps = task.get_extra_field("key_steps") or ""
        failure = task.get_extra_field("fail_reason") or ""
        coordination = task.get_extra_field("agent_coordination") or ""
        return f"{task.task_main}: {key_steps} {failure}\nAgent coordination: {coordination}"[:6000]
