# ---
# jupyter:
#   jupytext:
#     formats: ipynb,py:percent
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.16.0
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Run Energy Cone from YAML
# 
# この notebook は、`scripts/run_energy_cone.py` の処理を研究用途向けに分解して再現するための標準テンプレートです。
# 
# - **再現性**: 先頭の `config_path` を切り替えるだけで同一フローを再実行
# - **可読性**: 各ステップ（設定読込・入力確認・モデル実行・可視化・出力確認）を明示
# - **実装方針**: 計算ロジックは `src/energy_cone/` を再利用（重複実装しない）

# %%
from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import ipywidgets as widgets
import matplotlib.pyplot as plt
import numpy as np
import yaml
from IPython.display import display

# Notebook entrypoint: ここだけ変更すれば別ケースを再現可能
config_path = "../configs/rim-vents-real-S.yml"

# %% [markdown]
# ## 1) Imports & Path setup
# 
# `notebooks/` から相対パスで repo root / `src` を解決し、`energy_cone` を import できるようにします。

# %%
NOTEBOOK_DIR = Path.cwd()
REPO_ROOT = (NOTEBOOK_DIR / "..").resolve()
SRC_DIR = REPO_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from energy_cone.cone import union_for_vents
from energy_cone.io_raster import align_to_reference, load_dem
from energy_cone.pipeline import load_config
from energy_cone.sampling import bilinear_sample
from energy_cone.vents import (
    lava_polygon_from_thickness,
    inward_rim_vents_from_polygon,
    rim_vents_from_polygon,
    vents_with_zoffset_from_thickness,
)

print(f"Notebook directory : {NOTEBOOK_DIR}")
print(f"Repository root    : {REPO_ROOT}")
print(f"Source directory   : {SRC_DIR}")

# %% [markdown]
# ## 2) Config load
# 
# YAML を読み込み、重要パラメータを表示します。

# %%
cfg_path = (NOTEBOOK_DIR / config_path).resolve()
cfg = load_config(cfg_path)
cfg_base = cfg_path.parent

print(f"config_path      : {cfg_path}")
print(f"name             : {cfg.get('name')}")
print(f"vents_mode       : {cfg.get('vents_mode')}")
print(f"mu               : {cfg.get('mu')}")
print(f"zoffset_mode     : {cfg.get('zoffset_mode', 'fixed')}")
print(f"az_step_deg      : {cfg.get('az_step_deg', 1.0)}")
print(f"rim_spacing_m    : {cfg.get('rim_spacing_m', 'n/a')}")
print(f"simplify_m       : {cfg.get('simplify_m', 0.0)}")
print(f"min_area_m2      : {cfg.get('min_area_m2', 0.0)}")
print(f"output_dir       : {cfg.get('output_dir')}")

print("\n--- Raw config (JSON view) ---")
print(json.dumps(cfg, ensure_ascii=False, indent=2))

# %% [markdown]
# ## 3) Input check
# 
# DEM など入力ファイルの存在を検証し、Notebook から見た解決先パスを明示します。

# %%
def resolve_cfg_path(p: str | Path, base: Path) -> Path:
    pp = Path(p)
    return pp if pp.is_absolute() else (base / pp).resolve()


dem_with_lava_path = resolve_cfg_path(cfg["dem_with_lava"], cfg_base)
dem_no_lava_path = resolve_cfg_path(cfg.get("dem_no_lava", ""), cfg_base) if cfg.get("dem_no_lava") else None
output_dir = resolve_cfg_path(cfg.get("output_dir", "../output/notebook_run"), cfg_base)

print(f"DEM path (with lava): {dem_with_lava_path}")
if dem_no_lava_path is not None:
    print(f"DEM path (no lava)  : {dem_no_lava_path}")
print(f"Output directory    : {output_dir}")

