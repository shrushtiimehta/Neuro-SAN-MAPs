"""Defects found live in episode 3, with the ledger as evidence.

1. STRANDED TRIALS. A close-out that never runs leaves trials in the ledger for
   good. Every trial's window is episode-relative ("from steps 91-100"), so a
   stranded one re-arms each episode: at ep3 step 91 the ledger served four
   endgame trials from three episodes with cash floors of 4500/12000/15000.
   ActiveTrials now withholds anything too old to still apply.

2. RECYCLED IDS. _next_trial_id counted live rules, so a DeleteTrial mid-episode
   dropped the count and the next mint reissued a live id. The real ledger held
   t3_3 twice (and no t3_1), and t0_9 four times across four domains — one id,
   several trials, so DeleteTrial/ResolveTrials could only ever reach one.

3. ID-ONLY OUTCOMES. The outcome ledger recorded "t1_1 falsified" while the same
   call deleted t1_1's text from trial_strategies.md — so the next planner, told
   not to re-propose falsified ideas, could not know what they were.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import coded_tools.active_trials as at  # noqa: E402
from coded_tools.log_trial import LogTrial  # noqa: E402


def _ledger(tmp, strategies, criteria, outcomes=""):
    """Point every trial module at a throwaway ledger triple."""
    paths = {}
    for name, text in (("trial_strategies.md", strategies),
                       ("trial_strategies_criteria.md", criteria),
                       ("trial_strategies_outcome.md", outcomes)):
        p = Path(tmp) / name
        p.write_text(text)
        paths[name] = str(p)
    at.STRATEGIES_PATH = paths["trial_strategies.md"]
    at.CRITERIA_PATH = paths["trial_strategies_criteria.md"]
    return paths


def test_stale_trials_are_withheld(tmp):
    strategies = "".join(f"- t{e}_1: rule for episode {e}\n" for e in (0, 1, 2, 3))
    criteria = "".join(
        f"- t{e}_1 ep={e} step_start=91 domain=rides origin=micro section='x' "
        f"edit=add_line rationale='r' success='s' failure='f'\n" for e in (0, 1, 2, 3))
    _ledger(tmp, strategies, criteria)
    at._current_episode = lambda: 3                    # pretend we are in episode 3

    r = at.ActiveTrials().invoke({}, {})
    assert sorted(t["trial_id"] for t in r["trials"]) == ["t2_1", "t3_1"], r
    assert sorted(r["withheld_stale"]) == ["t0_1", "t1_1"]
    assert r["count"] == 2
    assert "never resolved" in r["withheld_reason"]     # says WHY, not silently gone

    # Unknown episode -> withhold nothing. A missing cache must never blank the loop.
    at._current_episode = lambda: None
    r = at.ActiveTrials().invoke({}, {})
    assert r["count"] == 4 and "withheld_stale" not in r

    # A malformed `ep` counts as current rather than being dropped.
    _ledger(tmp, "- tX_1: junk\n",
            "- tX_1 ep=banana step_start=1 domain=rides origin=micro section='x' "
            "edit=add_line rationale='r' success='s' failure='f'\n")
    at._current_episode = lambda: 3
    assert at.ActiveTrials().invoke({}, {})["count"] == 1


def test_ids_are_never_recycled(tmp):
    """t3_1 deleted mid-episode must NOT free up t3_3 for reuse."""
    paths = _ledger(tmp,
                    "- t3_2: b\n- t3_3: c\n",          # t3_1 was deleted: 2 live rules
                    "- t3_2 ep=3\n- t3_3 ep=3\n",
                    "- OUTCOME ep=3 trial_id=t3_1 outcome=falsified rule='a'\n")
    lt = LogTrial()
    lt.STRATEGIES_PATH = paths["trial_strategies.md"]
    lt.CRITERIA_PATH = paths["trial_strategies_criteria.md"]
    lt.OUTCOME_PATH = paths["trial_strategies_outcome.md"]

    assert lt._next_trial_id(3) == "t3_4", "counting live rules re-issued a live id"
    assert lt._next_trial_id(9) == "t9_1"              # untouched episode starts at 1

    # A deleted id survives only in the outcome ledger — still must not be reused.
    paths = _ledger(tmp, "", "", "- OUTCOME ep=5 trial_id=t5_7 outcome=falsified\n")
    lt.STRATEGIES_PATH = paths["trial_strategies.md"]
    lt.CRITERIA_PATH = paths["trial_strategies_criteria.md"]
    lt.OUTCOME_PATH = paths["trial_strategies_outcome.md"]
    assert lt._next_trial_id(5) == "t5_8"


def test_macro_outcome_lines_carry_the_rule_text(tmp):
    """The id alone is useless: the rule is deleted in the same call."""
    import coded_tools.resolve_trials as rt

    paths = _ledger(tmp, "- t4_1: never place a red coaster before step 50\n",
                    "- t4_1 ep=4 step_start=1 domain=rides origin=macro section='x' "
                    "edit=add_line rationale='r' success='s' failure='f'\n")
    rt.STRATEGIES_PATH = paths["trial_strategies.md"]
    rt.CRITERIA_PATH = paths["trial_strategies_criteria.md"]
    rt.OUTCOME_PATH = paths["trial_strategies_outcome.md"]
    rt.ResolveTrials().invoke(
        {"episode": 4, "report": [{"trial_id": "t4_1", "outcome": "falsified"}]}, {})
    line = Path(paths["trial_strategies_outcome.md"]).read_text()
    assert "never place a red coaster before step 50" in line, "no rule text"
    # ...and the rule really is gone from the active ledger, so the line is its only trace.
    assert Path(paths["trial_strategies.md"]).read_text().strip() == ""


def test_micro_trials_are_never_ledgered(tmp):
    """Micro rules are written for one episode's exact state — ledgering them
    buries the macro outcomes the next planner actually needs."""
    import coded_tools.delete_trial as dt
    import coded_tools.resolve_trials as rt

    micro = ("- t4_9 ep=4 step_start=1 domain=rides origin=micro section='x' "
             "edit=add_line rationale='r' success='s' failure='f'\n")
    for mod, call in ((dt, lambda m: m.DeleteTrial().invoke({"trial_id": "t4_9"}, {})),
                      (rt, lambda m: m.ResolveTrials().invoke({"episode": 4, "report": []}, {}))):
        paths = _ledger(tmp, "- t4_9: from steps 61-70, if cash is at least 8500\n", micro)
        mod.STRATEGIES_PATH = paths["trial_strategies.md"]
        mod.CRITERIA_PATH = paths["trial_strategies_criteria.md"]
        mod.OUTCOME_PATH = paths["trial_strategies_outcome.md"]
        call(mod)
        # Removed from the active ledger...
        assert Path(paths["trial_strategies.md"]).read_text().strip() == "", mod.__name__
        # ...and left no trace in the outcome ledger.
        assert Path(paths["trial_strategies_outcome.md"]).read_text().strip() == "", mod.__name__


def test_stranded_macro_trials_are_expired_not_kept(tmp):
    """The trap the age limit creates if ResolveTrials is not taught about it.

    ActiveTrials withholds an old trial -> the close-out never sees it -> it is
    never confirmed or falsified -> "inconclusive" KEEPS a macro trial. Result:
    a trial that is invisible to every reader and impossible to delete.
    """
    import coded_tools.resolve_trials as rt

    strategies = ("- t0_1: ancient macro rule\n- t0_9: ancient micro rule\n"
                  "- t2_1: recent macro rule\n- t3_1: current macro rule\n")
    criteria = (
        "- t0_1 ep=0 domain=rides origin=macro section='x' edit=add_line "
        "rationale='r' success='s' failure='f'\n"
        "- t0_9 ep=0 domain=rides origin=micro section='x' edit=add_line "
        "rationale='r' success='s' failure='f'\n"
        "- t2_1 ep=2 domain=rides origin=macro section='x' edit=add_line "
        "rationale='r' success='s' failure='f'\n"
        "- t3_1 ep=3 domain=rides origin=macro section='x' edit=add_line "
        "rationale='r' success='s' failure='f'\n")
    paths = _ledger(tmp, strategies, criteria)
    rt.STRATEGIES_PATH = paths["trial_strategies.md"]
    rt.CRITERIA_PATH = paths["trial_strategies_criteria.md"]
    rt.OUTCOME_PATH = paths["trial_strategies_outcome.md"]

    res = rt.ResolveTrials().invoke({"episode": 3, "report": []}, {})   # empty report
    assert "t0_1" in res["removed"], "stranded macro trial kept forever"
    assert "t0_9" in res["removed"], "micro trials are episode-scoped"
    # ep2 is still within carry-over, and ep3 is current: both legitimately kept.
    assert sorted(res["kept"]) == ["t2_1", "t3_1"], res

    out = Path(paths["trial_strategies_outcome.md"]).read_text()
    assert "outcome=expired" in out and "ancient macro rule" in out

    # The two rules must agree, or trials fall into the gap between them.
    assert rt.ResolveTrials._too_old({"ep": "0"}, 3) is True
    assert rt.ResolveTrials._too_old({"ep": "2"}, 3) is False
    assert rt.ResolveTrials._too_old({"ep": "nonsense"}, 3) is False    # never expire blind


def test_consultant_inputs_exist(tmp):
    """Two read-before-write deadlocks, both observed dead in a live run.

    A consultant reads a file in the same step whose tool is that file's only
    writer. Missing file -> state_read errors -> "STOP on any tool error" aborts
    the pass -> the write never happens -> every later episode fails identically:

      last_reward.md        read by episode_end step 1; written by advance_episode step 5
      episode_checklist.md  read by episode_start step 5; written by WriteEpisodePlan, same step
    """
    from coded_tools.seed_playbooks import SeedPlaybooks

    for f in ("last_reward.md", "episode_checklist.md"):
        assert f in SeedPlaybooks.ENSURED_STATE_FILES, f"{f} deadlock is back"

    sp = SeedPlaybooks()
    sp.STATE_DIR, sp.SEED_DIR = tmp, tmp
    sp.invoke({"overwrite": False}, {})
    for f in SeedPlaybooks.ENSURED_STATE_FILES:
        assert (Path(tmp) / f).exists(), f"consultant input {f} not created"
    # last_reward must parse the way advance_episode writes it, not just exist.
    assert (Path(tmp) / "last_reward.md").read_text().startswith("cumulative_reward:")

    # Never clobbered, even with overwrite=True — accumulated state must survive a reseed.
    (Path(tmp) / "last_reward.md").write_text("cumulative_reward: 122167.0\n")
    (Path(tmp) / "episode_checklist.md").write_text("turns 1-10: open the park\n")
    sp.invoke({"overwrite": True}, {})
    assert "122167" in (Path(tmp) / "last_reward.md").read_text()
    assert "open the park" in (Path(tmp) / "episode_checklist.md").read_text()


if __name__ == "__main__":
    import tempfile
    for fn in (test_stale_trials_are_withheld, test_ids_are_never_recycled,
               test_macro_outcome_lines_carry_the_rule_text, test_micro_trials_are_never_ledgered,
               test_stranded_macro_trials_are_expired_not_kept, test_consultant_inputs_exist):
        with tempfile.TemporaryDirectory() as td:
            fn(td)
    print("ok")
