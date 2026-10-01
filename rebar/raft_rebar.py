"""Bar bending schedule of the rafts, read from the reinforcement shown on the foundation
plan of FOUNDATIONS.dxf (layer S-Steel = typical bar, S-TEXT-STEEL = its label such as
"Ø14/15cm(Top)" or "Ø20/15cmX6.5m(Bot.)").

For every label:
  - bar           : the S-Steel polyline next to the label running in the label's direction;
                    bar length = drawn length incl. its hooks, or the length written in the
                    label ("x6.5m") when given
  - distribution  : the typical bar is shifted sideways (both ways) for as long as at least
                    90 % of its straight run still lies in concrete (RC footprint); that strip
                    width, less 2 x 75 mm cover, / spacing + 1 = number of bars
This is a take-off estimate from the plan - the extents of each bar zone are not drawn as
distribution lines, so check it against the detailed sections.
Outputs (in rebar/): raft_bbs.xlsx, raft_rebar.pdf
"""
import re, math, sys
import numpy as np
import ezdxf
from shapely.geometry import LineString, Point
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import openpyxl
from openpyxl.styles import Font, PatternFill

COVER = 0.075
sys.argv = sys.argv[:1]
exec(open("blinding_area.py").read().split("wb = openpyxl.Workbook()")[0])   # rc mask, X0, Y1, RES
footing_ns = {}
exec(open("footings_concrete.py").read().split('ws.title = "Footings & rafts"')[0], footing_ns)
lab, rows_fc = footing_ns["lab"], footing_ns["rows"]
iso_pieces = {r[0] for r in rows_fc if r[1].startswith("Footing") and "(x2)" not in r[1] and r[1] != "Footing F3"}

msp_f = ezdxf.readfile("FOUNDATIONS.dxf").modelspace()
pat = re.compile(r"%%C(\d{2})/?(\d{2})cm\s*(?:[xX]?\s*([\d.]+)\s*m)?\s*\((Top|Bot)")
labels = []
for e in msp_f.query('TEXT[layer=="S-TEXT-STEEL"]'):
    p = e.dxf.insert
    if not (X0 < p.x < X1 and Y0 < p.y < Y1):
        continue
    m = pat.search(e.dxf.text.replace(" ", ""))
    if not m:
        continue
    d, s, L, tb = int(m.group(1)), int(m.group(2)) / 100, m.group(3), m.group(4)
    labels.append(dict(text=e.dxf.text.replace("%%C", "Ø"), d=d, s=s, L=float(L) if L else None,
                       layer="Top" if tb == "Top" else "Bottom", x=p.x, y=p.y, rot=e.dxf.rotation % 180))

from ezdxf import path as zpath
bars = []
for e in [e for lay in ("S-Steel", "steel") for e in msp_f.query(f'LINE LWPOLYLINE[layer=="{lay}"]')]:
    pts = [(v.x, v.y) for v in zpath.make_path(e).flattening(0.02)]
    if len(pts) < 2 or LineString(pts).length < 1.0:
        continue
    segs = [(LineString([p, q]).length, p, q) for p, q in zip(pts, pts[1:])]
    ln, p0, p1 = max(segs)
    ang = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0])) % 180
    main = (p0, p1) if ln > 0.6 * LineString(pts).length else (pts[0], pts[-1])
    bars.append(dict(line=LineString(pts), pts=pts, main=main, ang=ang, length=LineString(pts).length))


def local_angle(bar, P):
    t = bar["line"].project(P)
    p = bar["line"].interpolate(max(t - .3, 0)); q = bar["line"].interpolate(min(t + .3, bar["line"].length))
    return math.degrees(math.atan2(q.y - p.y, q.x - p.x)) % 180


def angdiff(a, b):
    d = abs(a - b) % 180
    return min(d, 180 - d)


def in_rc(x, y):
    c, r = int((x - X0) / RES), int((Y1 - y) / RES)
    return 0 <= r < rc.shape[0] and 0 <= c < rc.shape[1] and rc[r, c]


def piece_at(x, y):
    c, r = int((x - X0) / RES), int((Y1 - y) / RES)
    return lab[r, c] if 0 <= r < lab.shape[0] and 0 <= c < lab.shape[1] else 0


