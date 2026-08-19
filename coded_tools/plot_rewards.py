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

# Latest run only: the run.epNNN.jsonl sitting in logs/maps_park (prior runs get
# archived into prior-runs/ when a new run starts).
paths = sorted(glob.glob(os.path.join(LOG_DIR, "run.ep*.jsonl")))

plt.style.use("seaborn-v0_8-whitegrid")
fig, ax = plt.subplots(figsize=(12, 7))
cmap = plt.get_cmap("viridis")

for i, path in enumerate(paths):
    rows = [json.loads(l) for l in open(path) if l.strip()]
    if not rows or not rows[-1]["done"]:
        continue  # in-flight / crashed episode, no final value to compare
    steps = [r["step"] for r in rows]
    cum = [r["cumulative_reward"] for r in rows]
    color = cmap(i / max(1, len(paths) - 1))
    ax.plot(steps, cum, lw=2, color=color,
            label=f'ep {rows[0]["episode"]} \u2014 {cum[-1]:,.0f}')
    ax.scatter(steps[-1], cum[-1], s=30, color=color, zorder=5)

ax.set_title("MAPs Park \u2014 cumulative reward, latest run",
             fontsize=16, fontweight="bold", pad=14)
ax.set_xlabel("Step (day)", fontsize=12)
ax.set_ylabel("Cumulative Reward", fontsize=12)
ax.legend(title="episode", frameon=True, fontsize=10, title_fontsize=11, loc="upper left")
ax.ticklabel_format(style="plain", axis="y")
ax.get_yaxis().set_major_formatter(
    matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
ax.margins(x=0.08)

fig.tight_layout()
fig.savefig(OUT, dpi=150, bbox_inches="tight")
print("wrote", OUT, f"({len(paths)} episodes)")
