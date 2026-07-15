#!/usr/bin/env python3
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
"""Compare run trajectories: cumulative reward for every maps_park run on one chart.

Run from the repo root:  python coded_tools/plot_rewards.py
Writes logs/maps_park/cumulative_reward.png
"""
import json
import glob
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Repo-root-relative so this works on any checkout (this file lives in
# coded_tools/, so logs/maps_park is one dir up).
LOG_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "logs", "maps_park"))
OUT = os.path.join(LOG_DIR, "cumulative_reward.png")

# Collect run files: current dir + prior-runs.
# Sort chronologically by (run-start timestamp, episode) so we can label
# them Run 1, Run 2, ... in time order. The current dir is the newest.
run_files = []
for f in glob.glob(os.path.join(LOG_DIR, "run.ep*.jsonl")):
    run_files.append(("99999999-999999", f))  # current run = latest
for f in glob.glob(os.path.join(LOG_DIR, "prior-runs", "*", "run.ep*.jsonl")):
    ts = os.path.basename(os.path.dirname(f))
    run_files.append((ts, f))

run_files.sort(key=lambda t: (t[0], os.path.basename(t[1])))


def load(path):
    steps, cum = [], []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            steps.append(r["step"])
            cum.append(r["cumulative_reward"])
    return steps, cum


plt.style.use("seaborn-v0_8-whitegrid")
fig, ax = plt.subplots(figsize=(12, 7))

# Palette with no green.
PALETTE = ["#1f77b4", "#ff7f0e", "#d62728", "#9467bd",
           "#8c564b", "#17becf", "#e377c2", "#7f7f7f"]
for i, (src, path) in enumerate(run_files):
    label = f"Run {i + 1}"
    steps, cum = load(path)
    color = PALETTE[i % len(PALETTE)]
    ax.plot(steps, cum, lw=2, color=color, label=label)
    ax.scatter(steps[-1], cum[-1], s=28, color=color, zorder=5)
    ax.annotate(f"{cum[-1]:,.0f}", (steps[-1], cum[-1]),
                textcoords="offset points", xytext=(6, 0),
                fontsize=8, color=color, va="center", fontweight="bold")

ax.set_title("MAPs Park — Cumulative Reward by Run", fontsize=16, fontweight="bold", pad=14)
ax.set_xlabel("Step", fontsize=12)
ax.set_ylabel("Cumulative Reward", fontsize=12)
ax.legend(title="Run", frameon=True, fontsize=10, title_fontsize=11, loc="upper left")
ax.ticklabel_format(style="plain", axis="y")
ax.get_yaxis().set_major_formatter(
    matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
ax.margins(x=0.08)

fig.tight_layout()
fig.savefig(OUT, dpi=150, bbox_inches="tight")
print("wrote", OUT)
