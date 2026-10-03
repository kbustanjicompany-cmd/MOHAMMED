"""Draw only the blinding of the isolated footings F1-F10 (16 No.) as a DXF, in the same
coordinates as FOUNDATIONS.dxf so it can be overlaid on the plan.

Each footing's concrete rectangle is taken from the S-CONCRETE PLANS lines of the plan:
starting from the footing's position and schedule size (A x B), every edge is snapped to
the nearest parallel concrete line within 0.15 m. The blinding is that rectangle offset by
PROJECTION (100 mm) on every side.
Outputs: footing_blinding.dxf, footing_blinding.pdf
"""
import sys
import numpy as np
import ezdxf
from ezdxf import path as zpath
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.argv = sys.argv[:1]
exec(open("footings_concrete.py").read().split('ws.title = "Footings & rafts"')[0])   # rows, SCHEDULE, PROJECTION
EXTRA = [("F2", 11.2, 6.05), ("F2", 19.5, 6.05), ("F3", 19.4, 9.4)]   # inside raft / tank pieces
foots = [(r[1].split()[1], r[4], r[5]) for r in rows if r[1].startswith("Footing") and "(x2)" not in r[1]
         and r[1] != "Footing F3"] + EXTRA
foots.sort(key=lambda f: (-round(f[2] / 3), f[1]))

# axis-aligned concrete segments of the plan
hseg, vseg = [], []
for g in conc_lines:
    c = list(g.coords)
    for (x1, y1), (x2, y2) in zip(c, c[1:]):
        if abs(y1 - y2) < 1e-3 and abs(x1 - x2) > .3:
            hseg.append((y1, min(x1, x2), max(x1, x2)))
        elif abs(x1 - x2) < 1e-3 and abs(y1 - y2) > .3:
            vseg.append((x1, min(y1, y2), max(y1, y2)))


def snap(val, segs, lo, hi, tol=0.15):
    best = None
    for pos, a, b in segs:
        if abs(pos - val) < tol and min(b, hi) - max(a, lo) > 0.3 * (hi - lo):
            if best is None or abs(pos - val) < abs(best - val):
                best = pos
    return best if best is not None else val


def piece_dims(x, y):
    """width (x) and height (y) of the footing piece at x, y in the footing mask."""
    k = lab[int((Y1 - y) / RES), int((x - X0) / RES)]
    if k == 0:
        return None
    sl = OBJS[k - 1]
    w, h = (sl[1].stop - sl[1].start) * RES, (sl[0].stop - sl[0].start) * RES
    return (w, h) if max(w, h) < 12 else None      # a raft / tank piece, not the footing itself


OBJS = ndi.find_objects(lab)
out = []
for i, (f, x, y) in enumerate(foots, 1):
    A, B, C = SCHEDULE[f]
    pd = piece_dims(x, y)
    # orientation: A along y unless the piece is wider than tall
    w, h = (max(A, B), min(A, B)) if pd and pd[0] > pd[1] + .1 else (min(A, B), max(A, B))
    if pd and abs(pd[0] - A) < .3 and abs(pd[1] - B) < .3:
        w, h = A, B
    elif pd and abs(pd[0] - B) < .3 and abs(pd[1] - A) < .3:
        w, h = B, A
    x0, x1, y0, y1 = x - w / 2, x + w / 2, y - h / 2, y + h / 2
    for _ in range(2):
        x0 = snap(x0, vseg, y0, y1); x1 = snap(x1, vseg, y0, y1)
        y0 = snap(y0, hseg, x0, x1); y1 = snap(y1, hseg, x0, x1)
    p = PROJECTION
    out.append(dict(no=i, f=f, conc=(x0, y0, x1, y1), blind=(x0 - p, y0 - p, x1 + p, y1 + p),
                    area=(x1 - x0 + 2 * p) * (y1 - y0 + 2 * p), size=(x1 - x0, y1 - y0)))

doc = ezdxf.new("R2018", setup=True); doc.units = ezdxf.units.M
msp = doc.modelspace()
doc.layers.add("BLINDING-FOOTINGS", color=1)
doc.layers.add("BLINDING-FOOTINGS-HATCH", color=1)
doc.layers.add("FOOTING-CONCRETE", color=4, linetype="DASHED")
doc.layers.add("FOOTING-LABEL", color=7)
for o in out:
    bx0, by0, bx1, by1 = o["blind"]
    pts = [(bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1)]
    msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "BLINDING-FOOTINGS"})
    h = msp.add_hatch(color=1, dxfattribs={"layer": "BLINDING-FOOTINGS-HATCH"})
    h.set_pattern_fill("ANSI31", scale=0.05); h.paths.add_polyline_path(pts, is_closed=True)
    cx0, cy0, cx1, cy1 = o["conc"]
    msp.add_lwpolyline([(cx0, cy0), (cx1, cy0), (cx1, cy1), (cx0, cy1)], close=True,
                       dxfattribs={"layer": "FOOTING-CONCRETE"})
    t = msp.add_mtext(f"{o['no']} - {o['f']}\\P{bx1 - bx0:.2f} x {by1 - by0:.2f}\\P{o['area']:.2f} m²",
                      dxfattribs={"layer": "FOOTING-LABEL", "char_height": 0.25})
    t.set_location(((bx0 + bx1) / 2, (by0 + by1) / 2), attachment_point=5)
total = sum(o["area"] for o in out)
msp.add_mtext(f"BLINDING UNDER ISOLATED FOOTINGS F1-F10 (16 No.) - 100 mm thick, projecting 100 mm\\P"
              f"TOTAL AREA = {total:.2f} m²", dxfattribs={"layer": "FOOTING-LABEL", "char_height": 0.6}
              ).set_location((-20, 62), attachment_point=7)
doc.saveas("footing_blinding.dxf")

fig, ax = plt.subplots(figsize=(16.5, 11.7))
for g in blind_lines: ax.plot(*g.xy, color="#dddddd", lw=.5)
for o in out:
    bx0, by0, bx1, by1 = o["blind"]
    ax.add_patch(plt.Rectangle((bx0, by0), bx1 - bx0, by1 - by0, fc="#f4cccc", ec="red", lw=1.5, hatch="///"))
    cx0, cy0, cx1, cy1 = o["conc"]
    ax.add_patch(plt.Rectangle((cx0, cy0), cx1 - cx0, cy1 - cy0, fill=False, ec="#0b7fab", lw=.8, ls="--"))
    small = o["area"] < 10
    ax.text((bx0 + bx1) / 2, by0 - .3 if small else (by0 + by1) / 2,
            f"{o['no']}-{o['f']}\n{bx1 - bx0:.2f}x{by1 - by0:.2f}\n{o['area']:.2f}m²" if small else
            f"{o['no']} - {o['f']}\n{bx1 - bx0:.2f} x {by1 - by0:.2f}\n{o['area']:.2f} m²",
            ha="center", va="top" if small else "center", fontsize=5.5 if small else 7.5, weight="bold",
            bbox=dict(fc="white", ec="none", alpha=.8, pad=1))
ax.set_xlim(-25, 25); ax.set_ylim(-4, 60); ax.set_aspect("equal"); ax.axis("off")
ax.set_title(f"Blinding under isolated footings F1-F10 (16 No.)   —   total {total:.2f} m²\n"
             "red = blinding (100 mm projection), dashed blue = footing concrete, grey = other foundation blinding",
             fontsize=13, weight="bold")
fig.savefig("footing_blinding.pdf", bbox_inches="tight")
for o in out:
    print(o["no"], o["f"], [round(v, 2) for v in o["size"]], round(o["area"], 2))
print("total", round(total, 2))
