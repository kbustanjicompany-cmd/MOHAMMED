"""Largest RECTANGULAR building inside the SITE2.dxf lot with setbacks: STREET_SETBACK = 3 m from the street
(west side, 13.52 m) and SIDE_SETBACK = 2.5 m from the other three sides.

  - setback line = intersection of the lot with every side moved inwards by its setback
  - the largest rectangle (max area) inside the setback line: for every orientation (0.5 deg)
    and width (0.1 m) a linear programme gives the largest depth, then refined to
    0.05 deg / 0.01 m; sides rounded down to the centimetre
  - the largest square inside the setback line is found by linear programming for every
    orientation (0.1 deg steps): maximise side s over centre (cx, cy) with all four corners
    inside every (convex) setback edge
  - also drawn: the full setback outline (a building following the lot shape)
Outputs: site2_building.dxf (site coordinates, for overlay), site2_building.pdf
"""
import numpy as np
import ezdxf
from ezdxf import path as zpath
from shapely.geometry import Polygon, Point
from shapely.geometry.polygon import orient
from scipy.optimize import linprog
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

STREET_SETBACK, SIDE_SETBACK = 3.0, 2.5
SETBACK = SIDE_SETBACK
msp_in = ezdxf.readfile("SITE2.dxf").modelspace()
lot = next(Polygon([(v.x, v.y) for v in zpath.make_path(e).flattening(0.005)])
           for e in msp_in.query('LWPOLYLINE[layer=="0"]') if e.closed and e.dxf.color == 11)
lot = orient(lot, 1.0)
lc = list(lot.exterior.coords)


def is_street(p, q):          # the west side: the 13.52 m edge whose midpoint is furthest west
    return abs(np.hypot(q[0] - p[0], q[1] - p[1]) - 13.518) < 0.05


inner = lot
for p, q in zip(lc, lc[1:]):
    p, q = np.array(p), np.array(q)
    e = q - p; n = np.array([-e[1], e[0]]) / np.linalg.norm(e)                # inward normal (CCW)
    d = STREET_SETBACK if is_street(p, q) else SIDE_SETBACK
    big = 1000 * e / np.linalg.norm(e)
    a0, a1 = p + n * d - big, q + n * d + big
    inner = inner.intersection(Polygon([tuple(a0), tuple(a1), tuple(a1 + n * 1000), tuple(a0 + n * 1000)]))
inner = orient(inner.simplify(0.001), 1.0)
assert abs(inner.convex_hull.area - inner.area) < 1e-6, "setback outline must be convex"
V = np.array(inner.exterior.coords)[:-1]
edges = [(V[k], V[(k + 1) % len(V)]) for k in range(len(V))]
ox, oy = V.mean(0)


def best_square(theta):
    u = np.array([np.cos(theta), np.sin(theta)]); v = np.array([-u[1], u[0]])
    corners = [(+.5, +.5), (+.5, -.5), (-.5, +.5), (-.5, -.5)]
    A, b = [], []
    for p, q in edges:
        e = q - p; n = np.array([-e[1], e[0]]); n /= np.linalg.norm(n)       # inward normal (CCW)
        for a_, b_ in corners:
            k = n @ (a_ * u + b_ * v)
            # n.(c + s*k_vec - p) >= 0  ->  -n.c - s*k <= -n.p
            A.append([-n[0], -n[1], -k]); b.append(-(n @ (p - [ox, oy])))
    r = linprog([0, 0, -1], A_ub=A, b_ub=b, bounds=[(None, None), (None, None), (0, None)])
    return (r.x[2], r.x[0] + ox, r.x[1] + oy, u, v) if r.success else (0, 0, 0, u, v)


def best_rect(theta, w):
    """largest h for a w x h rectangle (w along theta) inside the setback outline."""
    u = np.array([np.cos(theta), np.sin(theta)]); v = np.array([-u[1], u[0]])
    A, b = [], []
    for p, q in edges:
        e = q - p; n = np.array([-e[1], e[0]]); n /= np.linalg.norm(n)
        for a_, b_ in [(+.5, +.5), (+.5, -.5), (-.5, +.5), (-.5, -.5)]:
            # n.(c + a_*w*u + b_*h*v - p) >= 0
            A.append([-n[0], -n[1], -b_ * (n @ v)]); b.append(-(n @ (p - [ox, oy])) + a_ * w * (n @ u))
    r = linprog([0, 0, -1], A_ub=A, b_ub=b, bounds=[(None, None), (None, None), (0, None)])
    return (r.x[2], r.x[0] + ox, r.x[1] + oy) if r.success else (0, 0, 0)


