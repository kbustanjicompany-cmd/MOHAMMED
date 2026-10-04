"""Backfill = excavation - cyclopean - footing concrete - column necks / walls up to the platform level.
Used by cyclopean_ar.py.  Thicknesses: retaining-wall footing = RAFT 60 cm (S-TAGS), F3 = 0.6, F2 = 0.5
(footing schedule); F.B.L = 1118.5 on the drawing.  Vertical elements standing on the footings, from the
footing top up to 1120.9: columns (S-S-COLUMN HATCH), retaining wall (S-S-BEARING WALL HATCH) and the
underground walls on the north block (S-S-BEARING WALL HATCH UNDER THE GROUND)."""
import io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    exec(open("cyclopean.py").read())
from shapely.geometry import Polygon as _P
from shapely.ops import unary_union as _U

THK = {"F3": 0.6, "F2": 0.5, "RAFT": 0.6}
def kind(p):
    if p in ret: return "RAFT"
    return "F3" if p.area > 10 else "F2"
vert = []
for lay in ("S-S-COLUMN HATCH", "S-S-BEARING WALL HATCH", "S-S-BEARING WALL HATCH UNDER THE GROUND"):
    for h in msp.query(f'HATCH[layer=="{lay}"]'):
        for pth in path.from_hatch(h):
            vert.append(_P([(v.x, v.y) for v in pth.flattening(0.01)]).buffer(0))
vert = _U(vert)
cols = _U([_P([(v.x, v.y) for v in pth.flattening(0.01)]).buffer(0)
           for h in msp.query('HATCH[layer=="S-S-COLUMN HATCH"]') for pth in path.from_hatch(h)])

def fill_rows(rows_, base_level, area_key):
    """base_level: bottom of the footing concrete; area_key: 'ac' (cyclopean) or 'af' (blinding)."""
    out = []
    for (p, _), r in zip(names, rows_):
        t = THK[kind(p)]
        conc = p.buffer(-HATCH_GAP, join_style=2)
        top = base_level + t
        a_v = vert.intersection(p).area
        a_col = cols.intersection(p).area
        exc = r[area_key] * (TOP - FBL)
        cyc_v = r["ac"] * DEPTH if area_key == "ac" else 0.0
        foot_v = conc.area * t
        vert_v = a_v * (TOP - top)
        out.append(dict(name=r["name"], kind=kind(p), t=t, top=top, exc=exc, cyc=cyc_v, conc_a=conc.area,
                        foot=foot_v, a_vert=a_v, a_col=a_col, h_vert=TOP - top, vert=vert_v,
                        fill=exc - cyc_v - foot_v - vert_v))
    return out
AFTER = fill_rows(detail[0], CTOP, "ac")       # footings on the cyclopean at 1118.5
BEFORE = fill_rows(detail[0], FBL, "af")       # footings straight on 1118.0, pit = blinding outline
if __name__ == "__main__":
    for lbl, R in (("AFTER", AFTER), ("BEFORE", BEFORE)):
        print(lbl)
        for r in R: print(" ", r["name"][:30], r["kind"], round(r["exc"], 2), round(r["cyc"], 2), round(r["conc_a"], 2),
                          round(r["foot"], 2), round(r["a_vert"], 2), round(r["h_vert"], 2), round(r["vert"], 2), round(r["fill"], 2))
        print("  TOTAL", *[round(sum(r[k] for r in R), 2) for k in ("exc", "cyc", "foot", "vert", "fill")])
