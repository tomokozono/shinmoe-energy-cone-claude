from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import yaml

from .cone import union_for_vents
from .io_raster import align_to_reference, load_dem
from .sampling import bilinear_sample
from .vents import (
    lava_polygon_from_thickness,
    inward_rim_vents_from_polygon,
    rim_vents_from_polygon,
    vents_with_zoffset_from_thickness,
)


def _slope_magnitude_from_dem(dem: np.ndarray, dx: float, dy: float) -> np.ndarray:
    dzdx = np.empty_like(dem, dtype=float)
    dzdy = np.empty_like(dem, dtype=float)

    dzdx[:, 1:-1] = (dem[:, 2:] - dem[:, :-2]) / (2.0 * dx)
    dzdx[:, 0] = (dem[:, 1] - dem[:, 0]) / dx
    dzdx[:, -1] = (dem[:, -1] - dem[:, -2]) / dx

    dzdy[1:-1, :] = (dem[2:, :] - dem[:-2, :]) / (2.0 * dy)
    dzdy[0, :] = (dem[1, :] - dem[0, :]) / dy
    dzdy[-1, :] = (dem[-1, :] - dem[-2, :]) / dy

    return np.hypot(dzdx, dzdy)


def _plot_zoffset_vs_theory(
    *,
    vents: list[tuple[float, float]],
    zoffsets: list[float],
    dem_for_slope: np.ndarray,
    transform,
    inverse_transform,
    output_dir: Path,
    tau_y: float,
) -> None:
    if not vents or len(vents) != len(zoffsets):
        return

    dx = abs(float(transform.a))
    dy = abs(float(transform.e))
    slope_mag = _slope_magnitude_from_dem(dem_for_slope, dx=dx, dy=dy)
    theta = np.arctan(slope_mag)

    rho = 2500.0
    g = 9.8

    hs_values = []
    z_values = []
    for (x, y), zoffset in zip(vents, zoffsets):
        theta_sample = bilinear_sample(theta, inverse_transform, x, y)
        if np.isnan(theta_sample):
            continue
        sin_theta = np.sin(theta_sample)
        if sin_theta <= 0.0:
            continue
        hs_values.append(float(tau_y / (rho * g * sin_theta)))
        z_values.append(float(zoffset))

    if not hs_values:
        return

    hs_arr = np.asarray(hs_values, dtype=float)
    z_arr = np.asarray(z_values, dtype=float)

    diff_arr = z_arr - hs_arr
    mean_bias = float(np.mean(diff_arr))
    rmse = float(np.sqrt(np.mean(diff_arr**2)))
    mae = float(np.mean(np.abs(diff_arr)))

    min_v = float(min(np.min(hs_arr), np.min(z_arr)))
    max_v = float(max(np.max(hs_arr), np.max(z_arr)))

    fig, ax = plt.subplots(figsize=(7, 6))
    ax.scatter(hs_arr, z_arr, alpha=0.6, s=20)
    ax.plot([min_v, max_v], [min_v, max_v], "k--", linewidth=1.0, label="1:1")
    ax.set_xlabel("Theoretical thickness Hs (m)")
    ax.set_ylabel("Model thickness (zoffset) (m)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()
    fig.savefig(output_dir / "zoffset_vs_theory.png", dpi=250)
    plt.close(fig)

    corr = np.nan
    if hs_arr.size > 1 and z_arr.size > 1:
        corr = float(np.corrcoef(hs_arr, z_arr)[0, 1])

    print(
        "zoffset vs theory stats: "
        f"n_vents={hs_arr.size}, "
        f"median_theoretical_thickness={float(np.median(hs_arr)):.3f} m, "
        f"median_zoffset={float(np.median(z_arr)):.3f} m, "
        f"mean_bias={mean_bias:.3f} m, "
        f"rmse={rmse:.3f} m, "
        f"mae={mae:.3f} m, "
        f"correlation={corr:.4f}"
    )


def load_config(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _resolve_path(p: str, base: Path) -> Path:
    pp = Path(p)
    return pp if pp.is_absolute() else (base / pp).resolve()


def run(config: dict | str | Path) -> dict:
    if isinstance(config, (str, Path)):
        config_path = Path(config).resolve()
        cfg = load_config(config_path)
        cfg_base = config_path.parent
    else:
        cfg = config
        cfg_base = Path.cwd()

    dem_with_lava = load_dem(str(_resolve_path(cfg["dem_with_lava"], cfg_base)))
    dem = dem_with_lava.data
    transform = dem_with_lava.transform
    invA = ~transform
    extent = (
        dem_with_lava.bounds.left,
        dem_with_lava.bounds.right,
        dem_with_lava.bounds.bottom,
        dem_with_lava.bounds.top,
    )

    dr = float(cfg.get("dr", dem_with_lava.pixel_size))
    az_step_deg = float(cfg.get("az_step_deg", 1.0))
    mu = float(cfg["mu"])
    crs_epsg = cfg.get("crs_epsg", str(dem_with_lava.crs))

    output_base = _resolve_path(cfg.get("output_dir", "output"), cfg_base)
    output_dir = output_base / f"mu_{mu:.2f}"
    output_dir.mkdir(parents=True, exist_ok=True)

    vents_mode = cfg.get("vents_mode", "manual")
    vents = []
    rim_vents_original = None
    zoffsets = []
    lava_poly_for_plot = None
    inner_lava_poly_for_plot = None
    used_shift_m = float(cfg.get("vent_inward_shift_m", 0.0))

    if vents_mode == "manual":
        vents = [tuple(v) for v in cfg["vents"]]
        zoffset = float(cfg.get("zoffset", 0.0))
        zoffsets = [zoffset] * len(vents)

    elif vents_mode == "rim":
        dem_nolava = align_to_reference(
            str(_resolve_path(cfg["dem_no_lava"], cfg_base)), dem_with_lava.profile
        )
        diff = dem - dem_nolava

        lava_poly, mask = lava_polygon_from_thickness(
            diff=diff,
            transform=transform,
            threshold_m=float(cfg.get("thickness_threshold_m", 0.5)),
            simplify_m=float(cfg.get("simplify_m", 0.0)),
            min_area_m2=float(cfg.get("min_area_m2", 0.0)),
        )

        gdf_lava = gpd.GeoDataFrame(geometry=[lava_poly], crs=dem_with_lava.crs).to_crs(crs_epsg)
        lava_poly = gdf_lava.geometry.iloc[0]
        vent_inward_shift_m = float(cfg.get("vent_inward_shift_m", 0.0))
        inner_lava_poly, vents, used_shift_m = inward_rim_vents_from_polygon(
            lava_poly,
            spacing_m=float(cfg.get("rim_spacing_m", 50.0)),
            shift_m=vent_inward_shift_m,
        )
        rim_vents_original = rim_vents_from_polygon(lava_poly, spacing_m=float(cfg.get("rim_spacing_m", 50.0)))
        lava_poly_for_plot = lava_poly
        inner_lava_poly_for_plot = inner_lava_poly

        print(
            f"rim vents summary: n_vents={len(vents)}, requested_shift_m={vent_inward_shift_m:.3f}, "
            f"used_shift_m={used_shift_m:.3f}, spacing_m={float(cfg.get('rim_spacing_m', 50.0)):.3f}"
        )

        if cfg.get("zoffset_mode", "fixed") == "thickness":
            zoffsets, _ = vents_with_zoffset_from_thickness(
                vents=vents,
                thickness_grid=diff,
                inverse_transform=invA,
                zoffset_scale=float(cfg.get("zoffset_scale", 1.0)),
                zoffset_min_m=float(cfg.get("zoffset_min_m", 0.0)),
                zoffset_cap_m=cfg.get("zoffset_cap_m", None),
            )
        else:
            zoffset = float(cfg.get("zoffset", 0.0))
            zoffsets = [zoffset] * len(vents)

        if cfg.get("save_lava_mask", False):
            fig, ax = plt.subplots(figsize=(7, 7))
            ax.imshow(mask, origin="upper")
            ax.set_title("Lava mask")
            fig.tight_layout()
            fig.savefig(output_dir / "lava_mask.png", dpi=200)
            plt.close(fig)

        _plot_zoffset_vs_theory(
            vents=vents,
            zoffsets=zoffsets,
            dem_for_slope=dem,
            transform=transform,
            inverse_transform=invA,
            output_dir=output_dir,
            tau_y=float(cfg.get("tau_y", 3e4)),
        )
    else:
        raise ValueError(f"Unsupported vents_mode: {vents_mode}")

    union_geom, _ = union_for_vents(
        dem=dem,
        inverse_transform=invA,
        extent=extent,
        vents=vents,
        mu=mu,
        zoffsets=zoffsets,
        az_step_deg=az_step_deg,
        dr=dr,
    )

    gdf_union = gpd.GeoDataFrame(
        {
            "mu": [mu],
            "n_vents": [len(vents)],
            "az_step": [az_step_deg],
            "dr_m": [dr],
            "vent_shift": [float(cfg.get("vent_inward_shift_m", 0.0))],
        },
        geometry=[union_geom],
        crs=crs_epsg,
    )

    shp_name = "union.shp"
    png_name = "quicklook.png"

    shp_path = output_dir / shp_name
    png_path = output_dir / png_name
    gdf_union.to_file(shp_path)

    fig, ax = plt.subplots(figsize=(9, 7))
    im = ax.imshow(
        dem,
        cmap="terrain",
        extent=extent,
        origin="upper",
        vmin=cfg.get("plot_vmin", 0),
        vmax=cfg.get("plot_vmax", 1800),
    )
    plt.colorbar(im, ax=ax, label="Elevation (m)")
    gdf_union.plot(ax=ax, facecolor=(1, 0, 0, 0.25), edgecolor="red", linewidth=1.0, zorder=5)
    if lava_poly_for_plot is not None:
        gpd.GeoSeries([lava_poly_for_plot], crs=crs_epsg).boundary.plot(
            ax=ax, color="cyan", linewidth=1.0, zorder=6
        )
    if inner_lava_poly_for_plot is not None:
        gpd.GeoSeries([inner_lava_poly_for_plot], crs=crs_epsg).boundary.plot(
            ax=ax, color="magenta", linewidth=1.0, zorder=7
        )

    vx = [x for x, _ in vents]
    vy = [y for _, y in vents]
    if rim_vents_original is not None:
        rvx = [x for x, _ in rim_vents_original]
        rvy = [y for _, y in rim_vents_original]
        ax.scatter(rvx, rvy, c="white", edgecolors="black", s=6, zorder=10, label="original rim vents")
    zo_arr = np.asarray(zoffsets, dtype=float)
    if len(zoffsets) == len(vents) and zo_arr.max() - zo_arr.min() > 1e-6:
        sc = ax.scatter(vx, vy, c=zo_arr, s=8, zorder=11, label="inward-offset vents")
        plt.colorbar(sc, ax=ax, label="zoffset (m)")
    else:
        ax.scatter(vx, vy, c="yellow", edgecolors="black", s=8, zorder=11, label="inward-offset vents")

    if rim_vents_original is not None:
        ax.legend(loc="upper right")

    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_xlabel("Easting (m)")
    ax.set_ylabel("Northing (m)")
    ax.set_title(cfg.get("title", f"Energy Cone union μ={mu:.2f}"))
    fig.tight_layout()
    fig.savefig(png_path, dpi=300)
    plt.close(fig)

    bounds = union_geom.bounds

    return {
        "union_shapefile": str(shp_path),
        "quicklook_png": str(png_path),
        "n_vents": len(vents),
        "mu": mu,
        "az_step": az_step_deg,
        "dr_m": dr,
        "vent_inward_shift_m": float(cfg.get("vent_inward_shift_m", 0.0)),
        "used_vent_inward_shift_m": float(used_shift_m),
        "area_m2": float(union_geom.area),
        "bounds_minx": float(bounds[0]),
        "bounds_miny": float(bounds[1]),
        "bounds_maxx": float(bounds[2]),
        "bounds_maxy": float(bounds[3]),
        "output_dir": str(output_dir),
    }
