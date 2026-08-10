#!/usr/bin/env python3
"""Park Tycoon run dashboard — 9 panels from a MAPs trajectory TSV.

The TSV's end_state column carries the whole park each day (money, revenue,
rides, shops, staff, research), so everything here is replayed from one file.

Usage: python3 scripts/plot_dashboard.py <trajectory.tsv> [out.png]
"""
import csv, glob, json, sys
from collections import Counter

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

f = sys.argv[1] if len(sys.argv) > 1 else sorted(glob.glob("logs/maps_park/*.tsv"))[-1]
out = sys.argv[2] if len(sys.argv) > 2 else f.rsplit(".", 1)[0] + ".dashboard.png"

# palette: dataviz categorical slots + the game's own tier colors
C = dict(blue="#2a78d6", orange="#eb6834", aqua="#1baf7a", yellow="#eda100",
         violet="#4a3aa7", red="#e34948", warn="#fab219")
TIER = {"yellow": "#eda100", "blue": "#2a78d6", "green": "#008300", "red": "#e34948"}
SURFACE, GRID, MUTED, INK = "#fcfcfb", "#e1e0d9", "#898781", "#52514e"
RSPEED = {"none": "#f4f3ee", "slow": "#e3edfb", "medium": "#cde2fb", "fast": "#9ec5f4"}

rows = list(csv.DictReader(open(f), delimiter="\t"))
days, D = [], []
for r in rows:
    s = json.loads(r["end_state"])
    st = s["state"]
    ents = s["rides"] + s["shops"] + s["staff"]
    clean = [e["cleanliness"] for e in ents if "cleanliness" in e]
    D.append(dict(
        day=st["step"], cash=st["money"], value=st["value"],
        revenue=st["revenue"], expenses=st["expenses"],
        rating=st["park_rating"], excitement=st["park_excitement"],
        happiness=st["prev_guest_happiness"] * 100,
        guests=s["guestStats"]["total_guests"],
        capacity=sum(e["capacity"] for e in s["rides"]),
        intensity=sum(e["intensity"] for e in s["rides"]) / max(len(s["rides"]), 1),
        pairs=len({(e["subtype"], e["subclass"]) for e in s["rides"]}),
        rides=len(s["rides"]),
        clean_min=min(clean, default=1.0), clean_avg=sum(clean) / max(len(clean), 1),
        speed=st["research_speed"],
        tiers=Counter(e["subclass"] for e in ents),
        unlocked={c: sum(c in v for v in st["available_entities"].values())
                  for c in ("blue", "green", "red")},
    ))
days = [d["day"] for d in D]

# first day each entity type gained each tier: {subtype: {tier: day}}
TYPES = list(json.loads(rows[0]["end_state"])["state"]["available_entities"])
unlock_day = {t: {} for t in TYPES}
for r in rows:
    st = json.loads(r["end_state"])["state"]
    for t, colors in st["available_entities"].items():
        for c in colors:
            unlock_day[t].setdefault(c, st["step"])

fig, ax = plt.subplots(3, 3, figsize=(19, 13.2), facecolor="#f9f9f7")
last = D[-1]
meta = json.loads(rows[-1]["end_state"])

# ---- header: title + stat tiles ----
TILES = [("park value", f"${last['value']:,}"), ("park rating", f"{last['rating']:.1f}"),
         ("rides", str(last["rides"])), ("shops", str(len(meta["shops"]))),
         ("staff", str(len(meta["staff"])))]
for i, (lab, val) in enumerate(TILES):
    x = (i + 0.5) / len(TILES)  # evenly spaced slots, text centred in each
    fig.text(x, 0.972, " ".join(lab.upper()), fontsize=8, color=MUTED, va="top",
             ha="center", fontweight="bold")
    fig.text(x, 0.945, val, fontsize=17, color="#0b0b0b", va="top", ha="center",
             fontweight="bold")
fig.add_artist(plt.Line2D([0.012, 0.988], [0.916, 0.916], color="#c3c2b7", lw=1))

speed_segs, cur = [], None
for d in D:
    if cur is None or d["speed"] != cur[0]:
        cur = [d["speed"], d["day"], d["day"]]
        speed_segs.append(cur)
    else:
        cur[2] = d["day"]


def panel(a, title, ylab=""):
    a.set_facecolor(SURFACE)
    a.set_title(title, fontsize=12, loc="left", pad=9, color="#0b0b0b", fontweight="600")
    a.set_ylabel(ylab, fontsize=9, color=MUTED)
    a.grid(True, color=GRID, lw=0.7, zorder=0)
    a.set_axisbelow(True)
    a.tick_params(labelsize=9, colors=MUTED, length=0)
    for side in ("top", "right"):
        a.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        a.spines[side].set_color("#c3c2b7")
    a.set_xlim(0, days[-1])


def series(a, key, color, label, lw=2, **kw):
    a.plot(days, [d[key] for d in D], color=color, lw=lw, label=label, **kw)


def legend(a, **kw):
    a.legend(fontsize=9, framealpha=0.92, edgecolor=GRID, labelcolor=INK, **kw)


def money(a):
    a.yaxis.set_major_formatter(lambda v, _: f"${v/1e6:.1f}M" if abs(v) >= 1e6
                                else (f"${v/1e3:.0f}k" if abs(v) >= 1e3 else f"${v:.0f}"))


