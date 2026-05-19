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
Overlay metrics from multiple maps_park runs on the same dashboard as
plot_run.py, but with one line per run instead of one line per park.

Picks up the live run.jsonl plus every rotated run.jsonl.<timestamp> file
in logs/maps_park/ and plots them together.

Usage:
    python -m apps.maps_park.compare_runs                         # default dir
    python -m apps.maps_park.compare_runs --dir logs/maps_park
    python -m apps.maps_park.compare_runs run1.jsonl run2.jsonl   # explicit list
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt


DEFAULT_DIR = "logs/maps_park"


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


def discover(run_dir: str) -> list[str]:
    return sorted(glob.glob(str(Path(run_dir) / "run.jsonl*")))


def label_for(path: str) -> str:
    name = Path(path).name
    if name == "run.jsonl":
        return "current"
    return name[len("run.jsonl."):] if name.startswith("run.jsonl.") else name


def col(rows: list[dict], key: str) -> list:
    return [r.get(key) for r in rows]


def episode_breaks(rows: list[dict]) -> list[int]:
    breaks: list[int] = []
    for idx in range(1, len(rows)):
        prev_step = rows[idx - 1].get("step")
        cur_step = rows[idx].get("step")
        if prev_step is not None and cur_step is not None and cur_step < prev_step:
            breaks.append(idx)
    return breaks


def plot(file_to_rows: dict[str, list[dict]], out_path: str) -> None:
    if not file_to_rows:
        print("No run files found.", file=sys.stderr)
        sys.exit(1)

    fig, axes = plt.subplots(3, 2, figsize=(14, 11))
    fig.suptitle(f"MAPs Park Run Comparison — {len(file_to_rows)} run(s)",
                 fontsize=14, fontweight="bold")

    def per_run(ax, key: str, title: str, ylabel: str) -> None:
        for path, rows in file_to_rows.items():
            x = list(range(len(rows)))
            ax.plot(x, col(rows, key), label=label_for(path))
            for b in episode_breaks(rows):
                ax.axvline(b, color="red", linestyle="--", alpha=0.3, linewidth=0.6)
        ax.set_title(title)
        ax.set_xlabel("Step")
        ax.set_ylabel(ylabel)
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    per_run(axes[0, 0], "cash", "Cash per run", "Cash ($)")
    per_run(axes[0, 1], "cumulative_reward", "Cumulative reward per run", "Cum. reward")

    ax = axes[1, 0]
    for path, rows in file_to_rows.items():
        x = list(range(len(rows)))
        ax.plot(x, col(rows, "num_rides"), label=f"{label_for(path)} rides", linestyle="-")
        ax.plot(x, col(rows, "num_shops"), label=f"{label_for(path)} shops", linestyle="--")
    ax.set_title("Rides + shops per run")
    ax.set_xlabel("Step")
    ax.set_ylabel("Count")
    ax.legend(fontsize=7, ncol=2)
    ax.grid(True, alpha=0.3)

    per_run(axes[1, 1], "shop_revenue", "Shop revenue per run", "$")
    per_run(axes[2, 0], "park_rating", "Park rating per run", "Rating")
    per_run(axes[2, 1], "park_value", "Park value per run", "$")

    fig.tight_layout(rect=[0, 0, 1, 0.97])
    fig.savefig(out_path, dpi=120)
    print(f"Wrote {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*",
                        help="Explicit run.jsonl files (overrides --dir discovery)")
    parser.add_argument("--dir", default=DEFAULT_DIR,
                        help=f"Directory to scan for run.jsonl* (default: {DEFAULT_DIR})")
    parser.add_argument("--out", default=None,
                        help="Output PNG path (default: <dir>/compare.png)")
    args = parser.parse_args()

    files = args.files if args.files else discover(args.dir)
    if not files:
        print(f"No run.jsonl files found in {args.dir}", file=sys.stderr)
        sys.exit(1)

    file_to_rows: dict[str, list[dict]] = {}
    for f in files:
        if not Path(f).exists():
            print(f"Skipping missing file: {f}", file=sys.stderr)
            continue
        rows = load(f)
        if rows:
            file_to_rows[f] = rows
        else:
            print(f"Skipping empty file: {f}", file=sys.stderr)

    out = args.out or str(Path(args.dir) / "compare.png")
    plot(file_to_rows, out)


if __name__ == "__main__":
    main()
