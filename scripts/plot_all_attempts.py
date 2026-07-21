#!/usr/bin/env python3
"""All 7 attempts' per-day net-worth trajectories in one figure, with the
results table embedded (table doubles as the legend, color-keyed to lines).

Sources (recovered from disk):
  att 1,2,4,5,6 -> recovery/carved.txt  (carved cumulative_reward, see carve.sh)
  att 3         -> MAPs/logged_trajectories/672fdd9a-..._2.tsv (park value)
  att 7         -> logs/archive-20260714-062332/.../run.ep000.jsonl
park_value == cumulative_reward + 500 (starting cash); same net-worth quantity.
Writes images/all_attempts_trajectory.png.
"""
import json
import os
import re
import subprocess

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HOME = "/home/ec2-user"
HERE = os.path.dirname(__file__)
SCRATCH = ("/tmp/claude-1000/-home-ec2-user-neuro-san-studio/"
           "c1b738c5-f83a-4d5b-896e-caffc6469b91/scratchpad")

# Regenerate the carved series (att 1,2,4,5,6) then load it.
subprocess.run(["python3", os.path.join(SCRATCH, "reconstruct.py")], check=True)
carved = json.load(open(os.path.join(SCRATCH, "carved_series.json")))


def att3():
    tsv = os.path.join(HOME, "MAPs/logged_trajectories",
                       "672fdd9a-8e62-4c28-88be-554a4acfdba5_2.tsv")
    data = open(tsv, errors="ignore").read()
    sv = {}
    for m in re.finditer(r'"step":(\d+),"sandbox_mode":[^}]*?"value":(\d+)', data):
        sv[int(m.group(1))] = int(m.group(2))
    steps = sorted(k for k in sv if k >= 1)
    return steps, [sv[s] for s in steps]


def att7():
    f = os.path.join(HOME, "neuro-san-studio/logs/archive-20260714-062332",
                     "prior-runs/20260713-172409/run.ep000.jsonl")
    rows = [json.loads(l) for l in open(f) if l.strip()]
    return [r["step"] for r in rows], [r["cumulative_reward"] for r in rows]


series = {}
for a in (1, 2, 4, 5, 6):
    series[a] = (carved[str(a)]["steps"], carved[str(a)]["vals"])
series[3] = att3()
series[7] = att7()

FINALS = {1: 12121, 2: 9226, 3: 50162, 4: 119575, 5: 331642, 6: 195812, 7: 483019}
RECORDS = {5, 7}
# Ordered, distinct, CVD-reasonable; champion (att 7) gets the strong blue.
COLORS = {1: "#9C9C9C", 2: "#B07AA1", 3: "#76B7B2", 4: "#F28E2B",
          5: "#E15759", 6: "#59A14F", 7: "#4E79A7"}

plt.style.use("seaborn-v0_8-whitegrid")
fig, ax = plt.subplots(figsize=(10, 6))

for a in range(1, 8):
    steps, vals = series[a]
    lw = 2.6 if a in RECORDS else 1.8
    ax.plot(steps, vals, lw=lw, color=COLORS[a], zorder=3 if a in RECORDS else 2)
    ax.scatter(steps[-1], vals[-1], s=45, color=COLORS[a],
               edgecolor="white", linewidth=1.0, zorder=4)

ax.set_title("Cumulative reward across all seven attempts",
             fontsize=15, fontweight="bold", pad=12)
ax.set_xlabel("Day", fontsize=11)
ax.set_ylabel("Cumulative reward", fontsize=11)
ax.set_xlim(0, 104)
ax.set_ylim(0, 500000)
ax.get_yaxis().set_major_formatter(
    matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))

# Embedded results table (upper-left, where the plot is empty). Doubles as
# the legend: each row's Attempt cell is tinted with that attempt's colour.
rows = [[str(a), f"{FINALS[a]:,}"] for a in range(1, 8)]
tbl = ax.table(cellText=rows, colLabels=["Attempt", "Cumulative reward"],
               cellLoc="center", colWidths=[0.10, 0.15],
               bbox=[0.04, 0.44, 0.32, 0.52])
tbl.auto_set_font_size(False)
tbl.set_fontsize(9.5)
tbl.set_zorder(10)
ax.set_axisbelow(True)
for (r, c), cell in tbl.get_celld().items():
    cell.set_edgecolor("#d0d0d0")
    if r == 0:
        cell.set_facecolor("#f0f0f0")
        cell.set_text_props(fontweight="bold")
        continue
    a = r  # row 1 -> attempt 1
    if c == 0:
        cell.set_facecolor(COLORS[a])
        cell.set_text_props(color="white", fontweight="bold")
    else:
        cell.set_facecolor("white")
        if a in RECORDS:
            cell.set_text_props(fontweight="bold")

fig.tight_layout()
OUT = os.path.normpath(os.path.join(HERE, "..", "images", "all_attempts_trajectory.png"))
fig.savefig(OUT, dpi=150, bbox_inches="tight")
print("wrote", OUT)