def zone_width(a, b, nvec, keep=0.9, step=0.05):
    a, b = np.array(a), np.array(b)
    t = np.linspace(0, 1, max(int(np.linalg.norm(b - a) / 0.1), 2))
    base = a[None, :] + t[:, None] * (b - a)[None, :]
    nv = np.array(nvec)
    def inside(off):
        p = base + off * nv[None, :]
        c = ((p[:, 0] - X0) / RES).astype(int); r = ((Y1 - p[:, 1]) / RES).astype(int)
        ok = (r >= 0) & (r < rc.shape[0]) & (c >= 0) & (c < rc.shape[1])
        v = np.zeros(len(p), bool); v[ok] = rc[r[ok], c[ok]]
        return v.mean() >= keep
    w = 0.0
    for sgn in (1, -1):
        off = 0.0
        while off < 40 and inside(sgn * (off + step)):
            off += step
        w += off
    return w


out, unmatched = [], []
for L_ in labels:
    P = Point(L_["x"], L_["y"])
    cands = [b for b in bars if b["line"].distance(P) < 1.2
             and min(angdiff(local_angle(b, P), L_["rot"]), angdiff(b["ang"], L_["rot"])) < 12]
    if not cands:
        unmatched.append(L_); continue
    b = min(cands, key=lambda b: b["line"].distance(P))
    (ax_, ay_), (bx_, by_) = b["main"]
    u = np.array([bx_ - ax_, by_ - ay_]); u /= np.linalg.norm(u); nvec = (-u[1], u[0])
    W = zone_width(b["main"][0], b["main"][1], nvec)
    if W <= 0:
        unmatched.append(L_); continue
    n = math.floor(max(W - 2 * COVER, 0) / L_["s"]) + 1
    length = L_["L"] if L_["L"] else b["length"]
    mid = ((ax_ + bx_) / 2, (ay_ + by_) / 2)
    out.append(dict(L_, length=length, width=W, n=n, bar=b, mid=mid, piece=piece_at(*mid)))

# the same mesh is often labelled again in each bay: keep one zone per spec when zones overlap
from shapely.geometry import Polygon as _Poly
def zone_poly(o):
    (ax_, ay_), (bx_, by_) = o["bar"]["main"]
    u = np.array([bx_ - ax_, by_ - ay_]); u /= np.linalg.norm(u); nv = np.array([-u[1], u[0]])
    h = o["width"] / 2
    a_, b_ = np.array([ax_, ay_]), np.array([bx_, by_])
    return _Poly([a_ - h * nv, b_ - h * nv, b_ + h * nv, a_ + h * nv])
in_footing = [o for o in out if o["piece"] in iso_pieces]      # already in the footing BBS
out = [o for o in out if o["piece"] not in iso_pieces]
kept, dropped = [], []
for o in out:
    o["zone"] = zone_poly(o)
    dup = next((k for k in kept if k["d"] == o["d"] and k["s"] == o["s"] and k["layer"] == o["layer"]
                and k["L"] == o["L"] and angdiff(k["bar"]["ang"], o["bar"]["ang"]) < 8
                and k["zone"].intersection(o["zone"]).area > 0.5 * min(k["zone"].area, o["zone"].area)), None)
    (dropped if dup else kept).append(o)
    if dup:
        o["dup_of"] = dup
out = kept

kgm = lambda d: d * d / 162.0
wb = openpyxl.Workbook(); ws = wb.active; ws.title = "BBS rafts"
ws.append(["No.", "Label on plan", "Layer", "Dia (mm)", "Spacing (m)", "Bar length (m)", "Zone width (m)",
           "No. of bars", "Total length (m)", "kg/m", "Weight (kg)", "Plan X", "Plan Y"])
for c in ws[1]:
    c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="305496")
by_dia, total = {}, 0.0
for i, o in enumerate(out, 1):
    tl = o["n"] * o["length"]; wt = tl * kgm(o["d"])
    o["no"] = i
    ws.append([i, o["text"], o["layer"], o["d"], o["s"], round(o["length"], 2), round(o["width"], 2), o["n"],
               round(tl, 2), round(kgm(o["d"]), 3), round(wt, 1), round(o["x"], 2), round(o["y"], 2)])
    by_dia[o["d"]] = by_dia.get(o["d"], 0) + wt; total += wt
