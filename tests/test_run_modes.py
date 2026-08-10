"""Check the file mechanics behind the three run modes.

  --fresh    archive_state() MOVES the working dir into playbook_history/<ts>_prewipe/
             and strip_learned_from_seeds() clears the mirrored rules.
  (default)  restore_champion_playbooks() copies the NEWEST champion snapshot
             over the working playbooks.
  --resume   touches none of them, so there is nothing to test here.

--fresh relocates real user state, so the guards that matter are that it destroys
nothing, never touches playbook_history/ (the only copy of every champion) or
park_state.pkl, and leaves behind an archive dir the next run won't mistake for a
champion.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # runner imports coded_tools.*
from apps.maps_park import runner  # noqa: E402


def _state(tmp: Path) -> Path:
    """A state dir shaped like the real one: two champions plus live files."""
    hist = tmp / "playbook_history"
    for stamp, body in (("20260101-000000_ep000_champion", "OLD"),
                        ("20260808-183824_ep004_champion", "BEST")):
        (hist / stamp).mkdir(parents=True)
        (hist / stamp / "playbook_rides.md").write_text(body)
    (tmp / "playbook_rides.md").write_text("working copy")
    (tmp / "champion_reward.json").write_text("{}")
    (tmp / "trial_strategies.md").write_text("trials")
    (tmp / "park_state.pkl").write_text("env")
    runner.PLAYBOOK_STATE_DIR = str(tmp)
    runner.PLAYBOOK_HISTORY_DIR = str(hist)
    return tmp


def test_restore_takes_the_newest_champion():
    with tempfile.TemporaryDirectory() as td:
        state = _state(Path(td))
        used = runner.restore_champion_playbooks()
        assert used.endswith("ep004_champion"), used            # newest, not first
        assert (state / "playbook_rides.md").read_text() == "BEST"  # working copy replaced


def test_restore_returns_none_without_a_champion():
    with tempfile.TemporaryDirectory() as td:
        runner.PLAYBOOK_STATE_DIR = td
        runner.PLAYBOOK_HISTORY_DIR = os.path.join(td, "nope")
        # -> caller falls back to the config seeds (SeedPlaybooks overwrite=True).
        assert runner.restore_champion_playbooks() is None


def test_fresh_archives_state_instead_of_deleting_it():
    with tempfile.TemporaryDirectory() as td:
        state = _state(Path(td))
        dest = Path(runner.archive_state())

        assert dest.name.endswith("_prewipe")   # never matches the *_champion glob
        assert sorted(os.listdir(state)) == ["park_state.pkl", "playbook_history"]
        # Everything that left the working dir is recoverable, not gone.
        assert sorted(p.name for p in dest.iterdir()) == [
            "champion_reward.json", "playbook_rides.md", "trial_strategies.md"]
        assert (dest / "playbook_rides.md").read_text() == "working copy"
        # --fresh must not LOAD the champion archive, but must never DESTROY it.
        assert (state / "playbook_history" / "20260808-183824_ep004_champion"
                / "playbook_rides.md").exists()
        # ...and the run that follows must not pick the prewipe dir as a champion.
        assert runner.restore_champion_playbooks().endswith("ep004_champion")


def test_strip_learned_keeps_the_baseline_and_the_header():
    """Wiping state is not enough: PromoteTrial mirrors rules into the SEEDS too."""
    from coded_tools.promote_trial import PromoteTrial

    with tempfile.TemporaryDirectory() as td:
        seed = Path(td) / "rides_strategy.md"
        seed.write_text("- hand-authored baseline\n"
                        f"{PromoteTrial.LEARNED_SECTION}\n"
                        f"- price carousels at 4 {PromoteTrial.LEARNED_MARKER}003)\n")
        PromoteTrial.SEED_DIR, original = td, PromoteTrial.SEED_DIR
        try:
            assert runner.strip_learned_from_seeds() == 1
        finally:
            PromoteTrial.SEED_DIR = original
        left = seed.read_text()
        assert PromoteTrial.LEARNED_MARKER not in left           # the promoted rule is gone
        assert "hand-authored baseline" in left                  # ...the baseline is not
        assert PromoteTrial.LEARNED_SECTION in left              # header stays; append-only needs it


if __name__ == "__main__":
    test_restore_takes_the_newest_champion()
    test_restore_returns_none_without_a_champion()
    test_fresh_archives_state_instead_of_deleting_it()
    test_strip_learned_keeps_the_baseline_and_the_header()
    print("ok")
