#!/usr/bin/env python3
"""Reconstruct and draw the Park Tycoon park layout from a run.epNNN.jsonl.
Replays place/modify/remove over the x,y grid and renders it as square cells:
final park map + stats + growth snapshots.
Usage: python3 scripts/plot_park_map.py <run.jsonl> [out.png]
"""
import json, sys
from collections import Counter
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle
from matplotlib.lines import Line2D

f = sys.argv[1] if len(sys.argv) > 1 else \
    "logs/archive-20260714-062332/prior-runs/20260713-172409/run.ep000.jsonl"
out = sys.argv[2] if len(sys.argv) > 2 else f.rsplit(".", 1)[0] + ".parkmap.png"
rows = [json.loads(l) for l in open(f)]

TIER = {"yellow": "#f2c14e", "blue": "#2a78d6", "green": "#1a9e1a", "red": "#e0322f"}
SHOP_BG = "#c9a26b"      # shops (all base tier) get their own warm fill
EMPTY = "#f0eee7"
ABBR = {"carousel": "Carousel", "roller_coaster": "Coaster", "ferris_wheel": "Ferris",
        "food": "Food", "drink": "Drink", "specialty": "Gifts",
        "janitor": "Jan", "mechanic": "Mech", "specialist": "Spec"}
CODE = {"carousel": "Car", "roller_coaster": "Coa", "ferris_wheel": "Fer",
        "food": "Food", "drink": "Drnk", "specialty": "Gift"}


def replay(upto):
    cells, staff = {}, {}
    for r in rows:
        if r["step"] > upto:
            break
        if r.get("x") in (None, ""):
            continue
        key = (int(r["x"]), int(r["y"]))
        t = r.get("type")
        if r["action"] == "place":
            if t == "staff":
                staff[key] = staff.get(key, 0) + 1
            else:
                cells[key] = {"type": t, "subtype": r["subtype"], "subclass": r["subclass"]}
        elif r["action"] == "modify" and t != "staff" and key in cells:
            cells[key] = {"type": t, "subtype": r["subtype"], "subclass": r["subclass"]}
        elif r["action"] == "remove":
            if t == "staff":
                staff[key] = max(0, staff.get(key, 0) - 1)
            elif key in cells:
                del cells[key]
    return cells, {k: v for k, v in staff.items() if v > 0}


# fixed grid bounds from the whole run so snapshots line up
xs = [int(r["x"]) for r in rows if r.get("x") not in (None, "")]
ys = [int(r["y"]) for r in rows if r.get("y") not in (None, "")]
X0, X1, Y0, Y1 = min(xs), max(xs), min(ys), max(ys)


def draw_park(ax, cells, staff, title, labels=True):
    ax.set_title(title, fontsize=12, fontweight="bold", pad=8)
    for gx in range(X0, X1 + 1):
        for gy in range(Y0, Y1 + 1):
            k = (gx, gy)
            item = cells.get(k)
            if item:
                bg = TIER[item["subclass"]] if item["type"] == "ride" else SHOP_BG
            else:
                bg = EMPTY
            ax.add_patch(Rectangle((gx, gy), 1, 1, facecolor=bg,
                                   edgecolor="white", linewidth=1.5, zorder=1))
            if item and labels:
                ax.text(gx + 0.5, gy + 0.45, CODE.get(item["subtype"], item["subtype"]),
                        ha="center", va="center", fontsize=8, fontweight="bold",
                        color="#1a1a1a", zorder=3)
            # staff badge
            n = staff.get(k, 0)
            if n:
                if not item:  # staff-only cell -> lilac fill
                    ax.add_patch(Rectangle((gx, gy), 1, 1, facecolor="#e7e0f0",
                                           edgecolor="white", linewidth=1.5, zorder=1))
                ax.add_patch(Circle((gx + 0.79, gy + 0.21), 0.17, facecolor="#4a3aa7",
                                    edgecolor="white", linewidth=1, zorder=4))
                ax.text(gx + 0.79, gy + 0.21, str(n), ha="center", va="center",
                        fontsize=7.5, color="white", fontweight="bold", zorder=5)
    ax.set_xlim(X0, X1 + 1)
    ax.set_ylim(Y1 + 1, Y0)          # invert -> y grows downward, map style
    ax.set_aspect("equal")
    ax.set_xticks([x + 0.5 for x in range(X0, X1 + 1)])
    ax.set_xticklabels(range(X0, X1 + 1), fontsize=7)
    ax.set_yticks([y + 0.5 for y in range(Y0, Y1 + 1)])
    ax.set_yticklabels(range(Y0, Y1 + 1), fontsize=7)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(length=0)


