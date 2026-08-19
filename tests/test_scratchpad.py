"""A scratchpad note survives exactly ONE run, and only inside its own network.

Reading returns the note AND deletes it, so a plan left for the next run can
never rot into stale advice two runs later. Writing replaces; there is no
append and no history. player/watcher/planner each get their own pad file.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from coded_tools.scratchpad import Scratchpad  # noqa: E402


def test_one_turn_lifetime():
    pad = Scratchpad()
    pad.invoke({"pad": "player"}, {})                     # start clean

    assert pad.invoke({"pad": "player"}, {})["note"] == ""   # nothing left behind
    pad.invoke({"pad": "player", "note": "place blue drink @(4,7)"}, {})
    assert pad.invoke({"pad": "player"}, {})["note"] == "place blue drink @(4,7)"
    assert pad.invoke({"pad": "player"}, {})["note"] == ""   # gone after one read

    # Writing replaces rather than appends.
    pad.invoke({"pad": "player", "note": "first"}, {})
    pad.invoke({"pad": "player", "note": "second"}, {})
    assert pad.invoke({"pad": "player"}, {})["note"] == "second"

    # Oversized notes are capped, so the pad can't grow into a second playbook.
    pad.invoke({"pad": "player", "note": "\n".join(f"line{i}" for i in range(20))}, {})
    assert len(pad.invoke({"pad": "player"}, {})["note"].splitlines()) == Scratchpad.MAX_LINES


def test_pads_are_per_network():
    """One network's note is invisible to the others, and clearing one leaves the rest."""
    pad = Scratchpad()
    for name in ("player", "watcher", "planner"):
        pad.invoke({"pad": name}, {})                     # start clean
        pad.invoke({"pad": name, "note": f"note for {name}"}, {})

    assert pad.invoke({"pad": "watcher"}, {})["note"] == "note for watcher"
    # Reading watcher cleared only watcher.
    assert pad.invoke({"pad": "watcher"}, {})["note"] == ""
    assert pad.invoke({"pad": "player"}, {})["note"] == "note for player"
    assert pad.invoke({"pad": "planner"}, {})["note"] == "note for planner"

    # A missing/garbage pad key falls back to player rather than escaping the state dir.
    assert pad.invoke({"pad": "../../etc/passwd"}, {})["pad"] == "scratchpad_etcpasswd"
    assert pad.invoke({}, {})["pad"] == "scratchpad_player"


def test_planner_handoff_chain():
    """episode_start and episode_end SHARE one pad, on purpose.

        ep_end(N-1) -> ep_start(N) -> ep_end(N) -> ep_start(N+1) -> ...

    They never run concurrently, so each read gets exactly what the previous run
    wrote. Splitting them into two pads would cost the most useful handoff of
    all: the plan author telling the close-out which trial the episode rides on.
    """
    pad = Scratchpad()
    pad.invoke({"pad": "planner"}, {})                     # start clean

    def run(note):
        got = pad.invoke({"pad": "planner"}, {})["note"]   # read-and-clear
        pad.invoke({"pad": "planner", "note": note}, {})
        return got

    run("ep2 closed: t2_5 inconclusive")
    assert run("ep3 plan hinges on t3_2") == "ep2 closed: t2_5 inconclusive"
    assert run("ep3 closed: t3_2 confirmed") == "ep3 plan hinges on t3_2"
    assert run("ep4 doubles down on t3_2") == "ep3 closed: t3_2 confirmed"

    # The chain is planner-only: neither neighbour network sees any of it.
    assert pad.invoke({"pad": "player"}, {})["note"] == ""
    assert pad.invoke({"pad": "watcher"}, {})["note"] == ""
    pad.invoke({"pad": "planner"}, {})                     # leave it clean


if __name__ == "__main__":
    test_one_turn_lifetime()
    test_pads_are_per_network()
    test_planner_handoff_chain()
    print("ok")
