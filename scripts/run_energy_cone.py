#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import geopandas as gpd
import matplotlib.cm as cm
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

from energy_cone.io_raster import load_dem
from energy_cone.pipeline import load_config, run

DEFAULT_MU = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45]


def _plot_mu_comparison(cfg: dict, rows: list[dict], output_base: Path) -> Path:
    dem_grid = load_dem(cfg["dem_with_lava"])
    dem = dem_grid.data
    extent = (
        dem_grid.bounds.left,
        dem_grid.bounds.right,
        dem_grid.bounds.bottom,
        dem_grid.bounds.top,
    )

    mu_values = [r["mu"] for r in rows]
    colors = cm.plasma_r(np.linspace(0.15, 0.85, len(mu_values)))

    fig, ax = plt.subplots(figsize=(10, 8))
    im = ax.imshow(
        dem,
        cmap="terrain",
        extent=extent,
        origin="upper",
        vmin=cfg.get("plot_vmin", 0),
        vmax=cfg.get("plot_vmax", 1800),
    )
    plt.colorbar(im, ax=ax, label="Elevation (m)", fraction=0.03, pad=0.01)

    # Draw from largest polygon (lowest mu) to smallest so boundaries are all visible
    handles = []
    for r, color in zip(rows, colors):
        shp_path = Path(r["output_dir"]) / "union.shp"
        if not shp_path.exists():
            continue
        gdf = gpd.read_file(shp_path)
        fc = (*color[:3], 0.08)
        gdf.plot(ax=ax, facecolor=fc, edgecolor=color, linewidth=1.4)
        handles.append(mpatches.Patch(
            facecolor=fc, edgecolor=color, linewidth=1.4,
            label=f"μ = {r['mu']:.2f}  ({r['area_m2'] / 1e6:.2f} km²)",
        ))

    ax.legend(handles=handles, loc="upper right", fontsize=8, framealpha=0.85)
    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_xlabel("Easting (m)")
    ax.set_ylabel("Northing (m)")
    ax.set_title(cfg.get("name", "Energy Cone") + " — μ sensitivity")
    fig.tight_layout()

    out_path = output_base / "mu_comparison.png"
    fig.savefig(out_path, dpi=200)
    plt.close(fig)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Shinmoedake energy cone pipeline for all mu values"
    )
    parser.add_argument("--config", required=True, help="Path to YAML config")
    parser.add_argument(
        "--mu",
        nargs="+",
        type=float,
        default=DEFAULT_MU,
        metavar="MU",
        help=f"Mu values to compute (default: {DEFAULT_MU})",
    )
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    cfg_base = config_path.parent
    cfg = load_config(config_path)

    # Resolve relative paths to absolute so dict-based pipeline.run() works
    for key in ("dem_with_lava", "dem_no_lava", "output_dir"):
        if key in cfg:
            p = Path(cfg[key])
            if not p.is_absolute():
                cfg[key] = str((cfg_base / p).resolve())
    cfg.setdefault("output_dir", str(cfg_base / "output"))

    output_base = Path(cfg["output_dir"])
    output_base.mkdir(parents=True, exist_ok=True)

    rows = []
    for mu in args.mu:
        cfg_run = dict(cfg)
        cfg_run["mu"] = float(mu)
        result = run(cfg_run)
        rows.append(
            {
                "mu": float(mu),
                "n_vents": int(result["n_vents"]),
                "az_step": float(result["az_step"]),
                "dr_m": float(result["dr_m"]),
                "area_m2": float(result["area_m2"]),
                "bounds_minx": float(result["bounds_minx"]),
                "bounds_miny": float(result["bounds_miny"]),
                "bounds_maxx": float(result["bounds_maxx"]),
                "bounds_maxy": float(result["bounds_maxy"]),
                "output_dir": str(result["output_dir"]),
            }
        )

    columns = [
        "mu", "n_vents", "az_step", "dr_m", "area_m2",
        "bounds_minx", "bounds_miny", "bounds_maxx", "bounds_maxy", "output_dir",
    ]
    summary_path = output_base / "mu_sweep_summary.csv"
    with summary_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    comparison_path = _plot_mu_comparison(cfg, rows, output_base)

    print(
        json.dumps(
            {
                "config": str(config_path),
                "mu_values": args.mu,
                "summary_csv": str(summary_path),
                "mu_comparison_png": str(comparison_path),
                "runs": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
