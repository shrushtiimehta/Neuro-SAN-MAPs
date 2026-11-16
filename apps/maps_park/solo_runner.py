#!/usr/bin/env python3
"""Two-agent MAPs baseline: one player agent and one planner agent.

The deterministic lifecycle remains in :mod:`apps.maps_park.runner`. This
adapter selects the isolated roots before any coded tool is imported, points
the player at ``player_solo``, and reuses one ``planner_solo`` session for
episode-start, periodic, and episode-end work.
"""

from __future__ import annotations

import os
import shutil
import sys
from typing import Any

# These must be set before importing runner: coded-tool path constants are
# intentionally resolved once when the studio/runner process imports them.
os.environ.setdefault("MAPS_STATE_DIR", "state_solo")
os.environ.setdefault("MAPS_LOG_DIR", os.path.join("logs", "maps_park_solo"))
os.environ.setdefault("MAPS_MERGED_CONTEXT", "1")

from apps.maps_park import runner  # noqa: E402

PLAYER_AGENT = "player_solo"
PLANNER_AGENT = "planner_solo"

runner.DEFAULT_RUNNER_AGENT = PLAYER_AGENT
runner.DEFAULT_MICRO_AGENT = PLANNER_AGENT
runner.DEFAULT_MACRO_AGENT = PLANNER_AGENT

_open_session = runner.open_session
_planner_connection: tuple[Any, dict] | None = None


def open_session(agent_name: str, host: str, port: int):
    """Open one player connection and reuse exactly one planner connection."""
    global _planner_connection
    if agent_name == PLANNER_AGENT:
        if _planner_connection is None:
            _planner_connection = _open_session(agent_name, host, port)
        else:
            print("[solo] Reusing planner_solo session for macro + periodic work.")
        return _planner_connection
    return _open_session(agent_name, host, port)


def reset_agent_session_cache() -> None:
    """Discard the shared Solo planner connection at an episode boundary."""
    global _planner_connection
    _planner_connection = None


def save_champion_status() -> None:
    """Freeze the complete solo park snapshot for the next planning pass."""
    src = os.path.join(runner.PLAYBOOK_STATE_DIR, "status_solo.json")
    dest = os.path.join(runner.PLAYBOOK_STATE_DIR, "status_solo_champion.json")
    if os.path.exists(src):
        shutil.copy2(src, dest)


def _apply_solo_runtime() -> None:
    runner.open_session = open_session
    runner.reset_agent_session_cache = reset_agent_session_cache
    runner.STATUS_PATH = os.path.join(runner.PLAYBOOK_STATE_DIR, "status_solo.json")
    runner.STATUS_CHAMPION_PATH = os.path.join(runner.PLAYBOOK_STATE_DIR, "status_solo_champion.json")
    runner.save_champion_status = save_champion_status
    # The checked-in merged seed is an immutable experiment input. A fresh run
    # archives the live playbook and re-copies this seed; it never edits source.
    runner.strip_learned_from_seeds = lambda: 0


def _self_check() -> None:
    _apply_solo_runtime()
    assert os.environ["MAPS_STATE_DIR"] == "state_solo"
    assert os.environ["MAPS_MERGED_CONTEXT"] == "1"
    assert runner.DEFAULT_RUNNER_AGENT == PLAYER_AGENT
    assert runner.DEFAULT_MICRO_AGENT == runner.DEFAULT_MACRO_AGENT == PLANNER_AGENT
    assert runner.STATUS_PATH.endswith("state_solo/status_solo.json")
    print("[solo] self-check OK: one player, one shared planner, isolated state_solo.")


def main() -> None:
    if "--self-check" in sys.argv:
        _self_check()
        return
    _apply_solo_runtime()
    print("[solo] TWO-AGENT BASELINE: player_solo + planner_solo (periodic + macro).")
    runner.main()


if __name__ == "__main__":
    main()
