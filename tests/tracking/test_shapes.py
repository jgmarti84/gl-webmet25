"""Tests for the display geometry: filled holes and smoothed edges.

What matters to the map: a core is drawn as one solid shape (no holes), its
pixel staircase is gone, and it stays where and about as big as it was.
Polygons are built in lon/lat at about 1 km pixels, like gl-tracker's output.
"""

import json

import pytest
from shapely.geometry import MultiPolygon, Polygon, mapping, shape

from tracking_api.geojson import system_to_feature
from tracking_api.shapes import display_geometry, fill_holes, smooth_polygon

PX = 0.009  # about 1 km in degrees at -31° latitude (latitude direction)
LON0, LAT0 = -64.2, -31.4


def staircase(n=8):
    """An n x n pixel blob with a staircase corner, as gl-tracker outlines it."""
    steps = [(i, 0) for i in range(n)] + [
        (n, 0), (n, n - 3), (n - 1, n - 3), (n - 1, n - 2), (n - 2, n - 2),
        (n - 2, n - 1), (n - 3, n - 1), (n - 3, n), (0, n),
    ]
    return Polygon([(LON0 + x * PX, LAT0 + y * PX) for x, y in steps])


def square_with_hole():
    outer = [(LON0, LAT0), (LON0 + 10 * PX, LAT0), (LON0 + 10 * PX, LAT0 + 10 * PX),
             (LON0, LAT0 + 10 * PX)]
    hole = [(LON0 + 4 * PX, LAT0 + 4 * PX), (LON0 + 6 * PX, LAT0 + 4 * PX),
            (LON0 + 6 * PX, LAT0 + 6 * PX), (LON0 + 4 * PX, LAT0 + 6 * PX)]
    return Polygon(outer, [hole])


class TestFillHoles:
    def test_removes_the_hole(self):
        assert len(fill_holes(square_with_hole()).interiors) == 0

    def test_keeps_the_outline(self):
        poly = square_with_hole()
        assert fill_holes(poly).equals(Polygon(poly.exterior))

    def test_multipolygon_parts_are_filled(self):
        a = square_with_hole()
        b = Polygon([(x + 20 * PX, y) for x, y in a.exterior.coords],
                    [[(x + 20 * PX, y) for x, y in a.interiors[0].coords]])
        filled = fill_holes(MultiPolygon([a, b]))
        assert all(len(p.interiors) == 0 for p in filled.geoms)


class TestSmooth:
    def test_zero_sigma_is_a_no_op(self):
        poly = staircase()
        assert smooth_polygon(poly, 0).equals(poly)

    def test_result_is_valid(self):
        assert smooth_polygon(staircase(), 1.0).is_valid

    def test_keeps_roughly_the_same_area(self):
        poly = staircase()
        ratio = smooth_polygon(poly, 1.0).area / poly.area
        assert 0.85 < ratio <= 1.0

    def test_stays_in_place(self):
        poly = staircase()
        assert smooth_polygon(poly, 1.0).centroid.distance(poly.centroid) < PX

    def test_removes_sharp_corners(self):
        """A pixel staircase has right angles; the smoothed outline has none."""
        import numpy as np

        def max_turn(p):
            c = np.asarray(p.exterior.coords)[:-1]
            v1 = np.roll(c, -1, axis=0) - c
            v0 = c - np.roll(c, 1, axis=0)
            cos = (v0 * v1).sum(1) / (np.linalg.norm(v0, axis=1) * np.linalg.norm(v1, axis=1))
            return np.degrees(np.arccos(np.clip(cos, -1, 1))).max()

        assert max_turn(staircase()) >= 89
        assert max_turn(smooth_polygon(staircase(), 1.0)) < 30

    def test_tiny_polygon_falls_back_to_the_original(self):
        """A one-pixel blob would shrink to nothing; it is kept as it was."""
        tiny = Polygon([(LON0, LAT0), (LON0 + PX, LAT0), (LON0 + PX, LAT0 + PX), (LON0, LAT0 + PX)])
        out = smooth_polygon(tiny, 3.0)
        assert out.is_valid and out.area >= 0.5 * tiny.area


class TestDisplayGeometry:
    def test_fills_and_smooths_a_polygon(self):
        out = shape(display_geometry(mapping(square_with_hole()), 1.0))
        assert isinstance(out, Polygon) and len(out.interiors) == 0

    def test_multipolygon_stays_multipolygon(self):
        a = staircase()
        b = Polygon([(x + 20 * PX, y) for x, y in a.exterior.coords])
        out = shape(display_geometry(mapping(MultiPolygon([a, b])), 1.0))
        assert isinstance(out, MultiPolygon) and len(out.geoms) == 2

    def test_non_polygons_pass_through(self):
        point = {"type": "Point", "coordinates": [LON0, LAT0]}
        assert display_geometry(point, 1.0) == point

    def test_output_is_json_serialisable(self):
        json.dumps(display_geometry(mapping(square_with_hole()), 1.0))


class FakeGeom:
    def __init__(self, poly): self._blob = json.dumps(mapping(poly))
    def ExportToJson(self): return self._blob


class FakeSystem:
    name, event, attrs, timestamp = "abc", "CONTINUITY", {}, None

    def __init__(self, poly): self.geom = FakeGeom(poly)
    def getRelationshipNames(self): return []


class TestFeature:
    @pytest.mark.parametrize("kind,lead", [("system", None), ("forecast", 18)])
    def test_features_carry_display_geometry(self, kind, lead):
        """Cores and forecasts alike are drawn without holes."""
        f = system_to_feature(FakeSystem(square_with_hole()), kind=kind, lead_min=lead,
                              smooth_sigma_km=1.0)
        assert len(shape(f["geometry"]).interiors) == 0

    def test_zero_sigma_still_fills_holes(self):
        f = system_to_feature(FakeSystem(square_with_hole()), smooth_sigma_km=0)
        assert shape(f["geometry"]).equals(Polygon(square_with_hole().exterior))
