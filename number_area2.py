"""Number the 3x3 m grid squares inside the second hatched area (east strip)
and give each square's average level (mean of its 4 corner EL labels).

Area 2 = closed cyan (colour 4) LWPOLYLINE on layer 0 in HATCHED_AREA.dxf.
Numbering: top row to bottom row, left to right.
Excavation per square = max(avg - FORMATION_LEVEL, 0) x area inside the hatch.
"""
import ezdxf, numpy as np
from shapely.geometry import Polygon, box
from scipy.interpolate import LinearNDInterpolator
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

STEP, TEXT_OFFSET = 3.0, 0.2427
FORMATION_LEVEL = 1120.9  # excavate down to this level
doc = ezdxf.readfile("HATCHED_AREA.dxf"); msp = doc.modelspace()

labels = {}
for e in msp.query('MTEXT[layer=="C-TOPO-TEXT"]'):
    x, y, z = e.dxf.insert
    labels[(x - TEXT_OFFSET, y)] = z
X0 = min(x for x, _ in labels); Y0 = min(y for _, y in labels)
grid = {(round((x - X0) / STEP), round((y - Y0) / STEP)): z for (x, y), z in labels.items()}

pl = next(e for e in msp.query('LWPOLYLINE[layer=="0"]') if e.closed and e.dxf.color == 4)
area_poly = Polygon([p[:2] for p in pl.get_points()])
# excluded: small buildings (bathroom room / canteen) = closed blue polylines on layer 0 with a
# "room" label, and the hangar (closed blue polyline around "H: 1115.55"), each offset 1 m all round
from shapely.geometry import Point
from shapely.ops import unary_union
OFFSET = 1.0
room_labels = [Point(t.dxf.insert.x, t.dxf.insert.y) for t in msp.query('TEXT MTEXT')
               if (t.text if t.dxftype() == "MTEXT" else t.dxf.text).strip().lower() == "room"]
blue = [Polygon([p[:2] for p in e.get_points()]) for e in msp.query('LWPOLYLINE[layer=="0"]')
        if e.closed and e.dxf.color == 5]
rooms = [P for P in blue if any(P.contains(l) for l in room_labels)]
rooms.append(Polygon([(353773.47, 355954.98), (353778.69, 355954.96), (353778.82, 355960.19), (353773.65, 355959.85)]))  # guard room
hangar_fp = next(P for P in blue if len(P.exterior.coords) == 8)
excluded = unary_union([r.buffer(OFFSET, join_style=2) for r in rooms] + [hangar_fp.buffer(OFFSET, join_style=2)])
work_poly = area_poly.difference(excluded)

tin = [tuple(e.dxf.insert) for e in msp.query('INSERT[layer=="V-NODE"]')]
tin = np.array(tin + [(x, y, z) for (x, y), z in labels.items()])
interp = LinearNDInterpolator(tin[:, :2], tin[:, 2])

def level(i, j):
    if (i, j) in grid:
        return grid[(i, j)], False
    return float(interp(X0 + i * STEP, Y0 + j * STEP)), True

