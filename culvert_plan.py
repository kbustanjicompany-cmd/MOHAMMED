"""Plan of the excluded zones: culvert (+ its extension through the building) and
the hangar footprint offset 1 m,
drawn over the DXF, with the hatched area 1 outline. Output: culvert_plan.pdf/png"""
import ezdxf, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from ezdxf.addons.drawing import RenderContext, Frontend
from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
from ezdxf.addons.drawing.config import Configuration, BackgroundPolicy

src = open("compute_levels.py").read().split("# TIN for")[0]
exec(src)  # area_poly, culvert_head, culvert_ext, culvert

for l in doc.layers:
    if l.dxf.name in ("C-TOPO-TEXT", "Survey.td2", "Obs.ts.td2", "Obs.ts.td2_Mark",
                      "Obs.ts.td2_point_desc_Mark", "V-NODE", "C-TOPO-MINR", "C-TOPO-MAJR"):
        l.off()
fig, ax = plt.subplots(figsize=(14, 13), dpi=130)
Frontend(RenderContext(doc), MatplotlibBackend(ax),
         config=Configuration(background_policy=BackgroundPolicy.WHITE, lineweight_scaling=0.5)).draw_layout(msp, finalize=False)
ax.plot(*area_poly.exterior.xy, color="magenta", lw=2.5, label="Hatched area 1", zorder=20)
ax.fill(*culvert.exterior.xy, fc=(1, 0.55, 0, 0.35), ec="red", lw=2.5, hatch="//", label="Culvert zone (excluded)", zorder=21)
ax.plot(*culvert_head.exterior.xy, color="darkred", lw=1, ls="--")
ax.fill(*hangar_zone.exterior.xy, fc=(0.2, 0.4, 1, 0.18), ec="blue", lw=2.5, hatch="\\\\",
        label="Hangar (excluded)", zorder=19)
ax.plot(*hangar_fp.exterior.xy, color="blue", lw=1, ls="--", zorder=19)
for i, r in enumerate(rooms, 1):
    rz = r.buffer(HANGAR_OFFSET, join_style=2)
    ax.fill(*rz.exterior.xy, fc=(0.55, 0.2, 0.7, 0.25), ec="#7030a0", lw=2.5, hatch="xx", zorder=19,
            label=f"Bathroom, cafeteria, guard room (excluded)" if i == 1 else None)
    ax.plot(*r.exterior.xy, color="#7030a0", lw=1, ls="--", zorder=19)
    rx, ry = r.centroid.coords[0]
    name = list(named_rooms)[i - 1].upper()
    off = [(-6, 12), (4, 12), (14, -10)][i - 1]
    ax.annotate(f"{name}\n{r.area:.1f} m²", (rx, ry), xytext=(rx + off[0], ry + off[1]),
                fontsize=11, weight="bold", color="#7030a0", arrowprops=dict(arrowstyle="->", color="#7030a0"), zorder=30)
hzx, hzy = hangar_fp.centroid.coords[0]
ax.annotate(f"HANGAR\n{hangar_zone.area:.1f} m²", (hzx + 5, hzy), xytext=(hzx + 22, hzy - 18),
            fontsize=12, weight="bold", color="blue", arrowprops=dict(arrowstyle="->", color="blue"), zorder=30)
inside = culvert.intersection(area_poly).area
excl = area_poly.intersection(excluded).area
cx, cy = culvert_ext.centroid.coords[0]
ax.annotate(f"CULVERT EXTENSION\n{culvert_ext.area:.1f} m²", (cx, cy), xytext=(cx - 38, cy - 10),
            fontsize=12, weight="bold", color="red", arrowprops=dict(arrowstyle="->", color="red"))
hx, hy = culvert_head.centroid.coords[0]
ax.annotate(f"CULVERT\n{culvert_head.area:.1f} m²", (hx, hy), xytext=(hx - 30, hy + 4),
            fontsize=12, weight="bold", color="red", arrowprops=dict(arrowstyle="->", color="red"))
ax.set_aspect("equal", adjustable="box"); ax.set_xlim(353700, 353815); ax.set_ylim(355905, 355998); ax.axis("off")
ax.legend(loc="lower left", fontsize=12)
fig.suptitle(f"Excluded zones (culvert, hangar, rooms) — "
             f"{excl:.1f} m² excluded from hatched area 1",
             fontsize=14, weight="bold")
fig.savefig("culvert_plan.png", bbox_inches="tight"); fig.savefig("culvert_plan.pdf", bbox_inches="tight")
print(f"culvert total={culvert.area:.1f} inside area1={inside:.1f} excluded total={excl:.1f}")
