#!/usr/bin/env python3
"""Render presentation charts from the MAPs experiment log directories.

Only completed episodes contribute to average and maximum scores. The solo
chart includes all three replicates. For the embedded arm, the current partial
episode and remaining reserved episode slots are shown explicitly so the chart
can be refreshed while the run continues. Episode labels are one-based even
though the source logs use zero-based episode IDs.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from datetime import timezone
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
from matplotlib.ticker import MaxNLocator
from PIL import Image
from PIL import ImageDraw
from PIL import ImageFont

ROOT = Path(__file__).resolve().parents[1]
EMBEDDED_ROOT = ROOT.parent / "neuro-san-studio-ablation-embedded-player-planner-watcher"

BACKGROUND = "#F5F7FB"
PANEL = "#FFFFFF"
INK = "#111827"
MUTED = "#667085"
GRID = "#DDE3EC"
PARTIAL = "#F97316"
PENDING = "#C7CFDB"

# Comparison data supplied with the plotting request. Cost fields are
# intentionally omitted: the presentation is about score outcomes only.
PROVIDED_BASELINE = {
    0: 437459.0,
    1: 662771.0,
    2: 1501444.0,
    3: 450861.0,
    4: 754574.0,
    5: 445019.0,
    6: 681863.0,
    7: 909396.0,
    8: 622802.0,
    9: 1165773.0,
    10: 1104339.0,
}

SOLO_LOG_DIRS = (
    ROOT / "logs/maps_park_solo/prior-runs/20260912-153544",
    ROOT / "logs/maps_park_solo/prior-runs/20260912-223114",
    ROOT / "logs/maps_park_solo",
)
SOLO_COLORS = ("#A78BFA", "#7C3AED", "#4C1D95")


@dataclass(frozen=True)
class RunSpec:
    slug: str
    title: str
    subtitle: str
    log_dir: Path
    color: str
    expected_episodes: int | None = None
    show_incomplete: bool = False
    live: bool = False


@dataclass(frozen=True)
class EpisodeResult:
    episode: int
    step: int
    reward: float
    complete: bool


RUNS = (
    RunSpec(
        slug="01_baseline",
        title="Original Baseline",
        subtitle="Canonical multi-network player + planner + watcher",
        log_dir=ROOT / "logs/maps_park/prior-runs/20260819-233018",
        color="#2563EB",
    ),
    RunSpec(
        slug="02_solo_ablation",
        title="Solo Ablation",
        subtitle="One player agent + one combined planner/watcher agent",
        log_dir=ROOT / "logs/maps_park_solo",
        color="#7C3AED",
    ),
    RunSpec(
        slug="03_watcher_only",
        title="Watcher-Only Ablation",
        subtitle="Canonical player network + periodic watcher; planner disabled",
        log_dir=ROOT / "logs/maps_ablation_player_with_watcher",
        color="#0F9F8F",
        expected_episodes=7,
    ),
    RunSpec(
        slug="04_planner_only",
        title="Planner-Only Ablation",
        subtitle="Canonical player network + episode planner; watcher disabled",
        log_dir=ROOT / "logs/maps_ablation_player_with_planner",
        color="#D97706",
        expected_episodes=7,
    ),
    RunSpec(
        slug="05_embedded_player_planner_watcher",
        title="Embedded Player + Planner + Watcher",
        subtitle="All three roles embedded in one Neuro SAN network",
        log_dir=EMBEDDED_ROOT / "logs/maps_ablation_embedded_player_planner_watcher",
        color="#DB2777",
        expected_episodes=7,
        show_incomplete=True,
        live=True,
    ),
    RunSpec(
        slug="06_unstructured_planning",
        title="Unstructured Planning Ablation",
        subtitle="Player + watcher + trial-free planner with post-episode learning",
        log_dir=ROOT / "logs/maps_ablation_unstructured_player_planner_watcher",
        color="#16A34A",
        expected_episodes=7,
    ),
)


def _episode_number(path: Path) -> int:
    match = re.search(r"run\.ep(\d+)\.jsonl$", path.name)
    if not match:
        raise ValueError(f"unexpected episode filename: {path}")
    return int(match.group(1))


def _last_record(path: Path) -> dict:
    last: dict | None = None
    with path.open("r", encoding="utf-8") as handle:
        line: Any
        for line in handle:
            line = line.strip()
            if not line:
                continue
            last = json.loads(line)
    if last is None:
        raise ValueError(f"empty episode log: {path}")
    return last


def load_results(log_dir: Path) -> list[EpisodeResult]:
    if not log_dir.is_dir():
        raise FileNotFoundError(f"log directory not found: {log_dir}")

    results: list[EpisodeResult] = []
    path: Any
    for path in sorted(log_dir.glob("run.ep*.jsonl"), key=_episode_number):
        record = _last_record(path)
        episode = int(record.get("episode", _episode_number(path)))
        step = int(record.get("step", 0))
        reward = float(record.get("cumulative_reward", 0.0))
        complete = bool(record.get("done", False)) or step >= 100
        results.append(EpisodeResult(episode, step, reward, complete))
    return results


def compact(value: float) -> str:
    absolute = abs(value)
    if absolute >= 1_000_000:
        return f"{value / 1_000_000:.2f}M"
    if absolute >= 1_000:
        return f"{value / 1_000:.0f}K"
    return f"{value:.0f}"


def exact(value: float) -> str:
    return f"{value:,.0f}"


def display_episode(episode: int) -> int:
    """Convert the zero-based log ID to the one-based presentation label."""
    return episode + 1


def _rounded_ceiling(value: float) -> float:
    if value <= 0:
        return 1.0
    exponent = 10 ** math.floor(math.log10(value))
    normalized = value / exponent
    threshold: Any
    for threshold in (1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.5, 10.0):
        if normalized <= threshold:
            return threshold * exponent
    return 10.0 * exponent


def _metric(fig: plt.Figure, y: float, label: str, value: str, detail: str = "") -> None:
    fig.text(0.795, y, label.upper(), color=MUTED, fontsize=10, fontweight="bold")
    fig.text(0.795, y - 0.040, value, color=INK, fontsize=22, fontweight="bold")
    if detail:
        fig.text(0.795, y - 0.070, detail, color=MUTED, fontsize=9.5)


def render_chart(spec: RunSpec, output_dir: Path, snapshot: datetime) -> tuple[Path, dict]:
    results = load_results(spec.log_dir)
    completed = [result for result in results if result.complete]
    incomplete = [result for result in results if not result.complete]
    if not completed:
        raise ValueError(f"no completed episodes in {spec.log_dir}")

    completed_by_episode = {result.episode: result for result in completed}
    incomplete_by_episode = {result.episode: result for result in incomplete}

    if spec.expected_episodes is None:
        episode_ids = sorted(completed_by_episode)
    else:
        episode_ids = list(range(spec.expected_episodes))

    rewards = [result.reward for result in completed]
    average = sum(rewards) / len(rewards)
    best = max(completed, key=lambda result: result.reward)

    visible_values = [completed_by_episode[e].reward for e in episode_ids if e in completed_by_episode]
    if spec.show_incomplete:
        visible_values.extend(incomplete_by_episode[e].reward for e in episode_ids if e in incomplete_by_episode)
    max_value = max(visible_values + [average])
    y_max = _rounded_ceiling(max_value * 1.22)

    fig = plt.figure(figsize=(16, 9), dpi=120, facecolor=BACKGROUND)
    ax = fig.add_axes((0.075, 0.175, 0.655, 0.625), facecolor=PANEL)

    # Presentation header and status pill.
    fig.text(0.075, 0.925, "MAPs PARK • ABLATION RESULTS", color=spec.color, fontsize=11, fontweight="bold")
    fig.text(0.075, 0.865, spec.title, color=INK, fontsize=29, fontweight="bold")
    fig.text(0.075, 0.825, spec.subtitle, color=MUTED, fontsize=13)

    if spec.live:
        status_text = "RUNNING SNAPSHOT"
        status_color = PARTIAL
    else:
        status_text = "RUN COMPLETE" if not incomplete else "COMPLETED EPISODES"
        status_color = spec.color
    fig.text(
        0.925,
        0.913,
        status_text,
        ha="right",
        va="center",
        color="#FFFFFF",
        fontsize=9.5,
        fontweight="bold",
        bbox={"boxstyle": "round,pad=0.65", "facecolor": status_color, "edgecolor": "none"},
    )

    x_positions = list(range(len(episode_ids)))
    bar_width = 0.68
    legend_handles: list[mpatches.Patch] = []

    x: Any
    episode: Any
    for x, episode in zip(x_positions, episode_ids):
        if episode in completed_by_episode:
            result = completed_by_episode[episode]
            ax.bar(x, result.reward, width=bar_width, color=spec.color, edgecolor=spec.color, linewidth=1.2, zorder=3)
            ax.text(
                x,
                result.reward + y_max * 0.024,
                compact(result.reward),
                ha="center",
                va="bottom",
                fontsize=10.5,
                color=INK,
                fontweight="bold",
            )
        elif spec.show_incomplete and episode in incomplete_by_episode:
            result = incomplete_by_episode[episode]
            ax.bar(
                x,
                result.reward,
                width=bar_width,
                color=PARTIAL,
                edgecolor="#C2410C",
                linewidth=1.3,
                hatch="///",
                alpha=0.86,
                zorder=3,
            )
            ax.text(
                x,
                result.reward + y_max * 0.024,
                compact(result.reward),
                ha="center",
                va="bottom",
                fontsize=10.5,
                color=INK,
                fontweight="bold",
            )
            ax.text(
                x,
                max(result.reward * 0.50, y_max * 0.045),
                f"STEP {result.step}",
                ha="center",
                va="center",
                rotation=90,
                fontsize=9,
                color="#FFFFFF",
                fontweight="bold",
                zorder=4,
            )
        elif spec.show_incomplete:
            placeholder_height = y_max * 0.045
            ax.bar(
                x,
                placeholder_height,
                width=bar_width,
                color="none",
                edgecolor=PENDING,
                linewidth=1.7,
                linestyle=(0, (4, 3)),
                zorder=3,
            )
            ax.text(
                x,
                placeholder_height + y_max * 0.025,
                "RESERVED",
                ha="center",
                va="bottom",
                fontsize=8.5,
                color=MUTED,
                fontweight="bold",
            )

    ax.axhline(average, color=spec.color, linestyle=(0, (6, 4)), linewidth=1.8, alpha=0.8, zorder=2)
    ax.text(
        len(episode_ids) - 0.50,
        average + y_max * 0.015,
        f"Completed average  {compact(average)}",
        ha="right",
        va="bottom",
        color=spec.color,
        fontsize=9.5,
        fontweight="bold",
        bbox={"facecolor": PANEL, "edgecolor": "none", "pad": 2.5, "alpha": 0.88},
    )

    ax.set_xlim(-0.65, len(episode_ids) - 0.35)
    ax.set_ylim(0, y_max)
    ax.set_xticks(
        x_positions,
        [f"Episode {display_episode(episode)}" for episode in episode_ids],
    )
    ax.tick_params(axis="x", labelsize=10.5, length=0, pad=12, colors=INK)
    ax.tick_params(axis="y", labelsize=10, length=0, pad=8, colors=MUTED)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _position: compact(value)))
    ax.set_ylabel("Final cumulative score", fontsize=11, color=MUTED, labelpad=14)
    ax.grid(axis="y", color=GRID, linewidth=1.0, zorder=0)
    spine: Any
    for spine in ax.spines.values():
        spine.set_visible(False)

    # Summary panel.
    fig.patches.append(
        mpatches.FancyBboxPatch(
            (0.765, 0.175),
            0.185,
            0.625,
            boxstyle="round,pad=0.012,rounding_size=0.018",
            transform=fig.transFigure,
            facecolor=PANEL,
            edgecolor="#E4E8F0",
            linewidth=1.0,
            zorder=-1,
        )
    )
    denominator = spec.expected_episodes or len(completed)
    _metric(fig, 0.740, "Completed", f"{len(completed)} / {denominator}", "100-step episodes")
    _metric(fig, 0.585, "Average score", compact(average), "completed episodes only")
    _metric(
        fig,
        0.430,
        "Max score",
        compact(best.reward),
        f"Episode {display_episode(best.episode)} • {exact(best.reward)}",
    )

    current = max(incomplete, key=lambda result: result.episode, default=None)
    if spec.live and current is not None:
        fig.text(0.795, 0.242, "CURRENT SNAPSHOT", color=PARTIAL, fontsize=9.5, fontweight="bold")
        fig.text(
            0.795,
            0.210,
            f"Episode {display_episode(current.episode)} • Step {current.step}",
            color=INK,
            fontsize=12,
            fontweight="bold",
        )
        fig.text(0.795, 0.184, exact(current.reward), color=MUTED, fontsize=10)

    if spec.show_incomplete:
        legend_handles.extend(
            [
                mpatches.Patch(facecolor=PARTIAL, edgecolor="#C2410C", hatch="///", label="Partial snapshot"),
                mpatches.Patch(facecolor="none", edgecolor=PENDING, linestyle="--", label="Reserved episode"),
            ]
        )
        ax.legend(
            handles=legend_handles, loc="upper left", frameon=False, ncol=2, fontsize=9.5, bbox_to_anchor=(0, 1.02)
        )

    exclusion_note = ""
    if incomplete and not spec.show_incomplete:
        excluded = ", ".join(f"Ep {display_episode(r.episode)} at step {r.step}" for r in incomplete)
        exclusion_note = f" • Incomplete historical tail excluded: {excluded}"

    snapshot_text = snapshot.strftime("%Y-%m-%d %H:%M UTC")
    fig.text(
        0.075,
        0.095,
        f"Snapshot: {snapshot_text} • Final cumulative score at step 100{exclusion_note}",
        color=MUTED,
        fontsize=9.5,
    )
    fig.text(
        0.925,
        0.095,
        "Independent y-axis",
        ha="right",
        color=MUTED,
        fontsize=9.5,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{spec.slug}.png"
    fig.savefig(output_path, facecolor=BACKGROUND, dpi=120)
    plt.close(fig)

    metadata = {
        "title": spec.title,
        "source": str(spec.log_dir),
        "completed_episodes": len(completed),
        "average_completed_score": average,
        "max_score": best.reward,
        "max_score_episode": display_episode(best.episode),
        "incomplete": [
            {
                "episode": display_episode(result.episode),
                "step": result.step,
                "score": result.reward,
                "complete": result.complete,
            }
            for result in incomplete
        ],
        "image": str(output_path),
    }
    return output_path, metadata


def render_solo_chart(output_dir: Path, snapshot: datetime) -> tuple[Path, dict]:
    """Render every solo replicate as a distinct grouped-bar series."""
    runs = [load_results(log_dir) for log_dir in SOLO_LOG_DIRS]
    completed_runs = [[result for result in run if result.complete] for run in runs]
    completed = [result for run in completed_runs for result in run]
    if not completed:
        raise ValueError("no completed solo episodes")

    by_run = [{result.episode: result for result in run} for run in completed_runs]
    max_episode = max(result.episode for result in completed)
    episode_ids = list(range(max_episode + 1))
    rewards = [result.reward for result in completed]
    average = sum(rewards) / len(rewards)
    best = max(completed, key=lambda result: result.reward)
    best_run = next(index for index, run in enumerate(completed_runs, start=1) if best in run)
    y_max = _rounded_ceiling(max(max(rewards), average) * 1.22)

    fig = plt.figure(figsize=(16, 9), dpi=120, facecolor=BACKGROUND)
    ax = fig.add_axes((0.075, 0.175, 0.655, 0.625), facecolor=PANEL)
    fig.text(0.075, 0.925, "MAPs PARK • ABLATION RESULTS", color=SOLO_COLORS[1], fontsize=11, fontweight="bold")
    fig.text(0.075, 0.865, "Solo Ablation — Three Runs", color=INK, fontsize=29, fontweight="bold")
    fig.text(0.075, 0.825, "One player agent + one combined planner/watcher agent", color=MUTED, fontsize=13)
    fig.text(
        0.925,
        0.913,
        "3 RUNS",
        ha="right",
        va="center",
        color="#FFFFFF",
        fontsize=9.5,
        fontweight="bold",
        bbox={"boxstyle": "round,pad=0.65", "facecolor": SOLO_COLORS[1], "edgecolor": "none"},
    )

    xs = list(range(len(episode_ids)))
    width = 0.24
    offsets = (-width, 0.0, width)
    run_index: Any
    run: Any
    color: Any
    offset: Any
    for run_index, (run, color, offset) in enumerate(zip(by_run, SOLO_COLORS, offsets), start=1):
        x: Any
        episode: Any
        for x, episode in zip(xs, episode_ids):
            result = run.get(episode)
            if result is None:
                continue
            ax.bar(
                x + offset, result.reward, width=width * 0.92, color=color, edgecolor=color, linewidth=1.0, zorder=3
            )
            ax.text(
                x + offset,
                result.reward + y_max * 0.018,
                compact(result.reward),
                ha="center",
                va="bottom",
                fontsize=7.3,
                color=color,
                fontweight="bold",
            )

    ax.axhline(average, color=SOLO_COLORS[1], linestyle=(0, (6, 4)), linewidth=1.8, alpha=0.82, zorder=2)
    ax.text(
        len(episode_ids) - 0.45,
        average + y_max * 0.015,
        f"Overall average  {compact(average)}",
        ha="right",
        va="bottom",
        color=SOLO_COLORS[1],
        fontsize=9.5,
        fontweight="bold",
        bbox={"facecolor": PANEL, "edgecolor": "none", "pad": 2.5, "alpha": 0.88},
    )
    legend = [
        mpatches.Patch(facecolor=color, label=f"Solo run {index} (n={len(run)})")
        for index, (run, color) in enumerate(zip(completed_runs, SOLO_COLORS), start=1)
    ]
    ax.legend(handles=legend, loc="upper left", frameon=False, ncol=3, fontsize=9.2, bbox_to_anchor=(0, 1.02))
    ax.set_xlim(-0.65, len(episode_ids) - 0.35)
    ax.set_ylim(0, y_max)
    ax.set_xticks(xs, [f"Episode {display_episode(ep)}" for ep in episode_ids])
    ax.tick_params(axis="x", labelsize=9.5, length=0, pad=12, colors=INK)
    ax.tick_params(axis="y", labelsize=10, length=0, pad=8, colors=MUTED)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _position: compact(value)))
    ax.set_ylabel("Final cumulative score", fontsize=11, color=MUTED, labelpad=14)
    ax.grid(axis="y", color=GRID, linewidth=1.0, zorder=0)
    spine: Any
    for spine in ax.spines.values():
        spine.set_visible(False)

    fig.patches.append(
        mpatches.FancyBboxPatch(
            (0.765, 0.175),
            0.185,
            0.625,
            boxstyle="round,pad=0.012,rounding_size=0.018",
            transform=fig.transFigure,
            facecolor=PANEL,
            edgecolor="#E4E8F0",
            linewidth=1.0,
            zorder=-1,
        )
    )
    _metric(fig, 0.740, "Completed", str(len(completed)), "episodes across 3 runs")
    _metric(fig, 0.585, "Average score", compact(average), "all completed episodes")
    _metric(fig, 0.430, "Max score", compact(best.reward), f"Run {best_run} • Episode {display_episode(best.episode)}")
    fig.text(0.795, 0.290, "RUN AVERAGES", color=MUTED, fontsize=10, fontweight="bold")
    index: Any
    run: Any
    for index, run in enumerate(completed_runs, start=1):
        run_average = sum(result.reward for result in run) / len(run)
        fig.text(
            0.795,
            0.290 - index * 0.038,
            f"Run {index}  {compact(run_average)}",
            color=SOLO_COLORS[index - 1],
            fontsize=10.5,
            fontweight="bold",
        )

    incomplete_notes = []
    index: Any
    run: Any
    for index, run in enumerate(runs, start=1):
        incomplete = [result for result in run if not result.complete]
        if incomplete:
            tail = max(incomplete, key=lambda result: result.episode)
            incomplete_notes.append(f"run {index} Ep {display_episode(tail.episode)} at step {tail.step}")
    exclusion = " • Incomplete tails excluded: " + ", ".join(incomplete_notes)
    fig.text(
        0.075,
        0.095,
        f"Snapshot: {snapshot.strftime('%Y-%m-%d %H:%M UTC')} • Final cumulative score at step 100{exclusion}",
        color=MUTED,
        fontsize=9.2,
    )
    fig.text(0.925, 0.095, "Shared y-axis", ha="right", color=MUTED, fontsize=9.5)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "02_solo_ablation.png"
    fig.savefig(output_path, facecolor=BACKGROUND, dpi=120)
    plt.close(fig)

    return output_path, {
        "title": "Solo Ablation — Three Runs",
        "sources": [str(path) for path in SOLO_LOG_DIRS],
        "completed_episodes": len(completed),
        "completed_by_run": [len(run) for run in completed_runs],
        "average_completed_score": average,
        "average_score_by_run": [sum(result.reward for result in run) / len(run) for run in completed_runs],
        "max_score": best.reward,
        "max_score_run": best_run,
        "max_score_episode": display_episode(best.episode),
        "image": str(output_path),
    }


def render_baseline_comparison(baseline_spec: RunSpec, output_dir: Path) -> tuple[Path, dict]:
    """Render the original and supplied baselines without cost information."""
    baseline_results = [result for result in load_results(baseline_spec.log_dir) if result.complete]
    original = {result.episode: result.reward for result in baseline_results}
    provided = PROVIDED_BASELINE
    original_average = sum(original.values()) / len(original)
    provided_average = sum(provided.values()) / len(provided)
    original_best = max(original, key=original.get)
    provided_best = max(provided, key=provided.get)
    episodes = list(range(max(max(original), max(provided)) + 1))
    y_max = _rounded_ceiling(max(max(original.values()), max(provided.values())) * 1.22)

    blue, cyan = "#2563EB", "#06A6C7"
    fig = plt.figure(figsize=(16, 9), dpi=120, facecolor=BACKGROUND)
    ax = fig.add_axes((0.075, 0.175, 0.655, 0.625), facecolor=PANEL)
    fig.text(0.075, 0.925, "MAPs PARK • BASELINE COMPARISON", color=blue, fontsize=11, fontweight="bold")
    fig.text(0.075, 0.865, "Baseline Runs — Direct Comparison", color=INK, fontsize=29, fontweight="bold")
    fig.text(
        0.075, 0.825, "Original baseline vs provided run • final cumulative score by episode", color=MUTED, fontsize=13
    )
    fig.text(
        0.925,
        0.913,
        f"{len(original) + len(provided)} COMPLETE EPISODES",
        ha="right",
        va="center",
        color="#FFFFFF",
        fontsize=9.5,
        fontweight="bold",
        bbox={"boxstyle": "round,pad=0.65", "facecolor": blue, "edgecolor": "none"},
    )

    width = 0.34
    xs = list(range(len(episodes)))
    x: Any
    episode: Any
    for x, episode in zip(xs, episodes):
        if episode in original:
            value = original[episode]
            ax.bar(x - width / 2, value, width=width, color=blue, edgecolor=blue, zorder=3)
            ax.text(
                x - width / 2,
                value + y_max * 0.018,
                compact(value),
                ha="center",
                va="bottom",
                fontsize=8.2,
                color=blue,
                fontweight="bold",
            )
        if episode in provided:
            value = provided[episode]
            ax.bar(x + width / 2, value, width=width, color=cyan, edgecolor=cyan, zorder=3)
            ax.text(
                x + width / 2,
                value + y_max * 0.018,
                compact(value),
                ha="center",
                va="bottom",
                fontsize=8.2,
                color="#047A93",
                fontweight="bold",
            )

    ax.axhline(original_average, color=blue, linestyle=(0, (6, 4)), linewidth=1.6, alpha=0.82, zorder=2)
    ax.axhline(provided_average, color=cyan, linestyle=(0, (2, 3)), linewidth=1.9, alpha=0.9, zorder=2)
    ax.legend(
        handles=[
            mpatches.Patch(facecolor=blue, label="Original baseline"),
            mpatches.Patch(facecolor=cyan, label="Provided run"),
            plt.Line2D(
                [0], [0], color=blue, linestyle=(0, (6, 4)), label=f"Original average  {compact(original_average)}"
            ),
            plt.Line2D(
                [0], [0], color=cyan, linestyle=(0, (2, 3)), label=f"Provided average  {compact(provided_average)}"
            ),
        ],
        loc="upper left",
        frameon=False,
        ncol=2,
        fontsize=9.3,
        bbox_to_anchor=(0, 1.02),
    )
    ax.set_xlim(-0.65, len(episodes) - 0.35)
    ax.set_ylim(0, y_max)
    ax.set_xticks(xs, [f"Episode {display_episode(ep)}" for ep in episodes])
    ax.tick_params(axis="x", labelsize=9.3, length=0, pad=12, colors=INK)
    ax.tick_params(axis="y", labelsize=10, length=0, pad=8, colors=MUTED)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _position: compact(value)))
    ax.set_ylabel("Final cumulative score", fontsize=11, color=MUTED, labelpad=14)
    ax.grid(axis="y", color=GRID, linewidth=1.0, zorder=0)
    spine: Any
    for spine in ax.spines.values():
        spine.set_visible(False)

    fig.patches.append(
        mpatches.FancyBboxPatch(
            (0.765, 0.175),
            0.185,
            0.625,
            boxstyle="round,pad=0.012,rounding_size=0.018",
            transform=fig.transFigure,
            facecolor=PANEL,
            edgecolor="#E4E8F0",
            linewidth=1.0,
            zorder=-1,
        )
    )
    fig.text(0.795, 0.742, "ORIGINAL BASELINE", color=blue, fontsize=10, fontweight="bold")
    fig.text(0.795, 0.700, f"{len(original)} episodes", color=INK, fontsize=19, fontweight="bold")
    fig.text(0.795, 0.660, f"Average  {compact(original_average)}", color=MUTED, fontsize=11)
    fig.text(
        0.795,
        0.620,
        f"Max  {compact(original[original_best])} • Episode {display_episode(original_best)}",
        color=MUTED,
        fontsize=10,
    )
    fig.text(0.795, 0.525, "PROVIDED RUN", color=cyan, fontsize=10, fontweight="bold")
    fig.text(0.795, 0.483, f"{len(provided)} episodes", color=INK, fontsize=19, fontweight="bold")
    fig.text(0.795, 0.443, f"Average  {compact(provided_average)}", color=MUTED, fontsize=11)
    fig.text(
        0.795,
        0.403,
        f"Max  {compact(provided[provided_best])} • Episode {display_episode(provided_best)}",
        color=MUTED,
        fontsize=10,
    )
    change = (provided_average / original_average - 1) * 100
    fig.text(0.795, 0.300, "AVERAGE CHANGE", color=MUTED, fontsize=10, fontweight="bold")
    fig.text(0.795, 0.250, f"+{change:.1f}%", color="#079455", fontsize=24, fontweight="bold")
    fig.text(
        0.075,
        0.095,
        "Original: 8 completed episodes; incomplete Episode 9 excluded • Provided run: 11 completed episodes",
        color=MUTED,
        fontsize=9.5,
    )
    fig.text(0.925, 0.095, "Shared y-axis", ha="right", color=MUTED, fontsize=9.5)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "01_baseline_comparison.png"
    fig.savefig(output_path, facecolor=BACKGROUND, dpi=120)
    plt.close(fig)
    return output_path, {
        "title": "Baseline Runs — Direct Comparison",
        "original_average_score": original_average,
        "original_max_score": original[original_best],
        "provided_average_score": provided_average,
        "provided_max_score": provided[provided_best],
        "image": str(output_path),
    }


def render_contact_sheet(paths: list[Path], output_dir: Path) -> Path:
    images = [Image.open(path).convert("RGB") for path in paths]
    cell_width, cell_height = images[0].size
    gap, header, margin = 24, 120, 24
    canvas = Image.new(
        "RGB",
        (margin * 2 + cell_width * 2 + gap, margin * 2 + header + cell_height * 3 + gap * 2),
        "#E8EDF5",
    )
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
    except OSError:
        font = ImageFont.load_default()
    draw.text((margin + 12, margin + 20), "MAPs Park — Ablation Results", fill=INK, font=font)
    index: Any
    image: Any
    for index, image in enumerate(images):
        row, column = divmod(index, 2)
        canvas.paste(
            image,
            (margin + column * (cell_width + gap), margin + header + row * (cell_height + gap)),
        )
    output_path = output_dir / "00_all_ablation_results.png"
    canvas.save(output_path, optimize=True)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "artifacts/ablation_charts_2026-09-15",
        help="Directory for the PNGs and their snapshot metadata.",
    )
    args = parser.parse_args()

    snapshot = datetime.now(timezone.utc)
    metadata: list[dict] = []
    chart_paths: list[Path] = []
    spec: Any
    for spec in RUNS:
        if spec.slug == "02_solo_ablation":
            output_path, run_metadata = render_solo_chart(args.output_dir, snapshot)
        else:
            output_path, run_metadata = render_chart(spec, args.output_dir, snapshot)
        metadata.append(run_metadata)
        print(output_path)

        if spec.slug == "01_baseline":
            comparison_path, comparison_metadata = render_baseline_comparison(spec, args.output_dir)
            chart_paths.append(comparison_path)
            metadata.append(comparison_metadata)
            print(comparison_path)
        else:
            chart_paths.append(output_path)

    contact_sheet = render_contact_sheet(chart_paths, args.output_dir)
    print(contact_sheet)

    metadata_path = args.output_dir / "snapshot_data.json"
    metadata_path.write_text(
        json.dumps(
            {
                "snapshot_utc": snapshot.isoformat(),
                "episode_labels": "one-based",
                "runs": metadata,
                "contact_sheet": str(contact_sheet),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(metadata_path)


if __name__ == "__main__":
    main()