best = (0,)
for a in np.arange(0, 180, 0.5):
    th = np.radians(a)
    for w in np.arange(4, 20, 0.1):
        h, rx, ry = best_rect(th, w)
        if w * h > best[0]:
            best = (w * h, w, h, rx, ry, th)
# refine around the best orientation / width
a0, w0 = np.degrees(best[5]), best[1]
for a in np.arange(a0 - 0.6, a0 + 0.6, 0.05):
    th = np.radians(a)
    for w in np.arange(w0 - 0.2, w0 + 0.2, 0.01):
        h, rx, ry = best_rect(th, w)
        if w * h > best[0]:
            best = (w * h, w, h, rx, ry, th)
_, rw, rh, rx, ry, rth = best
rw, rh = np.floor(rw * 100) / 100, np.floor(rh * 100) / 100
ru = np.array([np.cos(rth), np.sin(rth)]); rv = np.array([-ru[1], ru[0]])
rect = [np.array([rx, ry]) + a_ * rw * ru + b_ * rh * rv for a_, b_ in [(-.5, -.5), (.5, -.5), (.5, .5), (-.5, .5)]]
rect_poly = Polygon(rect)
assert inner.buffer(1e-6).contains(rect_poly)

cands = [best_square(np.radians(a)) for a in np.arange(0, 90, 0.1)]
s, cx, cy, u, v = max(cands, key=lambda t: t[0])
s = np.floor(s * 100) / 100                     # round the side down to the centimetre
sq = [np.array([cx, cy]) + s * (a_ * u + b_ * v) for a_, b_ in [(-.5, -.5), (.5, -.5), (.5, .5), (-.5, .5)]]
square = Polygon(sq)
assert inner.buffer(1e-6).contains(square)
ang = np.degrees(np.arctan2(u[1], u[0]))
# clearance of the square to every lot side
lot_c = list(lot.exterior.coords)
clear = []
for p, q in zip(lot_c, lot_c[1:]):
    from shapely.geometry import LineString
    clear.append((LineString([p, q]).length, LineString([p, q]).distance(rect_poly)))

doc = ezdxf.new("R2018", setup=True); doc.units = ezdxf.units.M
msp = doc.modelspace()
for name, col, lt in (("LOT", 7, "CONTINUOUS"), ("SETBACK-LINE", 3, "DASHED"), ("BUILDING-SQUARE", 1, "CONTINUOUS"),
                      ("BUILDING-SQUARE-HATCH", 1, "CONTINUOUS"), ("BUILDING-SETBACK-SHAPE", 5, "CONTINUOUS"), ("BUILDING-RECTANGLE", 6, "CONTINUOUS"),
                      ("DIM-TEXT", 2, "CONTINUOUS")):
    doc.layers.add(name, color=col, linetype=lt)
msp.add_lwpolyline(list(lot.exterior.coords)[:-1], close=True, dxfattribs={"layer": "LOT"})
msp.add_lwpolyline([tuple(p) for p in V], close=True, dxfattribs={"layer": "SETBACK-LINE"})
msp.add_lwpolyline([tuple(p) for p in V], close=True, dxfattribs={"layer": "BUILDING-SETBACK-SHAPE"})
msp.add_lwpolyline([tuple(p) for p in sq], close=True, dxfattribs={"layer": "BUILDING-SQUARE"})
msp.add_lwpolyline([tuple(p) for p in rect], close=True, dxfattribs={"layer": "BUILDING-RECTANGLE"})
hr = msp.add_hatch(color=5, dxfattribs={"layer": "BUILDING-RECTANGLE"})
hr.set_pattern_fill("ANSI31", scale=0.1); hr.paths.add_polyline_path([tuple(p) for p in rect], is_closed=True)
rang_ = np.degrees(rth); rrot_ = rang_ if -90 < rang_ <= 90 else rang_ - 180
msp.add_mtext(f"BUILDING {rw:.2f} x {rh:.2f} m\\PAREA = {rw * rh:.2f} m²\\P(street >= 3 m, sides >= 2.5 m)",
              dxfattribs={"layer": "DIM-TEXT", "char_height": 0.45, "rotation": rrot_}).set_location((rx, ry), attachment_point=5)
