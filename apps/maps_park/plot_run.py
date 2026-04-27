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
Render a multi-panel dashboard from logs/maps_park/run.jsonl.

Usage:
    python -m apps.maps_park.plot_run                  # default log path
    python -m apps.maps_park.plot_run path/to/run.jsonl
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt


DEFAULT_LOG = "logs/maps_park/run.jsonl"


def load(path: str) -> list[dict]:
    rows: list[dict] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def split_by_park(rows: list[dict]) -> dict[int, list[dict]]:
    by_park: dict[int, list[dict]] = {}
    for row in rows:
        park = row.get("park")
        if park is None:
            continue
        by_park.setdefault(park, []).append(row)
    return by_park


def episode_breaks(park_rows: list[dict]) -> list[int]:
    breaks: list[int] = []
    for idx in range(1, len(park_rows)):
        prev_step = park_rows[idx - 1].get("step")
        cur_step = park_rows[idx].get("step")
        if prev_step is not None and cur_step is not None and cur_step < prev_step:
            breaks.append(idx)
    return breaks


def col(rows: list[dict], key: str) -> list:
    return [r.get(key) for r in rows]


def plot(rows: list[dict], out_path: str) -> None:
    if not rows:
        print("No rows to plot.", file=sys.stderr)
        sys.exit(1)

    by_park = split_by_park(rows)
    parks = sorted(by_park.keys())

    fig, axes = plt.subplots(3, 2, figsize=(14, 11))
    fig.suptitle(f"MAPs Park Run — {len(parks)} park(s)", fontsize=14, fontweight="bold")

    def plot_per_park(ax, key: str, title: str, ylabel: str) -> None:
        for park in parks:
            park_rows = by_park[park]
            x = list(range(len(park_rows)))
            ax.plot(x, col(park_rows, key), label=f"park {park}")
            for b in episode_breaks(park_rows):
                ax.axvline(b, color="red", linestyle="--", alpha=0.3, linewidth=0.6)
        ax.set_title(title); ax.set_xlabel("Step"); ax.set_ylabel(ylabel)
        ax.legend(fontsize=8); ax.grid(True, alpha=0.3)

    plot_per_park(axes[0, 0], "cash", "Cash per park", "Cash ($)")
    plot_per_park(axes[0, 1], "cumulative_reward", "Cumulative reward per park", "Cum. reward")

    ax = axes[1, 0]
    for park in parks:
        park_rows = by_park[park]
        x = list(range(len(park_rows)))
        ax.plot(x, col(park_rows, "num_rides"), label=f"park {park} rides", linestyle="-")
        ax.plot(x, col(park_rows, "num_shops"), label=f"park {park} shops", linestyle="--")
    ax.set_title("Rides + shops per park"); ax.set_xlabel("Step"); ax.set_ylabel("Count")
    ax.legend(fontsize=7, ncol=2); ax.grid(True, alpha=0.3)

    plot_per_park(axes[1, 1], "shop_revenue", "Shop revenue (cum.) per park", "$")

    ax = axes[2, 0]
    totals_by_step: dict[int, int] = {}
    for row in rows:
        cr = row.get("cumulative_reward")
        if cr is not None:
            step = row.get("step", 0) or 0
            totals_by_step[step] = totals_by_step.get(step, 0) + cr
    if totals_by_step:
        steps = sorted(totals_by_step.keys())
        ax.plot(steps, [totals_by_step[s] for s in steps], color="C2", linewidth=2)
    ax.set_title("Total cumulative reward (sum across parks)")
    ax.set_xlabel("Step"); ax.set_ylabel("Total cum. reward")
    ax.grid(True, alpha=0.3)

    plot_per_park(axes[2, 1], "park_value", "Park value per park", "$")

    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(out_path, dpi=120)
    print(f"Wrote {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("log_path", nargs="?", default=DEFAULT_LOG)
    parser.add_argument("--out", default="logs/maps_park/dashboard.png")
    args = parser.parse_args()

    if not Path(args.log_path).exists():
        print(f"Log file not found: {args.log_path}", file=sys.stderr)
        sys.exit(1)

    rows = load(args.log_path)
    plot(rows, args.out)


if __name__ == "__main__":
    main()
