"""Plan of the culvert zone (culvert + its extension through the building)
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
inside = culvert.intersection(area_poly).area
cx, cy = culvert_ext.centroid.coords[0]
ax.annotate(f"CULVERT EXTENSION\n{culvert_ext.area:.1f} m²", (cx, cy), xytext=(cx - 38, cy - 10),
            fontsize=12, weight="bold", color="red", arrowprops=dict(arrowstyle="->", color="red"))
hx, hy = culvert_head.centroid.coords[0]
ax.annotate(f"CULVERT\n{culvert_head.area:.1f} m²", (hx, hy), xytext=(hx - 30, hy + 4),
            fontsize=12, weight="bold", color="red", arrowprops=dict(arrowstyle="->", color="red"))
ax.set_aspect("equal", adjustable="box"); ax.set_xlim(353700, 353815); ax.set_ylim(355905, 355990); ax.axis("off")
ax.legend(loc="lower left", fontsize=12)
fig.suptitle(f"Culvert zone — total {culvert.area:.1f} m², of which {inside:.1f} m² inside hatched area 1",
             fontsize=14, weight="bold")
fig.savefig("culvert_plan.png", bbox_inches="tight"); fig.savefig("culvert_plan.pdf", bbox_inches="tight")
print(f"culvert total={culvert.area:.1f} inside area1={inside:.1f}")
