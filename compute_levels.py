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
        a = area_poly.intersection(box(x, y, x + STEP, y + STEP)).area
        if a < 0.01:
            continue
        corners = [(i, j + 1), (i + 1, j + 1), (i + 1, j), (i, j)]  # TL TR BR BL
        lv = [level(*c) for c in corners]
        rows.append(dict(no=len(rows) + 1, i=i, j=j, x=x, y=y, area=a,
                         h=[v for v, _ in lv], hangar=sum(f == "HANGAR" for _, f in lv),
                         interp=sum(f == "TIN" for _, f in lv),
                         avg=sum(v for v, _ in lv) / 4))

# ---- Excel
wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Average levels"
hdr = ["Square No.", "Avg level (m)", "Top-left", "Top-right", "Bottom-right", "Bottom-left",
       "Area inside hatch (m²)", "Corners at hangar level", "Corners interpolated (TIN)", "X min", "Y min"]
ws.append(hdr)
for c in ws[1]:
    c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="305496")
    c.alignment = Alignment(horizontal="center", wrap_text=True)
yellow = PatternFill("solid", fgColor="FFF2CC"); orange = PatternFill("solid", fgColor="F8CBAD")
for r in rows:
    ws.append([r["no"], round(r["avg"], 3), *[round(v, 2) for v in r["h"]], round(r["area"], 2),
               r["hangar"], r["interp"], round(r["x"], 3), round(r["y"], 3)])
    if r["hangar"] or r["interp"]:
        for c in ws[ws.max_row]: c.fill = orange if r["interp"] else yellow
n = len(rows) + 1
ws.append([])
ws.append(["Squares", len(rows)])
ws.append(["Total area (m²)", f"=SUM(G2:G{n})"])
ws.append(["Simple mean of averages", f"=ROUND(AVERAGE(B2:B{n}),3)"])
ws.append(["Area-weighted mean level", f"=ROUND(SUMPRODUCT(B2:B{n},G2:G{n})/SUM(G2:G{n}),3)"])
ws.append([f"Yellow rows: one or more corners inside the hangar area, taken as {HANGAR_LEVEL}."])
ws.append(["Orange rows: one corner had no EL label and was interpolated from the survey TIN."])
for col, w in zip("ABCDEFGHIJK", [11, 13, 11, 11, 13, 12, 14, 12, 13, 14, 14]):
    ws.column_dimensions[col].width = w
ws.freeze_panes = "A2"
wb.save("average_levels.xlsx")

# ---- Drawing
fig, ax = plt.subplots(figsize=(22, 24), dpi=110)
ax.fill(*area_poly.exterior.xy, color="#e8eef7", zorder=0)
ax.plot(*area_poly.exterior.xy, color="magenta", lw=2, zorder=3)
for r in rows:
    ax.add_patch(plt.Rectangle((r["x"], r["y"]), STEP, STEP, fill=bool(r["hangar"] or r["interp"]),
                               fc="#f8cbad" if r["interp"] else "#fff2cc", ec="red", lw=0.6, zorder=1))
    cx, cy = r["x"] + STEP / 2, r["y"] + STEP / 2
    ax.text(cx, cy + 0.45, str(r["no"]), ha="center", va="center", fontsize=7.5, weight="bold", color="#b00000")
    ax.text(cx, cy - 0.55, f'{r["avg"]:.2f}', ha="center", va="center", fontsize=6.5, color="#003366")
ax.set_aspect("equal"); ax.axis("off")
ax.set_title("Square number (red) and average level in m (blue) — yellow = corner at hangar level 1115.55, orange = corner interpolated", fontsize=14)
fig.savefig("average_levels.png", bbox_inches="tight"); plt.close(fig)

a = np.array([r["avg"] for r in rows]); w = np.array([r["area"] for r in rows])
print(f"squares={len(rows)} area={w.sum():.1f} min={a.min():.2f} max={a.max():.2f} "
      f"weighted mean={np.average(a, weights=w):.3f} hangar squares={sum(1 for r in rows if r['hangar'])} TIN squares={sum(1 for r in rows if r['interp'])} "
      f"hangar points={len(hangar)}")
