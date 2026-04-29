from __future__ import annotations

import warnings

import numpy as np
from rasterio.features import shapes
from shapely.geometry import LineString, MultiPolygon, Polygon
from shapely.geometry import shape as shp_shape
from shapely.ops import unary_union

from .sampling import bilinear_sample


def lava_polygon_from_thickness(
    diff: np.ndarray,
    transform,
    threshold_m: float,
    simplify_m: float = 0.0,
    min_area_m2: float = 0.0,
):
    mask = np.isfinite(diff) & (diff >= threshold_m)
    geoms = []
    for geom, val in shapes(mask.astype(np.uint8), mask=mask, transform=transform):
        if val != 1:
            continue
        poly = shp_shape(geom)
        if min_area_m2 > 0 and poly.area < min_area_m2:
            continue
        geoms.append(poly)

    if not geoms:
        raise RuntimeError("No lava polygon extracted; lower thickness threshold.")

    lava_poly = unary_union(geoms)
    if lava_poly.geom_type == "MultiPolygon":
        lava_poly = max(list(lava_poly.geoms), key=lambda p: p.area)

    if simplify_m > 0:
        lava_poly = lava_poly.simplify(simplify_m, preserve_topology=True)

    return lava_poly, mask


def _largest_polygon(geom) -> Polygon:
    if isinstance(geom, Polygon):
        return geom
    if isinstance(geom, MultiPolygon):
        return max(list(geom.geoms), key=lambda p: p.area)
    raise ValueError(f"Expected Polygon or MultiPolygon, got {geom.geom_type}.")


def inward_offset_polygon(lava_polygon, shift_m: float, min_shift_m: float = 1.0):
    """Generate a robust inward polygon via geometry offset.

    Compared to point-wise normal shifting, buffering the whole polygon is more robust
    for concave corners, local boundary noise, and thin neck regions because topology
    handling is delegated to Shapely's polygon offset operation.

    Returns
    -------
    tuple[Polygon, float]
        Inner polygon and the actually used inward shift distance [m].
    """
    cleaned = lava_polygon.buffer(0)
    cleaned = _largest_polygon(cleaned)

    if shift_m <= 0:
        return cleaned, 0.0

    used_shift = float(shift_m)
    while used_shift >= float(min_shift_m):
        inner = cleaned.buffer(-used_shift)
        if not inner.is_empty:
            inner = inner.buffer(0)
            try:
                return _largest_polygon(inner), used_shift
            except ValueError:
                pass

        used_shift *= 0.5

    raise RuntimeError(
        "Failed to compute inward polygon offset. "
        f"Requested shift={shift_m:.3f} m, retried down to < {min_shift_m:.3f} m."
    )


def rim_vents_from_polygon(lava_polygon, spacing_m: float):
    rim = LineString(lava_polygon.exterior.coords)
    L = rim.length
    n = max(3, int(np.floor(L / spacing_m)))
    dists = np.linspace(0.0, L, n, endpoint=False)
    pts = [rim.interpolate(d) for d in dists]
    return [(float(pt.x), float(pt.y)) for pt in pts]


def inward_rim_vents_from_polygon(lava_polygon, spacing_m: float, shift_m: float):
    """Offset polygon inward, then generate uniformly spaced vents on the new boundary."""
    inner_polygon, used_shift_m = inward_offset_polygon(lava_polygon, shift_m=shift_m)
    if 0.0 < used_shift_m < float(shift_m):
        warnings.warn(
            f"Requested vent inward shift {shift_m:.3f} m was reduced to {used_shift_m:.3f} m.",
            RuntimeWarning,
            stacklevel=2,
        )
    vents = rim_vents_from_polygon(inner_polygon, spacing_m=spacing_m)
    return inner_polygon, vents, used_shift_m


def vents_with_zoffset_from_thickness(
    vents,
    thickness_grid: np.ndarray,
    inverse_transform,
    zoffset_scale: float = 1.0,
    zoffset_min_m: float = 0.0,
    zoffset_cap_m: float | None = None,
):
    zoffsets = []
    thicknesses = []
    for x, y in vents:
        th = bilinear_sample(thickness_grid, inverse_transform, x, y)
        if not np.isfinite(th):
            th = 0.0
        th = max(0.0, float(th))

        zo = max(zoffset_min_m, zoffset_scale * th)
        if zoffset_cap_m is not None:
            zo = min(zo, zoffset_cap_m)
        zoffsets.append(float(zo))
        thicknesses.append(float(th))
    return np.asarray(zoffsets, dtype=np.float32), np.asarray(thicknesses, dtype=np.float32)