assert dem_with_lava_path.exists(), f"Missing DEM file: {dem_with_lava_path}"
if cfg.get("vents_mode", "manual") == "rim":
    assert dem_no_lava_path is not None and dem_no_lava_path.exists(), f"Missing DEM file: {dem_no_lava_path}"

output_dir.mkdir(parents=True, exist_ok=True)
print("Input check passed.")

# %% [markdown]
# ## 4) Model execution (decomposed, inward-offset vents)
# 
# `scripts/run_energy_cone.py` → `energy_cone.pipeline.run` の流れを、研究用途で追えるように段階実行します。

# %%
# 4.1 DEM load and runtime parameters
r = load_dem(str(dem_with_lava_path))
dem = r.data
transform = r.transform
inv_transform = ~transform
extent = (r.bounds.left, r.bounds.right, r.bounds.bottom, r.bounds.top)

mu = float(cfg["mu"])
az_step_deg = float(cfg.get("az_step_deg", 1.0))
dr = float(cfg.get("dr", r.pixel_size))
crs_epsg = cfg.get("crs_epsg", str(r.crs))

print(f"DEM shape        : {dem.shape}")
print(f"mu               : {mu}")
print(f"az_step_deg      : {az_step_deg}")
print(f"dr (m)           : {dr}")
print(f"CRS              : {crs_epsg}")

# %%
# 4.2 Vent generation + zoffset setup
vents_mode = cfg.get("vents_mode", "manual")
vents = []
zoffsets = []
lava_poly = None
lava_mask = None
rim_vents_original = None
inner_lava_poly = None
used_shift_m = float(cfg.get("vent_inward_shift_m", 0.0))
thickness_grid = None
theory_hs = None

if vents_mode == "manual":
    vents = [tuple(v) for v in cfg["vents"]]
    zoffset = float(cfg.get("zoffset", 0.0))
    zoffsets = [zoffset] * len(vents)

elif vents_mode == "rim":
    dem_no_lava = align_to_reference(str(dem_no_lava_path), r.profile)
    thickness_grid = dem - dem_no_lava

    lava_poly, lava_mask = lava_polygon_from_thickness(
        diff=thickness_grid,
        transform=transform,
        threshold_m=float(cfg.get("thickness_threshold_m", 0.5)),
        simplify_m=float(cfg.get("simplify_m", 0.0)),
        min_area_m2=float(cfg.get("min_area_m2", 0.0)),
    )

    lava_poly = gpd.GeoSeries([lava_poly], crs=r.crs).to_crs(crs_epsg).iloc[0]
    inner_lava_poly, vents, used_shift_m = inward_rim_vents_from_polygon(
        lava_poly,
        spacing_m=float(cfg.get("rim_spacing_m", 50.0)),
        shift_m=float(cfg.get("vent_inward_shift_m", 0.0)),
    )
    rim_vents_original = rim_vents_from_polygon(
        lava_poly,
        spacing_m=float(cfg.get("rim_spacing_m", 50.0)),
    )

    if cfg.get("zoffset_mode", "fixed") == "thickness":
        zoffsets_arr, sampled_thickness = vents_with_zoffset_from_thickness(
            vents=vents,
            thickness_grid=thickness_grid,
            inverse_transform=inv_transform,
            zoffset_scale=float(cfg.get("zoffset_scale", 1.0)),
            zoffset_min_m=float(cfg.get("zoffset_min_m", 0.0)),
            zoffset_cap_m=cfg.get("zoffset_cap_m", None),
        )
        zoffsets = zoffsets_arr.tolist()
        zoffset_summary = {
            "mode": "thickness",
            "median_thickness_m": float(np.median(sampled_thickness)),
            "median_zoffset_m": float(np.median(zoffsets_arr)),
        }
    else:
        zoffset = float(cfg.get("zoffset", 0.0))
        zoffsets = [zoffset] * len(vents)
        zoffset_summary = {"mode": "fixed", "zoffset_m": zoffset}

