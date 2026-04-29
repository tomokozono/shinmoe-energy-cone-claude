from __future__ import annotations

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

from .sampling import bilinear_sample


def raycast_boundary_for_vent(
    dem: np.ndarray,
    inverse_transform,
    extent,
    x0: float,
    y0: float,
    mu: float,
    zoffset: float,
    az_step_deg: float = 1.0,
    dr: float = 10.0,
):
    rows, cols = dem.shape
    col0, row0 = inverse_transform * (x0, y0)
    col0 = int(np.clip(np.floor(col0), 0, cols - 1))
    row0 = int(np.clip(np.floor(row0), 0, rows - 1))
    z0 = float(dem[row0, col0])

    corners = [
        (extent[0], extent[2]),
        (extent[0], extent[3]),
        (extent[1], extent[2]),
        (extent[1], extent[3]),
    ]
    r_max_bound = max(np.hypot(x0 - cx, y0 - cy) for (cx, cy) in corners) + 2.0 * dr

    az_list = np.arange(0.0, 360.0, az_step_deg)
    stop_xy = []

    for az in az_list:
        rad = np.deg2rad(az)
        dx = np.cos(rad)
        dy = np.sin(rad)
        r = 0.0
        zt_prev = bilinear_sample(dem, inverse_transform, x0, y0)
        zc_prev = z0 + zoffset
        hit = None

        while r <= r_max_bound:
            r += dr
            x = x0 + r * dx
            y = y0 + r * dy

            zt = bilinear_sample(dem, inverse_transform, x, y)
            if np.isnan(zt):
                break

            zc = z0 + zoffset - mu * r
            if zt >= zc:
                r1 = r - dr
                f0 = zc_prev - zt_prev
                f1 = zc - zt
                alpha = 0.0
                if (f0 - f1) != 0:
                    alpha = np.clip(f0 / (f0 - f1), 0.0, 1.0)
                r_star = r1 + alpha * dr
                hit = (x0 + r_star * dx, y0 + r_star * dy)
                break

            zc_prev, zt_prev = zc, zt

        if hit is None:
            hit = (x, y)
        stop_xy.append(hit)

    if len(stop_xy) < 3:
        return None

    poly = Polygon(np.asarray(stop_xy))
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly


def union_for_vents(
    dem: np.ndarray,
    inverse_transform,
    extent,
    vents,
    mu: float,
    zoffsets,
    az_step_deg: float,
    dr: float,
):
    polys = []
    for (x0, y0), zo in zip(vents, zoffsets):
        poly = raycast_boundary_for_vent(
            dem=dem,
            inverse_transform=inverse_transform,
            extent=extent,
            x0=float(x0),
            y0=float(y0),
            mu=mu,
            zoffset=float(zo),
            az_step_deg=az_step_deg,
            dr=dr,
        )
        if poly is not None and not poly.is_empty:
            polys.append(poly)

    if not polys:
        raise RuntimeError("No valid polygons generated; check mu/zoffset/step.")
    return unary_union(polys), polys
