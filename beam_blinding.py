"""Blinding under the ground (tie) beams only (G.B, G.B1-G.B5) at a uniform width of
BEAM_W = 0.50 m for every beam.

  - beam concrete = the foundation RC footprint minus the footings/rafts (parts narrower
    than 1 m, see footings_concrete.py); pieces under 0.3 m² (corner slivers) are ignored
  - the beam zone = beam concrete grown by 100 mm, minus the blinding already under the
    footings and rafts (so nothing is counted twice); each separate beam piece is measured
    along its own axis (principal direction) from footing blinding to footing blinding
  - beam blinding = length x BEAM_W; a branching piece (wider than 1 m across its axis)
    is taken as its area / BEAM_W
Outputs: beam_blinding.dxf (traced closed polylines, plan coordinates), beam_blinding.pdf,
beam_blinding.xlsx
"""
import sys
import numpy as np
from skimage import measure
from shapely.geometry import Polygon
from shapely.ops import unary_union
import ezdxf
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import openpyxl
from openpyxl.styles import Font, PatternFill

sys.argv = sys.argv[:1]
exec(open("footings_concrete.py").read().split('ws.title = "Footings & rafts"')[0])
beam_rc = rc & ~feet
lb, nb = ndi.label(beam_rc)
sizes = ndi.sum(np.ones_like(lb), lb, index=np.arange(1, nb + 1)) * RES * RES
beam_rc = np.isin(lb, [i + 1 for i, a in enumerate(sizes) if a > 0.3])
BEAM_W = 0.50
k2 = 2 * int(0.2 / 2 / RES) + 1      # drop thin fringes left along the footing faces
beam_rc = ndi.maximum_filter(ndi.minimum_filter(beam_rc.astype(np.uint8), size=k2), size=k2).astype(bool)
P = int(round(PROJECTION / RES)); pdisk = np.hypot(*np.mgrid[-P:P + 1, -P:P + 1]) <= P
beam_bl = ndi.binary_dilation(beam_rc, structure=pdisk) & ~feet_blind
conc_area = beam_rc.sum() * RES * RES
bl_area = beam_bl.sum() * RES * RES
drawn_area = (blind & ~feet_blind).sum() * RES * RES


def trace(mask):
    m = np.pad(mask, 1)
    geom = Polygon()
    rings = []
    for c in measure.find_contours(m.astype(np.uint8), 0.5):
        if len(c) >= 4:
            pg = Polygon([(X0 + (cc - 1) * RES + RES / 2, Y1 - (rr - 1) * RES - RES / 2) for rr, cc in c]).buffer(0)
            if pg.area > 0.02:
                rings.append(pg)
    for pg in sorted(rings, key=lambda g: -g.area):
        geom = geom.symmetric_difference(pg)
    return geom.simplify(0.01)


pieces = []      # (length, centre, axis unit vector, polygon)
lbp, _ = ndi.label(beam_bl)
for kk, sl in enumerate(ndi.find_objects(lbp), 1):
    rr, cc = np.nonzero(lbp[sl] == kk)
    if len(rr) < 20:
        continue
    pts = np.c_[X0 + (cc + sl[1].start) * RES, Y1 - (rr + sl[0].start) * RES]
    mu = pts.mean(0); _, _, Vt = np.linalg.svd(pts - mu, full_matrices=False)
    u, nv = Vt[0], Vt[1]
    a_ = (pts - mu) @ u; b_ = (pts - mu) @ nv
    across = np.percentile(b_, 99) - np.percentile(b_, 1)
    area_px = len(rr) * RES * RES
    if across > 1.0:                       # branching piece
        L = area_px / BEAM_W
        poly = trace(lbp == kk)
    else:
        L = a_.max() - a_.min()
        c0 = mu + u * (a_.max() + a_.min()) / 2 + nv * (np.percentile(b_, 99) + np.percentile(b_, 1)) / 2
        h = BEAM_W / 2
        poly = Polygon([tuple(c0 - u * L / 2 - nv * h), tuple(c0 + u * L / 2 - nv * h),
                        tuple(c0 + u * L / 2 + nv * h), tuple(c0 - u * L / 2 + nv * h)])
    pieces.append((L, mu, u, poly))
