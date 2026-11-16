#!/usr/bin/env python3
"""Render exact final MAPs layouts from full-state trajectory TSV files.

Each input is ``LABEL=PATH``. Unlike action replay, the TSV's final
``end_state`` includes staff movement and the action taken on terminal step 100.

Example:
    python scripts/plot_final_park_tsv_comparison.py \
      --episode 'Episode 3=path/to/park.tsv' \
      --episode 'Episode 4=path/to/park.tsv' \
      --output artifacts/final-layouts.png \
      --summary artifacts/final-layouts.json
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Circle
from matplotlib.patches import Patch
from matplotlib.patches import Rectangle

TIER_COLORS = {
    "yellow": "#f2c14e",
    "blue": "#4c8eda",
    "green": "#4caf63",
    "red": "#e45756",
}
RIDE_CODES = {"carousel": "Ca", "ferris_wheel": "FW", "roller_coaster": "RC"}
SHOP_CODES = {"drink": "Dr", "food": "Fd", "specialty": "Sp"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--episode",
        action="append",
        required=True,
        metavar="LABEL=TSV",
        help="episode label and full-state TSV path; repeat for each panel",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--title", default="Final park layout comparison")
    return parser.parse_args()


def load_final(label_path: str) -> dict[str, Any]:
    if "=" not in label_path:
        raise ValueError(f"expected LABEL=TSV, got {label_path!r}")
    label, raw_path = label_path.split("=", 1)
    path = Path(raw_path).resolve()
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    if not rows:
        raise ValueError(f"empty TSV: {path}")
    return {
        "label": label,
        "source": str(path),
        "trajectory_step": int(rows[-1]["step"]),
        "end_state": json.loads(rows[-1]["end_state"]),
    }


def connected_paths(state: dict[str, Any]) -> tuple[set[tuple[int, int]], set[tuple[int, int]]]:
    paths = {(tile["x"], tile["y"]) for tile in state["terrain"] if tile["type"] == "path"}
    entrance = (state["entrance"]["x"], state["entrance"]["y"])
    exit_coord = (state["exit"]["x"], state["exit"]["y"])
    walkable = paths | {entrance, exit_coord}
    reachable = {entrance}
    frontier = [entrance]
    while frontier:
        x, y = frontier.pop()
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            neighbor = (x + dx, y + dy)
            if neighbor in walkable and neighbor not in reachable:
                reachable.add(neighbor)
                frontier.append(neighbor)
    return paths, reachable


def touches_reachable_path(entity: dict[str, Any], reachable: set[tuple[int, int]]) -> bool:
    x, y = entity["x"], entity["y"]
    return any((x + dx, y + dy) in reachable for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)))


def adjacent_water(entity: dict[str, Any], water: set[tuple[int, int]]) -> int:
    x, y = entity["x"], entity["y"]
    return sum((x + dx, y + dy) in water for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)))


def summarize(item: dict[str, Any]) -> dict[str, Any]:
    state = item["end_state"]
    paths, reachable = connected_paths(state)
    water = {(tile["x"], tile["y"]) for tile in state["terrain"] if tile["type"] == "water"}
    rides = []
    for source in state["rides"]:
        ride = dict(source)
        ride["reachable"] = touches_reachable_path(source, reachable)
        ride["adjacent_water"] = adjacent_water(source, water)
        rides.append(ride)
    shops = []
    for source in state["shops"]:
        shop = dict(source)
        shop["reachable"] = touches_reachable_path(source, reachable)
        shops.append(shop)
    cleanable = [
        *state["terrain"],
        *state["rides"],
        *state["shops"],
        state["entrance"],
        state["exit"],
    ]
    raw = state["state"]
    return {
        "label": item["label"],
        "source_tsv": item["source"],
        "step": item["trajectory_step"],
        "park_id": raw.get("parkId"),
        "metrics": {
            "cash": raw["money"],
            "park_value": raw["value"],
            "park_rating": raw["park_rating"],
            "revenue": raw["revenue"],
            "expenses": raw["expenses"],
            "park_excitement": raw["park_excitement"],
            "min_cleanliness": min(entity["cleanliness"] for entity in cleanable),
            "min_uptime": min([ride["uptime"] for ride in rides] + [shop["uptime"] for shop in shops]),
        },
        "counts": {
            "rides": len(rides),
            "reachable_rides": sum(ride["reachable"] for ride in rides),
            "stranded_rides": sum(not ride["reachable"] for ride in rides),
            "shops": len(shops),
            "staff": len(state["staff"]),
            "reachable_paths": len(reachable & paths),
            "disconnected_paths": len(paths - reachable),
        },
        "ride_tiers_reachable": dict(Counter(ride["subclass"] for ride in rides if ride["reachable"])),
        "ride_tiers_stranded": dict(Counter(ride["subclass"] for ride in rides if not ride["reachable"])),
        "staff_types": {
            f"{kind}/{tier}": count
            for (kind, tier), count in Counter(
                (person["subtype"], person["subclass"]) for person in state["staff"]
            ).items()
        },
        "guest_stats": state.get("guestStats"),
        "rides": rides,
        "shops": shops,
        "staff": state["staff"],
    }


def draw_panel(ax: Any, item: dict[str, Any], summary: dict[str, Any]) -> None:
    state = item["end_state"]
    paths, reachable = connected_paths(state)
    water = {(tile["x"], tile["y"]) for tile in state["terrain"] if tile["type"] == "water"}
    rides = {(ride["x"], ride["y"]): ride for ride in summary["rides"]}
    shops = {(shop["x"], shop["y"]): shop for shop in summary["shops"]}
    staff_by_coord = Counter((person["x"], person["y"]) for person in summary["staff"])
    entrance = (state["entrance"]["x"], state["entrance"]["y"])
    exit_coord = (state["exit"]["x"], state["exit"]["y"])

    for y in range(20):
        for x in range(20):
            coord = (x, y)
            face = "#edf2df"
            hatch = None
            if coord in water:
                face = "#c8e3f1"
            elif coord in paths:
                face = "#f5f1e8" if coord in reachable else "#d0d0d0"
                hatch = None if coord in reachable else ".."
            if coord == entrance:
                face = "#73c686"
            elif coord == exit_coord:
                face = "#ec8a84"
            ax.add_patch(
                Rectangle(
                    (x, y),
                    1,
                    1,
                    facecolor=face,
                    edgecolor="#ffffff",
                    linewidth=0.55,
                    hatch=hatch,
                    zorder=1,
                )
            )

            entity = rides.get(coord) or shops.get(coord)
            if entity:
                is_shop = entity["type"] == "shop"
                stranded = not entity["reachable"]
                edge = "#a31319" if stranded else ("#7b2f81" if is_shop else "#303030")
                ax.add_patch(
                    Rectangle(
                        (x + 0.08, y + 0.08),
                        0.84,
                        0.84,
                        facecolor=TIER_COLORS[entity["subclass"]],
                        edgecolor=edge,
                        linewidth=2.4 if stranded else (2 if is_shop else 1),
                        hatch="xx" if stranded else None,
                        zorder=3,
                    )
                )
                code = (
                    SHOP_CODES.get(entity["subtype"], entity["subtype"][:2])
                    if is_shop
                    else RIDE_CODES.get(entity["subtype"], entity["subtype"][:2])
                )
                tier = entity["subclass"][0].upper()
                ax.text(
                    x + 0.5,
                    y + 0.48,
                    f"{code}{tier}",
                    ha="center",
                    va="center",
                    fontsize=6.3,
                    fontweight="bold",
                    zorder=4,
                )
                if stranded:
                    ax.text(
                        x + 0.5,
                        y + 0.8,
                        "U",
                        ha="center",
                        va="center",
                        fontsize=5.5,
                        color="#8f1015",
                        fontweight="bold",
                        zorder=5,
                    )

            staff_count = staff_by_coord.get(coord, 0)
            if staff_count:
                ax.add_patch(
                    Circle(
                        (x + 0.78, y + 0.22),
                        0.18,
                        facecolor="#27233a",
                        edgecolor="white",
                        linewidth=0.8,
                        zorder=6,
                    )
                )
                ax.text(
                    x + 0.78,
                    y + 0.22,
                    str(staff_count),
                    color="white",
                    ha="center",
                    va="center",
                    fontsize=6,
                    fontweight="bold",
                    zorder=7,
                )

    counts = summary["counts"]
    metrics = summary["metrics"]
    ax.set_title(
        f"{summary['label']} — true step {summary['step']}\n"
        f"value ${metrics['park_value']:,.0f}  •  rating {metrics['park_rating']:.1f}\n"
        f"rides {counts['rides']} ({counts['reachable_rides']} reachable / "
        f"{counts['stranded_rides']} stranded)  •  shops {counts['shops']}  •  staff {counts['staff']}",
        fontsize=10,
        fontweight="bold",
        pad=8,
    )
    ax.set_xlim(0, 20)
    ax.set_ylim(20, 0)
    ax.set_aspect("equal")
    ax.set_xticks([x + 0.5 for x in range(20)])
    ax.set_xticklabels(range(20), fontsize=6)
    ax.set_yticks([y + 0.5 for y in range(20)])
    ax.set_yticklabels(range(20), fontsize=6)
    ax.set_xlabel("x", fontsize=8)
    ax.set_ylabel("y", fontsize=8)
    ax.tick_params(length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)


def main() -> int:
    args = parse_args()
    items = [load_final(value) for value in args.episode]
    summaries = [summarize(item) for item in items]

    width = max(7.2 * len(items), 9)
    fig, axes = plt.subplots(1, len(items), figsize=(width, 8.3), squeeze=False)
    for ax, item, summary in zip(axes[0], items, summaries):
        draw_panel(ax, item, summary)
    fig.suptitle(args.title, fontsize=16, fontweight="bold", y=0.99)
    legend = [
        Patch(facecolor="#f5f1e8", edgecolor="#999", label="entrance-connected path"),
        Patch(facecolor="#d0d0d0", edgecolor="#999", hatch="..", label="disconnected path"),
        Patch(facecolor="#c8e3f1", edgecolor="#999", label="water"),
        Patch(facecolor="#edf2df", edgecolor="#999", label="buildable land"),
        Patch(facecolor="#f2c14e", edgecolor="#303030", label="ride (fill = tier)"),
        Patch(facecolor="#f2c14e", edgecolor="#7b2f81", linewidth=2, label="shop (purple border)"),
        Patch(facecolor="#f2c14e", edgecolor="#a31319", linewidth=2, hatch="xx", label="stranded $0 ride"),
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            markerfacecolor="#27233a",
            markeredgecolor="white",
            markersize=9,
            label="staff at final position",
        ),
    ]
    fig.legend(
        handles=legend,
        loc="lower center",
        ncol=4,
        fontsize=8.5,
        frameon=False,
        bbox_to_anchor=(0.5, 0.005),
    )
    fig.text(
        0.5,
        0.055,
        "Codes: Ca carousel, FW ferris wheel, RC roller coaster; Dr drink, Fd food, Sp specialty. "
        "Suffix: Y/B/G/R tier. U + red hatching = no entrance-connected path.",
        ha="center",
        fontsize=8.5,
    )
    fig.subplots_adjust(left=0.025, right=0.99, top=0.89, bottom=0.11, wspace=0.16)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=180, bbox_inches="tight")
    print(f"wrote {args.output}")
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summaries, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {args.summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
