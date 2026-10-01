"""Building outlines to exclude, read from BUILDINGS.dxf (the architectural plan, same
coordinates as HATCHED_AREA.dxf).

  - hangar: closed green (colour 3) polyline on layer 0 around the "hangar" label
  - bathroom, cafeteria, guard room: closed blue (colour 5) polylines on layer 0 around
    their labels
The outlines in this file already include the 1 m clearance, so they are used as drawn.
The file also holds a copy of the plan shifted ~100 m east; only the outline that
contains the label is used.
"""
import ezdxf
from shapely.geometry import Polygon, Point

_msp = ezdxf.readfile("BUILDINGS.dxf").modelspace()
_labels = {t.dxf.text.strip().lower(): Point(t.dxf.insert.x, t.dxf.insert.y)
           for t in _msp.query('TEXT[layer=="0"]')}
_closed = [(e.dxf.color, Polygon([p[:2] for p in e.get_points()]))
           for e in _msp.query('LWPOLYLINE[layer=="0"]') if e.closed and len(e) >= 3]


def _outline(label, color):
    return next(P for c, P in _closed if c == color and P.contains(_labels[label]))


hangar = _outline("hangar", 3)
rooms = {"Bathroom": _outline("bathroom", 5),
         "Cafeteria": _outline("cafeteria", 5),
         "Guard room": _outline("guard room", 5)}