else:
    raise ValueError(f"Unsupported vents_mode: {vents_mode}")

print(f"n_vents               : {len(vents)}")
print(f"requested_shift_m     : {float(cfg.get('vent_inward_shift_m', 0.0))}")
print(f"used_shift_m          : {used_shift_m}")
print(f"rim_spacing_m         : {cfg.get('rim_spacing_m', 'n/a')}")
print(f"zoffset summary       : {zoffset_summary}")
print(f"simplify_m            : {cfg.get('simplify_m', 0.0)}")
print(f"min_area_m2           : {cfg.get('min_area_m2', 0.0)}")


# %%
# 4.2b Vent placement check: lava polygon / inward polygon / vents
if lava_poly is not None and inner_lava_poly is not None:
    fig, ax = plt.subplots(figsize=(8, 8))
    gpd.GeoSeries([lava_poly], crs=crs_epsg).boundary.plot(ax=ax, color="cyan", linewidth=1.5, label="lava polygon")
    gpd.GeoSeries([inner_lava_poly], crs=crs_epsg).boundary.plot(ax=ax, color="magenta", linewidth=1.2, label="inward offset polygon")
    if rim_vents_original is not None:
        rvx = [x for x, _ in rim_vents_original]
        rvy = [y for _, y in rim_vents_original]
        ax.scatter(rvx, rvy, s=10, c="white", edgecolors="black", label="original rim vents")
    vx = [x for x, _ in vents]
    vy = [y for _, y in vents]
    ax.scatter(vx, vy, s=12, c="yellow", edgecolors="black", label="inward-offset vents")
    ax.set_title("Vent placement on inward-offset polygon")
    ax.set_xlabel("Easting (m)")
    ax.set_ylabel("Northing (m)")
    ax.legend(loc="best")
    ax.set_aspect("equal", adjustable="box")
    fig.tight_layout()
    plt.show()

# %%
# 4.2c zoffset vs theory summary (Hs vs model zoffset)
if vents_mode == "rim" and len(vents) == len(zoffsets) and len(vents) > 0:
    dx = abs(float(transform.a))
    dy = abs(float(transform.e))

    dzdx = np.empty_like(dem, dtype=float)
    dzdy = np.empty_like(dem, dtype=float)
    dzdx[:, 1:-1] = (dem[:, 2:] - dem[:, :-2]) / (2.0 * dx)
    dzdx[:, 0] = (dem[:, 1] - dem[:, 0]) / dx
    dzdx[:, -1] = (dem[:, -1] - dem[:, -2]) / dx
    dzdy[1:-1, :] = (dem[2:, :] - dem[:-2, :]) / (2.0 * dy)
    dzdy[0, :] = (dem[1, :] - dem[0, :]) / dy
    dzdy[-1, :] = (dem[-1, :] - dem[-2, :]) / dy

    theta = np.arctan(np.hypot(dzdx, dzdy))
    rho = 2500.0
    g = 9.8
    tau_y = float(cfg.get("tau_y", 3e4))

    hs_vals = []
    z_vals = []
    for (x, y), zoffset in zip(vents, zoffsets):
        th = bilinear_sample(theta, inv_transform, x, y)
        if not np.isfinite(th):
            continue
        s = np.sin(th)
        if s <= 0:
            continue
        hs_vals.append(float(tau_y / (rho * g * s)))
        z_vals.append(float(zoffset))

    if hs_vals:
        theory_hs = np.asarray(hs_vals, dtype=float)
        model_zo = np.asarray(z_vals, dtype=float)
        diff = model_zo - theory_hs

        fig, ax = plt.subplots(figsize=(7, 6))
        ax.scatter(theory_hs, model_zo, s=20, alpha=0.7, label=f"vents (n={len(model_zo)})")
        vmin = min(float(np.min(theory_hs)), float(np.min(model_zo)))
        vmax = max(float(np.max(theory_hs)), float(np.max(model_zo)))
        ax.plot([vmin, vmax], [vmin, vmax], "k--", linewidth=1.0, label="1:1")
        ax.set_xlabel("Theoretical thickness Hs (m)")
        ax.set_ylabel("Model thickness (zoffset) (m)")
        ax.set_title("zoffset vs theory")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best")
        fig.tight_layout()
        plt.show()

        corr = float(np.corrcoef(theory_hs, model_zo)[0, 1]) if len(model_zo) > 1 else float("nan")
        print("zoffset vs theory summary:")
        print(f"  mean bias (m): {float(np.mean(diff)):.3f}")
        print(f"  RMSE (m):      {float(np.sqrt(np.mean(diff**2))):.3f}")
        print(f"  MAE (m):       {float(np.mean(np.abs(diff))):.3f}")
        print(f"  correlation:   {corr:.4f}")

