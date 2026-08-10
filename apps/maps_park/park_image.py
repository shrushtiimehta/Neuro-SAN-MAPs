"""Render a MAPs park to a PNG: one cell per tile, each labelled with its x,y.

    python park_image.py                              # the live park (state/status_layout.json)
    python park_image.py <run.epNNN.jsonl> [step]     # a past episode, from its .tsv snapshot
    python park_image.py <park_id.tsv> [step]         # same, by tsv path

Past episodes come from the per-step .tsv trajectories, which carry the full
end_state (terrain, every asset, every metric) — so water and cleanliness are
real, not inferred. Default step is 99, the last one before the env resets.
"""

import csv
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

csv.field_size_limit(10 ** 9)

REPO = Path("/home/ec2-user/neuro-san-studio")
LIVE = REPO / "coded_tools/state/status_layout.json"
PARK_IDS = REPO / "logs/maps_park/park_ids.jsonl"
SIZE = 20

COLORS = {
    "empty":       "#f4f4f2",
    "path":        "#ded5c4",
    "water":       "#bcd9ea",
    "unreachable": "#ece4f2",
    "free":        "#dff0d8",
    "ride":        "#5b9bd5",
    "shop":        "#e59866",
    "gate":        "#4d5f6d",
}
RIDE_TAG = {"carousel": "CAR", "ferris_wheel": "FER", "roller_coaster": "RC"}
SHOP_TAG = {"drink": "DRK", "food": "FOOD", "specialty": "SPEC"}
STAFF_TAG = {"janitor": "J", "mechanic": "M", "specialist": "S"}


def resolve_tsv(arg: str) -> Path:
    """A run.epNNN.jsonl path resolves to the .tsv of the park it played."""
    p = Path(arg)
    if p.suffix == ".tsv":
        return p
    # Match on final reward: park_ids records final_value = reward + $500 seed cash.
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    target = rows[-1].get("cumulative_reward")
    for line in PARK_IDS.read_text().splitlines():
        rec = json.loads(line)
        if abs((rec.get("final_value") or 0) - (target or 0) - 500) < 1:
            hits = list(p.parent.glob(f"{rec['park_id']}*.tsv"))
            if hits:
                return hits[0]
    raise SystemExit(f"no .tsv found for {p} (final reward {target})")


def from_tsv(path: Path, step: int) -> dict:
    rows = list(csv.DictReader(path.open(), delimiter="\t"))
    match = [r for r in rows if int(r["step"]) == step]
    if not match:
        raise SystemExit(f"step {step} not in {path.name} (has 0..{rows[-1]['step']})")
    st = json.loads(match[-1]["end_state"])

    def profit(e, is_shop):
        cost = ((e.get("order_quantity") or 0) * (e.get("item_cost") or 0)) if is_shop \
            else (e.get("operating_cost") or 0)
        return (e.get("revenue_generated") or 0) - cost

    return {
        "step": st["state"]["step"],
        "park_rating": round(st["state"]["park_rating"], 2),
        "park_value": st["state"]["value"],
        "terrain": st.get("terrain") or [],
        "entrance": [st["entrance"]["x"], st["entrance"]["y"]] if st.get("entrance") else None,
        "exit": [st["exit"]["x"], st["exit"]["y"]] if st.get("exit") else None,
        "placed_rides": [dict(e, profit=profit(e, False)) for e in st.get("rides") or []],
        "placed_shops": [dict(e, profit=profit(e, True)) for e in st.get("shops") or []],
        "placed_staff": st.get("staff") or [],
    }


