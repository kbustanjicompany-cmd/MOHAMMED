"""Excavation under the footings and rafts (blinding area, ground beams excluded).

  - Footprint: blinding under footings & rafts from footings_concrete.py (FOUNDATIONS.dxf,
    local coordinates), placed on site with the exact transform found by matching the
    S-BLINDING LINE polylines that HATCHED_AREA.dxf also carries (rotation -6.81 deg).
  - Ground level: the same grid levels as compute_levels.py (EL labels, hangar points at
    1115.55, all lowered by LEVEL_DEDUCTION), interpolated bilinearly inside each 3 m square.
  - Bottom level: 1113.0 in area 1, 1118.0 in area 2.
  - Two figures are reported:
      A) below the bulk excavation level (area 1: 1114.85, area 2: 1120.9) down to the
         bottom level - the extra excavation for the footings after the bulk dig;
      B) from ground level down to the bottom level.
Outputs: footing_excavation.xlsx, footing_excavation.pdf/png
"""
import sys
import numpy as np
from shapely.geometry import Point
from shapely import contains_xy
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import openpyxl
from openpyxl.styles import Font, PatternFill

BOTTOM = {1: 1113.0, 2: 1118.0}
BULK = {1: 1114.85, 2: 1120.9}
COARSE = 5                     # integrate on 10 cm cells (5 x 2 cm pixels)

sys.argv = sys.argv[:1]
exec(open("footings_concrete.py").read().split('ws.title = "Footings & rafts"')[0])   # feet_blind, RES, X0, Y1, ...
ns = {}
exec(open("compute_levels.py").read().split("rows = []")[0], ns)                 # level(), X0/Y0 grid, area_poly
level, GX0, GY0, STEP, area1 = ns["level"], ns["X0"], ns["Y0"], ns["STEP"], ns["area_poly"]
a2 = {}
exec(open("number_area2.py").read().split("tin = ")[0], a2)
area2 = a2["area_poly"]

# local -> site transform (matched on S-BLINDING LINE polylines, residual < 1 mm)
ROT = np.radians(-6.808781732785986)
T = np.array([353780.83527366, 355922.56974443])
Rm = np.array([[np.cos(ROT), -np.sin(ROT)], [np.sin(ROT), np.cos(ROT)]])

