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
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import coded_tools.active_trials as at  # noqa: E402
from coded_tools.log_trial import LogTrial  # noqa: E402


def _ledger(tmp, strategies, criteria, outcomes=""):
    """Point every trial module at a throwaway ledger triple."""
    paths = {}
    name: Any
    text: Any
    for name, text in (
        ("trial_strategies.md", strategies),
        ("trial_strategies_criteria.md", criteria),
        ("trial_strategies_outcome.md", outcomes),
    ):
        p = Path(tmp) / name
        p.write_text(text)
        paths[name] = str(p)
    at.STRATEGIES_PATH = paths["trial_strategies.md"]
    at.CRITERIA_PATH = paths["trial_strategies_criteria.md"]
    return paths


def test_stale_trials_are_withheld(tmp_path):
    tmp = tmp_path
    strategies = "".join(f"- t{e}_1: rule for episode {e}\n" for e in (0, 1, 2, 3))
    criteria = "".join(
        f"- t{e}_1 ep={e} step_start=91 domain=rides origin=micro section='x' "
        f"edit=add_line rationale='r' success='s' failure='f'\n"
        for e in (0, 1, 2, 3)
    )
    _ledger(tmp, strategies, criteria)
    at._current_episode = lambda: 3  # pretend we are in episode 3

    r = at.ActiveTrials().invoke({}, {})
    assert sorted(t["trial_id"] for t in r["trials"]) == ["t2_1", "t3_1"], r
    assert sorted(r["withheld_stale"]) == ["t0_1", "t1_1"]
    assert r["count"] == 2
    assert "never resolved" in r["withheld_reason"]  # says WHY, not silently gone

    # Unknown episode -> withhold nothing. A missing cache must never blank the loop.
    at._current_episode = lambda: None
    r = at.ActiveTrials().invoke({}, {})
    assert r["count"] == 4 and "withheld_stale" not in r

    # A malformed `ep` counts as current rather than being dropped.
    _ledger(
        tmp,
        "- tX_1: junk\n",
        "- tX_1 ep=banana step_start=1 domain=rides origin=micro section='x' "
        "edit=add_line rationale='r' success='s' failure='f'\n",
    )
    at._current_episode = lambda: 3
    assert at.ActiveTrials().invoke({}, {})["count"] == 1


def test_all_filters_mean_no_filter(tmp_path):
    strategies = "- t3_1: macro ride rule\n- t3_2: micro shop rule\n"
    criteria = (
        "- t3_1 ep=3 step_start=1 domain=rides origin=macro section='x' "
        "edit=add_line rationale='r' success='s' failure='f'\n"
        "- t3_2 ep=3 step_start=1 domain=shops origin=micro section='x' "
        "edit=add_line rationale='r' success='s' failure='f'\n"
    )
    _ledger(tmp_path, strategies, criteria)
    at._current_episode = lambda: 3

    args: Any
    for args in ({"domain": "all"}, {"trial_origin": "all"}, {"domain": " ALL ", "trial_origin": " ALL "}):
        result = at.ActiveTrials().invoke(args, {})
        assert result["count"] == 2, result
        assert result["domain"] is None
        assert result["origin"] is None

    assert at.ActiveTrials().invoke({"domain": "rides"}, {})["count"] == 1
    assert at.ActiveTrials().invoke({"trial_origin": "micro"}, {})["count"] == 1


def test_trial_count_is_not_capped(tmp_path):
    paths = _ledger(tmp_path, "", "")
    logger = LogTrial()
    logger.STRATEGIES_PATH = paths["trial_strategies.md"]
    logger.CRITERIA_PATH = paths["trial_strategies_criteria.md"]
    logger.OUTCOME_PATH = paths["trial_strategies_outcome.md"]

    number: Any
    for number in range(12):
        result = logger.invoke(
            {
                "episode": 3,
                "domain": f"domain_{number}",
                "origin": "macro",
                "edit_type": "add_line",
                "new_text": f"trial rule {number}",
                "section": "x",
                "rationale": "r",
                "success_criterion": "s",
                "failure_criterion": "f",
                "step_start": 1,
            },
            {},
        )
        assert result == {"trial_id": f"t3_{number + 1}"}

    at._current_episode = lambda: 3
    result = at.ActiveTrials().invoke({"domain": "all"}, {})
    assert result["count"] == 12


