"""Keep control-arm prompts inherited verbatim from their canonical networks.

Only experiment infrastructure may be overlaid here. In particular, do not
rewrite, rename, or paraphrase an instruction string in a derived HOCON. The
generated files inline dependencies because Neuro SAN resolves nested HOCON
includes relative to the including file; the agent instruction values themselves
remain byte-for-byte identical to their canonical source.
"""

from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


AAOSA = ROOT / "registries" / "aaosa_basic.hocon"
LLM = ROOT / "config" / "llm_config.hocon"
LLM_MINI = ROOT / "config" / "llm_config_gpt5_mini.hocon"
LLM_QWEN_4B = ROOT / "config" / "llm_config_qwen4b.hocon"
LLM_QWEN_30B_A3B = ROOT / "config" / "llm_config_qwen30b_a3b.hocon"


def _inlined(path: Path, *, strip_outer_object: bool = False) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    if strip_outer_object:
        first = next(i for i, line in enumerate(lines) if line.strip() == "{")
        last = max(i for i, line in enumerate(lines) if line.strip() == "}")
        lines = [line for i, line in enumerate(lines) if i not in {first, last}]
    relative = path.relative_to(ROOT).as_posix()
    return f"# BEGIN INLINED: {relative}\n" + "\n".join(lines) + f"\n# END INLINED: {relative}\n"


def _canonical(
    source: str,
    *,
    player_overlay: str = "",
    llm_source: Path = LLM,
) -> str:
    """Return a self-contained canonical graph without changing any prompt."""
    text = (ROOT / source).read_text(encoding="utf-8")
    aaosa = _inlined(AAOSA)
    text = text.replace('include "registries/aaosa_basic.hocon"\n', aaosa, 1)
    text = text.replace(
        'include "config/llm_config.hocon",\n',
        _inlined(llm_source, strip_outer_object=True),
        1,
    )
    if player_overlay:
        text = text.replace(aaosa, aaosa + "\n" + player_overlay.strip() + "\n", 1)
    return text


def _solo_model(source: str, *, player: bool, model_name: str, llm_source: Path, model_class: str) -> str:
    """Copy a Solo graph verbatim and change only its model configuration."""
    text = (ROOT / source).read_text(encoding="utf-8")
    if player:
        overlay = _model_overlay(model_name, llm_source, model_class)
        text = text.replace('    model_name = "gpt-5.5"\n', overlay, 1)
        return text
    begin = "# BEGIN INLINED: config/llm_config.hocon\n"
    end = "# END INLINED: config/llm_config.hocon\n"
    start = text.index(begin)
    stop = text.index(end, start) + len(end)
    return text[:start] + _inlined(llm_source, strip_outer_object=True) + text[stop:]


def _model_overlay(model_name: str, llm_source: Path, model_class: str) -> str:
    """Render a top-level player-model override after the canonical defaults."""
    config = _inlined(llm_source, strip_outer_object=True)
    return f'    class = "{model_class}"\n    model_name = "{model_name}"\n{config}'


def _player_model(source: str, *, model_name: str, llm_source: Path, model_class: str) -> str:
    """Keep a canonical player graph and overlay one experiment model."""
    return _canonical(
        source,
        player_overlay=_model_overlay(model_name, llm_source, model_class),
    )


PLAYER_52 = """
# Model-only experiment setting; prompt/tool behavior comes from player.hocon.
model_name = "gpt-5.2"
llm_config = {
    class = "openai"
    model_name = "gpt-5.2"
}
"""

PLAYER_MINI = """
# Model-only experiment setting; prompt/tool behavior comes from the included player.
model_name = "gpt-5-mini"
llm_config = {
    class = "openai"
    model_name = "gpt-5-mini"
}
"""


SHARED_PLAYER = _canonical("registries/player.hocon", player_overlay=PLAYER_52)
SHARED_PLANNER = _canonical("registries/planner.hocon")
SHARED_WATCHER = _canonical("registries/watcher.hocon")
MINI_PLAYER = _canonical("registries/player.hocon", player_overlay=PLAYER_MINI).replace(
    '"model_name": "gpt-5.5"', '"model_name": "gpt-5-mini"', 1
)
MINI_PLANNER = _canonical("registries/planner.hocon", llm_source=LLM_MINI)
MINI_WATCHER = _canonical("registries/watcher.hocon", llm_source=LLM_MINI)
QWEN_4B_PLAYER = _player_model(
    "registries/player.hocon",
    model_name="qwen3:4b",
    llm_source=LLM_QWEN_4B,
    model_class="ollama",
)
QWEN_4B_PLANNER = _canonical("registries/planner.hocon", llm_source=LLM_QWEN_4B)
QWEN_4B_WATCHER = _canonical("registries/watcher.hocon", llm_source=LLM_QWEN_4B)
QWEN_STRONG_PLANNER = _canonical("registries/planner.hocon", llm_source=LLM_QWEN_30B_A3B)
QWEN_STRONG_WATCHER = _canonical("registries/watcher.hocon", llm_source=LLM_QWEN_30B_A3B)
FIXED_MULTI_PLAYER = _canonical("registries/player.hocon")
FIXED_MULTI_PLANNER = _canonical("registries/planner.hocon")
FIXED_MULTI_WATCHER = _canonical("registries/watcher.hocon")
FIXED_SOLO_PLAYER = (ROOT / "registries/ablations/single_agent/player_solo.hocon").read_text(encoding="utf-8")
FIXED_SOLO_PLANNER = (ROOT / "registries/ablations/single_agent/planner_solo.hocon").read_text(encoding="utf-8")