# ---- figure ----
fig = plt.figure(figsize=(15, 11))
gs = fig.add_gridspec(2, 4, height_ratios=[2.4, 1], hspace=0.22, wspace=0.25)
fig.suptitle(f"Park Tycoon — Episode 0 · park layout   ({f.split('/')[-1]})",
             fontsize=16, fontweight="bold", y=0.98)

# main map = peak build (step 99, before the reset row)
cells, staff = replay(99)
ax_main = fig.add_subplot(gs[0, :3])
draw_park(ax_main, cells, staff, "Final park (step 99, peak build)")

# ---- stats panel ----
ax_s = fig.add_subplot(gs[0, 3]); ax_s.axis("off")
rides = [v for v in cells.values() if v["type"] == "ride"]
shops = [v for v in cells.values() if v["type"] == "shop"]
tier_ct = Counter(v["subclass"] for v in rides)
ride_ct = Counter(v["subtype"] for v in rides)
shop_ct = Counter(v["subtype"] for v in shops)
last = rows[-2]  # step 99 (row before reset)

lines = [("PARK TOTALS", None, 13, "bold")]
lines += [(f"Rides", str(len(rides)), 11, "normal"),
          (f"Shops", str(len(shops)), 11, "normal"),
          (f"Staff", str(sum(staff.values())), 11, "normal"),
          ("", "", 6, "normal"),
          ("RIDE TIERS", None, 12, "bold")]
for t in ["yellow", "blue", "green", "red"]:
    lines.append((t.title(), str(tier_ct.get(t, 0)), 11, "normal"))
lines += [("", "", 6, "normal"), ("RIDES", None, 12, "bold")]
for k, v in ride_ct.most_common():
    lines.append((ABBR.get(k, k), str(v), 11, "normal"))
lines += [("", "", 6, "normal"), ("SHOPS", None, 12, "bold")]
for k, v in shop_ct.most_common():
    lines.append((ABBR.get(k, k), str(v), 11, "normal"))
lines += [("", "", 6, "normal"), ("END STATE (step 99)", None, 12, "bold"),
          ("Cash", f"${last['cash']:,}", 11, "normal"),
          ("Park value", f"${last['park_value']:,}", 11, "normal"),
          ("Park rating", f"{last['park_rating']:.1f}", 11, "normal")]

y = 0.98
for label, val, sz, w in lines:
    if val is None:
        ax_s.text(0.0, y, label, fontsize=sz, fontweight=w, color="#17150f",
                  transform=ax_s.transAxes)
    elif label == "":
        pass
    else:
        color = TIER.get(label.lower(), "#5b574c")
        ax_s.text(0.05, y, label, fontsize=sz, fontweight=w, color="#5b574c",
                  transform=ax_s.transAxes)
        ax_s.text(0.95, y, val, fontsize=sz, fontweight="bold", ha="right",
                  color=color if label.lower() in TIER else "#17150f",
                  transform=ax_s.transAxes)
    y -= 0.033

# ---- growth snapshots ----
for i, step in enumerate([20, 50, 87, 99]):
    c, st = replay(step)
    ax = fig.add_subplot(gs[1, i])
    draw_park(ax, c, st, f"step {step}", labels=False)

# legend
leg = [Line2D([0], [0], marker="s", color="none", markerfacecolor=TIER["yellow"], markersize=13, label="ride: yellow"),
       Line2D([0], [0], marker="s", color="none", markerfacecolor=TIER["blue"], markersize=13, label="ride: blue"),
       Line2D([0], [0], marker="s", color="none", markerfacecolor=TIER["green"], markersize=13, label="ride: green"),
       Line2D([0], [0], marker="s", color="none", markerfacecolor=TIER["red"], markersize=13, label="ride: red"),
       Line2D([0], [0], marker="s", color="none", markerfacecolor=SHOP_BG, markersize=13, label="shop"),
       Line2D([0], [0], marker="s", color="none", markerfacecolor="#e7e0f0", markersize=13, label="staff cell"),
       Line2D([0], [0], marker="o", color="none", markerfacecolor="#4a3aa7", markersize=11, label="staff count")]
fig.legend(handles=leg, loc="lower center", ncol=7, fontsize=10, frameon=False,
           bbox_to_anchor=(0.5, 0.0))

fig.savefig(out, dpi=130, bbox_inches="tight")
print("wrote", out)
