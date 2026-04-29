from shapely.geometry import Point, Polygon

from energy_cone.vents import (
    inward_offset_polygon,
    inward_rim_vents_from_polygon,
    rim_vents_from_polygon,
)


def test_inward_offset_polygon_returns_polygon_and_shift():
    poly = Polygon([(0.0, 0.0), (20.0, 0.0), (20.0, 10.0), (0.0, 10.0)])

    inner, used_shift = inward_offset_polygon(poly, shift_m=2.0)

    assert used_shift == 2.0
    assert inner.area < poly.area
    assert poly.covers(inner)


def test_inward_offset_polygon_reduces_shift_for_thin_polygon():
    # Half-height is 2.0 m, so shift=3.0 collapses the polygon but shift=1.5 fits.
    poly = Polygon([(0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (0.0, 4.0)])

    inner, used_shift = inward_offset_polygon(poly, shift_m=3.0)

    assert 1.0 <= used_shift < 3.0
    assert not inner.is_empty


def test_inward_rim_vents_stay_inside_original_polygon():
    poly = Polygon([(0.0, 0.0), (30.0, 0.0), (30.0, 15.0), (0.0, 15.0)])

    inner_poly, vents, _ = inward_rim_vents_from_polygon(poly, spacing_m=5.0, shift_m=1.0)

    assert inner_poly.area < poly.area
    assert len(vents) >= 3
    for x, y in vents:
        assert poly.covers(Point(x, y))