for p, q in zip(rect, rect[1:] + rect[:1]):
    m2 = (p + q) / 2; ea = np.degrees(np.arctan2(q[1] - p[1], q[0] - p[0])); ea = ea if -90 < ea <= 90 else ea - 180
    msp.add_text(f"{np.linalg.norm(q - p):.2f}", height=0.3, rotation=ea, dxfattribs={"layer": "DIM-TEXT"}
                 ).set_placement(tuple(m2), align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)

rot = ang if -90 < ang <= 90 else ang - 180

for (p, q) in edges:
    mid = (p + q) / 2
    msp.add_text(f"{np.linalg.norm(q - p):.2f}", height=0.3, dxfattribs={"layer": "DIM-TEXT"}).set_placement(tuple(mid))
msp.add_mtext(f"LOT {lot.area:.2f} m²  |  BUILDING (largest rectangle) {rw:.2f} x {rh:.2f} = {rw * rh:.2f} m²  |  square option {s:.2f} x {s:.2f} = {s * s:.2f} m²",
              dxfattribs={"layer": "DIM-TEXT", "char_height": 0.5}).set_location((lot.bounds[0], lot.bounds[3] + 2), attachment_point=7)
doc.saveas("site2_building.dxf")

fig, ax = plt.subplots(figsize=(14, 11))
ax.plot(*lot.exterior.xy, color="black", lw=2, label=f"lot {lot.area:.2f} m²")
ax.plot(*inner.exterior.xy, color="green", lw=1.2, ls="--",
        label=f"setback line: street 3 m, sides 2.5 m ({inner.area:.2f} m²)")
ax.fill(*rect_poly.exterior.xy, fc="#cfe2f3", ec="#1f4e9c", lw=2.5, hatch="//",
        label=f"BUILDING - largest rectangle {rw:.2f} x {rh:.2f} = {rw * rh:.2f} m²")
rang = np.degrees(rth); rrot = rang if -90 < rang <= 90 else rang - 180
ax.text(rx, ry, f"{rw:.2f} x {rh:.2f} m\n{rw * rh:.2f} m²", ha="center", va="center", fontsize=13,
        weight="bold", rotation=rrot, color="#0b3d91", bbox=dict(fc="white", ec="none", alpha=.85))
for p, q in zip(rect, rect[1:] + rect[:1]):
    m2 = (p + q) / 2
    ax.text(*m2, f"{np.linalg.norm(q - p):.2f}", fontsize=10, color="#0b3d91", ha="center", va="center",
            bbox=dict(fc="#ffffcc", ec="none", alpha=.9))
ic = inner.centroid

ax.fill(*square.exterior.xy, fc="none", ec="red", lw=1, ls=":", label=f"(previous option: square {s:.2f} x {s:.2f} = {s * s:.2f} m²)")
for (L_, d_), (p, q) in zip(clear, zip(lot_c, lot_c[1:])):
    m_ = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
    tag = "STREET\n" if abs(L_ - 13.518) < 0.05 else ""
    ax.text(*m_, f"{tag}{L_:.2f} m\nclear {d_:.2f}", fontsize=9, ha="center", color="#333333",
            bbox=dict(fc="white", ec="none", alpha=.8))

ax.set_aspect("equal"); ax.axis("off"); ax.legend(loc="lower right", fontsize=11)
ax.text(*lot.centroid.coords[0], "", fontsize=1)
ax.set_title(f"Largest rectangular building {rw:.2f} x {rh:.2f} m = {rw * rh:.2f} m²\n"
             "at least 3 m from the street (west) and 2.5 m from the other sides", fontsize=13, weight="bold")
fig.savefig("site2_building.pdf", bbox_inches="tight")
print(f"lot={lot.area:.2f} setback={inner.area:.2f} square side={s:.2f} area={s*s:.2f} angle={ang:.1f} rect={rw:.2f}x{rh:.2f}={rw*rh:.2f} rect_angle={np.degrees(rth):.1f}")
rcl = [(round(LineString([p, q]).length, 2), round(LineString([p, q]).distance(rect_poly), 2)) for p, q in zip(lot_c, lot_c[1:])]
print("rectangle clearances", rcl)
print("rectangle clearances (plot)", [(round(L_, 2), round(d_, 2)) for L_, d_ in clear])
