import numpy as np
from rasterio.transform import from_origin

from energy_cone.sampling import bilinear_sample


def test_bilinear_interpolation_on_plane():
    transform = from_origin(0.0, 3.0, 1.0, 1.0)
    inv = ~transform

    rows, cols = 4, 4
    arr = np.zeros((rows, cols), dtype=float)
    for r in range(rows):
        for c in range(cols):
            x, y = transform * (c, r)  # top-left corner of each pixel
            arr[r, c] = 2.0 * x + 3.0 * y + 1.0

    xq, yq = 1.25, 1.75
    zq = bilinear_sample(arr, inv, xq, yq)
    expected = 2.0 * xq + 3.0 * yq + 1.0
    assert np.isclose(zq, expected, atol=1e-6)
