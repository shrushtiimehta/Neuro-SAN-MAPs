"""Capture live multi-agent exchanges from the Neuro SAN message stream."""

from __future__ import annotations

import json
import re
from typing import Any
from typing import ClassVar

from neuro_san.internals.journals.origination import Origination
from neuro_san.message.types.chat_message_type import ChatMessageType

from coded_tools.ablations.g_memory_player_planner_watcher.g_memory_store import GMemoryStore
from neuro_san_studio.conversation_logging import ConversationThinkingFileMessageProcessor


class GMemoryInteractionProcessor(ConversationThinkingFileMessageProcessor):
    """Save agent requests, responses, and delegations with parent relationships."""

    CONTEXT: ClassVar[dict[str, Any]] = {"episode": 0, "turn": 0, "chat_kind": "player"}
    AGENTS: ClassVar[frozenset[str]] = frozenset(
        {
            "park_director",
            "strategy_coordinator",
            "rides_manager",
            "shops_manager",
            "staffing_manager",
            "research_manager",
            "research_lead",
            "park_layout_planner",
            "guest_analyst",
            "macro_orchestrator",
            "episode_start",
            "episode_end",
            "mid_episode_analyst",
        }
    )

    @classmethod
    def set_context(cls, episode: int, turn: int, chat_kind: str) -> None:
        """Bind the current runner call to an episode and action turn."""
        cls.CONTEXT = {"episode": episode, "turn": turn, "chat_kind": chat_kind}

    def process_message(self, chat_message_dict: dict[str, Any], message_type: ChatMessageType) -> None:
        """Mirror only the agent exchange fields that GMemory needs."""
        super().process_message(chat_message_dict, message_type)
        normalized = ChatMessageType.from_response_type(message_type)
        if normalized not in {ChatMessageType.HUMAN, ChatMessageType.AI, ChatMessageType.AGENT}:
            return
        origin = Origination.get_full_name_from_origin(chat_message_dict.get("origin")) or ""
        if not origin:
            return
        agent_path = ".".join(re.sub(r"-\d+$", "", part) for part in origin.split("."))
        agent = agent_path.rsplit(".", 1)[-1]
        if agent not in self.AGENTS:
            return
        parent = agent_path.rsplit(".", 1)[0] if "." in agent_path else ""
        structure = chat_message_dict.get("structure")
        target = ""
        if isinstance(structure, dict):
            target = str(structure.get("invoked_agent_name") or "")
        if normalized == ChatMessageType.AGENT and target not in self.AGENTS:
            return
        content = str(chat_message_dict.get("text") or "")
        if not content and structure is not None:
            content = json.dumps(structure, default=str)
        if not content and not target:
            return
        GMemoryStore().append_interaction(
            {
                **self.CONTEXT,
                "agent_name": agent_path,
                "parent_name": parent,
                "message_type": ChatMessageType.to_string(normalized),
                "target_name": target,
                "content": content[:3000],
            }
        )
