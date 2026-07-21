#!/usr/bin/env python3
"""Per-day net-worth trajectory for attempt 3 (50,162) vs attempt 7 (483,019).

Sources (recovered from disk, see recovery/carve.sh):
  attempt 3 -> MAPs/logged_trajectories/672fdd9a-..._2.tsv   (park value per step)
  attempt 7 -> logs/archive-20260714-062332/.../run.ep000.jsonl (cumulative_reward)
park_value == cumulative_reward + 500 (starting cash), so both are net worth.
Writes images/run3_vs_run7_trajectory.png.
"""
import json
import os
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HOME = "/home/ec2-user"


def attempt3():
    tsv = os.path.join(HOME, "MAPs/logged_trajectories",
                       "672fdd9a-8e62-4c28-88be-554a4acfdba5_2.tsv")
    data = open(tsv, errors="ignore").read()
    sv = {}
    for m in re.finditer(r'"step":(\d+),"sandbox_mode":[^}]*?"value":(\d+)', data):
        sv[int(m.group(1))] = int(m.group(2))
    steps = sorted(k for k in sv if k >= 1)
    return steps, [sv[s] for s in steps]


def attempt7():
    f = os.path.join(HOME, "neuro-san-studio/logs/archive-20260714-062332",
                     "prior-runs/20260713-172409/run.ep000.jsonl")
    rows = [json.loads(l) for l in open(f) if l.strip()]
    return [r["step"] for r in rows], [r["cumulative_reward"] for r in rows]

# Tableau-10 blue/orange: CVD-distinguishable, and both lines are direct-labeled.
BLUE, ORANGE = "#4E79A7", "#F28E2B"

plt.style.use("seaborn-v0_8-whitegrid")
fig, ax = plt.subplots(figsize=(9, 5.5))

for (steps, vals), color, label in [
    (attempt3(), BLUE, "Attempt 3"),
    (attempt7(), ORANGE, "Attempt 7"),
]:
    ax.plot(steps, vals, lw=2.2, color=color, label=label)
    ax.scatter(steps[-1], vals[-1], s=55, color=color,
               edgecolor="white", linewidth=1.2, zorder=5)
    ax.annotate(f"{vals[-1]:,.0f}", (steps[-1], vals[-1]),
                textcoords="offset points", xytext=(8, 0), ha="left",
                va="center", fontsize=10, fontweight="bold", color=color)

ax.set_title("Net worth over the 100-day run — attempt 3 vs attempt 7",
             fontsize=15, fontweight="bold", pad=12)
ax.set_xlabel("Day", fontsize=11)
ax.set_ylabel("Cumulative reward", fontsize=11)
ax.set_xlim(0, 108)
ax.set_ylim(0, 500000)
ax.get_yaxis().set_major_formatter(
    matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
ax.legend(frameon=True, fontsize=10, loc="upper left")

fig.tight_layout()
OUT = os.path.join(os.path.dirname(__file__), "..", "images",
                   "run3_vs_run7_trajectory.png")
fig.savefig(os.path.normpath(OUT), dpi=150, bbox_inches="tight")
print("wrote", os.path.normpath(OUT))