def build(layout):
    tiles = {}
    # Terrain first (tsv source), then the derived tile sets (live source).
    for t in layout.get("terrain") or []:
        if t.get("type") in ("water", "path"):
            tiles[(t["x"], t["y"])] = {"kind": t["type"], "label": "", "sub": ""}
    for t in layout.get("unreachable_tiles") or []:
        tiles[(t["x"], t["y"])] = {"kind": "unreachable", "label": "", "sub": ""}
    for t in layout.get("path_coords") or []:
        tiles[(t["x"], t["y"])] = {"kind": "path", "label": "", "sub": ""}
    for t in layout.get("free_tiles") or []:
        tiles[(t["x"], t["y"])] = {"kind": "free", "label": "", "sub": ""}
    for r in layout.get("placed_rides") or []:
        tiles[(r["x"], r["y"])] = {"kind": "ride", "label": RIDE_TAG.get(r["subtype"], "?"),
                                   "sub": f"{r['subclass'][:1].upper()} ${r.get('profit', 0)}"}
    for s in layout.get("placed_shops") or []:
        tiles[(s["x"], s["y"])] = {"kind": "shop", "label": SHOP_TAG.get(s["subtype"], "?"),
                                   "sub": f"{s['subclass'][:1].upper()} ${s.get('profit', 0)}"}
    # Staff share the tile under them — annotate, never overwrite.
    for s in layout.get("placed_staff") or []:
        cell = tiles.setdefault((s["x"], s["y"]), {"kind": "empty", "label": "", "sub": ""})
        cell["staff"] = cell.get("staff", "") + STAFF_TAG.get(s["subtype"], "?")
    for key, tag in (("entrance", "IN"), ("exit", "EXIT")):
        c = layout.get(key)
        if c:
            tiles[(c[0], c[1])] = {"kind": "gate", "label": tag, "sub": ""}
    return tiles


def draw(layout, out, title):
    tiles = build(layout)
    fig, ax = plt.subplots(figsize=(16, 16.6))
    for y in range(SIZE):
        for x in range(SIZE):
            cell = tiles.get((x, y), {"kind": "empty", "label": "", "sub": ""})
            ax.add_patch(Rectangle((x, y), 1, 1, facecolor=COLORS[cell["kind"]],
                                   edgecolor="#ffffff", linewidth=1.2))
            ax.text(x + 0.05, y + 0.17, f"{x},{y}", fontsize=6.5, color="#5b5b5b",
                    ha="left", va="center", family="monospace")
            if cell["label"]:
                ax.text(x + 0.5, y + 0.52, cell["label"], fontsize=8.5, weight="bold",
                        color="#12212e", ha="center", va="center")
            if cell["sub"]:
                ax.text(x + 0.5, y + 0.74, cell["sub"], fontsize=6, color="#22303c",
                        ha="center", va="center")
            if cell.get("staff"):
                ax.text(x + 0.93, y + 0.17, cell["staff"], fontsize=7, weight="bold",
                        color="#922b21", ha="right", va="center")

    ax.set_xlim(0, SIZE)
    ax.set_ylim(SIZE, 0)
    ax.set_aspect("equal")
    ax.set_xticks([i + 0.5 for i in range(SIZE)], [str(i) for i in range(SIZE)], fontsize=8)
    ax.set_yticks([i + 0.5 for i in range(SIZE)], [str(i) for i in range(SIZE)], fontsize=8)
    ax.xaxis.set_ticks_position("top")
    ax.set_xlabel("x", fontsize=11)
    ax.xaxis.set_label_position("top")
    ax.set_ylabel("y", fontsize=11, rotation=0, labelpad=12)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)

    kinds = ("ride", "shop", "path", "water", "free", "unreachable", "gate", "empty")
    ax.legend([Rectangle((0, 0), 1, 1, facecolor=COLORS[k], edgecolor="#cccccc") for k in kinds],
              ["ride", "shop", "path", "water", "free (buildable)", "unreachable",
               "entrance / exit", "empty"],
              loc="upper center", bbox_to_anchor=(0.5, -0.02), ncol=8, fontsize=8, frameon=False)
    ax.set_title(title + "\ncell = type, subclass initial, profit;  red letters = staff (J/M/S)",
                 fontsize=13, pad=26)
    fig.savefig(out, dpi=140, bbox_inches="tight", facecolor="white")
    print(f"wrote {out}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    if not args:
        layout = json.loads(LIVE.read_text())
        title = f"MAPs park (live) — step {layout.get('step')}   rating {layout.get('park_rating')}"
        draw(layout, "park.png", title)
    else:
        tsv = resolve_tsv(args[0])
        step = int(args[1]) if len(args) > 1 else 99
        layout = from_tsv(tsv, step)
        name = Path(args[0]).stem
        title = (f"MAPs {name} — step {layout['step']}   "
                 f"rating {layout['park_rating']}   park_value ${layout['park_value']:,}")
        draw(layout, f"{name}.step{step}.png", title)