# coarse cells: fraction of each 10 cm cell covered by blinding
h, w = (feet_blind.shape[0] // COARSE) * COARSE, (feet_blind.shape[1] // COARSE) * COARSE
frac = feet_blind[:h, :w].reshape(h // COARSE, COARSE, w // COARSE, COARSE).mean(axis=(1, 3))
r, c = np.nonzero(frac)
cell = RES * COARSE
lx = X0 + (c + 0.5) * cell
ly = Y1 - (r + 0.5) * cell
sx, sy = (Rm @ np.vstack([lx, ly])) + T[:, None]
cell_area = frac[r, c] * cell * cell

# ground level (bilinear in the 3 m grid squares)
gi, gj = (sx - GX0) / STEP, (sy - GY0) / STEP
i0, j0 = np.floor(gi).astype(int), np.floor(gj).astype(int)
fx, fy = gi - i0, gj - j0
cache = {}
def L(i, j):
    if (i, j) not in cache:
        cache[(i, j)] = level(i, j)[0]
    return cache[(i, j)]
z = np.array([(1 - a) * (1 - b) * L(i, j) + a * (1 - b) * L(i + 1, j) + (1 - a) * b * L(i, j + 1) + a * b * L(i + 1, j + 1)
              for i, j, a, b in zip(i0, j0, fx, fy)])

zone = np.zeros(len(sx), int)
zone[contains_xy(area1, sx, sy)] = 1
zone[contains_xy(area2, sx, sy)] = 2
in_excl = contains_xy(ns["excluded"], sx, sy)     # hangar / rooms (excluded from the bulk excavation)

res = {}
for k in (1, 2, 0):
    m = zone == k
    if not m.any():
        continue
    if k == 0:
        res[k] = dict(area=cell_area[m].sum())
        continue
    bot = BOTTOM[k]
    top_b = np.minimum(z[m], BULK[k])
    vol_a = (np.clip(top_b - bot, 0, None) * cell_area[m]).sum()
    vol_b = (np.clip(z[m] - bot, 0, None) * cell_area[m]).sum()
    e = in_excl[m]
    vol_a_ex = (np.clip(top_b - bot, 0, None) * cell_area[m])[e].sum()
    vol_b_ex = (np.clip(z[m] - bot, 0, None) * cell_area[m])[e].sum()
    res[k] = dict(area=cell_area[m].sum(), vol_a=vol_a, vol_b=vol_b,
                  zmin=z[m].min(), zmax=z[m].max(), zmean=np.average(z[m], weights=cell_area[m]),
                  area_ex=cell_area[m][e].sum(), vol_a_ex=vol_a_ex, vol_b_ex=vol_b_ex)

wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Footing excavation"
ws.append(["Zone", "Blinding area (m²)", "Bottom level", "Bulk exc. level",
           "A) below bulk level (m³)", "B) from ground (m³)", "Ground min", "Ground mean", "Ground max"])
for cc in ws[1]:
    cc.font = Font(bold=True, color="FFFFFF"); cc.fill = PatternFill("solid", fgColor="305496")
    cc.alignment = openpyxl.styles.Alignment(wrap_text=True)
tot = [0, 0, 0]
for k in (1, 2):
    if k in res:
        d = res[k]
        ws.append([f"Area {k}", round(d["area"], 2), BOTTOM[k], BULK[k], round(d["vol_a"], 2), round(d["vol_b"], 2),
                   round(d["zmin"], 2), round(d["zmean"], 2), round(d["zmax"], 2)])
        tot[0] += d["area"]; tot[1] += d["vol_a"]; tot[2] += d["vol_b"]
ws.append(["TOTAL (areas 1 + 2)", round(tot[0], 2), "", "", round(tot[1], 2), round(tot[2], 2)])
for cc in ws[ws.max_row]: cc.font = Font(bold=True)
if 0 in res:
    ws.append(["Outside both hatched areas (not counted)", round(res[0]["area"], 2)])
ws.append([])
ws.append(["Of which inside hangar / rooms zones", "Blinding area (m²)", "", "", "A) (m³)", "B) (m³)"])
for cc in ws[ws.max_row]: cc.font = Font(bold=True)
for k in (1, 2):
    if k in res:
        d = res[k]
        ws.append([f"Area {k} - inside hangar/rooms", round(d["area_ex"], 2), "", "", round(d["vol_a_ex"], 2), round(d["vol_b_ex"], 2)])
        ws.append([f"Area {k} - outside hangar/rooms", round(d["area"] - d["area_ex"], 2), "", "",
                   round(d["vol_a"] - d["vol_a_ex"], 2), round(d["vol_b"] - d["vol_b_ex"], 2)])
ws.append([])
ws.append(["Footprint", "blinding under footings & rafts, ground beams excluded (FOUNDATIONS.dxf)"])
ws.append(["Ground", f"grid levels lowered by {ns['LEVEL_DEDUCTION']} m, bilinear inside each 3 m square"])
ws.append(["A)", "from min(ground, bulk excavation level) down to the bottom level"])
ws.append(["B)", "from ground level down to the bottom level"])
for col, wd in zip("ABCDEFGHI", [36, 16, 12, 14, 18, 16, 11, 12, 11]):
    ws.column_dimensions[col].width = wd
wb.save("footing_excavation.xlsx")

fig, ax = plt.subplots(figsize=(16, 15), dpi=110)
ax.plot(*area1.exterior.xy, color="magenta", lw=2, label="Area 1 (to 1113.0)")
ax.plot(*area2.exterior.xy, color="#00a0c0", lw=2, label="Area 2 (to 1118.0)")
depth = np.where(zone == 1, np.minimum(z, BULK[1]) - BOTTOM[1], np.where(zone == 2, np.minimum(z, BULK[2]) - BOTTOM[2], np.nan))
sc = ax.scatter(sx, sy, c=depth, s=0.6, marker="s", cmap="YlOrRd", vmin=0, vmax=np.nanmax(depth))
ax.scatter(sx[zone == 0], sy[zone == 0], s=0.6, marker="s", color="#bbbbbb")
for gz in getattr(ns["excluded"], "geoms", [ns["excluded"]]):
    ax.plot(*gz.exterior.xy, color="blue", lw=1.5, ls="--")
ax.plot([], [], color="blue", ls="--", label="Hangar / rooms (excluded from bulk excavation)")
plt.colorbar(sc, ax=ax, shrink=0.6, label="depth below bulk excavation level (m)")
ax.set_aspect("equal"); ax.axis("off"); ax.legend(loc="lower left", fontsize=12)
ax.set_title(f"Excavation under footings & rafts (blinding area, no ground beams)\n"
             f"A) below bulk level = {tot[1]:,.1f} m³    B) from ground = {tot[2]:,.1f} m³", fontsize=14, weight="bold")
fig.savefig("footing_excavation.png", bbox_inches="tight"); fig.savefig("footing_excavation.pdf", bbox_inches="tight")
for k, d in res.items(): print(k, {kk: round(float(v), 2) for kk, v in d.items()})
print("total", [round(v, 2) for v in tot])
