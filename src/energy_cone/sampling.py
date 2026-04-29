from __future__ import annotations

import numpy as np
from rasterio.transform import Affine


def bilinear_sample(arr: np.ndarray, inverse_transform: Affine, x: float, y: float) -> float:
    rows, cols = arr.shape
    col_f, row_f = inverse_transform * (x, y)
    if (col_f < 0) or (row_f < 0) or (col_f > cols - 1) or (row_f > rows - 1):
        return float("nan")

    c0 = int(np.floor(col_f))
    r0 = int(np.floor(row_f))
    c1 = min(c0 + 1, cols - 1)
    r1 = min(r0 + 1, rows - 1)

    dc = col_f - c0
    drf = row_f - r0

    z00 = arr[r0, c0]
    z10 = arr[r0, c1]
    z01 = arr[r1, c0]
    z11 = arr[r1, c1]

    z0_ = z00 * (1.0 - dc) + z10 * dc
    z1_ = z01 * (1.0 - dc) + z11 * dc
    return float(z0_ * (1.0 - drf) + z1_ * drf)
