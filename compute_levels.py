"""Average level of every 3x3 m grid square inside the hatched area.

Reads HATCHED_AREA.dxf:
  - grid levels: MTEXT "EL:xxxx.xx" on layer C-TOPO-TEXT (Z = exact level,
    grid point = centre of the small X marker, 0.2427 m left of the text)
  - hatched area: outer boundary of the white SOLID hatch on layer 0
  - grid points with no EL label in the hangar area (the large unlabeled block
    under the "hangar" text) take the hangar level HANGAR_LEVEL
  - any other unlabeled grid point is interpolated from the TIN nodes (V-NODE)
Square average = mean of its 4 corner levels.
Numbering: top row to bottom row, left to right.
Excavation per square = max(avg - FORMATION_LEVEL, 0) x area inside the hatch
(fill = the same for squares below the formation level).
"""
import ezdxf, numpy as np
from shapely.geometry import Polygon, box
from scipy.interpolate import LinearNDInterpolator
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

STEP, TEXT_OFFSET = 3.0, 0.2427
HANGAR_LEVEL = 1115.55
import sys
# excavate down to this level; pass another one on the command line, e.g. python3 compute_levels.py 1113
FORMATION_LEVEL = float(sys.argv[1]) if len(sys.argv) > 1 else 1114.85
SUFFIX = f"{FORMATION_LEVEL:g}"
doc = ezdxf.readfile("HATCHED_AREA.dxf"); msp = doc.modelspace()

labels = {}
for e in msp.query('MTEXT[layer=="C-TOPO-TEXT"]'):
    x, y, z = e.dxf.insert
    labels[(x - TEXT_OFFSET, y)] = z
X0 = min(x for x, _ in labels); Y0 = min(y for _, y in labels)
grid = {(round((x - X0) / STEP), round((y - Y0) / STEP)): z for (x, y), z in labels.items()}

hatch = next(h for h in msp.query('HATCH[layer=="0"]') if h.dxf.pattern_name == "SOLID")
outer = max((p for p in hatch.paths if hasattr(p, "vertices") and len(p.vertices) > 2),
            key=lambda p: Polygon([v[:2] for v in p.vertices]).area)
area_poly = Polygon([(v[0], v[1]) for v in outer.vertices])
# culvert (box culvert) zone, excluded from the volumes (square numbering is unchanged):
#  - culvert outline: closed magenta polyline on layer 0 around the "box cl" survey points
#  - its extension through the building: the two long S-SYMPOLS lines running south from it,
#    closed at both ends by the zig-zag break-line polylines
from shapely.ops import unary_union
culvert_head = next(Polygon([p[:2] for p in e.get_points()]) for e in msp.query('LWPOLYLINE[layer=="0"]')
                    if e.closed and e.dxf.color == 6 and len(e) == 8)
sym = [[tuple(p[:2]) for p in e.get_points()] for e in msp.query('LWPOLYLINE[layer=="S-SYMPOLS"]')]
long_lines = sorted((p for p in sym if len(p) in (3, 4) and max(y for _, y in p) - min(y for _, y in p) > 40),
                    key=lambda p: min(x for x, _ in p))
breaks = [p for p in sym if len(p) == 6 and max(x for x, _ in p) - min(x for x, _ in p) > 5]
west = sorted(long_lines[0], key=lambda q: -q[1])          # north -> south
east = sorted(long_lines[1], key=lambda q: q[1])           # south -> north
south_break = sorted(min(breaks, key=lambda p: p[0][1]), key=lambda q: q[0])   # west -> east
north_break = sorted(max(breaks, key=lambda p: p[0][1]), key=lambda q: -q[0])  # east -> west
culvert_ext = Polygon(west + south_break + east + north_break).buffer(0)
culvert = unary_union([culvert_head, culvert_ext])
# hangar footprint: closed blue polyline on layer 0 around "H: 1115.55", offset 1 m on its
# whole perimeter; excluded from all volumes like the culvert
HANGAR_OFFSET = 1.0
hangar_fp = next(Polygon([p[:2] for p in e.get_points()]) for e in msp.query('LWPOLYLINE[layer=="0"]')
                 if e.closed and e.dxf.color == 5 and len(e) == 7)
hangar_zone = hangar_fp.buffer(HANGAR_OFFSET, join_style=2)
# small buildings (bathroom room and canteen): the other closed blue polylines on layer 0
# that carry a "room" label, also offset 1 m all round and excluded
from shapely.geometry import Point
room_labels = [Point(t.dxf.insert.x, t.dxf.insert.y) for t in msp.query('TEXT MTEXT')
               if (t.text if t.dxftype() == "MTEXT" else t.dxf.text).strip().lower() == "room"]
