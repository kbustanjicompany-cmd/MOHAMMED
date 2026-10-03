"""Blinding under the hatched and the not-hatched foundations of hatched-footings.dxf.

Hatched = the grey SOLID hatches on layer S-D-WATER PROOF (they follow the blinding outline
exactly, e.g. F2 + F2 + F3 = 24.94 m²) plus the footing the user hatched yellow on layer 0
(the F2 next to the water tank) - for that one its full blinding rectangle is used.
Not hatched = the rest of the blinding of all foundations (footings, rafts/mat, strip
footings, water tank; ground beams excluded) from footing_excavation.py.
Output: hatched_blinding.xlsx, hatched_blinding.pdf
"""
import sys
import numpy as np
import ezdxf
from ezdxf import path as zpath
from shapely.geometry import Polygon, box as sbox
from shapely.ops import unary_union
from shapely import contains_xy
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import openpyxl
from openpyxl.styles import Font, PatternFill

SRC = "hatched-footings.dxf"
sys.argv = sys.argv[:1]
fe = {}
exec(open("footing_excavation.py").read().split("lines = []")[0], fe)          # sx, sy, a_all, Rm, T
fb = {}
exec(open("footing_blinding_dxf.py").read().split("doc = ezdxf.new")[0], fb)    # isolated rectangles `out`
sx, sy, a_all, Rm, T = fe["sx"], fe["sy"], fe["a_all"], fe["Rm"], fe["T"]

msp = ezdxf.readfile(SRC).modelspace()


def hatch_geom(h):
    g = Polygon()
    for p in h.paths:
        pts = [(v.x, v.y) for v in zpath.from_hatch_boundary_path(p).flattening(0.005)]
        if len(pts) >= 3:
            g = g.symmetric_difference(Polygon(pts).buffer(0))
    return g


grey = [hatch_geom(h) for h in msp.query('HATCH[layer=="S-D-WATER PROOF"]')]
yellow = unary_union([hatch_geom(h) for h in msp.query('HATCH[layer=="0"]') if h.dxf.color == 2])
# full blinding rectangle of the footing the user hatched yellow (local -> site)
yel_rects = []
for o in fb["out"]:
    bx0, by0, bx1, by1 = o["blind"]
    corners = np.array([[bx0, by0], [bx1, by0], [bx1, by1], [bx0, by1]])
    site = Polygon([tuple(Rm @ c + T) for c in corners])
    if site.intersection(yellow).area > 0.5:
        yel_rects.append((o, site))
hatched = unary_union(grey + [s for _, s in yel_rects])
hatched_area = hatched.area

inside = contains_xy(hatched.buffer(0.03), sx, sy)
blind_total = a_all.sum()
blind_in = a_all[inside].sum()
blind_out = blind_total - blind_in

wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Hatched vs not"
ws.append(["Item", "Blinding area (m²)", "Volume @ 100 mm (m³)"])
for c in ws[1]:
    c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="305496")
for i, g in enumerate(grey, 1):
    ws.append([f"Hatched (grey) piece {i}", round(g.area, 2), round(g.area * .1, 2)])
for o, s in yel_rects:
    ws.append([f"Hatched (yellow) footing {o['f']} - full blinding {o['blind'][2] - o['blind'][0]:.2f} x "
               f"{o['blind'][3] - o['blind'][1]:.2f}", round(s.area, 2), round(s.area * .1, 2)])
ws.append(["HATCHED total (as drawn)", round(hatched_area, 2), round(hatched_area * .1, 2)])
ws.append(["NOT HATCHED total (blinding outside the hatch)", round(blind_out, 2), round(blind_out * .1, 2)])
ws.append(["ALL (hatched + not hatched)", round(hatched_area + blind_out, 2), round((hatched_area + blind_out) * .1, 2)])
for r in range(ws.max_row - 2, ws.max_row + 1):
    for c in ws[r]: c.font = Font(bold=True)
ws.append([])
ws.append(["check: traced blinding inside the hatch", round(blind_in, 2),
           "the hatch is drawn a little larger than the traced blinding"])
ws.column_dimensions["A"].width = 60; ws.column_dimensions["B"].width = 18; ws.column_dimensions["C"].width = 20
wb.save("hatched_blinding.xlsx")

fig, ax = plt.subplots(figsize=(15, 15))
ax.scatter(sx[~inside], sy[~inside], s=.5, marker="s", color="#6fa8dc", label=f"not hatched: {blind_out:,.2f} m²")
ax.scatter(sx[inside], sy[inside], s=.5, marker="s", color="#999999", label=f"hatched: {hatched_area:,.2f} m²")
for g in getattr(hatched, "geoms", [hatched]):
    ax.plot(*g.exterior.xy, color="black", lw=.8)
for o, s in yel_rects:
    ax.fill(*s.exterior.xy, color="yellow", ec="black", lw=.8)
ax.set_aspect("equal"); ax.axis("off"); ax.legend(loc="lower left", fontsize=13, markerscale=15)
ax.set_title(f"Blinding under foundations — hatched {hatched_area:,.2f} m²  |  not hatched {blind_out:,.2f} m²"
             f"  |  total {hatched_area + blind_out:,.2f} m²", fontsize=13, weight="bold")
fig.savefig("hatched_blinding.pdf", bbox_inches="tight")
print("grey", [round(g.area, 2) for g in grey], "yellow", [(o["f"], round(s.area, 2)) for o, s in yel_rects])
print(f"hatched={hatched_area:.2f} cells_in={blind_in:.2f} not={blind_out:.2f} sum={hatched_area + blind_out:.2f}")