beam_len = sum(p[0] for p in pieces)
bl_area_drawn_rule = bl_area
bl_area = beam_len * BEAM_W
polys = [p[3] for p in pieces]
doc = ezdxf.new("R2018", setup=True); doc.units = ezdxf.units.M
msp = doc.modelspace()
doc.layers.add("BLINDING-GROUND-BEAMS", color=30); doc.layers.add("BLINDING-GROUND-BEAMS-HATCH", color=30)
doc.layers.add("BLINDING-LABEL", color=7)
for pg in polys:
    ext = list(pg.exterior.coords)[:-1]
    msp.add_lwpolyline(ext, close=True, dxfattribs={"layer": "BLINDING-GROUND-BEAMS"})
    h = msp.add_hatch(color=30, dxfattribs={"layer": "BLINDING-GROUND-BEAMS-HATCH"})
    h.set_pattern_fill("ANSI31", scale=0.03)
    h.paths.add_polyline_path(ext, is_closed=True, flags=ezdxf.const.BOUNDARY_PATH_EXTERNAL)
    for hole in pg.interiors:
        msp.add_lwpolyline(list(hole.coords)[:-1], close=True, dxfattribs={"layer": "BLINDING-GROUND-BEAMS"})
        h.paths.add_polyline_path(list(hole.coords)[:-1], is_closed=True)
for L_, mu_, u_, pg in pieces:
    ang = float(np.degrees(np.arctan2(u_[1], u_[0])))
    ang = ang + 180 if ang < -90 else (ang - 180 if ang > 90 else ang)
    msp.add_text(f"{L_:.2f}", height=0.15, rotation=ang, dxfattribs={"layer": "BLINDING-LABEL"}
                 ).set_placement(tuple(mu_), align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)
msp.add_mtext(f"BLINDING UNDER GROUND (TIE) BEAMS - width {BEAM_W:.2f} m for all beams\\P"
              f"total length = {beam_len:.2f} m\\Pbeam blinding = {bl_area:.2f} m²  (volume @ 100 mm = {bl_area * .1:.2f} m³)",
              dxfattribs={"layer": "BLINDING-LABEL", "char_height": 0.5}).set_location((-50, 66), attachment_point=7)
doc.saveas("beam_blinding.dxf")

fig, ax = plt.subplots(figsize=(16.5, 13))
xs = np.linspace(X0, X1, W); ys = np.linspace(Y1, Y0, H)
ax.contourf(xs, ys, feet_blind.astype(float), levels=[.5, 1.5], colors=["#dddddd"])
for pg in polys:
    ax.fill(*pg.exterior.xy, fc="#e69138", ec="#7f4000", lw=.4)
ax.set_xlim(X0, X1); ax.set_ylim(Y0, Y1); ax.set_aspect("equal"); ax.axis("off")
ax.fill([], [], fc="#e69138", label=f"ground beam blinding: {bl_area:,.2f} m²")
ax.fill([], [], fc="#dddddd", label="footings / rafts blinding (not included)")
ax.legend(loc="upper center", bbox_to_anchor=(.5, -.01), ncol=2, fontsize=12, frameon=False)
ax.set_title(f"Blinding under ground (tie) beams only — width {BEAM_W:.2f} m — length {beam_len:,.1f} m — {bl_area:,.2f} m²", fontsize=14, weight="bold")
fig.savefig("beam_blinding.pdf", bbox_inches="tight")

wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Ground beams"
ws.append(["Item", "Value"])
for c in ws[1]:
    c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="305496")
for row in [("Blinding width taken for every tie beam (m)", BEAM_W),
            ("Total beam length between footing/raft blinding (m)", round(beam_len, 2)),
            ("Ground beam blinding = length x width (m²)", round(bl_area, 2)),
            ("Blinding volume @ 100 mm (m³)", round(bl_area * .1, 2)),
            ("Check: concrete + 100 mm each side (m²)", round(bl_area_drawn_rule, 2)),
            ("Check: beam blinding as drawn on the plan (m²)", round(drawn_area, 2))]:
    ws.append(list(row))
ws.append([])
ws.append(["Piece", "Length (m)", "Blinding @ width (m²)", "Centre X", "Centre Y"])
for c in ws[ws.max_row]: c.font = Font(bold=True)
for i, (L_, mu_, u_, pg) in enumerate(sorted(pieces, key=lambda p: (-round(p[1][1]), p[1][0])), 1):
    ws.append([i, round(L_, 2), round(L_ * BEAM_W, 2), round(mu_[0], 2), round(mu_[1], 2)])
ws.column_dimensions["A"].width = 70; ws.column_dimensions["B"].width = 14
wb.save("beam_blinding.xlsx")
print(f"length={beam_len:.2f} blinding@{BEAM_W}={bl_area:.2f} rule+0.1={bl_area_drawn_rule:.2f} drawn={drawn_area:.2f} pieces={len(pieces)}")