# %%
# 4.3 Union computation (energy cone core)
union_geom, each_vent_polys = union_for_vents(
    dem=dem,
    inverse_transform=inv_transform,
    extent=extent,
    vents=vents,
    mu=mu,
    zoffsets=zoffsets,
    az_step_deg=az_step_deg,
    dr=dr,
)

print(f"union area (m2)  : {union_geom.area:.1f}")
print(f"union bounds     : {union_geom.bounds}")

# %%
# 4.4 Save artifacts (vector + quicklook PNG)
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

shp_path = output_dir / cfg.get("union_shapefile", f"merged_mu_{mu:.2f}_union.shp")
png_path = output_dir / cfg.get("quicklook_png", f"merged_mu_{mu:.2f}_union.png")
gdf_union.to_file(shp_path)

fig, ax = plt.subplots(figsize=(10, 8))
im = ax.imshow(
    dem,
    cmap="terrain",
    extent=extent,
    origin="upper",
    vmin=cfg.get("plot_vmin", 0),
    vmax=cfg.get("plot_vmax", 1800),
)
plt.colorbar(im, ax=ax, label="Elevation (m)")

if lava_poly is not None:
    gpd.GeoSeries([lava_poly], crs=crs_epsg).boundary.plot(
        ax=ax,
        color="cyan",
        linewidth=1.0,
        zorder=6,
        label="lava rim",
    )

gdf_union.plot(ax=ax, facecolor=(1, 0, 0, 0.25), edgecolor="red", linewidth=1.0, zorder=5)

vx = [x for x, _ in vents]
vy = [y for _, y in vents]
ax.scatter(vx, vy, c="yellow", edgecolors="black", s=10, zorder=10, label="vents")

ax.set_title(cfg.get("title", f"Energy Cone union μ={mu:.2f}"))
ax.set_xlabel("Easting (m)")
ax.set_ylabel("Northing (m)")
ax.set_xlim(extent[0], extent[1])
ax.set_ylim(extent[2], extent[3])
ax.legend(loc="upper right")
fig.tight_layout()
fig.savefig(png_path, dpi=300)
plt.show()

print(f"saved shapefile   : {shp_path}")
print(f"saved quicklook   : {png_path}")

# %% [markdown]
# ## 5) Visualization quicklook
# 
# - DEM（背景）
# - lava mask（利用可能な場合）
# - 到達範囲（union）

# %%
fig, axes = plt.subplots(1, 2 if lava_mask is not None else 1, figsize=(14, 5))
if not isinstance(axes, np.ndarray):
    axes = np.array([axes])

ax0 = axes[0]
ax0.imshow(dem, cmap="terrain", extent=extent, origin="upper")
gdf_union.boundary.plot(ax=ax0, color="red", linewidth=1.2)
if lava_poly is not None:
    gpd.GeoSeries([lava_poly], crs=crs_epsg).boundary.plot(ax=ax0, color="cyan", linewidth=1.0)
