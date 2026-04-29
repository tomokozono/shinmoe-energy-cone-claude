import numpy as np
from rasterio.transform import from_origin

from energy_cone.cone import union_for_vents


def _area_for_mu(mu: float) -> float:
    dem = np.zeros((200, 200), dtype=float)
    transform = from_origin(0.0, 2000.0, 10.0, 10.0)
    inv = ~transform
    extent = (0.0, 2000.0, 0.0, 2000.0)

    union_geom, _ = union_for_vents(
        dem=dem,
        inverse_transform=inv,
        extent=extent,
        vents=[(1000.0, 1000.0)],
        mu=mu,
        zoffsets=[50.0],
        az_step_deg=5.0,
        dr=5.0,
    )
    return float(union_geom.area)


def test_union_area_decreases_as_mu_increases():
    area_low_mu = _area_for_mu(0.10)
    area_high_mu = _area_for_mu(0.20)
    assert area_low_mu > area_high_mu
