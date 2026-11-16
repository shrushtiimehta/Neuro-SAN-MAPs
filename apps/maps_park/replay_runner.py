#!/usr/bin/env python3
"""Player + watcher only — no planner. Replays whatever strategy is in state/.

runner.py's default mode restores the champion playbooks over state/ and lets
the planner (macro) rewrite the checklist, the coordinator summary and the
trials at every episode boundary. This runner does neither: the files sitting in
state/ when it starts are the ones played for the whole run.

    ./state_1.8M/restore.sh                       # ep3's champion inputs
    python3 -m apps.maps_park.replay_runner        # services already up

Two patches on runner.py, no fork:

  * open_session refuses the macro agent, so runner.py's own
    "macro analyzer session failed; running without it" path leaves
    macro_session = None — neither the episode_start pass nor the episode_end
    close-out fires, and nothing edits a playbook or a trial.
  * restore_champion_playbooks becomes a no-op that still reports success.
    Returning None instead would set overwrite=True and SeedPlaybooks would
    stamp the config_files seeds over the state we just restored.

The watcher (micro) is untouched: it still runs at steps 10..90 and still
judges the run against champion_reward.json (1,861,276 after restore.sh).

Unsupported flags: --fresh (archives state/ straight back out) and
--macro-agent (there is nothing to point it at). Everything else works.
"""

from __future__ import annotations

import sys
from typing import Any

from apps.maps_park import runner

_open_session = runner.open_session


def open_session(agent_name: str, host: str, port: int):
    """Connect every network except the planner."""
    if agent_name == runner.DEFAULT_MACRO_AGENT:
        raise RuntimeError(f"'{agent_name}' disabled by replay_runner (no planner)")
    return _open_session(agent_name, host, port)


def _apply_patches() -> None:
    runner.open_session = open_session
    # ponytail: truthy sentinel, not None — runner.py reads the return value as
    # "was a champion restored?" and falls back to the config seeds on None.
    runner.restore_champion_playbooks = lambda: "state/ as-is (replay_runner)"


def _self_check() -> None:
    """Smoke test for the two patches. No server, no LLM: `--self-check`."""
    _apply_patches()
    try:
        runner.open_session(runner.DEFAULT_MACRO_AGENT, "localhost", 8090)
    except RuntimeError:
        pass
    else:
        raise AssertionError("planner session was NOT refused")
    assert runner.restore_champion_playbooks(), "champion no-op must stay truthy"
    print("[replay] self-check OK: planner refused, state/ left alone.")


def main() -> None:
    if "--self-check" in sys.argv:
        _self_check()
        return
    bad: Any
    why: Any
    for bad, why in (
        ("--fresh", "archives state/ back out — see state_1.8M/README.md"),
        ("--macro-agent", "the planner is off in this runner"),
    ):
        if bad in sys.argv:
            sys.exit(f"replay_runner: {bad} is unsupported: {why}")
    _apply_patches()
    print("[replay] planner OFF — playing state/ as-is (player + watcher only).")
    runner.main()


if __name__ == "__main__":
    main()
