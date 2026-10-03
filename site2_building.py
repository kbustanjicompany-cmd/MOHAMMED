"""Building inside the SITE2.dxf lot with setbacks: STREET_SETBACK = 3 m from the street
(west side, 13.52 m) and SIDE_SETBACK = 2.5 m from the other three sides.

  - setback line = intersection of the lot with every side moved inwards by its setback
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
    clear.append((LineString([p, q]).length, LineString([p, q]).distance(inner)))

doc = ezdxf.new("R2018", setup=True); doc.units = ezdxf.units.M
msp = doc.modelspace()
for name, col, lt in (("LOT", 7, "CONTINUOUS"), ("SETBACK-LINE", 3, "DASHED"), ("BUILDING-SQUARE", 1, "CONTINUOUS"),
                      ("BUILDING-SQUARE-HATCH", 1, "CONTINUOUS"), ("BUILDING-SETBACK-SHAPE", 5, "CONTINUOUS"),
                      ("DIM-TEXT", 2, "CONTINUOUS")):
    doc.layers.add(name, color=col, linetype=lt)
msp.add_lwpolyline(list(lot.exterior.coords)[:-1], close=True, dxfattribs={"layer": "LOT"})
msp.add_lwpolyline([tuple(p) for p in V], close=True, dxfattribs={"layer": "SETBACK-LINE"})
msp.add_lwpolyline([tuple(p) for p in V], close=True, dxfattribs={"layer": "BUILDING-SETBACK-SHAPE"})
msp.add_lwpolyline([tuple(p) for p in sq], close=True, dxfattribs={"layer": "BUILDING-SQUARE"})
h = msp.add_hatch(color=1, dxfattribs={"layer": "BUILDING-SQUARE-HATCH"})
h.set_pattern_fill("ANSI31", scale=0.1); h.paths.add_polyline_path([tuple(p) for p in sq], is_closed=True)
rot = ang if -90 < ang <= 90 else ang - 180
msp.add_mtext(f"SQUARE BUILDING {s:.2f} x {s:.2f} m\\PAREA = {s * s:.2f} m²\\P(street {STREET_SETBACK:g} m, other sides {SIDE_SETBACK:g} m)",
              dxfattribs={"layer": "DIM-TEXT", "char_height": 0.45, "rotation": rot}).set_location((cx, cy), attachment_point=5)
for (p, q) in edges:
    mid = (p + q) / 2
    msp.add_text(f"{np.linalg.norm(q - p):.2f}", height=0.3, dxfattribs={"layer": "DIM-TEXT"}).set_placement(tuple(mid))
msp.add_mtext(f"LOT {lot.area:.2f} m²  |  SETBACK OUTLINE (street 3 m, sides 2.5 m) {inner.area:.2f} m²  |  SQUARE {s:.2f} x {s:.2f} = {s * s:.2f} m²",
              dxfattribs={"layer": "DIM-TEXT", "char_height": 0.5}).set_location((lot.bounds[0], lot.bounds[3] + 2), attachment_point=7)
doc.saveas("site2_building.dxf")

fig, ax = plt.subplots(figsize=(14, 11))
ax.plot(*lot.exterior.xy, color="black", lw=2, label=f"lot {lot.area:.2f} m²")
ax.fill(*inner.exterior.xy, fc="#cfe2f3", ec="#1f4e9c", lw=2,
        label=f"building on the setback line (street 3 m, sides 2.5 m): {inner.area:.2f} m²")
ic = inner.centroid
ax.text(ic.x - 4, ic.y - 1.5, f"{inner.area:.2f} m²", fontsize=12, weight="bold", color="#1f4e9c")
for p, q in zip(list(inner.exterior.coords), list(inner.exterior.coords)[1:]):
    ax.text((p[0] + q[0]) / 2, (p[1] + q[1]) / 2, f"{np.hypot(q[0] - p[0], q[1] - p[1]):.2f}", fontsize=9,
            color="#1f4e9c", ha="center", bbox=dict(fc="white", ec="none", alpha=.7))
ax.fill(*square.exterior.xy, fc="none", ec="red", lw=1.5, ls="--", hatch="//", label=f"option: largest square {s:.2f} x {s:.2f} = {s * s:.2f} m²")
for (L_, d_), (p, q) in zip(clear, zip(lot_c, lot_c[1:])):
    m_ = ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)
    tag = "STREET\n" if abs(L_ - 13.518) < 0.05 else ""
    ax.text(*m_, f"{tag}{L_:.2f} m\nclear {d_:.2f}", fontsize=9, ha="center", color="#333333",
            bbox=dict(fc="white", ec="none", alpha=.8))
ax.text(cx, cy, f"{s:.2f} x {s:.2f}\n{s * s:.2f} m²", ha="center", va="center", fontsize=12, weight="bold", rotation=rot)
ax.set_aspect("equal"); ax.axis("off"); ax.legend(loc="lower right", fontsize=11)
ax.text(*lot.centroid.coords[0], "", fontsize=1)
ax.set_title("Building with setbacks: street (west) 3 m, other sides 2.5 m", fontsize=14, weight="bold")
fig.savefig("site2_building.pdf", bbox_inches="tight")
print(f"lot={lot.area:.2f} setback={inner.area:.2f} square side={s:.2f} area={s*s:.2f} angle={ang:.1f}")
print("setback-outline clearances", [(round(L_, 2), round(d_, 2)) for L_, d_ in clear])