# ---- 1: money ----
a = ax[0][0]; panel(a, "Park value, cash and built assets", "$")
series(a, "value", C["violet"], "park value")
series(a, "cash", C["blue"], "cash")
a.plot(days, [d["value"] - d["cash"] for d in D], color=C["aqua"], lw=2, label="assets")
money(a)
legend(a, loc="upper left")

# ---- 2: daily P&L ----
a = ax[0][1]; panel(a, "Daily revenue, expenses and profit", "$ / day")
series(a, "revenue", C["aqua"], "revenue", lw=1.6)
series(a, "expenses", C["red"], "expenses", lw=1.6)
prof = [d["revenue"] - d["expenses"] for d in D]
a.plot(days, prof, color=C["blue"], lw=2, label="profit")
a.axhline(0, color="#c3c2b7", lw=1)
money(a)
legend(a, loc="upper left")

# ---- 3: demand vs supply ----
a = ax[0][2]; panel(a, "Guests in park against ride capacity", "guests")
series(a, "guests", C["blue"], "guests in park", lw=1.6)
series(a, "capacity", C["violet"], "ride capacity per cycle")
legend(a, loc="upper left")

# ---- 4: quality ----
a = ax[1][0]; panel(a, "Rating, excitement and guest happiness", "0–100")
series(a, "rating", C["red"], "park rating", lw=1.6)
series(a, "excitement", C["violet"], "excitement")
series(a, "happiness", C["aqua"], "happiness ×100")
legend(a, loc="upper left")

# ---- 5: cleanliness ----
a = ax[1][1]; panel(a, "Cleanliness — 0.8 is the penalty threshold", "cleanliness")
series(a, "clean_avg", C["blue"], "average")
series(a, "clean_min", C["red"], "worst entity", lw=1.6)
a.axhline(0.8, color=C["warn"], lw=1.6, ls="--", label="penalty threshold")
a.set_ylim(0, 1.05)
legend(a, loc="lower left")

# ---- 6: variety ----
a = ax[1][2]; panel(a, "Ride variety and intensity", "count / intensity")
series(a, "rides", C["violet"], "rides built")
series(a, "pairs", C["blue"], "distinct type+tier")
series(a, "intensity", C["orange"], "avg intensity", lw=1.6)
legend(a, loc="upper left")

# ---- 7: research ----
a = ax[2][0]; panel(a, "Research speed (shading) and tiers unlocked", "entity types unlocked")
for sp, x0, x1 in speed_segs:
    a.axvspan(x0, x1, color=RSPEED[sp], lw=0, zorder=0)
for tier in ("blue", "green", "red"):
    a.plot(days, [d["unlocked"][tier] for d in D], color=TIER[tier], lw=2,
           drawstyle="steps-post", label=f"{tier} tier")
a.set_ylim(0, 9.8); a.set_xlabel("day", fontsize=9, color=MUTED)
speed_keys = [k for k in RSPEED if any(s[0] == k for s in speed_segs)]
legend(a, loc="upper left", ncol=2, handles=(
    a.get_legend_handles_labels()[0]
    + [Patch(facecolor=RSPEED[k], label=f"research: {k}") for k in speed_keys]))

# ---- 8: composition ----
a = ax[2][1]; panel(a, "Park composition by tier", "entities")
base = [0] * len(D)
for tier in ("yellow", "blue", "green", "red"):
    vals = [d["tiers"].get(tier, 0) for d in D]
    top = [b + v for b, v in zip(base, vals)]
    a.fill_between(days, base, top, color=TIER[tier], alpha=0.85, lw=0, label=tier)
    base = top
a.set_xlabel("day", fontsize=9, color=MUTED)
legend(a, loc="upper left", ncol=2)

# ---- 9: which tier each entity type reached, and when ----
a = ax[2][2]; panel(a, "Tier unlocked per entity type (day of unlock)", "")
a.grid(axis="y", visible=False)
for i, t in enumerate(reversed(TYPES)):
    a.plot([0, days[-1]], [i, i], color=GRID, lw=1, zorder=1)
    for tier, day in unlock_day[t].items():
        a.scatter(day, i, s=95, color=TIER[tier], zorder=3,
                  edgecolors=SURFACE, linewidths=1.5)
        if tier != "yellow":
            a.annotate(str(day), (day, i), textcoords="offset points", xytext=(0, 9),
                       ha="center", fontsize=8, color=TIER[tier], fontweight="bold")
a.set_yticks(range(len(TYPES)))
a.set_yticklabels([t.replace("_", " ") for t in reversed(TYPES)], fontsize=10, color=INK)
a.set_ylim(-1.5, len(TYPES) - 0.3)  # blank band at the bottom for the legend
a.set_xlim(-3, days[-1])
a.set_xlabel("day", fontsize=9, color=MUTED)
a.legend(handles=[Patch(facecolor=TIER[k], label=k) for k in TIER],
         fontsize=9, ncol=4, framealpha=0.92, edgecolor=GRID, labelcolor=INK,
         loc="lower right")

fig.tight_layout(rect=[0, 0, 1, 0.905])
fig.savefig(out, dpi=140, facecolor=fig.get_facecolor())
print("wrote", out)
for t in TYPES:
    got = {k: v for k, v in unlock_day[t].items() if k != "yellow"}
    print(f"  {t:<15}", ", ".join(f"{k} @ day {v}" for k, v in got.items()) or "yellow only")
