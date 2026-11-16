# Copyright © 2025-2026 Cognizant Technology Solutions Corp, www.cognizant.com.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# END COPYRIGHT
"""
The solo arm: ONE merged playbook + ONE merged economics doc (run_solo.sh).

Three things can break silently here, so they are checked rather than remembered:

  1. BASELINE COMPLETENESS. The merged seed must carry every non-learned line
     from all seven source playbooks rather than a hand-written abbreviation.
  2. ANCHOR UNIQUENESS. WriteEpisodePlan and PromoteTrial both find their target
     by FIRST match. The merged file must have one complete-strategy block, no
     domain-summary blocks, and one '## Learned rules' target.
  3. THE OTHER TWO ARMS. The merged file is opted into explicitly, so the
     per-domain arms must take exactly the path they always took.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from pyhocon import ConfigFactory

from coded_tools.promote_trial import PromoteTrial
from coded_tools.seed_playbooks import SeedPlaybooks
from coded_tools.write_episode_plan import WriteEpisodePlan

ROOT = Path(__file__).resolve().parents[1]
REGISTRIES = ROOT / "registries" / "ablations" / "single_agent"
CONFIG = str(ROOT / "coded_tools" / "ablations" / "single_agent" / "config_files")
BASE_CONFIG = ROOT / "coded_tools" / "config_files"
MERGED_SEED = "seed_playbook_all.md"
LEARNED_SECTION = "## Learned rules (promoted from prior runs)"


def test_merged_playbook_anchors_are_unique():
    """One complete strategy, no domain summaries, one empty learned section."""
    text = (Path(CONFIG) / MERGED_SEED).read_text()

    marker: Any
    for marker in ("<!-- STRATEGY_SUMMARY:BEGIN -->", "<!-- STRATEGY_SUMMARY:END -->"):
        assert text.count(marker) == 1, f"{marker} appears {text.count(marker)}x; writes would collide"
    assert "PLAYBOOK_SUMMARY" not in text
    assert "Current domain briefs" not in text
    assert text.count(LEARNED_SECTION) == 1

    domains = ("coordinator", "rides", "shops", "staff", "research", "layout", "survey")
    domain: Any
    for domain in domains:
        assert f"\n## {domain.upper()}\n" in text, f"{domain} section missing from merged playbook"
    assert not text.split(LEARNED_SECTION, 1)[1].strip(), "source learned rules leaked into solo seed"
    assert "(learned ep" not in text


def test_merged_playbook_keeps_every_non_learned_source_line():
    """All baseline prose survives; only headings/markers and learned rules differ."""
    merged = (Path(CONFIG) / MERGED_SEED).read_text().splitlines()
    merged_lines = set(merged)
    domains = ("coordinator", "rides", "shops", "staff", "research", "layout", "survey")
    domain: Any
    for domain in domains:
        source = (BASE_CONFIG / f"seed_playbook_{domain}.md").read_text()
        baseline = source.split(LEARNED_SECTION, 1)[0]
        line: Any
        for line in baseline.splitlines():
            if not line.strip() or line.startswith("#") or line.startswith("<!-- PLAYBOOK_SUMMARY:"):
                continue
            assert line in merged_lines, f"{domain} baseline line lost from merged seed: {line}"


def test_merged_economics_keeps_what_the_unified_table_drops():
    """The raw per-domain constants must survive the merge, not just the summary."""
    text = (Path(CONFIG) / "economics_merged.md").read_text()
    constant: Any
    for constant in (
        "break_even_days",  # rides raw table only
        "cleaning_threshold",  # staff raw constants only
        "restock_threshold",  # staff raw constants only
        "points_required",  # research raw table only
        "runs to repay",
    ):  # the unified table's derived column
        assert constant in text, f"{constant} lost in the economics merge"


def test_solo_arm_seeds_one_playbook_and_the_others_seed_seven():
    """SeedPlaybooks follows the seed dir: one merged seed in, one playbook out."""
    with tempfile.TemporaryDirectory() as td:
        seeds, state = Path(td) / "seeds", Path(td) / "state"
        seeds.mkdir(parents=True)
        shutil.copy2(Path(CONFIG) / MERGED_SEED, seeds / MERGED_SEED)
        original = SeedPlaybooks.SEED_DIR, SeedPlaybooks.STATE_DIR
        original_merged = SeedPlaybooks.MERGED
        SeedPlaybooks.SEED_DIR, SeedPlaybooks.STATE_DIR = str(seeds), str(state)
        SeedPlaybooks.MERGED = True
        try:
            result = SeedPlaybooks().invoke({"overwrite": True}, {})
            assert result["seeded"] == ["playbook_all"], result
            assert (state / "playbook_all.md").read_text().count("## RIDES\n") == 1

            # Regression guard for the two per-domain arms: no merged seed, so the
            # seven are laid down exactly as before.
            (seeds / MERGED_SEED).unlink()
            name: Any
            seed_file: Any
            for name, seed_file in SeedPlaybooks.PLAYBOOKS.items():
                (seeds / seed_file).write_text(f"# {name}\n")
            SeedPlaybooks.MERGED = False
            per_domain = SeedPlaybooks().invoke({"overwrite": True}, {})
            assert sorted(per_domain["seeded"]) == sorted(SeedPlaybooks.PLAYBOOKS), per_domain
        finally:
            SeedPlaybooks.SEED_DIR, SeedPlaybooks.STATE_DIR = original
            SeedPlaybooks.MERGED = original_merged


def test_episode_plan_writes_one_complete_strategy_into_the_playbook():
    """Solo writes/replaces one complete strategy and never writes domain briefs."""
    with tempfile.TemporaryDirectory() as td:
        shutil.copy2(Path(CONFIG) / MERGED_SEED, Path(td) / MERGED_SEED)
        playbook = Path(td) / "playbook_all.md"
        playbook.write_text((Path(td) / MERGED_SEED).read_text())
        original, WriteEpisodePlan.STATE_DIR = WriteEpisodePlan.STATE_DIR, td
        original_merged, WriteEpisodePlan.MERGED = WriteEpisodePlan.MERGED, True

        args = {"checklist_items": ["turns 1-50: build", "turns 51-100: upgrade"], "strategy": "COMPLETE-STRATEGY-V1"}
        out = WriteEpisodePlan().invoke(dict(args), {})
        assert out["playbook_summaries_written"] == [], out
        assert out["playbook_coordinator_path"] == str(playbook)
        body = playbook.read_text()
        assert "COMPLETE-STRATEGY-V1" in body
        assert "PLAYBOOK_SUMMARY" not in body

        # Second episode replaces the strategy rather than stacking it, and the
        # hand-authored guidance underneath is untouched.
        args["strategy"] = "COMPLETE-STRATEGY-V2"
        WriteEpisodePlan().invoke(dict(args), {})
        body = playbook.read_text()
        assert "COMPLETE-STRATEGY-V1" not in body
        assert "COMPLETE-STRATEGY-V2" in body
        assert body.count("<!-- STRATEGY_SUMMARY:BEGIN -->") == 1
        assert "## LAYOUT\n" in body and LEARNED_SECTION in body
        snapshot = (Path(td) / "plan_current.json").read_text()
        assert '"strategy": "COMPLETE-STRATEGY-V2"' in snapshot
        assert "strategy_summary" not in snapshot and "playbook_summaries" not in snapshot
        WriteEpisodePlan.STATE_DIR = original
        WriteEpisodePlan.MERGED = original_merged


def test_promotion_tags_domain_without_mutating_frozen_seed():
    """Confirmed rules change live state while the experiment input stays fixed."""
    with tempfile.TemporaryDirectory() as td:
        seeds, state = Path(td) / "seeds", Path(td) / "state"
        seeds.mkdir()
        state.mkdir()
        shutil.copy2(Path(CONFIG) / MERGED_SEED, seeds / MERGED_SEED)
        (state / "playbook_all.md").write_text((seeds / MERGED_SEED).read_text())
        original = PromoteTrial.SEED_DIR, PromoteTrial.STATE_DIR
        original_merged = PromoteTrial.MERGED
        PromoteTrial.SEED_DIR, PromoteTrial.STATE_DIR = str(seeds), str(state)
        PromoteTrial.MERGED = True

        out = PromoteTrial().invoke(
            {
                "domain": "rides",
                "edit_type": "add_line",
                "new_text": "Place the best unlocked tier first",
                "episode": 12,
                "section": "Learned rules (promoted from prior runs)",
            },
            {},
        )
        assert out["action_taken"] == "promoted" and out["playbook"] == "playbook_all", out
        assert out["seed_mirror"] == "immutable_seed_skipped", out
        assert out["line"].startswith("[rides] ") and out["line"].endswith("(learned ep12)")
        # Present in live state, absent from the checked-in experiment input.
        assert out["line"] in (state / "playbook_all.md").read_text()
        assert out["line"] not in (seeds / MERGED_SEED).read_text()

        # Demotion still self-corrects, and still protects the baseline.
        back = PromoteTrial().invoke(
            {"domain": "rides", "edit_type": "remove_line", "find_text": "Place the best unlocked tier first"}, {}
        )
        assert back["action_taken"] == "demoted" and back["seed_mirror"] == "immutable_seed_skipped", back
        assert out["line"] not in (state / "playbook_all.md").read_text()
        PromoteTrial.SEED_DIR, PromoteTrial.STATE_DIR = original
        PromoteTrial.MERGED = original_merged


def test_solo_networks_are_registered_and_read_the_merged_files():
    manifest = (REGISTRIES / "manifest.hocon").read_text()
    name: Any
    for name in ("player_solo.hocon", "planner_solo.hocon"):
        assert re.search(rf'"{re.escape(name)}"\s*:\s*true', manifest), (
            f"{name} is not registered true; the server will not serve it"
        )
        body = (REGISTRIES / name).read_text()
        config = ConfigFactory.parse_file(str(REGISTRIES / name), resolve=True)
        state_read = next(tool for tool in config["tools"] if tool["name"] == "state_read")
        paths = dict(state_read["args"]["name_map"])
        assert paths["playbook"] == "state_solo/playbook_all.md", paths.get("playbook")
        assert paths["economics"] == "coded_tools/ablations/single_agent/config_files/economics_merged.md"
        if name == "planner_solo.hocon":
            assert paths["seed_playbook"] == "coded_tools/ablations/single_agent/config_files/seed_playbook_all.md"
        # No per-domain leftovers, and nothing pointing at another arm's tree.
        assert not [k for k in paths if re.match(r"(playbook|economics|seed_playbook)_", k)], paths
        key: Any
        path: Any
        for key, path in paths.items():
            assert not path.startswith(("state/", "state_single_agent/")), f"{name}: {key} -> {path}"
        # The merged playbook is bigger than StateRead's default cap.
        assert "max_content_chars" in body, f"{name}: the ~28 KB playbook would be truncated"

    assert '"watcher_solo.hocon"' not in manifest

    planner = (REGISTRIES / "planner_solo.hocon").read_text()
    write_plan = planner.split('name = "WriteEpisodePlan"', 1)[1].split('name = "PromoteTrial"', 1)[0]
    assert "strategy =" in write_plan
    assert "strategy_summary" not in write_plan
    assert "playbook_summaries" not in write_plan