def test_ids_are_never_recycled(tmp_path):
    tmp = tmp_path
    """t3_1 deleted mid-episode must NOT free up t3_3 for reuse."""
    paths = _ledger(
        tmp,
        "- t3_2: b\n- t3_3: c\n",  # t3_1 was deleted: 2 live rules
        "- t3_2 ep=3\n- t3_3 ep=3\n",
        "- OUTCOME ep=3 trial_id=t3_1 outcome=falsified rule='a'\n",
    )
    lt = LogTrial()
    lt.STRATEGIES_PATH = paths["trial_strategies.md"]
    lt.CRITERIA_PATH = paths["trial_strategies_criteria.md"]
    lt.OUTCOME_PATH = paths["trial_strategies_outcome.md"]

    assert lt._next_trial_id(3) == "t3_4", "counting live rules re-issued a live id"
    assert lt._next_trial_id(9) == "t9_1"  # untouched episode starts at 1

    # A deleted id survives only in the outcome ledger — still must not be reused.
    paths = _ledger(tmp, "", "", "- OUTCOME ep=5 trial_id=t5_7 outcome=falsified\n")
    lt.STRATEGIES_PATH = paths["trial_strategies.md"]
    lt.CRITERIA_PATH = paths["trial_strategies_criteria.md"]
    lt.OUTCOME_PATH = paths["trial_strategies_outcome.md"]
    assert lt._next_trial_id(5) == "t5_8"


def test_macro_outcome_lines_carry_the_rule_text(tmp_path):
    tmp = tmp_path
    """The id alone is useless: the rule is deleted in the same call."""
    import coded_tools.resolve_trials as rt

    paths = _ledger(
        tmp,
        "- t4_1: never place a red coaster before step 50\n",
        "- t4_1 ep=4 step_start=1 domain=rides origin=macro section='x' "
        "edit=add_line rationale='r' success='s' failure='f'\n",
    )
    rt.STRATEGIES_PATH = paths["trial_strategies.md"]
    rt.CRITERIA_PATH = paths["trial_strategies_criteria.md"]
    rt.OUTCOME_PATH = paths["trial_strategies_outcome.md"]
    rt.ResolveTrials().invoke({"episode": 4, "report": [{"trial_id": "t4_1", "outcome": "falsified"}]}, {})
    line = Path(paths["trial_strategies_outcome.md"]).read_text()
    assert "never place a red coaster before step 50" in line, "no rule text"
    # ...and the rule really is gone from the active ledger, so the line is its only trace.
    assert Path(paths["trial_strategies.md"]).read_text().strip() == ""


def test_micro_trials_are_never_ledgered(tmp_path):
    tmp = tmp_path
    """Micro rules are written for one episode's exact state — ledgering them
    buries the macro outcomes the next planner actually needs."""
    import coded_tools.delete_trial as dt
    import coded_tools.resolve_trials as rt

    micro = (
        "- t4_9 ep=4 step_start=1 domain=rides origin=micro section='x' "
        "edit=add_line rationale='r' success='s' failure='f'\n"
    )
    mod: Any
    call: Any
    for mod, call in (
        (dt, lambda m: m.DeleteTrial().invoke({"trial_id": "t4_9"}, {})),
        (
            rt,
            lambda m: m.ResolveTrials().invoke(
                {
                    "episode": 4,
                    "report": [{"trial_id": "t4_9", "outcome": "not_applied"}],
                },
                {},
            ),
        ),
    ):
        paths = _ledger(tmp, "- t4_9: from steps 61-70, if cash is at least 8500\n", micro)
        mod.STRATEGIES_PATH = paths["trial_strategies.md"]
        mod.CRITERIA_PATH = paths["trial_strategies_criteria.md"]
        mod.OUTCOME_PATH = paths["trial_strategies_outcome.md"]
        call(mod)
        # Removed from the active ledger...
        assert Path(paths["trial_strategies.md"]).read_text().strip() == "", mod.__name__
        # ...and left no trace in the outcome ledger.
        assert Path(paths["trial_strategies_outcome.md"]).read_text().strip() == "", mod.__name__


