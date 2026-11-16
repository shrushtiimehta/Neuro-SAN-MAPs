"""Bounded hybrid runner that gives one planner agent a single shared session.

The player remains the canonical multi-agent network.  The same planner network
and conversation own episode-start, periodic, and episode-end analysis.
"""

from __future__ import annotations

import os
from typing import Any

from apps.maps_park import runner

_base_open_session = runner.open_session
_planner_connection: tuple[Any, dict] | None = None


def _open_session(agent_name: str, host: str, port: int):
    """Reuse one connection when micro and macro select the same planner."""
    global _planner_connection
    planner_name = os.environ.get("MAPS_MACRO_AGENT", "planner_single")
    micro_name = os.environ.get("MAPS_MICRO_AGENT", planner_name)
    if agent_name == planner_name == micro_name:
        if _planner_connection is None:
            _planner_connection = _base_open_session(agent_name, host, port)
        else:
            print("[hybrid] Reusing the single planner session for periodic + macro work.")
        return _planner_connection
    return _base_open_session(agent_name, host, port)


def main() -> None:
    """Apply session sharing, then run the standard bounded ablation lifecycle."""
    runner.open_session = _open_session
    from apps.maps_park import ablation_runner

    ablation_runner.main()


if __name__ == "__main__":
    main()
