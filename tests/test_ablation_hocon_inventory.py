"""Guards the baseline repository's canonical ablation HOCON inventory."""

from __future__ import annotations

import re
from pathlib import Path

from apps.maps_park.validate_ablations import _load

ROOT = Path(__file__).resolve().parents[1]
ABLATIONS = ROOT / "registries" / "ablations"
EXPECTED_MANIFEST_ARMS = {
    "baseline_gpt5_mini",
    "embedded_player_planner_watcher",
    "multi_player_single_planner",
    "no_self_improvement_multi",
    "no_self_improvement_single",
    "player_with_planner",
    "player_with_watcher",
    "qwen4b_multi",
    "qwen4b_single",
    "qwen4b_strong_planner_multi",
    "qwen4b_strong_planner_single",
    "full_status_subagents",
    "g_memory_player_planner_watcher",
    "single_agent",
    "single_agent_gpt5_mini",
    "single_player_multi_planner_watcher",
    "unstructured_player_planner_watcher",
}


def test_baseline_contains_every_ablation_manifest_and_hocon() -> None:
    """Every known arm must have a manifest whose enabled HOCONs parse."""
    actual_arms = {path.parent.name for path in ABLATIONS.glob("*/manifest.hocon")}
    assert actual_arms == EXPECTED_MANIFEST_ARMS

    for arm in sorted(EXPECTED_MANIFEST_ARMS):
        arm_dir = ABLATIONS / arm
        manifest = {str(name).strip('"'): enabled for name, enabled in _load(arm_dir / "manifest.hocon").items()}
        assert manifest, f"{arm} manifest is empty"
        assert all(enabled is True for enabled in manifest.values())
        for filename in manifest:
            config = arm_dir / filename
            assert config.is_file(), f"{arm} manifest is missing {filename}"
            parsed = _load(config)
            assert parsed.get("tools"), f"{arm}/{filename} has no tools"


def test_all_registry_execution_timeouts_are_12000() -> None:
    """No baseline or ablation network may retain a shorter execution cap."""
    assignments: list[tuple[Path, int]] = []
    for path in sorted((ROOT / "registries").rglob("*.hocon")):
        for value in re.findall(
            r"\bmax_execution_seconds\s*=\s*(\d+)",
            path.read_text(encoding="utf-8"),
        ):
            assignments.append((path.relative_to(ROOT), int(value)))

    assert assignments, "no max_execution_seconds assignments found"
    assert all(value == 12000 for _, value in assignments), assignments
