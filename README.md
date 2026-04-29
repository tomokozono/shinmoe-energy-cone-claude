# Shinmoedake Energy Cone (Notebook Refactor)

This repository refactors six original notebooks into reusable Python modules and a single configurable CLI pipeline.

## Structure

- `src/energy_cone/io_raster.py` — DEM loading and grid alignment.
- `src/energy_cone/sampling.py` — bilinear sampling utility.
- `src/energy_cone/vents.py` — lava thickness to lava polygon, rim vent generation, and thickness-based z-offsets.
- `src/energy_cone/cone.py` — ray-casting energy cone boundary and union across vents.
- `src/energy_cone/pipeline.py` — high-level `run(config)` workflow.
- `scripts/run_energy_cone.py` — CLI wrapper.
- `configs/*.yml` — six scenarios matching the six notebooks.

## DEM input files

Create a local `data/` directory and place the GeoTIFF files there:

- `data/demShinmoeRL2025N.tif`
- `data/demShinmoeRL2025S.tif`
- `data/demShinmoe2025_nolava.tif`

Do **not** commit `.tif` files.

## Install dependencies

```bash
uv sync --dev
```

または pip の場合:

```bash
pip install -e .
```

## Run the pipeline

Example (as requested):

```bash
python scripts/run_energy_cone.py --config configs/rim-vents-real-S.yml
```

Other notebook-equivalent configs:

- `configs/multi-vents-N.yml`
- `configs/multi-vents-S.yml`
- `configs/rim-vents-N.yml`
- `configs/rim-vents-S.yml`
- `configs/rim-vents-real-N.yml`
- `configs/rim-vents-real-S.yml`


### Inward-shifted rim vents

For `vents_mode: rim`, you can keep rim sampling on the lava boundary and shift vents inward before raycasting:

```yaml
vents_mode: rim
rim_spacing_m: 50.0
vent_inward_shift_m: 10.0
```

`vent_inward_shift_m` defaults to `0.0` (no shift, same behavior as before).

Example command:

```bash
python scripts/run_energy_cone.py --config configs/rim-vents-real-S.yml
```

## Mu sweep

Run the same case for multiple `mu` values without duplicating config files:

```bash
python scripts/sweep_mu.py --config configs/rim-vents-real-S.yml --mu 0.25 0.30 0.35 0.40
```

For each `mu`, the runner overrides `mu` in-memory and writes outputs to:

- `outputs/<case_name>/mu_<value>/`

It also writes a summary table at:

- `outputs/<case_name>/mu_sweep_summary.csv`

## Outputs

Each run writes to `output_dir` in the selected config and includes:

- union polygon shapefile (`*.shp` + sidecars)
- quicklook PNG map

Some rim-vent configs also save a lava mask quicklook.

## Keeping behavior close to notebooks

The refactor preserves notebook logic:

- same ray-casting stop criterion (`terrain >= cone`)
- same azimuth stepping and DEM-derived radial step default
- same rim extraction flow from DEM difference threshold
- same option for fixed or thickness-derived z-offsets

---

## Code Review (2026-04-29)

### バグ・正確性

| ファイル | 行 | 内容 |
|---|---|---|
| `pyproject.toml` | 2 | プロジェクト名が `"kirishima-energy-cone"` になっている。`"shinmoe-energy-cone"` に変更すべき。 |
| `pyproject.toml` | — | `pyyaml` が依存関係に未記載（`pipeline.py` で `import yaml` を使用）。`pytest` も dev deps に未記載。 |
| `main.py` | — | スキャフォールディングの残骸。`"Hello from kirishima-energy-cone!"` を出力するだけで本体のどこからも呼ばれていない。 |
| `vents.py` | 93 | `rim.interpolate(d)` を 1 距離につき 2 回呼んでいる（`.x` と `.y` のアクセスで）。`pt = rim.interpolate(d)` に一度代入してから参照するべき。 |
| `pipeline.py` | 281 | `set(np.round(np.asarray(zoffsets), 6))` で一意性を判定しているが、浮動小数点の精度次第で誤カラーマップになりうる。`np.ptp(zoffsets) > 1e-6` などに置き換えた方が安全。 |
| `cone.py` | 71 | NaN ブレーク後に `hit = (x, y)` で DEM 境界外の座標を使う。意図通りだが、`r_max_bound` 超過によるループ終了時も同じ変数を参照する点は要注意（どちらのケースでも実用上は問題ない）。 |

### 設定・スクリプト

| ファイル | 内容 |
|---|---|
| `auto.sh` | `python` を直接呼び出している。 |
| `auto-real.sh` | `uv run python` を使用。2 つのスクリプト間で実行環境が不一致。どちらかに統一すること。 |
| `scripts/*.py`, `tests/*.py` | `sys.path.insert(0, ROOT / "src")` を手動で追加している。`uv pip install -e .` または `pip install -e .` でパッケージをインストールすれば不要になる。 |

### コード品質

| ファイル | 行 | 内容 |
|---|---|---|
| `vents.py` | 109–172 | `shift_vents_inward` が `@deprecated` コメントと警告付きで残っている。`test_vents_shift.py` でも引き続きテストされており、削除タイミングが不明確。使わないなら削除を検討。 |
| `pipeline.py` | 53–55 | `rho = 2500.0`（溶岩密度 kg/m³）と `g = 9.8`（重力加速度 m/s²）がハードコードされている。`_plot_zoffset_vs_theory` の診断プロットにのみ使用されるが、config で指定できると汎用性が上がる。 |
| `pipeline.py` | 94–107 | 相関係数などの統計量は `print` されるのみ。図中にテキストアノテーションとして入れると視認性が高まる。 |

### 科学的・ドメイン的な注意点

| 内容 |
|---|
| **方位角の慣習**：`cone.py` の方位角ループ（`az=0° → East, CCW`）は数学的慣習。地質・地理の標準は北基準・時計回り。全方位のユニオンを取るため最終出力に影響はないが、個別レイの方向を解析する場合は注意が必要。 |
| **`tau_y` の 10 倍差**：`rim-vents-real-N.yml` では `tau_y: 30000.0 Pa`、`rim-vents-real-N-tah10h.yml` では `tau_y: 300000.0 Pa`（10 倍）。`zoffset_vs_theory.png` の理論厚さに直接影響するため、設定値の意図を README に明記しておくことを推奨。 |
| **DEM 座標系**：`align_to_reference` は CRS・グリッドが一致しない場合に自動リプロジェクションするが、元の DEM が地理座標系（度単位）だと `rim_spacing_m` や `vent_inward_shift_m` が度単位として解釈される。現状の EPSG:6689（平面直角座標系）運用では問題ない。 |

### テストカバレッジ

現状のテストは以下をカバーしている：

- `test_cone_monotonic.py`：μ 増加 → コーン面積減少（単調性）
- `test_sampling.py`：平面上の双線形補間精度
- `test_vents_shift.py`：ポリゴンオフセットと内側ベント生成
- `test_sweep_mu.py`：μ スイープスクリプトのモック統合テスト

追加すると良いテスト：

- `lava_polygon_from_thickness`（閾値ゼロや全 NaN グリッドの境界ケース）
- `align_to_reference`（同一グリッドのショートサーキット）
- 平坦 DEM を使ったパイプライン end-to-end（DEM ファイルなしでも実行可能な形）

