"""The active checklist phase is middleware context, never park status."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from typing import cast

from langchain.agents.middleware.types import ModelRequest
from langchain_core.messages import HumanMessage
from middleware.episode_phase_middleware import EpisodePhaseMiddleware

from coded_tools.episode_phases import phases_for_turn
from coded_tools.episode_phases import validate_phase_items

CHECKLIST = """# Episode Strategy Plan
turns 1-10: establish the park
turns 11-30: grow capacity
turns 31-100: maximize value
"""


def test_phases_for_turn_selects_current_and_next_lines() -> None:
    current, next_phase = phases_for_turn(CHECKLIST, 7) or (None, None)
    assert current and current.text == "turns 1-10: establish the park"
    assert next_phase and next_phase.text == "turns 11-30: grow capacity"

    current, next_phase = phases_for_turn(CHECKLIST, 11) or (None, None)
    assert current and current.text == "turns 11-30: grow capacity"
    assert next_phase and next_phase.text == "turns 31-100: maximize value"

    current, next_phase = phases_for_turn(CHECKLIST, 100) or (None, None)
    assert current and current.text == "turns 31-100: maximize value"
    assert next_phase is None


def test_phase_ranges_must_be_exactly_ordered_and_gap_free() -> None:
    assert validate_phase_items(CHECKLIST.splitlines()[1:]) is None
    assert validate_phase_items(["turns 1-9: first", "turns 11-100: second"])
    assert validate_phase_items(["turns 1-20: first", "turns 20-100: overlap"])
    assert validate_phase_items(["turns 1-99: incomplete"])
    assert phases_for_turn("turns 1-9: first\nturns 11-100: second", 9) is None


def test_middleware_injects_phase_into_latest_human_message(tmp_path) -> None:
    (tmp_path / "episode_checklist.md").write_text(CHECKLIST, encoding="utf-8")
    (tmp_path / "latest_observations.json").write_text(
        json.dumps({"park_0": [{"observation": {"step": 10}}]}),
        encoding="utf-8",
    )
    middleware = EpisodePhaseMiddleware(state_dir=str(tmp_path))
    request = ModelRequest(
        model=cast(Any, object()),
        messages=[HumanMessage(content="Propose one ride action.")],
    )
    captured: dict[str, Any] = {}

    async def handler(updated: ModelRequest) -> Any:
        captured["request"] = updated
        return "ok"

    result = asyncio.run(middleware.awrap_model_call(request, handler))

    assert result == "ok"
    content = captured["request"].messages[0].content
    assert "<RUNTIME_EPISODE_PHASE>" in content
    assert "Completed simulator step: 10" in content
    assert "Action turn being planned: 11" in content
    assert "turns 11-30: grow capacity" in content
    assert "Next phase you can prepare for:\nturns 31-100: maximize value" in content
    assert "Propose one ride action." in content
    assert "turns 1-10" not in content


def test_middleware_uses_new_episode_observation_at_step_zero(tmp_path) -> None:
    (tmp_path / "episode_checklist.md").write_text(CHECKLIST, encoding="utf-8")
    (tmp_path / "latest_observations.json").write_text(
        json.dumps({"park_0": [{"new_park_observation": {"step": 0}}]}),
        encoding="utf-8",
    )

    middleware = EpisodePhaseMiddleware(state_dir=str(tmp_path))

    assert middleware._current_phase() == "turns 1-10: establish the park"


def test_middleware_phase_boundaries_use_the_action_turn(tmp_path) -> None:
    (tmp_path / "episode_checklist.md").write_text(CHECKLIST, encoding="utf-8")
    observation_path = tmp_path / "latest_observations.json"
    middleware = EpisodePhaseMiddleware(state_dir=str(tmp_path))

    expected = {
        0: (1, "turns 1-10: establish the park", "turns 11-30: grow capacity"),
        9: (10, "turns 1-10: establish the park", "turns 11-30: grow capacity"),
        10: (11, "turns 11-30: grow capacity", "turns 31-100: maximize value"),
        29: (30, "turns 11-30: grow capacity", "turns 31-100: maximize value"),
        30: (31, "turns 31-100: maximize value", None),
        99: (100, "turns 31-100: maximize value", None),
    }
    for completed_step, expected_context in expected.items():
        observation_path.write_text(
            json.dumps({"park_0": [{"observation": {"step": completed_step}}]}),
            encoding="utf-8",
        )
        context = middleware._phase_context()
        assert context is not None
        _, action_turn, current, next_phase = context
        assert (action_turn, current, next_phase) == expected_context

    observation_path.write_text(
        json.dumps({"park_0": [{"step": 100, "observation": {"step": 99}}]}),
        encoding="utf-8",
    )
    assert middleware._phase_context() is None


def test_middleware_prefers_authoritative_envelope_step(tmp_path) -> None:
    (tmp_path / "episode_checklist.md").write_text(CHECKLIST, encoding="utf-8")
    (tmp_path / "latest_observations.json").write_text(
        json.dumps({"park_0": [{"step": 10, "observation": {"step": 9}}]}),
        encoding="utf-8",
    )

    context = EpisodePhaseMiddleware(state_dir=str(tmp_path))._phase_context()

    assert context == (
        10,
        11,
        "turns 11-30: grow capacity",
        "turns 31-100: maximize value",
    )
