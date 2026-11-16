#!/usr/bin/env python3
"""Compare Baseline Run 19 with the retained 1.8M baseline champion.

The per-turn JSONL is the action/reward ledger.  The MAPs TSV is used for the
true terminal state because the legacy JSONL terminal envelope carries the
step-99 observation even though its reward and cumulative reward are step 100.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
RUN19_DIR = ROOT / "logs/maps_park/prior-runs/20260820-234115"
CHAMPION_DIR = ROOT / "logs/maps_park/prior-runs/20260819-233018"
RUN19_PARK_IDS = (
    "557725d9-d044-4d43-b05c-e6da30ead0a8",
    "b6c3b383-b229-478c-82aa-38e519eac45e",
    "1a3d1c5e-b509-418b-920a-42ccfc23e6fe",
    "aaa6d6b4-f8b2-4b66-9426-7926b3f61e9b",
    "f5131767-7ed8-4403-9567-49e1a4ab26e8",
    "6e5d8338-b5c2-40b7-8700-22a0c8b31bfb",
    "e380d646-b0a8-4c51-822e-d0e5822c9344",
    "de7a1c37-e26b-454f-856e-96e3db02cb12",
    "812a2301-5e15-4b0e-b380-e32d88c164f1",
    "d7fa26e4-665b-4c7c-9b4c-d87662beaf9a",
    "0f8aa709-9b06-4f3d-8a23-4fabc57caa03",
)
CHAMPION_PARK_ID = "88abc67f-411b-44cf-b71f-80f3bd819bd0"
CHECKPOINTS = (10, 20, 30, 40, 50, 60, 70, 80, 90, 99, 100)


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts/baseline_run19_vs_1_8m.png",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=ROOT / "artifacts/baseline_run19_vs_1_8m.json",
    )
    return parser.parse_args()


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def final_state(path: Path) -> dict[str, Any]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    if not rows or int(rows[-1]["step"]) != 100:
        raise ValueError(f"expected a complete 100-step TSV: {path}")
    return json.loads(rows[-1]["end_state"])


def connected_paths(state: dict[str, Any]) -> set[tuple[int, int]]:
    paths = {(tile["x"], tile["y"]) for tile in state["terrain"] if tile["type"] == "path"}
    entrance = (state["entrance"]["x"], state["entrance"]["y"])
    exit_coord = (state["exit"]["x"], state["exit"]["y"])
    walkable = paths | {entrance, exit_coord}
    reached = {entrance}
    frontier = [entrance]
    while frontier:
        x, y = frontier.pop()
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            neighbor = (x + dx, y + dy)
            if neighbor in walkable and neighbor not in reached:
                reached.add(neighbor)
                frontier.append(neighbor)
    return reached


def touches(entity: dict[str, Any], paths: set[tuple[int, int]]) -> bool:
    x, y = entity["x"], entity["y"]
    return any((x + dx, y + dy) in paths for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)))


def action_counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    actions = Counter(row.get("action") for row in rows)
    placements = Counter(row.get("type") for row in rows if row.get("action") == "place")
    removals = Counter(row.get("type") for row in rows if row.get("action") == "remove")
    return {
        "actions": dict(actions),
        "placements": dict(placements),
        "removals": dict(removals),
        "errors": sum(row.get("error") is not None for row in rows),
    }


def summarize(label: str, trajectory_path: Path, tsv_path: Path) -> dict[str, Any]:
    rows = jsonl(trajectory_path)
    state = final_state(tsv_path)
    raw = state["state"]
    paths = connected_paths(state)
    reachable = [ride for ride in state["rides"] if touches(ride, paths)]
    stranded = [ride for ride in state["rides"] if not touches(ride, paths)]
    all_cleanable = [
        *state["terrain"],
        *state["rides"],
        *state["shops"],
        state["entrance"],
        state["exit"],
    ]
    idle_staff = [
        person
        for person in state["staff"]
        if not person.get("tiles_traversed") and not person.get("success_metric_value")
    ]
    checkpoints = {
        str(step): {
            key: row.get(key)
            for key in (
                "cumulative_reward",
                "cash",
                "park_value",
                "park_rating",
                "num_rides",
                "num_shops",
                "num_staff",
                "shop_revenue",
                "min_cleanliness",
                "min_uptime",
            )
        }
        for step in CHECKPOINTS
        for row in rows
        if row.get("step") == step
    }
    terminal = rows[-1]
    return {
        "label": label,
        "trajectory": str(trajectory_path.resolve()),
        "tsv": str(tsv_path.resolve()),
        "park_id": raw["parkId"],
        "seed": raw["seed"],
        "cumulative_reward": terminal["cumulative_reward"],
        "true_final": {
            "cash": raw["money"],
            "park_value": raw["value"],
            "park_rating": raw["park_rating"],
            "revenue": raw["revenue"],
            "expenses": raw["expenses"],
            "park_excitement": raw["park_excitement"],
            "total_salary_paid": raw["total_salary_paid"],
            "rides": len(state["rides"]),
            "reachable_rides": len(reachable),
            "stranded_rides": len(stranded),
            "capacity": sum(ride["capacity"] for ride in state["rides"]),
            "reachable_capacity": sum(ride["capacity"] for ride in reachable),
            "stranded_capacity": sum(ride["capacity"] for ride in stranded),
            "reachable_ride_revenue": sum(ride["revenue_generated"] for ride in reachable),
            "reachable_guests_entertained": sum(ride["guests_entertained"] for ride in reachable),
            "reachable_ride_tiers": dict(Counter(ride["subclass"] for ride in reachable)),
            "stranded_ride_tiers": dict(Counter(ride["subclass"] for ride in stranded)),
            "shops": len(state["shops"]),
            "shop_revenue": sum(shop["revenue_generated"] for shop in state["shops"]),
            "staff": len(state["staff"]),
            "staff_types": {
                f"{kind}/{tier}": count
                for (kind, tier), count in Counter(
                    (person["subtype"], person["subclass"]) for person in state["staff"]
                ).items()
            },
            "idle_staff": len(idle_staff),
            "min_cleanliness": min(item["cleanliness"] for item in all_cleanable),
            "min_uptime": min(
                [ride["uptime"] for ride in state["rides"]] + [shop["uptime"] for shop in state["shops"]]
            ),
            "guest_stats": state["guestStats"],
        },
        "jsonl_terminal_carried_state": {
            key: terminal.get(key)
            for key in (
                "cash",
                "park_value",
                "park_rating",
                "num_rides",
                "num_shops",
                "num_staff",
                "min_cleanliness",
                "min_uptime",
                "shop_revenue",
            )
        },
        "actions": action_counts(rows),
        "checkpoints": checkpoints,
        "trajectory_rows": rows,
    }


def pearson(xs: list[float], ys: list[float]) -> float | None:
    xbar, ybar = statistics.mean(xs), statistics.mean(ys)
    numerator = sum((x - xbar) * (y - ybar) for x, y in zip(xs, ys))
    xsum = sum((x - xbar) ** 2 for x in xs)
    ysum = sum((y - ybar) ** 2 for y in ys)
    denominator = math.sqrt(xsum * ysum)
    return numerator / denominator if denominator else None


def compact(item: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in item.items() if key != "trajectory_rows"}


def make_plot(run19: list[dict[str, Any]], champion: dict[str, Any], output: Path) -> None:
    best = max(run19, key=lambda item: item["cumulative_reward"])
    fig, axes = plt.subplots(1, 3, figsize=(17, 5.5))
    ax = axes[0]
    for item in run19:
        steps = [row["step"] for row in item["trajectory_rows"]]
        rewards = [row["cumulative_reward"] for row in item["trajectory_rows"]]
        if item is best:
            ax.plot(steps, rewards, color="#3274a1", linewidth=2.8, label="Run 19 best (E3)")
        else:
            ax.plot(steps, rewards, color="#b8bdc5", linewidth=1, alpha=0.65)
    ax.plot(
        [row["step"] for row in champion["trajectory_rows"]],
        [row["cumulative_reward"] for row in champion["trajectory_rows"]],
        color="#d64b40",
        linewidth=2.8,
        label="1.8M champion",
    )
    ax.axvline(80, color="#777777", linestyle="--", linewidth=1)
    ax.set(title="Reward trajectories", xlabel="Day / step", ylabel="Cumulative reward")
    ax.ticklabel_format(axis="y", style="plain")
    ax.legend(frameon=False, loc="upper left")

    ax = axes[1]
    steps = list(range(1, 101))
    for item, color, name in (
        (best, "#3274a1", "Run 19 best"),
        (champion, "#d64b40", "1.8M champion"),
    ):
        by_step = {row["step"]: row for row in item["trajectory_rows"]}
        ax.step(
            steps,
            [by_step[step]["num_rides"] for step in steps],
            where="post",
            color=color,
            linewidth=2.4,
            label=name,
        )
    ax.set(title="Ride count locks in the late gap", xlabel="Day / step", ylabel="Placed rides")
    ax.legend(frameon=False, loc="upper left")

    ax = axes[2]
    labels = ["Total\ncapacity", "Guests", "Avg guest\nspend", "Day-100\nrevenue", "Day-100\nexpenses"]
    champ_final = champion["true_final"]
    best_final = best["true_final"]
    champion_values = [
        champ_final["capacity"],
        champ_final["guest_stats"]["total_guests"],
        champ_final["guest_stats"]["avg_money_spent"],
        champ_final["revenue"] / 100,
        champ_final["expenses"] / 100,
    ]
    best_values = [
        best_final["capacity"],
        best_final["guest_stats"]["total_guests"],
        best_final["guest_stats"]["avg_money_spent"],
        best_final["revenue"] / 100,
        best_final["expenses"] / 100,
    ]
    positions = list(range(len(labels)))
    width = 0.37
    ax.bar([x - width / 2 for x in positions], champion_values, width, color="#d64b40", label="1.8M champion")
    ax.bar([x + width / 2 for x in positions], best_values, width, color="#3274a1", label="Run 19 best")
    ax.set_xticks(positions, labels)
    ax.set_title("Terminal economic drivers\n(revenue/expenses shown in hundreds)")
    ax.legend(frameon=False, loc="upper right")
    ax.grid(axis="y", alpha=0.2)

    fig.suptitle("Baseline Run 19 vs. the retained 1.8M champion", fontsize=15, fontweight="bold")
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=180, bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    options = args()
    run19 = [
        summarize(
            f"Run 19 Episode {index + 1}",
            RUN19_DIR / f"run.ep{index:03d}.jsonl",
            RUN19_DIR / f"{park_id}_1.tsv",
        )
        for index, park_id in enumerate(RUN19_PARK_IDS)
    ]
    champion = summarize(
        "1.8M champion (Baseline Run 18 Episode 4)",
        CHAMPION_DIR / "run.ep003.jsonl",
        CHAMPION_DIR / f"{CHAMPION_PARK_ID}_1.tsv",
    )
    rewards = [float(item["cumulative_reward"]) for item in run19]
    correlations = {}
    for name, getter in {
        "total_capacity": lambda item: item["true_final"]["capacity"],
        "reachable_capacity": lambda item: item["true_final"]["reachable_capacity"],
        "guests": lambda item: item["true_final"]["guest_stats"]["total_guests"],
        "average_guest_spend": lambda item: item["true_final"]["guest_stats"]["avg_money_spent"],
        "park_rating": lambda item: item["true_final"]["park_rating"],
        "day_100_revenue": lambda item: item["true_final"]["revenue"],
        "day_100_expenses": lambda item: item["true_final"]["expenses"],
        "ride_placements": lambda item: item["actions"]["placements"].get("ride", 0),
        "staff_placements": lambda item: item["actions"]["placements"].get("staff", 0),
        "research_actions": lambda item: item["actions"]["actions"].get("set_research", 0),
    }.items():
        correlations[name] = pearson(rewards, [float(getter(item)) for item in run19])
    best = max(run19, key=lambda item: item["cumulative_reward"])
    payload = {
        "method_note": (
            "JSONL supplies actions/rewards; TSV supplies true step-100 state because "
            "the legacy JSONL terminal state fields are the carried step-99 observation."
        ),
        "run19": {
            "wandb_parent": "https://wandb.ai/shrushtm-cognizant/maps-park-ablations/runs/histc5a2de9ad421",
            "completed_episodes": len(run19),
            "mean_reward": statistics.mean(rewards),
            "median_reward": statistics.median(rewards),
            "sample_stdev_reward": statistics.stdev(rewards),
            "min_reward": min(rewards),
            "max_reward": max(rewards),
            "episodes_above_1m": sum(reward > 1_000_000 for reward in rewards),
            "correlations_descriptive_not_causal": correlations,
            "episodes": [compact(item) for item in run19],
        },
        "champion": {
            "wandb_parent": "https://wandb.ai/shrushtm-cognizant/maps-park-ablations/runs/hist914c492c5d30",
            **compact(champion),
        },
        "best_to_champion": {
            "run19_best": best["label"],
            "final_reward_gap": champion["cumulative_reward"] - best["cumulative_reward"],
            "day_80_gap_champion_minus_best": (
                champion["checkpoints"]["80"]["cumulative_reward"] - best["checkpoints"]["80"]["cumulative_reward"]
            ),
            "day_90_gap_champion_minus_best": (
                champion["checkpoints"]["90"]["cumulative_reward"] - best["checkpoints"]["90"]["cumulative_reward"]
            ),
            "day_80_to_90_swing": (
                champion["checkpoints"]["90"]["cumulative_reward"] - best["checkpoints"]["90"]["cumulative_reward"]
            )
            - (champion["checkpoints"]["80"]["cumulative_reward"] - best["checkpoints"]["80"]["cumulative_reward"]),
            "day_90_to_100_swing": (champion["cumulative_reward"] - best["cumulative_reward"])
            - (champion["checkpoints"]["90"]["cumulative_reward"] - best["checkpoints"]["90"]["cumulative_reward"]),
        },
    }
    options.summary.parent.mkdir(parents=True, exist_ok=True)
    options.summary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    make_plot(run19, champion, options.output)
    print(options.output.resolve())
    print(options.summary.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