rooms = [P for P in (Polygon([p[:2] for p in e.get_points()]) for e in msp.query('LWPOLYLINE[layer=="0"]')
                     if e.closed and e.dxf.color == 5)
         if any(P.contains(l) for l in room_labels)]
rooms_zone = unary_union([r.buffer(HANGAR_OFFSET, join_style=2) for r in rooms])
excluded = unary_union([culvert, hangar_zone, rooms_zone])
work_poly = area_poly.difference(excluded)

# TIN for grid points without a label: TIN nodes + the known labels
tin = [tuple(e.dxf.insert) for e in msp.query('INSERT[layer=="V-NODE"]')]
tin += [(x, y, z) for (x, y), z in labels.items()]
tin = np.array(tin)
interp = LinearNDInterpolator(tin[:, :2], tin[:, 2])

# hangar area = largest 4-connected block of unlabeled grid points inside the label extent
I_MAX = max(i for i, _ in grid); J_MAX = max(j for _, j in grid)
unlabeled = {(i, j) for i in range(I_MAX + 1) for j in range(J_MAX + 1) if (i, j) not in grid
             and any((a, j) in grid for a in range(i)) and any((a, j) in grid for a in range(i + 1, I_MAX + 1))
             and any((i, b) in grid for b in range(j)) and any((i, b) in grid for b in range(j + 1, J_MAX + 1))}
hangar, seen = set(), set()
for start in unlabeled:
    if start in seen:
        continue
    block, todo = set(), [start]
    while todo:
        c = todo.pop()
        if c in seen or c not in unlabeled:
            continue
        seen.add(c); block.add(c)
        todo += [(c[0] + 1, c[1]), (c[0] - 1, c[1]), (c[0], c[1] + 1), (c[0], c[1] - 1)]
    if len(block) > len(hangar):
        hangar = block

def level(i, j):
    """Return (level, source) with source 'EL', 'HANGAR' or 'TIN'."""
    if (i, j) in grid:
        return grid[(i, j)], "EL"
    if (i, j) in hangar:
        return HANGAR_LEVEL, "HANGAR"
    return float(interp(X0 + i * STEP, Y0 + j * STEP)), "TIN"