DERIVED: dict[str, str] = {
    # Shared control graphs.
    "registries/ablations/shared/player_ablation.hocon": SHARED_PLAYER,
    "registries/ablations/shared/planner_ablation.hocon": SHARED_PLANNER,
    "registries/ablations/shared/watcher_ablation.hocon": SHARED_WATCHER,
    # Arms whose named side is the unchanged canonical control.
    "registries/ablations/player_with_watcher/player_ablation.hocon": SHARED_PLAYER,
    "registries/ablations/player_with_watcher/watcher_ablation.hocon": SHARED_WATCHER,
    "registries/ablations/player_with_planner/player_ablation.hocon": SHARED_PLAYER,
    "registries/ablations/player_with_planner/planner_ablation.hocon": SHARED_PLANNER,
    "registries/ablations/unstructured_player_planner_watcher/player_ablation.hocon": SHARED_PLAYER,
    "registries/ablations/unstructured_player_planner_watcher/watcher_ablation.hocon": SHARED_WATCHER,
    "registries/ablations/multi_player_single_planner/player_ablation.hocon": SHARED_PLAYER,
    "registries/ablations/single_player_multi_planner_watcher/planner_ablation.hocon": SHARED_PLANNER,
    "registries/ablations/single_player_multi_planner_watcher/watcher_ablation.hocon": SHARED_WATCHER,
    # Model-only controls: identical instructions, different model configuration.
    "registries/ablations/baseline_gpt5_mini/player.hocon": MINI_PLAYER,
    "registries/ablations/baseline_gpt5_mini/planner.hocon": MINI_PLANNER,
    "registries/ablations/baseline_gpt5_mini/watcher.hocon": MINI_WATCHER,
    "registries/ablations/single_agent_gpt5_mini/player_solo.hocon": _solo_model(
        "registries/ablations/single_agent/player_solo.hocon",
        player=True,
        model_name="gpt-5-mini",
        llm_source=LLM_MINI,
        model_class="openai",
    ),
    "registries/ablations/single_agent_gpt5_mini/planner_solo.hocon": _solo_model(
        "registries/ablations/single_agent/planner_solo.hocon",
        player=False,
        model_name="gpt-5-mini",
        llm_source=LLM_MINI,
        model_class="openai",
    ),
    # Qwen topology controls and strong-planner treatment arms.
    "registries/ablations/qwen4b_multi/player.hocon": QWEN_4B_PLAYER,
    "registries/ablations/qwen4b_multi/planner.hocon": QWEN_4B_PLANNER,
    "registries/ablations/qwen4b_multi/watcher.hocon": QWEN_4B_WATCHER,
    "registries/ablations/qwen4b_single/player_solo.hocon": _solo_model(
        "registries/ablations/single_agent/player_solo.hocon",
        player=True,
        model_name="qwen3:4b",
        llm_source=LLM_QWEN_4B,
        model_class="ollama",
    ),
    "registries/ablations/qwen4b_single/planner_solo.hocon": _solo_model(
        "registries/ablations/single_agent/planner_solo.hocon",
        player=False,
        model_name="qwen3:4b",
        llm_source=LLM_QWEN_4B,
        model_class="ollama",
    ),
    "registries/ablations/qwen4b_strong_planner_multi/player.hocon": QWEN_4B_PLAYER,
    "registries/ablations/qwen4b_strong_planner_multi/planner.hocon": QWEN_STRONG_PLANNER,
    "registries/ablations/qwen4b_strong_planner_multi/watcher.hocon": QWEN_STRONG_WATCHER,
    "registries/ablations/qwen4b_strong_planner_single/player_solo.hocon": _solo_model(
        "registries/ablations/single_agent/player_solo.hocon",
        player=True,
        model_name="qwen3:4b",
        llm_source=LLM_QWEN_4B,
        model_class="ollama",
    ),
    "registries/ablations/qwen4b_strong_planner_single/planner_solo.hocon": _solo_model(
        "registries/ablations/single_agent/planner_solo.hocon",
        player=False,
        model_name="qwen3:30b-a3b",
        llm_source=LLM_QWEN_30B_A3B,
        model_class="ollama",
    ),
    # No-carryover baselines keep every strategy network active within an episode.
    "registries/ablations/no_self_improvement_multi/player.hocon": FIXED_MULTI_PLAYER,
    "registries/ablations/no_self_improvement_multi/planner.hocon": FIXED_MULTI_PLANNER,
    "registries/ablations/no_self_improvement_multi/watcher.hocon": FIXED_MULTI_WATCHER,
    "registries/ablations/no_self_improvement_single/player_solo.hocon": FIXED_SOLO_PLAYER,
    "registries/ablations/no_self_improvement_single/planner_solo.hocon": FIXED_SOLO_PLANNER,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if any generated control HOCON differs; do not write files.",
    )
    args = parser.parse_args()

    drifted: list[str] = []
    for relative, expected in DERIVED.items():
        path = ROOT / relative
        actual = path.read_text(encoding="utf-8") if path.exists() else ""
        if actual == expected:
            continue
        drifted.append(relative)
        if not args.check:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(expected, encoding="utf-8")

    if args.check and drifted:
        raise SystemExit("Derived prompt HOCON drifted: " + ", ".join(drifted))
    action = "verified" if args.check else "synchronized"
    print(f"{action} {len(DERIVED)} derived prompt HOCON files")


if __name__ == "__main__":
    main()