def test_stranded_macro_trials_are_expired_not_kept(tmp_path):
    tmp = tmp_path
    """The trap the age limit creates if ResolveTrials is not taught about it.

    ActiveTrials withholds an old trial -> the close-out never sees it -> it is
    never confirmed or falsified -> "inconclusive" KEEPS a macro trial. Result:
    a trial that is invisible to every reader and impossible to delete.
    """
    import coded_tools.resolve_trials as rt

    strategies = (
        "- t0_1: ancient macro rule\n- t0_9: ancient micro rule\n"
        "- t2_1: recent macro rule\n- t3_1: current macro rule\n"
    )
    criteria = (
        "- t0_1 ep=0 domain=rides origin=macro section='x' edit=add_line "
        "rationale='r' success='s' failure='f'\n"
        "- t0_9 ep=0 domain=rides origin=micro section='x' edit=add_line "
        "rationale='r' success='s' failure='f'\n"
        "- t2_1 ep=2 domain=rides origin=macro section='x' edit=add_line "
        "rationale='r' success='s' failure='f'\n"
        "- t3_1 ep=3 domain=rides origin=macro section='x' edit=add_line "
        "rationale='r' success='s' failure='f'\n"
    )
    paths = _ledger(tmp, strategies, criteria)
    rt.STRATEGIES_PATH = paths["trial_strategies.md"]
    rt.CRITERIA_PATH = paths["trial_strategies_criteria.md"]
    rt.OUTCOME_PATH = paths["trial_strategies_outcome.md"]

    res = rt.ResolveTrials().invoke(
        {
            "episode": 3,
            "report": [
                {"trial_id": "t2_1", "outcome": "inconclusive", "note": "needs another episode"},
                {"trial_id": "t3_1", "outcome": "inconclusive", "note": "metric did not resolve"},
            ],
        },
        {},
    )
    assert "t0_1" in res["removed"], "stranded macro trial kept forever"
    assert "t0_9" in res["removed"], "micro trials are episode-scoped"
    # ep2 is still within carry-over, and ep3 is current: both legitimately kept.
    assert sorted(res["kept"]) == ["t2_1", "t3_1"], res

    out = Path(paths["trial_strategies_outcome.md"]).read_text()
    assert "outcome=expired" in out and "ancient macro rule" in out

    # The two rules must agree, or trials fall into the gap between them.
    assert rt.ResolveTrials._too_old({"ep": "0"}, 3) is True
    assert rt.ResolveTrials._too_old({"ep": "2"}, 3) is False
    assert rt.ResolveTrials._too_old({"ep": "nonsense"}, 3) is False  # never expire blind


def test_resolve_trials_accepts_native_wrapped_and_fenced_reports(tmp_path):
    tmp = tmp_path
    import coded_tools.resolve_trials as rt

    paths = _ledger(tmp, "- t4_1: test rule\n", "- t4_1 ep=4 domain=rides origin=macro\n")
    rt.STRATEGIES_PATH = paths["trial_strategies.md"]
    rt.CRITERIA_PATH = paths["trial_strategies_criteria.md"]
    rt.OUTCOME_PATH = paths["trial_strategies_outcome.md"]

    report: Any
    for report in (
        [{"trial_id": "t4_1", "outcome": "confirmed"}],
        {"report": [{"trial_id": "t4_1", "outcome": "confirmed"}]},
        '```json\n[{"trial_id":"t4_1","outcome":"confirmed"}]\n```',
    ):
        assert rt.ResolveTrials._normalize_report(report)[0]["trial_id"] == "t4_1"


def test_resolve_trials_rejects_incomplete_or_invalid_reports_without_writing(tmp_path):
    import coded_tools.resolve_trials as rt

    strategies = "- t4_1: first rule\n- t4_2: second rule\n"
    criteria = "- t4_1 ep=4 domain=rides origin=macro\n- t4_2 ep=4 domain=shops origin=macro\n"
    paths = _ledger(tmp_path, strategies, criteria)
    rt.STRATEGIES_PATH = paths["trial_strategies.md"]
    rt.CRITERIA_PATH = paths["trial_strategies_criteria.md"]
    rt.OUTCOME_PATH = paths["trial_strategies_outcome.md"]

    invalid_reports = (
        [],
        [{"trial_id": "t4_1", "outcome": "confirmed"}],
        [
            {"trial_id": "t4_1", "outcome": "confirmed"},
            {"trial_id": "t4_1", "outcome": "falsified"},
        ],
        [
            {"trial_id": "t4_1", "outcome": "confirmed"},
            {"trial_id": "t4_9", "outcome": "falsified"},
        ],
        [
            {"trial_id": "t4_1", "outcome": "confirmed"},
            {"trial_id": "t4_2", "outcome": "inconclusive"},
        ],
        [
            {"trial_id": "t4_1", "outcome": "confirmed"},
            {"trial_id": "t4_2", "outcome": "typo"},
        ],
    )
    original = {name: Path(path).read_text() for name, path in paths.items()}
    report: Any
    for report in invalid_reports:
        result = rt.ResolveTrials().invoke({"episode": 4, "report": report}, {})
        assert isinstance(result, str) and result.startswith("ERROR:"), result
        assert {name: Path(path).read_text() for name, path in paths.items()} == original


