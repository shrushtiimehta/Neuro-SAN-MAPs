#!/usr/bin/env python3
"""Plot a Park Tycoon RL episode (run.epNNN.jsonl) as a multi-panel PNG.
Usage: python3 scripts/plot_episode.py <run.jsonl> [out.png]
"""
import json, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

f = sys.argv[1] if len(sys.argv) > 1 else \
    "logs/archive-20260714-062332/prior-runs/20260713-172409/run.ep000.jsonl"
out = sys.argv[2] if len(sys.argv) > 2 else f.rsplit(".", 1)[0] + ".analysis.png"

rows = [json.loads(l) for l in open(f)]
steps = [r["step"] for r in rows]

TIER = {"yellow": "#eda100", "blue": "#2a78d6", "green": "#1a9e1a", "red": "#e0322f"}
RSPEED = {"none": "#e8e6df", "slow": "#bcd6f5", "medium": "#6fa8e6", "fast": "#2a78d6"}

# research-speed contiguous segments -> shaded background
segs, cur = [], None
for r in rows:
    if cur is None or r["research_speed"] != cur[0]:
        cur = [r["research_speed"], r["step"], r["step"]]
        segs.append(cur)
    else:
        cur[2] = r["step"]

# tier events (non-yellow placements/removals) and errors
tier_events = [(r["step"], r["subclass"], r["action"]) for r in rows
               if r.get("subclass") and r["subclass"] != "yellow"]
red_steps = [r["step"] for r in rows if r.get("subclass") == "red"]
err_steps = [r["step"] for r in rows if r.get("error")]

fig, ax = plt.subplots(5, 1, figsize=(14, 16), sharex=True,
                       gridspec_kw={"height_ratios": [0.5, 1, 1, 1, 1], "hspace": 0.12})
fig.suptitle(f"Park Tycoon — Episode 0 analysis   ({f.split('/')[-1]})",
             fontsize=16, fontweight="bold", y=0.995)


def shade_research(a):
    for sp, x0, x1 in segs:
        a.axvspan(x0 - 0.5, x1 + 0.5, color=RSPEED[sp], alpha=0.5, lw=0, zorder=0)


def red_guides(a):
    for s in red_steps:
        a.axvline(s, color=TIER["red"], ls=":", lw=1, alpha=0.6, zorder=1)


# ---- panel 0: research + tier-unlock timeline ----
a = ax[0]
shade_research(a)
for step, tier, action in tier_events:
    marker = "^" if action == "place" else "v"
    face = TIER[tier] if action == "place" else "none"
    a.scatter(step, 0.5, marker=marker, s=170, color=TIER[tier],
              facecolors=face, edgecolors=TIER[tier], linewidths=1.8, zorder=3)
for s in err_steps:
    a.scatter(s, 0.5, marker="x", s=90, color="#d03b3b", zorder=3)
red_guides(a)
a.set_ylim(0, 1); a.set_yticks([])
a.set_title("Research speed (shading) & attraction-tier unlocks — ▲ placed  ▽ removed  ✕ invalid",
            fontsize=11, loc="left", pad=6)
# annotate the two red unlocks (stagger so labels don't collide)
for i, s in enumerate(red_steps):
    dx, ha = (-6, "right") if i % 2 == 0 else (6, "left")
    a.annotate(f"RED @ {s}", (s, 0.5), textcoords="offset points", xytext=(dx, 16),
               ha=ha, fontsize=9, fontweight="bold", color=TIER["red"])

# ---- panel 1: cash & park value ----
a = ax[1]
shade_research(a); red_guides(a)
a.plot(steps, [r["cash"] for r in rows], color="#2a78d6", lw=2, label="cash")
a.plot(steps, [r["park_value"] for r in rows], color="#4a3aa7", lw=1.6, ls="--", label="park value")
a.set_ylabel("$"); a.set_title("Cash & park value", fontsize=11, loc="left")
a.legend(loc="upper left", fontsize=9, framealpha=.9)
a.ticklabel_format(axis="y", style="plain")

# ---- panel 2: park rating ----
a = ax[2]
shade_research(a); red_guides(a)
a.plot(steps, [r["park_rating"] for r in rows], color="#1baf7a", lw=2)
a.fill_between(steps, [r["park_rating"] for r in rows], color="#1baf7a", alpha=0.12)
a.set_ylabel("rating"); a.set_title("Park rating", fontsize=11, loc="left")

# ---- panel 3: reward per step (diverging bars) ----
a = ax[3]
shade_research(a); red_guides(a)
rw = [r["reward"] for r in rows]
a.bar(steps, rw, color=["#2a78d6" if v >= 0 else "#d03b3b" for v in rw], width=0.8)
a.axhline(0, color="#888", lw=0.8)
a.set_ylabel("reward"); a.set_title("Reward per step (blue = gain, red = loss)", fontsize=11, loc="left")
worst = min(rows, key=lambda r: r["reward"])
a.annotate(f"{worst['reward']:.0f}  (place {worst['subtype']})", (worst["step"], worst["reward"]),
           textcoords="offset points", xytext=(8, 12), fontsize=8, color="#d03b3b",
           va="center", ha="left")

# ---- panel 4: cumulative reward ----
a = ax[4]
shade_research(a); red_guides(a)
a.plot(steps, [r["cumulative_reward"] for r in rows], color="#4a3aa7", lw=2)
a.fill_between(steps, [r["cumulative_reward"] for r in rows], color="#4a3aa7", alpha=0.12)
a.set_ylabel("cum. reward"); a.set_title("Cumulative reward", fontsize=11, loc="left")
a.set_xlabel("step")
a.set_xlim(0.5, len(rows) + 0.5)

# research legend on the figure
rlegend = [Line2D([0], [0], marker="s", color="none", markerfacecolor=RSPEED[k],
                  markersize=12, label=f"research: {k}") for k in RSPEED]
tlegend = [Line2D([0], [0], marker="^", color="none", markerfacecolor=TIER[k],
                  markeredgecolor=TIER[k], markersize=11, label=f"tier: {k}") for k in TIER]
fig.legend(handles=rlegend + tlegend, loc="lower center", ncol=8, fontsize=9,
           frameon=False, bbox_to_anchor=(0.5, -0.005))

fig.tight_layout(rect=[0, 0.02, 1, 0.985])
fig.savefig(out, dpi=130, bbox_inches="tight")
print("wrote", out)
