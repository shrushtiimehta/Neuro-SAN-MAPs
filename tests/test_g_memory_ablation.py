"""Focused checks for the no-Markdown GMemory ablation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from neuro_san.message.types.chat_message_type import ChatMessageType

from coded_tools.ablations.g_memory_player_planner_watcher import g_memory_interaction_processor
from coded_tools.ablations.g_memory_player_planner_watcher import g_memory_store
from coded_tools.ablations.g_memory_player_planner_watcher.g_memory_backend import GMemoryBackend
from coded_tools.ablations.g_memory_player_planner_watcher.g_memory_phase_middleware import GMemoryPhaseMiddleware
from coded_tools.ablations.g_memory_player_planner_watcher.g_memory_runtime_tool import GMemoryRuntimeTool
from coded_tools.ablations.g_memory_player_planner_watcher.g_memory_seed import GMemorySeed
from coded_tools.ablations.g_memory_player_planner_watcher.g_memory_state_read import GMemoryStateRead
from coded_tools.ablations.g_memory_player_planner_watcher.g_memory_store import GMemoryStore
from coded_tools.ablations.g_memory_player_planner_watcher.g_memory_write_episode_plan import GMemoryWriteEpisodePlan


class TestGMemoryAblation:
    """Verify live state semantics and the absence of runtime Markdown output."""

    @staticmethod
    def _configure(tmp_path: Path, monkeypatch: Any) -> GMemoryStore:
        """Give each test an isolated GMemory live database."""
        monkeypatch.setattr(g_memory_store, "state_path", lambda name: str(tmp_path / name))
        return GMemoryStore()

    def embed_query(self, query: str) -> list[float]:
        """Provide a deterministic vector for the optional upstream smoke test."""
        del query
        return [0.1] * 8

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed each test task without downloading a model."""
        return [[0.1] * 8 for _ in texts]

    def __call__(self, messages: list[Any], **kwargs: Any) -> str:
        """Answer upstream extraction prompts without a live API call."""
        del messages, kwargs
        return "1. Build earning rides early."

    def test_seed_plan_phase_and_playbook_use_live_store(self, tmp_path: Path, monkeypatch: Any) -> None:
        """The canonical plan can be read without working playbook files."""
        store = self._configure(tmp_path, monkeypatch)
        seeded = GMemorySeed().invoke({"overwrite": True}, {})
        assert seeded.get("errors") == []
        domains = ("rides", "shops", "staff", "research", "layout", "survey")
        plan = GMemoryWriteEpisodePlan().invoke(
            {
                "checklist_items": ["turns 1-100: Build profitable attractions and monitor cash."],
                "strategy_summary": "Choose the best expected profitable move each turn.",
                "playbook_summaries": {domain: f"Operate {domain} for value." for domain in domains},
            },
            {},
        )
        assert isinstance(plan, dict)
        assert "turns 1-100" in (store.get("episode_checklist") or "")
        name_map = {"playbook_rides": "gmemory:playbook_rides"}
        read = GMemoryStateRead().invoke({"name": "playbook_rides", "name_map": name_map}, {})
        assert isinstance(read, dict)
        assert "Operate rides for value" in read.get("content", "")
        assert "gmemory:playbook_rides" == read.get("file_path")
        assert not list(tmp_path.glob("*.md"))

    def test_trials_outcomes_and_scratchpad_are_structured(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Watch and planning records survive in SQLite without trial ledgers."""
        store = self._configure(tmp_path, monkeypatch)
        tool = GMemoryRuntimeTool()
        trial = tool.invoke(
            {
                "memory_operation": "log_trial",
                "episode": 2,
                "origin": "macro",
                "step_start": 1,
                "domain": "rides",
                "section": "new",
                "edit_type": "add_line",
                "new_text": "Place the unlocked ride early.",
                "rationale": "Revenue rose after placement.",
                "success_criterion": "Park value rises by turn 40.",
                "failure_criterion": "Cash stalls by turn 40.",
            },
            {},
        )
        assert isinstance(trial, dict)
        trial_id = trial.get("trial_id")
        active = tool.invoke({"memory_operation": "active_trials", "domain": "rides"}, {})
        assert isinstance(active, dict) and active.get("count") == 1
        resolved = tool.invoke(
            {
                "memory_operation": "resolve_trials",
                "episode": 2,
                "report": [
                    {"trial_id": trial_id, "domain": "rides", "outcome": "confirmed", "note": "Value rose by turn 40."}
                ],
            },
            {},
        )
        assert isinstance(resolved, dict)
        assert resolved.get("removed") == [trial_id]
        assert store.outcomes()[0].get("rule") == "Place the unlocked ride early."
        written = tool.invoke({"memory_operation": "scratchpad", "pad": "player", "note": "Next: check cash."}, {})
        assert isinstance(written, dict) and written.get("action") == "wrote"
        read = tool.invoke({"memory_operation": "scratchpad", "pad": "player"}, {})
        assert isinstance(read, dict) and read.get("note") == "Next: check cash."
        reread = tool.invoke({"memory_operation": "scratchpad", "pad": "player"}, {})
        assert isinstance(reread, dict) and reread.get("note") == ""
        assert not list(tmp_path.glob("*.md"))

    def test_promotion_and_demotion_are_live_records(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Promoted guidance is reversible and never edits shared seed files."""
        store = self._configure(tmp_path, monkeypatch)
        tool = GMemoryRuntimeTool()
        promoted = tool.invoke(
            {
                "memory_operation": "promote_trial",
                "domain": "rides",
                "edit_type": "add_line",
                "new_text": "Prefer reachable high revenue rides.",
                "episode": 1,
            },
            {},
        )
        assert isinstance(promoted, dict) and promoted.get("action_taken") == "promoted"
        assert json.loads(store.get("promoted_rides") or "[]") == ["Prefer reachable high revenue rides."]
        demoted = tool.invoke(
            {
                "memory_operation": "promote_trial",
                "domain": "rides",
                "edit_type": "remove_line",
                "find_text": "reachable high revenue",
            },
            {},
        )
        assert isinstance(demoted, dict) and demoted.get("action_taken") == "demoted"
        assert json.loads(store.get("promoted_rides") or "[]") == []
        assert not list(tmp_path.glob("*.md"))

    def test_replacement_suppresses_old_baseline_rule(self, tmp_path: Path, monkeypatch: Any) -> None:
        """A learned replacement changes the composed playbook without editing a seed file."""
        store = self._configure(tmp_path, monkeypatch)
        store.put("baseline_rides", "# Rides\nPrefer the cheapest ride.\n")
        tool = GMemoryRuntimeTool()
        result = tool.invoke(
            {
                "memory_operation": "promote_trial",
                "domain": "rides",
                "edit_type": "replace_line",
                "find_text": "Prefer the cheapest ride.",
                "new_text": "Prefer the best profitable ride.",
                "episode": 2,
            },
            {},
        )
        assert isinstance(result, dict) and result.get("action_taken") == "promoted"
        read = GMemoryStateRead().invoke(
            {"name": "playbook_rides", "name_map": {"playbook_rides": "gmemory:playbook_rides"}}, {}
        )
        assert isinstance(read, dict)
        assert "Prefer the best profitable ride." in read.get("content", "")
        assert "Prefer the cheapest ride." not in read.get("content", "")

    def test_stream_records_specialist_coordination(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Neuro SAN agent messages retain role, parent, turn, and content."""
        store = self._configure(tmp_path, monkeypatch)
        (tmp_path / "thinking").mkdir()
        processor = g_memory_interaction_processor.GMemoryInteractionProcessor(
            str(tmp_path / "thinking.txt"), str(tmp_path / "thinking")
        )
        g_memory_interaction_processor.GMemoryInteractionProcessor.set_context(3, 20, "player")
        processor.process_message(
            {
                "type": "AGENT",
                "text": "Ask rides manager for a profitable choice.",
                "structure": {"invoked_agent_name": "rides_manager"},
                "origin": [{"tool": "strategy_coordinator"}],
            },
            ChatMessageType.AGENT,
        )
        processor.process_message(
            {
                "type": "AI",
                "text": "Recommend the profitable carousel.",
                "origin": [{"tool": "strategy_coordinator"}, {"tool": "rides_manager"}],
            },
            ChatMessageType.AI,
        )
        events = store.interactions(3)
        assert len(events) == 2
        assert events[0].get("target_name") == "rides_manager"
        assert events[1].get("agent_name") == "strategy_coordinator.rides_manager"
        assert events[1].get("parent_name") == "strategy_coordinator"
        assert events[1].get("turn") == 20

    def test_phase_middleware_uses_stored_plan(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Turn timing is unchanged when the checklist is stored in the database."""
        store = self._configure(tmp_path, monkeypatch)
        store.put("episode_checklist", "turns 1-10: establish park\nturns 11-100: grow value\n")
        observation = tmp_path / "latest_observations.json"
        observation.write_text(json.dumps({"park_0": [{"step": 10, "observation": {"step": 10}}]}))
        middleware = GMemoryPhaseMiddleware(state_dir=str(tmp_path), latest_observation_path=str(observation))
        assert middleware._phase_context() == (10, 11, "turns 11-100: grow value", None)
        assert not (tmp_path / "episode_checklist.md").exists()

    def test_actual_upstream_gmemory_add_and_retrieve(self, tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
        """The adapter calls the repository's GMemory class and persists recall."""
        if not (Path.home() / "GMemory-upstream" / "mas" / "memory" / "mas_memory" / "GMemory.py").exists():
            pytest.skip("optional upstream GMemory checkout is not installed")
        pytest.importorskip("langchain_chroma")
        monkeypatch.setenv("OPENAI_API_KEY", "test-key-must-not-appear")
        backend = GMemoryBackend(embedding_func=self, llm_model=self, working_dir=str(tmp_path))
        assert type(backend.memory).__module__ == "mas.memory.mas_memory.GMemory"
        saved = backend.add_episode(
            episode=0,
            final_reward=400000,
            telemetry={
                "steps": [
                    {
                        "step": 1,
                        "action": "place",
                        "type": "ride",
                        "subtype": "carousel",
                        "reward": 100,
                        "cash": 5000,
                        "park_value": 10000,
                        "park_rating": 0.7,
                        "daily_profit": 100,
                    }
                ],
                "rollup": {},
            },
            plan={},
            outcomes=[],
            interactions=[
                {
                    "event_id": 1,
                    "turn": 0,
                    "chat_kind": "episode_start",
                    "agent_name": "macro_orchestrator.episode_start",
                    "parent_name": "macro_orchestrator",
                    "message_type": "AI",
                    "target_name": "",
                    "content": "Build a profitable ride first.",
                },
                {
                    "event_id": 2,
                    "turn": 1,
                    "chat_kind": "player",
                    "agent_name": "strategy_coordinator",
                    "parent_name": "",
                    "message_type": "AGENT",
                    "target_name": "rides_manager",
                    "content": "Ask rides manager for the best earning ride.",
                },
                {
                    "event_id": 3,
                    "turn": 1,
                    "chat_kind": "player",
                    "agent_name": "strategy_coordinator.rides_manager",
                    "parent_name": "strategy_coordinator",
                    "message_type": "AI",
                    "target_name": "",
                    "content": "Propose the yellow carousel.",
                },
            ],
        )
        assert saved.get("memory_size") == 1
        recalled = backend.retrieve("profitable MAPS ride strategy").get("successful")
        assert recalled and "strategy_coordinator->rides_manager" in recalled[0]
        metadata = backend.memory.main_memory.get().get("metadatas", [])[0]
        restored = backend.message_type.from_dict(metadata)
        graph = restored.chain_of_states.get_state(0)
        assert len(graph.nodes) == 3
        assert len(graph.edges) >= 1
        assert "test-key-must-not-appear" not in capsys.readouterr().out
