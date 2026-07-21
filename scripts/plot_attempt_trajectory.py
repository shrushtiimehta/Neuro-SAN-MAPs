#!/usr/bin/env python3
"""Plot cumulative reward across the 7 self-improvement attempts (blog table).

Data is the blog_post.md results table, not per-run JSON: only the champion
run's per-day file still exists on disk, so these are the recorded finals.
Writes images/reward_trajectory.png.
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ATTEMPTS = [1, 2, 3, 4, 5, 6, 7]
REWARDS = [12121, 9226, 50162, 119575, 331642, 195812, 483019]
RECORDS = {5, 7}  # attempts that set a new high-water mark (bold in the table)

INK = "#1f77b4"
GOLD = "#d4a017"

plt.style.use("seaborn-v0_8-whitegrid")
fig, ax = plt.subplots(figsize=(9, 5.5))

ax.plot(ATTEMPTS, REWARDS, lw=2.2, color=INK, zorder=2)

for a, r in zip(ATTEMPTS, REWARDS):
    record = a in RECORDS
    ax.scatter(a, r, s=90 if record else 55,
               color=GOLD if record else INK,
               edgecolor="white", linewidth=1.2, zorder=3)
    ax.annotate(f"{r:,}", (a, r), textcoords="offset points",
                xytext=(0, 12), ha="center", fontsize=9,
                fontweight="bold" if record else "normal",
                color=GOLD if record else "#333333")

ax.set_title("Learning across attempts — cumulative reward per run",
             fontsize=15, fontweight="bold", pad=12)
ax.set_xlabel("Attempt", fontsize=11)
ax.set_ylabel("Cumulative reward", fontsize=11)
ax.set_xticks(ATTEMPTS)
ax.set_ylim(0, max(REWARDS) * 1.15)
ax.get_yaxis().set_major_formatter(
    matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
ax.margins(x=0.06)

fig.tight_layout()
OUT = os.path.join(os.path.dirname(__file__), "..", "images", "reward_trajectory.png")
fig.savefig(os.path.normpath(OUT), dpi=150, bbox_inches="tight")
print("wrote", os.path.normpath(OUT))
