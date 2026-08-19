"""A leftover trial informs exactly ONE planning pass, then stops existing.

    episode START  design                 -> LogTrial
    episode END    confirmed  -> promoted
                   falsified  -> removed
                   neither    -> LEFT OVER   (ResolveTrials keeps it)
    next START     fed to the planner AND DELETED  <- CarryoverTrials

Without the delete, a leftover re-arms every episode: the live ledger reached
ep3 still serving ep0/ep1/ep2 trials whose episode-relative windows ("from
steps 91-100") all fired at once with cash floors of 4500/12000/15000.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import coded_tools.carryover_trials as ct  # noqa: E402


def _ledger(tmp, strategies, criteria, outcomes=""):
    paths = {}
    for name, text in (("s.md", strategies), ("c.md", criteria), ("o.md", outcomes)):
        p = Path(tmp) / name
        p.write_text(text)
        paths[name] = str(p)
    ct.CarryoverTrials.STRATEGIES_PATH = paths["s.md"]
    ct.CarryoverTrials.CRITERIA_PATH = paths["c.md"]
    ct.CarryoverTrials.OUTCOME_PATH = paths["o.md"]
    return paths


def _crit(tid, ep, origin="macro"):
    return (f"- {tid} ep={ep} step_start=91 domain=rides origin={origin} section='x' "
            f"edit=add_line rationale='r' success='s' failure='f'\n")


def test_leftovers_are_returned_then_deleted(tmp):
    paths = _ledger(
        tmp,
        "- t1_1: leftover from ep1\n- t2_1: leftover from ep2\n- t3_1: logged for ep3\n",
        _crit("t1_1", 1) + _crit("t2_1", 2) + _crit("t3_1", 3),
    )
    res = ct.CarryoverTrials().invoke({"episode": 3}, {})

    # Fed to the planner: full rule text and criteria, not just ids.
    assert res["count"] == 2 and sorted(res["cleared"]) == ["t1_1", "t2_1"]
    assert {t["rule"] for t in res["trials"]} == {"leftover from ep1", "leftover from ep2"}
    assert all(t["success_criterion"] == "s" for t in res["trials"])

    # ...and gone from both ledgers in the same call.
    left = Path(paths["s.md"]).read_text()
    assert "t1_1" not in left and "t2_1" not in left
    assert "t3_1" in left, "a trial for the episode being planned was wiped"
    assert "t1_1" not in Path(paths["c.md"]).read_text()

    # The rule text survives in the outcome ledger — its only remaining trace.
    out = Path(paths["o.md"]).read_text()
    assert "outcome=carried_over" in out and "leftover from ep1" in out

    # Second call is a no-op: nothing left to carry, so nothing to re-report.
    again = ct.CarryoverTrials().invoke({"episode": 3}, {})
    assert again["count"] == 0 and again["cleared"] == []


def test_safe_to_call_after_logging_this_episode_s_trials(tmp):
    """Order independence: calling it late must not bin the plan just written."""
    _ledger(tmp, "- t3_1: brand new\n- t3_2: also new\n", _crit("t3_1", 3) + _crit("t3_2", 3))
    res = ct.CarryoverTrials().invoke({"episode": 3}, {})
    assert res["count"] == 0, "wiped trials logged for the episode being planned"


def test_micro_leftovers_are_cleared_but_not_ledgered(tmp):
    """The abort backstop: the runner sweeps at every fresh-episode start, so a
    killed run's leftovers still die — but micro rules are episode-scoped and
    must not bury the macro outcomes in the ledger."""
    paths = _ledger(tmp, "- t1_9: from steps 91-100, if cash is at least 8500\n"
                         "- t1_1: a macro standing direction\n",
                    _crit("t1_9", 1, origin="micro") + _crit("t1_1", 1))
    res = ct.CarryoverTrials().invoke({"episode": 2}, {})
    assert sorted(res["cleared"]) == ["t1_1", "t1_9"], "a leftover survived the sweep"
    assert Path(paths["s.md"]).read_text().strip() == ""
    ledger = Path(paths["o.md"]).read_text()
    assert "t1_1" in ledger, "the macro outcome was dropped"
    assert "t1_9" not in ledger, "an episode-scoped micro rule was ledgered"


def test_malformed_and_bad_input_are_not_deleted_blind(tmp):
    paths = _ledger(tmp, "- tX_1: no episode stamp\n", "- tX_1 domain=rides origin=macro\n")
    res = ct.CarryoverTrials().invoke({"episode": 3}, {})
    assert res["count"] == 0, "a trial with an unparseable ep was binned"
    assert "tX_1" in Path(paths["s.md"]).read_text()

    assert str(ct.CarryoverTrials().invoke({}, {})).startswith("ERROR:")
    assert "tX_1" in Path(paths["s.md"]).read_text(), "a bad call still mutated the ledger"


if __name__ == "__main__":
    import tempfile
    for fn in (test_leftovers_are_returned_then_deleted,
               test_safe_to_call_after_logging_this_episode_s_trials,
               test_micro_leftovers_are_cleared_but_not_ledgered,
               test_malformed_and_bad_input_are_not_deleted_blind):
        with tempfile.TemporaryDirectory() as td:
            fn(td)
    print("ok")