xs = [p[0] for p in area_poly.exterior.coords]; ys = [p[1] for p in area_poly.exterior.coords]
i_rng = range(int((min(xs) - X0) // STEP), int((max(xs) - X0) // STEP) + 1)
j_rng = range(int((max(ys) - Y0) // STEP), int((min(ys) - Y0) // STEP) - 1, -1)

rows = []
for j in j_rng:
    for i in i_rng:
        x, y = X0 + i * STEP, Y0 + j * STEP
        cell = box(x, y, x + STEP, y + STEP)
        if area_poly.intersection(cell).area < 0.01:
            continue
        a = work_poly.intersection(cell).area
        corners = [(i, j + 1), (i + 1, j + 1), (i + 1, j), (i, j)]  # TL TR BR BL
        lv = [level(*c) for c in corners]
        rows.append(dict(no=len(rows) + 1, i=i, j=j, x=x, y=y, area=a,
                         h=[v for v, _ in lv], hangar=sum(f == "HANGAR" for _, f in lv),
                         interp=sum(f == "TIN" for _, f in lv),
                         avg=sum(v for v, _ in lv) / 4))

# ---- Excel
wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Average levels"
hdr = ["Square No.", "Avg level (m)", "Top-left", "Top-right", "Bottom-right", "Bottom-left",
       "Area inside hatch excl. culvert, hangar & rooms (m²)", "Corners at hangar level", "Corners interpolated (TIN)", "X min", "Y min",
       "Depth to formation (m)", "Cut volume (m³)", "Fill volume (m³)"]
ws.append(hdr)
for c in ws[1]:
    c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="305496")
    c.alignment = Alignment(horizontal="center", wrap_text=True)
yellow = PatternFill("solid", fgColor="FFF2CC"); orange = PatternFill("solid", fgColor="F8CBAD")
for r in rows:
    ws.append([r["no"], round(r["avg"], 3), *[round(v, 2) for v in r["h"]], round(r["area"], 2),
               r["hangar"], r["interp"], round(r["x"], 3), round(r["y"], 3)])
    k = ws.max_row
    d = r["avg"] - FORMATION_LEVEL
    r["cut"], r["fill"] = max(d, 0) * r["area"], max(-d, 0) * r["area"]
    ws[f"L{k}"], ws[f"M{k}"], ws[f"N{k}"] = round(d, 3), round(r["cut"], 2), round(r["fill"], 2)
    if r["hangar"] or r["interp"]:
        for c in ws[ws.max_row]: c.fill = orange if r["interp"] else yellow
n = len(rows) + 1
ws.append([])
ws.append(["Squares", len(rows)])
ws.append(["Total cut (m³)", round(sum(r["cut"] for r in rows), 2)])
ws.append(["Total fill (m³)", round(sum(r["fill"] for r in rows), 2)])
ws.append(["Total area (m²)", round(sum(r["area"] for r in rows), 2)])
ws.append(["Simple mean of averages", round(sum(r["avg"] for r in rows) / len(rows), 3)])
ws.append(["Area-weighted mean level", round(sum(r["avg"] * r["area"] for r in rows) / sum(r["area"] for r in rows), 3)])
ws.append([f"Yellow rows: one or more corners inside the hangar area, taken as {HANGAR_LEVEL}."])
ws.append(["Orange rows: one corner had no EL label and was interpolated from the survey TIN."])
for col, w in zip("ABCDEFGHIJKLMN", [11, 13, 11, 11, 13, 12, 14, 12, 13, 14, 14, 13, 13, 13]):
    ws.column_dimensions[col].width = w
ws.freeze_panes = "A2"
sm = wb.create_sheet("Summary", 0)
cut, fill = sum(r["cut"] for r in rows), sum(r["fill"] for r in rows)
for row in [["Formation level (m)", FORMATION_LEVEL],
            ["Squares", len(rows)],
            ["Total area (m²)", round(sum(r["area"] for r in rows), 2)],
            ["Total cut / excavation (m³)", round(cut, 2)],
            ["Total fill (m³)", round(fill, 2)],
            ["Net (cut - fill) (m³)", round(cut - fill, 2)],
            ["Squares with cut", sum(r["cut"] > 0 for r in rows)],
            ["Squares with fill", sum(r["fill"] > 0 for r in rows)],
            ["Method", "Grid method: square average = mean of 4 corner levels; volume = depth x area inside hatch"],
            ["Culvert area excluded (m²)", round(area_poly.intersection(culvert).area, 2)],
            [f"Hangar + {HANGAR_OFFSET:g} m area excluded (m²)", round(area_poly.intersection(hangar_zone).area, 2)],
            [f"Rooms (bathroom / canteen) + {HANGAR_OFFSET:g} m area excluded (m²)", round(area_poly.intersection(rooms_zone).area, 2)],
            ["Total excluded (overlaps counted once) (m²)", round(area_poly.intersection(excluded).area, 2)],
            ["Hangar area", f"Unlabeled grid points under the hangar taken as {HANGAR_LEVEL}"]]:
    sm.append(row)
for c in sm["A"]: c.font = Font(bold=True)
sm["B1"].fill = PatternFill("solid", fgColor="FFFF00")
sm.column_dimensions["A"].width = 44; sm.column_dimensions["B"].width = 18
wb.save(f"average_levels_{SUFFIX}.xlsx")

# ---- Drawing
fig, ax = plt.subplots(figsize=(22, 24), dpi=110)
ax.fill(*area_poly.exterior.xy, color="#e8eef7", zorder=0)
ax.plot(*area_poly.exterior.xy, color="magenta", lw=2, zorder=3)
ax.fill(*hangar_zone.exterior.xy, fc=(1, 1, 1, 0.55), ec="#1f4e9c", hatch="\\\\", lw=1.5, zorder=2)
ax.fill(*culvert.exterior.xy, fc=(1, 1, 1, 0.0), ec="#555555", hatch="///", lw=1.2, zorder=2)
for rz in getattr(rooms_zone, "geoms", [rooms_zone]):
    ax.fill(*rz.exterior.xy, fc=(1, 1, 1, 0.55), ec="#7030a0", hatch="xx", lw=1.5, zorder=2)
    ax.text(*rz.centroid.coords[0], f"ROOM + {HANGAR_OFFSET:g} m\n(excluded)", ha="center", va="center", fontsize=8,
            weight="bold", color="#7030a0", zorder=5, bbox=dict(fc="white", ec="none", alpha=0.8))
ax.text(*hangar_fp.centroid.coords[0], f"HANGAR + {HANGAR_OFFSET:g} m  (excluded)", ha="center", va="center", fontsize=10,
        weight="bold", color="#1f4e9c", rotation=-78, zorder=5, bbox=dict(fc="white", ec="none", alpha=0.8))
ax.text(*culvert_head.centroid.coords[0], "CULVERT\n(excluded)", ha="center", va="center", fontsize=9, weight="bold", color="black", zorder=5, bbox=dict(fc="white", ec="none", alpha=0.8))
for r in rows:
    ax.add_patch(plt.Rectangle((r["x"], r["y"]), STEP, STEP, fill=bool(r["hangar"] or r["interp"]),
                               fc="#f8cbad" if r["interp"] else "#fff2cc", ec="red", lw=0.6, zorder=1))
    cx, cy = r["x"] + STEP / 2, r["y"] + STEP / 2
    ax.text(cx, cy + 0.45, str(r["no"]), ha="center", va="center", fontsize=7.5, weight="bold", color="#b00000")
    ax.text(cx, cy - 0.55, f'{r["avg"]:.2f}', ha="center", va="center", fontsize=6.5, color="#003366")
ax.set_aspect("equal"); ax.axis("off")
ax.set_title("Square number (red) and average level in m (blue) — yellow = corner at hangar level 1115.55, orange = corner interpolated", fontsize=14)
fig.savefig("average_levels.png", bbox_inches="tight"); fig.savefig("average_levels.pdf", bbox_inches="tight"); plt.close(fig)

fig, ax = plt.subplots(figsize=(22, 24), dpi=110)
ax.plot(*area_poly.exterior.xy, color="magenta", lw=2, zorder=3)
ax.fill(*hangar_zone.exterior.xy, fc=(1, 1, 1, 0.55), ec="#1f4e9c", hatch="\\\\", lw=1.5, zorder=2)
ax.fill(*culvert.exterior.xy, fc=(1, 1, 1, 0.0), ec="#555555", hatch="///", lw=1.2, zorder=2)
for rz in getattr(rooms_zone, "geoms", [rooms_zone]):
    ax.fill(*rz.exterior.xy, fc=(1, 1, 1, 0.55), ec="#7030a0", hatch="xx", lw=1.5, zorder=2)
    ax.text(*rz.centroid.coords[0], f"ROOM + {HANGAR_OFFSET:g} m\n(excluded)", ha="center", va="center", fontsize=8,
            weight="bold", color="#7030a0", zorder=5, bbox=dict(fc="white", ec="none", alpha=0.8))
ax.text(*hangar_fp.centroid.coords[0], f"HANGAR + {HANGAR_OFFSET:g} m  (excluded)", ha="center", va="center", fontsize=10,
        weight="bold", color="#1f4e9c", rotation=-78, zorder=5, bbox=dict(fc="white", ec="none", alpha=0.8))
ax.text(*culvert_head.centroid.coords[0], "CULVERT\n(excluded)", ha="center", va="center", fontsize=9, weight="bold", color="black", zorder=5, bbox=dict(fc="white", ec="none", alpha=0.8))
for r in rows:
    d = r["avg"] - FORMATION_LEVEL
    ax.add_patch(plt.Rectangle((r["x"], r["y"]), STEP, STEP, fc="#f4cccc" if d > 0 else "#cfe2f3",
                               ec="grey", lw=0.5, zorder=1))
    cx, cy = r["x"] + STEP / 2, r["y"] + STEP / 2
    ax.text(cx, cy + 0.75, str(r["no"]), ha="center", va="center", fontsize=7, weight="bold", color="#b00000")
    ax.text(cx, cy, f'{d:+.2f} m', ha="center", va="center", fontsize=6, color="#222222")
    ax.text(cx, cy - 0.75, f'{r["cut"] if d > 0 else -r["fill"]:.1f} m³', ha="center", va="center", fontsize=6, color="#003366")
ax.set_aspect("equal"); ax.axis("off")
cut = sum(r["cut"] for r in rows); fill = sum(r["fill"] for r in rows)
ax.set_title(f"Excavation to {FORMATION_LEVEL}: square no. / depth / volume — red = cut, blue = fill\n"
             f"Total cut = {cut:,.1f} m³   Total fill = {fill:,.1f} m³", fontsize=14)
fig.savefig(f"excavation_{SUFFIX}.png", bbox_inches="tight"); fig.savefig(f"excavation_{SUFFIX}.pdf", bbox_inches="tight"); plt.close(fig)
print(f"cut={cut:.2f} fill={fill:.2f} cut squares={sum(r['cut'] > 0 for r in rows)} fill squares={sum(r['fill'] > 0 for r in rows)}")

a = np.array([r["avg"] for r in rows]); w = np.array([r["area"] for r in rows])
print(f"squares={len(rows)} area={w.sum():.1f} min={a.min():.2f} max={a.max():.2f} "
      f"weighted mean={np.average(a, weights=w):.3f} hangar squares={sum(1 for r in rows if r['hangar'])} TIN squares={sum(1 for r in rows if r['interp'])} "
      f"hangar points={len(hangar)}")