def test_resolve_trials_accepts_explicit_evidenced_inconclusive(tmp_path):
    import coded_tools.resolve_trials as rt

    paths = _ledger(
        tmp_path,
        "- t4_1: test rule\n",
        "- t4_1 ep=4 domain=rides origin=macro\n",
    )
    rt.STRATEGIES_PATH = paths["trial_strategies.md"]
    rt.CRITERIA_PATH = paths["trial_strategies_criteria.md"]
    rt.OUTCOME_PATH = paths["trial_strategies_outcome.md"]

    result = rt.ResolveTrials().invoke(
        {
            "episode": 4,
            "report": [
                {
                    "trial_id": "t4_1",
                    "outcome": "inconclusive",
                    "note": "success and failure thresholds were both unobserved",
                }
            ],
        },
        {},
    )
    assert result["kept"] == ["t4_1"]
    assert "outcome=inconclusive" in Path(paths["trial_strategies_outcome.md"]).read_text()

    # Retrying the same close-out keeps the active inconclusive trial but must
    # not append a second outcome for the same episode/trial transaction.
    repeated = rt.ResolveTrials().invoke(
        {
            "episode": 4,
            "report": [
                {
                    "trial_id": "t4_1",
                    "outcome": "inconclusive",
                    "note": "success and failure thresholds were both unobserved",
                }
            ],
        },
        {},
    )
    assert repeated["outcomes_appended"] == 0
    assert Path(paths["trial_strategies_outcome.md"]).read_text().count("ep=4 trial_id=t4_1") == 1


def test_resolve_trials_replays_pending_transaction(tmp_path, monkeypatch):
    """A failure after journaling leaves enough state for an exact retry."""
    import coded_tools.resolve_trials as rt

    paths = _ledger(
        tmp_path,
        "- t4_1: test rule\n",
        "- t4_1 ep=4 domain=rides origin=macro\n",
    )
    rt.STRATEGIES_PATH = paths["trial_strategies.md"]
    rt.CRITERIA_PATH = paths["trial_strategies_criteria.md"]
    rt.OUTCOME_PATH = paths["trial_strategies_outcome.md"]

    real_write = rt.FileIO.write_text_atomic
    failed_once = False

    def fail_strategy_once(path, content):
        nonlocal failed_once
        if path == rt.STRATEGIES_PATH and not failed_once:
            failed_once = True
            raise OSError("simulated interruption")
        return real_write(path, content)

    monkeypatch.setattr(rt.FileIO, "write_text_atomic", fail_strategy_once)
    first = rt.ResolveTrials().invoke(
        {
            "episode": 4,
            "report": [{"trial_id": "t4_1", "outcome": "falsified"}],
        },
        {},
    )
    assert str(first).startswith("ERROR:")
    assert Path(rt.ResolveTrials._pending_path()).exists()

    second = rt.ResolveTrials().invoke(
        {
            "episode": 4,
            "report": [{"trial_id": "t4_1", "outcome": "falsified"}],
        },
        {},
    )
    assert second["removed"] == ["t4_1"]
    assert not Path(rt.ResolveTrials._pending_path()).exists()
    assert Path(rt.STRATEGIES_PATH).read_text() == ""
    assert Path(rt.OUTCOME_PATH).read_text().count("ep=4 trial_id=t4_1") == 1


def test_resolve_trials_ignores_prose_report_when_no_trials_exist(tmp_path):
    tmp = tmp_path
    import coded_tools.resolve_trials as rt

    paths = _ledger(tmp, "", "")
    rt.STRATEGIES_PATH = paths["trial_strategies.md"]
    rt.CRITERIA_PATH = paths["trial_strategies_criteria.md"]
    rt.OUTCOME_PATH = paths["trial_strategies_outcome.md"]

    result = rt.ResolveTrials().invoke({"episode": 4, "report": "no active trials"}, {})
    assert result == {"kept": [], "removed": [], "outcomes_appended": 0}


def test_consultant_inputs_exist(tmp_path):
    tmp = tmp_path
    """Two read-before-write deadlocks, both observed dead in a live run.

    A consultant reads a file in the same step whose tool is that file's only
    writer. Missing file -> state_read errors -> "STOP on any tool error" aborts
    the pass -> the write never happens -> every later episode fails identically:

      last_reward.md        read by episode_end step 1; written by advance_episode step 5
      episode_checklist.md  read by episode_start step 5; written by WriteEpisodePlan, same step
    """
    from coded_tools.seed_playbooks import SeedPlaybooks

    f: Any
    for f in ("last_reward.md", "episode_checklist.md"):
        assert f in SeedPlaybooks.ENSURED_STATE_FILES, f"{f} deadlock is back"

    sp = SeedPlaybooks()
    sp.STATE_DIR, sp.SEED_DIR = tmp, tmp
    sp.invoke({"overwrite": False}, {})
    f: Any
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

    fn: Any
    for fn in (
        test_stale_trials_are_withheld,
        test_ids_are_never_recycled,
        test_macro_outcome_lines_carry_the_rule_text,
        test_micro_trials_are_never_ledgered,
        test_stranded_macro_trials_are_expired_not_kept,
        test_consultant_inputs_exist,
    ):
        with tempfile.TemporaryDirectory() as td:
            fn(td)
    print("ok")