minx, miny, maxx, maxy = area_poly.bounds
rows = []
for j in range(int((maxy - Y0) // STEP), int((miny - Y0) // STEP) - 1, -1):
    for i in range(int((minx - X0) // STEP), int((maxx - X0) // STEP) + 1):
        x, y = X0 + i * STEP, Y0 + j * STEP
        cell = box(x, y, x + STEP, y + STEP)
        if area_poly.intersection(cell).area < 0.01:
            continue
        a = work_poly.intersection(cell).area
        lv = [level(*c) for c in [(i, j + 1), (i + 1, j + 1), (i + 1, j), (i, j)]]
        rows.append(dict(no=len(rows) + 1, x=x, y=y, area=a, h=[v for v, _ in lv],
                         interp=sum(f for _, f in lv), avg=sum(v for v, _ in lv) / 4))
        d = rows[-1]["avg"] - FORMATION_LEVEL
        rows[-1].update(depth=d, cut=max(d, 0) * a, fill=max(-d, 0) * a)
cut, fill = sum(r["cut"] for r in rows), sum(r["fill"] for r in rows)

wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Area 2"
ws.append(["Square No.", "Avg level (m)", "Top-left", "Top-right", "Bottom-right", "Bottom-left",
           "Area inside hatch excl. rooms (m²)", "Corners interpolated (TIN)", "X min", "Y min",
           "Depth to formation (m)", "Cut volume (m³)", "Fill volume (m³)"])
for c in ws[1]:
    c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="305496")
    c.alignment = Alignment(horizontal="center", wrap_text=True)
for r in rows:
    ws.append([r["no"], round(r["avg"], 3), *[round(v, 2) for v in r["h"]], round(r["area"], 2),
               r["interp"], round(r["x"], 3), round(r["y"], 3),
               round(r["depth"], 3), round(r["cut"], 2), round(r["fill"], 2)])
    if r["interp"]:
        for c in ws[ws.max_row]: c.fill = PatternFill("solid", fgColor="F8CBAD")
ws.append([])
ws.append(["Squares", len(rows)])
ws.append([f"Rooms / hangar + {OFFSET:g} m area excluded (m²)", round(area_poly.intersection(excluded).area, 2)])
ws.append(["Total area (m²)", round(sum(r["area"] for r in rows), 2)])
ws.append([f"Formation level (m)", FORMATION_LEVEL])
ws.append(["Total cut (m³)", round(cut, 2)])
ws.append(["Total fill (m³)", round(fill, 2)])
ws.append(["Area-weighted mean level", round(sum(r["avg"] * r["area"] for r in rows) / sum(r["area"] for r in rows), 3)])
for col, w in zip("ABCDEFGHIJKLM", [11, 13, 11, 11, 13, 12, 14, 13, 14, 14, 13, 13, 13]):
    ws.column_dimensions[col].width = w
ws.freeze_panes = "A2"
wb.save("area2_levels.xlsx")

fig, ax = plt.subplots(figsize=(9, 24), dpi=110)
ax.fill(*area_poly.exterior.xy, color="#e8eef7", zorder=0)
ax.plot(*area_poly.exterior.xy, color="#00a0c0", lw=2, zorder=3)
for r in rows:
    ax.add_patch(plt.Rectangle((r["x"], r["y"]), STEP, STEP, fill=bool(r["interp"]), fc="#f8cbad",
                               ec="red", lw=0.6, zorder=1))
    cx, cy = r["x"] + STEP / 2, r["y"] + STEP / 2
    ax.text(cx, cy + 0.45, str(r["no"]), ha="center", va="center", fontsize=9, weight="bold", color="#b00000")
    ax.text(cx, cy - 0.55, f'{r["avg"]:.2f}', ha="center", va="center", fontsize=7.5, color="#003366")
for ez in getattr(excluded, "geoms", [excluded]):
    if ez.intersection(area_poly).area > 0:
        ax.fill(*ez.exterior.xy, fc=(1, 1, 1, 0.55), ec="#7030a0", hatch="xx", lw=1.5, zorder=2)
        ax.text(*ez.intersection(area_poly).centroid.coords[0], f"ROOM + {OFFSET:g} m\n(excluded)", ha="center",
                va="center", fontsize=8, weight="bold", color="#7030a0", zorder=5,
                bbox=dict(fc="white", ec="none", alpha=0.8))
ax.set_aspect("equal"); ax.axis("off")
ax.set_title(f"Area 2 — {len(rows)} squares: number (red) / average level m (blue)", fontsize=13)
fig.savefig("area2_numbered.png", bbox_inches="tight"); fig.savefig("area2_numbered.pdf", bbox_inches="tight")
plt.close(fig)
fig, ax = plt.subplots(figsize=(9, 24), dpi=110)
ax.plot(*area_poly.exterior.xy, color="#00a0c0", lw=2, zorder=3)
for r in rows:
    d = r["depth"]
    ax.add_patch(plt.Rectangle((r["x"], r["y"]), STEP, STEP, fc="#f4cccc" if d > 0 else "#cfe2f3",
                               ec="grey", lw=0.5, zorder=1))
    cx, cy = r["x"] + STEP / 2, r["y"] + STEP / 2
    ax.text(cx, cy + 0.75, str(r["no"]), ha="center", va="center", fontsize=9, weight="bold", color="#b00000")
    ax.text(cx, cy, f"{d:+.2f} m", ha="center", va="center", fontsize=7.5, color="#222222")
    ax.text(cx, cy - 0.75, f'{r["cut"] if d > 0 else -r["fill"]:.1f} m³', ha="center", va="center", fontsize=7.5, color="#003366")
for ez in getattr(excluded, "geoms", [excluded]):
    if ez.intersection(area_poly).area > 0:
        ax.fill(*ez.exterior.xy, fc=(1, 1, 1, 0.55), ec="#7030a0", hatch="xx", lw=1.5, zorder=2)
        ax.text(*ez.intersection(area_poly).centroid.coords[0], f"ROOM + {OFFSET:g} m\n(excluded)", ha="center",
                va="center", fontsize=8, weight="bold", color="#7030a0", zorder=5,
                bbox=dict(fc="white", ec="none", alpha=0.8))
ax.set_aspect("equal"); ax.axis("off")
ax.set_title(f"Area 2 — excavation to {FORMATION_LEVEL}\nsquare no. / depth / volume\n"
             f"Total cut = {cut:,.1f} m³   Total fill = {fill:,.1f} m³", fontsize=13)
fig.savefig("area2_excavation.png", bbox_inches="tight"); fig.savefig("area2_excavation.pdf", bbox_inches="tight")
plt.close(fig)
print(f"cut={cut:.2f} fill={fill:.2f} max depth={max(r['depth'] for r in rows):.2f} min depth={min(r['depth'] for r in rows):.2f}")
a = np.array([r["avg"] for r in rows])
print(f"squares={len(rows)} area={sum(r['area'] for r in rows):.1f} min={a.min():.2f} max={a.max():.2f} "
      f"interp squares={sum(1 for r in rows if r['interp'])}")
