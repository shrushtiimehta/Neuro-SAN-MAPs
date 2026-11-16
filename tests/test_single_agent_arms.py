"""Structural guards for the two-agent solo baseline."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRIES = ROOT / "registries" / "ablations" / "single_agent"


def _agent_blocks(path: Path) -> list[str]:
    """Return top-level tool blocks that define instructions (LLM agents)."""
    src = path.read_text()
    start = re.search(r"^\s*tools\s*=\s*\[", src, re.M)
    assert start, f"{path}: missing tools array"
    body = src[start.end() :]
    blocks: list[str] = []
    depth = 0
    block_start = None
    i = 0
    while i < len(body):
        if body[i : i + 3] == '"""':
            end = body.find('"""', i + 3)
            assert end >= 0
            i = end + 3
            continue
        char = body[i]
        if char == "{":
            if depth == 0:
                block_start = i
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and block_start is not None:
                blocks.append(body[block_start : i + 1])
        i += 1
    return [block for block in blocks if re.search(r"^\s*instructions\s*=", block, re.M)]


def test_exactly_one_agent_in_each_solo_network():
    assert len(_agent_blocks(REGISTRIES / "player_solo.hocon")) == 1
    assert len(_agent_blocks(REGISTRIES / "planner_solo.hocon")) == 1


def test_solo_manifest_has_two_networks_and_no_watcher():
    manifest = (REGISTRIES / "manifest.hocon").read_text()
    assert re.search(r'"player_solo\.hocon"\s*:\s*true', manifest)
    assert re.search(r'"planner_solo\.hocon"\s*:\s*true', manifest)
    assert "watcher_solo.hocon" not in manifest


def test_solo_runner_reuses_planner_for_periodic_and_macro():
    source = (ROOT / "apps/maps_park/solo_runner.py").read_text()
    assert 'PLAYER_AGENT = "player_solo"' in source
    assert 'PLANNER_AGENT = "planner_solo"' in source
    assert "DEFAULT_MICRO_AGENT = PLANNER_AGENT" in source
    assert "DEFAULT_MACRO_AGENT = PLANNER_AGENT" in source
    assert "_planner_connection" in source


def test_solo_launcher_never_generates_frozen_context():
    source = (ROOT / "apps/maps_park/run_all.sh").read_text()
    solo_branch = source.split('if [[ "$RUNNER_NET" == *_solo', 1)[1].split("elif [[", 1)[0]
    assert "merge_context" not in solo_branch
    assert "economics_merged.md" in solo_branch
    assert "seed_playbook_all.md" in solo_branch


def test_launcher_checks_exact_registered_agent_names():
    """player_solo must never satisfy the readiness check for planner_solo."""
    source = (ROOT / "apps/maps_park/run_all.sh").read_text()
    readiness = source.split("studio_ready=0", 1)[1].split("All background services up", 1)[0]
    assert r"\"agent_name\"" in readiness
    assert "studio_ready -ne 1" in readiness


def test_solo_paths_are_isolated():
    launcher = (ROOT / "apps/maps_park/run_solo.sh").read_text()
    assert "MAPS_STATE_DIR=state_solo" in launcher
    assert "MAPS_LOG_DIR=logs/maps_park_solo" in launcher
    name: Any
    for name in ("player_solo.hocon", "planner_solo.hocon"):
        body = (REGISTRIES / name).read_text()
        assert 'maps_state_dir = "state_solo"' in body
        assert "${maps_state_dir}" in body
        assert '"state/' not in body


def test_single_agent_ablation_is_bounded_to_ten_episodes():
    launcher = (ROOT / "apps/maps_park/run_single_agent_ablation.sh").read_text()
    adapter = (ROOT / "apps/maps_park/solo_ablation_runner.py").read_text()
    assert 'MAPS_EPISODE_LIMIT="${MAPS_EPISODE_LIMIT:-10}"' in launcher
    assert "apps.maps_park.solo_ablation_runner" in launcher
    assert "run_ablation_services.sh" in launcher
    assert "manifest.hocon" in launcher
    assert "solo_runner._apply_solo_runtime()" in adapter
    assert "bounded_runner.main()" in adapter


def test_combined_hocons_preserve_role_specific_instruction_contracts():
    player = (REGISTRIES / "player_solo.hocon").read_text()
    phrase: Any
    for phrase in (
        "Current complete strategy` is TOP PRIORITY",
        "evaluate ALL four main roles",
        "AVOID REMOVE",
        "order_quantity` is required for place/modify",
        "new_x,new_y",
        "N = min(total_guests, 25)",
        "rejected twice",
    ):
        assert phrase in player, f"player role contract lost: {phrase}"

    planner = (REGISTRIES / "planner_solo.hocon").read_text()
    phrase: Any
    for phrase in (
        "Treat the best run as your floor",
        "STRUCTURAL BLOCKER",
        "An untried lever teaches more",
        "refine a proven plan; do not start from scratch",
        "Review ONLY micro trials",
        "A falsified trial is worth as much as a confirmed one",
        "intended action did not happen → not_applied",
        "Do not output separate domain",
    ):
        assert phrase in planner, f"planner role contract lost: {phrase}"