if inner_lava_poly is not None:
    gpd.GeoSeries([inner_lava_poly], crs=crs_epsg).boundary.plot(ax=ax0, color="magenta", linewidth=1.0)
ax0.set_title("DEM + union (+ lava rim)")
ax0.set_xlabel("Easting (m)")
ax0.set_ylabel("Northing (m)")

if lava_mask is not None:
    ax1 = axes[1]
    ax1.imshow(lava_mask, cmap="magma", origin="upper")
    ax1.set_title("Lava mask")
    ax1.set_xlabel("column")
    ax1.set_ylabel("row")

fig.tight_layout()
plt.show()

# %% [markdown]
# ## 6) Output check
# 
# 出力ディレクトリ配下の生成物を一覧表示します。

# %%
for p in sorted(output_dir.glob("*")):
    print(p.name)

# %% [markdown]
# ## 7) Interactive `mu` slider experiment
# 
# `mu` をスライダーで動的に変更し、cone の再計算結果をインタラクティブに再描画します。
# 
# - 範囲: 0.20 ～ 0.50
# - 初期値: 0.25
# - ステップ: 0.01
# - `continuous_update=False`（無駄な再計算を抑制）
# 
# パフォーマンス配慮として、DEM / lava polygon / vents / zoffsets / theory 散布点は事前計算済みとし、
# `update(mu)` 内では `union_for_vents`（cone計算）と可視化のみを再実行します。

# %%
def _max_runout_m(poly, vent_xy):
    if poly is None or poly.is_empty:
        return np.nan
    x0, y0 = vent_xy
    polys = list(poly.geoms) if poly.geom_type == "MultiPolygon" else [poly]
    max_d = 0.0
    for geom in polys:
        coords = np.asarray(geom.exterior.coords)
        d = np.hypot(coords[:, 0] - x0, coords[:, 1] - y0)
        if d.size:
            max_d = max(max_d, float(np.nanmax(d)))
    return max_d


