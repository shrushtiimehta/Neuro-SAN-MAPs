#!/usr/bin/env python3
"""
Vertical comparison of two MAPs runs from the full park screenshots in images/.

Two columns (early run | best run) by five rows (day ~10 -> 99, top to bottom).
Each cell is the ENTIRE screenshot, which already shows Day / Value / Money /
Profit in-game. No text is drawn.

Run:  python scripts/make_run_comparison.py
Out:  images/run_comparison.png
"""
from __future__ import annotations
import os
from PIL import Image, ImageDraw, ImageFont

IMG = os.path.join(os.path.dirname(__file__), "..", "images")

EARLY_DAYS = [11, 25, 50, 75, 99]
BEST_DAYS  = [10, 25, 50, 75, 99]

TW = 900          # scaled width per screenshot
GAP = 18
MARGIN = 24
BG = (14, 15, 18)
AMBER = (224, 178, 92)     # early run
GREEN = (78, 202, 128)     # best run


def font(sz, bold=True):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    cands = []
    try:
        import matplotlib
        cands.append(os.path.join(os.path.dirname(matplotlib.__file__),
                                  "mpl-data", "fonts", "ttf", name))
    except Exception:
        pass
    cands += [f"/usr/share/fonts/truetype/dejavu/{name}",
              f"/usr/share/fonts/dejavu/{name}", name]
    for p in cands:
        try:
            return ImageFont.truetype(p, sz)
        except OSError:
            continue
    try:
        return ImageFont.load_default(sz)   # Pillow >= 10 honors size
    except TypeError:
        return ImageFont.load_default()


def load(tag, day):
    im = Image.open(os.path.join(IMG, f"run_{tag}_day{day:02d}.png")).convert("RGB")
    h = round(TW * im.height / im.width)
    return im.resize((TW, h))


cells = [[load("early", d) for d in EARLY_DAYS],
         [load("best", d) for d in BEST_DAYS]]
CH = cells[0][0].height

HEADER_H = 96
W = MARGIN * 2 + 2 * TW + GAP
H = MARGIN + HEADER_H + 5 * CH + 4 * GAP + MARGIN
out = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(out)

f_col = font(58)


def centered(text, fnt, cx, y, fill):
    w = d.textlength(text, font=fnt)
    d.text((cx - w / 2, y), text, font=fnt, fill=fill)


# column labels only, centered over each column
col_cx = [MARGIN + TW / 2, MARGIN + TW + GAP + TW / 2]
WHITE = (245, 246, 248)
for cx, (name, accent) in zip(col_cx, [("Early Run", WHITE), ("Best Run", WHITE)]):
    centered(name, f_col, cx, MARGIN + 14, accent)

# grid
for col in range(2):
    for row in range(5):
        x = MARGIN + col * (TW + GAP)
        y = MARGIN + HEADER_H + row * (CH + GAP)
        out.paste(cells[col][row], (x, y))

path = os.path.join(IMG, "run_comparison.png")
out.save(path)
print("saved", os.path.abspath(path), out.size)
