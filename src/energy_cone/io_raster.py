from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import rasterio
from rasterio.transform import Affine
from rasterio.warp import Resampling, reproject


@dataclass
class RasterGrid:
    data: np.ndarray
    transform: Affine
    crs: object
    bounds: object
    profile: dict

    @property
    def shape(self) -> tuple[int, int]:
        return self.data.shape

    @property
    def pixel_size(self) -> float:
        return (abs(self.transform.a) + abs(self.transform.e)) * 0.5


def load_dem(path: str) -> RasterGrid:
    with rasterio.open(path) as src:
        data = src.read(1).astype(np.float32)
        return RasterGrid(
            data=data,
            transform=src.transform,
            crs=src.crs,
            bounds=src.bounds,
            profile=src.profile,
        )


def align_to_reference(src_path: str, ref_profile: dict) -> np.ndarray:
    with rasterio.open(src_path) as src:
        src_arr = src.read(1).astype(np.float32)
        src_profile = src.profile

        same_grid = (
            src_profile["crs"] == ref_profile["crs"]
            and src_profile["transform"] == ref_profile["transform"]
            and src_profile["width"] == ref_profile["width"]
            and src_profile["height"] == ref_profile["height"]
        )
        if same_grid:
            return src_arr

        out = np.full((ref_profile["height"], ref_profile["width"]), np.nan, dtype=np.float32)
        reproject(
            source=src_arr,
            destination=out,
            src_transform=src_profile["transform"],
            src_crs=src_profile["crs"],
            dst_transform=ref_profile["transform"],
            dst_crs=ref_profile["crs"],
            resampling=Resampling.bilinear,
            src_nodata=src_profile.get("nodata", None),
            dst_nodata=np.nan,
        )
        return out