ws.append([])
ws.append(["Summary by diameter"]); ws[ws.max_row][0].font = Font(bold=True)
for d in sorted(by_dia):
    ws.append(["", f"Ø{d}", "", d, "", "", "", "", "", "", round(by_dia[d], 1)])
ws.append(["", "TOTAL (kg)", "", "", "", "", "", "", "", "", round(total, 1)])
ws.append(["", "TOTAL (ton)", "", "", "", "", "", "", "", "", round(total / 1000, 3)])
for r in (ws.max_row - 1, ws.max_row):
    for c in ws[r]: c.font = Font(bold=True)
if in_footing:
    ws.append([]); ws.append(["Labels inside isolated footings F1-F10 (counted in footing_bbs.xlsx):"])
    for o in in_footing:
        ws.append(["", o["text"], o["layer"], o["d"], o["s"], "", "", "", "", "", "", round(o["x"], 2), round(o["y"], 2)])
if dropped:
    ws.append([]); ws.append(["Repeated labels of a mesh already counted (not counted again):"])
    for o in dropped:
        ws.append(["", o["text"], o["layer"], o["d"], o["s"], "", "", "", "", "", f"same as row {o['dup_of']['no']}",
                   round(o["x"], 2), round(o["y"], 2)])
if unmatched:
    ws.append([]); ws.append(["Labels without a matching bar (not counted):"])
    for u_ in unmatched:
        ws.append(["", u_["text"], u_["layer"], u_["d"], u_["s"], "", "", "", "", "", "", round(u_["x"], 2), round(u_["y"], 2)])
ws.append([])
for line in __doc__.strip().splitlines():
    ws.append([line])
for col, w in zip("ABCDEFGHIJKLM", [6, 28, 8, 8, 10, 13, 13, 10, 14, 7, 12, 9, 9]):
    ws.column_dimensions[col].width = w
wb.save("rebar/raft_bbs.xlsx")

# drawing: RC footprint, every bar zone shaded, typical bar + label number
fig, ax = plt.subplots(figsize=(23.4, 16.5))
xs = np.linspace(X0, X1, rc.shape[1]); ys = np.linspace(Y1, Y0, rc.shape[0])
ax.contourf(xs, ys, rc.astype(float), levels=[.5, 1.5], colors=["#eeeeee"])
for g in blind_lines: ax.plot(*g.xy, color="#cc0000", lw=.3)
for o in out:
    col = "#1a7f37" if o["layer"] == "Bottom" else "#8e24aa"
    ax.plot(*o["bar"]["line"].xy, color=col, lw=1.6 if o["layer"] == "Bottom" else 1.2,
            ls="-" if o["layer"] == "Bottom" else "--")
    ang = o["rot"] if o["rot"] <= 90 else o["rot"] - 180
    ax.text(o["x"], o["y"], f"[{o['no']}] {o['n']} Ø{o['d']}/{o['s'] * 100:.0f} {o['layer'][:3]}  L={o['length']:.2f}",
            fontsize=5.2, color=col, rotation=ang, rotation_mode="anchor", va="bottom")
ax.set_xlim(X0, X1); ax.set_ylim(Y0, Y1); ax.set_aspect("equal"); ax.axis("off")
ax.plot([], [], color="#1a7f37", lw=2, label="bottom bars"); ax.plot([], [], color="#8e24aa", lw=2, ls="--", label="top bars")
ax.legend(loc="lower left", fontsize=12)
ax.set_title(f"Raft reinforcement (from the foundation plan) — {len(out)} bar zones — total {total / 1000:,.2f} t\n"
             "[n] = row in raft_bbs.xlsx; counts estimated from zone width / spacing", fontsize=15, weight="bold")
fig.savefig("rebar/raft_rebar.pdf", bbox_inches="tight")
print(f"labels={len(labels)} kept={len(out)} repeated={len(dropped)} in_footings={len(in_footing)} unmatched={len(unmatched)} total={total:,.1f} kg",
      {d: round(w, 1) for d, w in sorted(by_dia.items())})
for u_ in unmatched: print("unmatched", u_["text"], round(u_["x"], 2), round(u_["y"], 2), u_["rot"])