def update(mu: float):
    union_geom_mu, each_vent_polys_mu = union_for_vents(
        dem=dem,
        inverse_transform=inv_transform,
        extent=extent,
        vents=vents,
        mu=float(mu),
        zoffsets=zoffsets,
        az_step_deg=az_step_deg,
        dr=dr,
    )

    per_vent_runout_m = np.asarray(
        [_max_runout_m(poly, vent_xy) for vent_xy, poly in zip(vents, each_vent_polys_mu)],
        dtype=float,
    )
    per_vent_runout_m = per_vent_runout_m[np.isfinite(per_vent_runout_m)]

    runout_max_km = float(np.nanmax(per_vent_runout_m) / 1000.0) if per_vent_runout_m.size else float("nan")
    runout_p95_km = float(np.nanpercentile(per_vent_runout_m, 95) / 1000.0) if per_vent_runout_m.size else float("nan")
    area_km2 = float(union_geom_mu.area / 1e6)

    fig = plt.figure(figsize=(18, 6))
    gs = fig.add_gridspec(1, 3, width_ratios=[1.3, 1.0, 1.0])
    ax_map = fig.add_subplot(gs[0, 0])
    ax_metrics = fig.add_subplot(gs[0, 1])
    ax_theory = fig.add_subplot(gs[0, 2])

    # 図1: 地図表示（DEM + polygon + vents + runout）
    im = ax_map.imshow(
        dem,
        cmap="terrain",
        extent=extent,
        origin="upper",
        vmin=cfg.get("plot_vmin", 0),
        vmax=cfg.get("plot_vmax", 1800),
        alpha=0.95,
    )
    if lava_poly is not None:
        gpd.GeoSeries([lava_poly], crs=crs_epsg).boundary.plot(
            ax=ax_map, color="cyan", linewidth=1.2, zorder=7, label="lava polygon"
        )
    if inner_lava_poly is not None:
        gpd.GeoSeries([inner_lava_poly], crs=crs_epsg).boundary.plot(
            ax=ax_map, color="magenta", linewidth=1.0, zorder=8, label="inward offset polygon"
        )
    gpd.GeoSeries([union_geom_mu], crs=crs_epsg).plot(
        ax=ax_map,
        facecolor=(1, 0, 0, 0.25),
        edgecolor="red",
        linewidth=1.1,
        zorder=6,
        label="energy cone runout",
    )
    vx = [x for x, _ in vents]
    vy = [y for _, y in vents]
    ax_map.scatter(vx, vy, c="yellow", edgecolors="black", s=14, zorder=10, label="vents")
    ax_map.set_title(f"Map overlay (mu={mu:.2f})")
    ax_map.set_xlabel("Easting (m)")
    ax_map.set_ylabel("Northing (m)")
    ax_map.set_xlim(extent[0], extent[1])
    ax_map.set_ylim(extent[2], extent[3])
    ax_map.legend(loc="upper right", fontsize=8)
    plt.colorbar(im, ax=ax_map, shrink=0.82, label="Elevation (m)")

    # 図2: runout 指標の変化
    labels = ["runout_max_km", "runout_p95_km", "area_km2"]
    values = [runout_max_km, runout_p95_km, area_km2]
    colors = ["#d62728", "#ff7f0e", "#1f77b4"]
    ax_metrics.bar(labels, values, color=colors, alpha=0.85)
    ax_metrics.set_title("Runout metrics vs mu")
    ax_metrics.set_ylabel("Value")
    ax_metrics.tick_params(axis="x", rotation=20)
    for i, v in enumerate(values):
        if np.isfinite(v):
            ax_metrics.text(i, v, f"{v:.3f}", ha="center", va="bottom", fontsize=9)

    # 図3: zoffset vs theory（既存と同等）
    if theory_hs is not None and len(theory_hs) == len(zoffsets):
        model_zo = np.asarray(zoffsets, dtype=float)
        ax_theory.scatter(theory_hs, model_zo, s=20, alpha=0.7, label=f"vents (n={len(model_zo)})")
        vmin = min(float(np.min(theory_hs)), float(np.min(model_zo)))
        vmax = max(float(np.max(theory_hs)), float(np.max(model_zo)))
        ax_theory.plot([vmin, vmax], [vmin, vmax], "k--", linewidth=1.0, label="1:1")
        ax_theory.set_xlabel("Theoretical thickness Hs (m)")
        ax_theory.set_ylabel("Model thickness (zoffset) (m)")
        ax_theory.set_title("zoffset vs theory")
        ax_theory.grid(True, alpha=0.3)
        ax_theory.legend(loc="best", fontsize=8)
    else:
        ax_theory.text(0.5, 0.5, "zoffset/theory data unavailable", ha="center", va="center")
        ax_theory.set_title("zoffset vs theory")

    fig.tight_layout()
    plt.show()

    print(
        f"mu={mu:.2f} | runout_max_km={runout_max_km:.3f} | "
        f"runout_p95_km={runout_p95_km:.3f} | area_km2={area_km2:.3f}"
    )


mu_slider = widgets.FloatSlider(
    value=0.25,
    min=0.2,
    max=0.5,
    step=0.01,
    description="mu",
    continuous_update=False,
    readout_format=".2f",
)
display(mu_slider)
interactive_out = widgets.interactive_output(update, {"mu": mu_slider})
display(interactive_out)

# %% [markdown]
# ## 8) Summary
# 
# - 本 notebook は、`config_path` の変更のみで同一の energy cone フローを再現可能です。
# - `mu` は `ipywidgets` スライダー（0.20～0.50）で変更でき、更新ごとに cone 計算を再実行して可視化します。
# - 計算は `src/energy_cone` の既存関数（DEM読込・vent生成・union計算）を再利用しています。
# - パフォーマンスのため、DEM / polygon / vents / zoffset は事前計算し、`update()` では cone 計算と描画更新のみを実行します。
