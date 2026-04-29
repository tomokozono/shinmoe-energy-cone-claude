# Shinmoedake Energy Cone

新燃岳（霧島山）を対象とした Energy Cone モデル。
6本のオリジナルノートブックを再利用可能な Python パッケージとシングル CLI パイプラインにリファクタリングしたもの。

## リポジトリ構成

```
src/energy_cone/
  io_raster.py   — DEM 読み込み・グリッド整合
  sampling.py    — 双線形補間ユーティリティ
  vents.py       — 溶岩ポリゴン抽出・リムベント生成・厚さベース z オフセット
  cone.py        — レイキャスト Energy Cone 境界 + ベントユニオン
  pipeline.py    — run(config) 高レベルワークフロー

scripts/
  run_energy_cone.py  — 単一シナリオ CLI
  sweep_mu.py         — μ 感度分析

configs/            — 9 シナリオの YAML 設定ファイル
tests/              — pytest テストスイート
notebooks/          — リファクタリング後のノートブック
notebooks_archive/  — オリジナルノートブック（参照用）
```

## DEM 入力ファイル

`data/` ディレクトリを作成し、以下の GeoTIFF を配置（コミット禁止）：

| ファイル | 用途 |
|---|---|
| `data/demShinmoeRL2025N.tif` | 溶岩込み DEM（北側） |
| `data/demShinmoeRL2025S.tif` | 溶岩込み DEM（南側） |
| `data/demShinmoe2025N_V1.tif` | 溶岩込み DEM（北側 V1） |
| `data/demShinmoe2025S_V1.tif` | 溶岩込み DEM（南側 V1） |
| `data/demShinmoe2025_nolava.tif` | 溶岩なし DEM（差分計算用） |

## セットアップ

```bash
uv sync --dev
```

または pip の場合：

```bash
pip install -e .
```

## 実行スクリプト

| スクリプト | 用途 |
|---|---|
| `./run_all.sh` | 全シナリオ実行（ログ付き） |
| `./run_real.sh` | `rim-vents-real-*` シナリオのみ実行 |
| `./run_sweep.sh [config] [mu...]` | μ 感度分析 |

```bash
# 全シナリオ
./run_all.sh

# real シナリオのみ
./run_real.sh

# μ スイープ（引数指定）
./run_sweep.sh configs/rim-vents-real-S.yml 0.20 0.25 0.30 0.35 0.40

# μ スイープ（引数なし → 全 real シナリオ × デフォルト μ）
./run_sweep.sh
```

## 単一シナリオ実行

```bash
uv run python scripts/run_energy_cone.py --config configs/rim-vents-real-S.yml
```

## 出力構造

各実行の出力は `<output_dir>/mu_<value>/` 以下に固定ファイル名で書き出される：

```
output/
  rim-vents-real-S/
    mu_0.25/
      union.shp         # Energy Cone ユニオンポリゴン（+ sidecars）
      quicklook.png     # クイックルック地図
      lava_mask.png     # 溶岩マスク（rim モード時）
      zoffset_vs_theory.png  # zoffset vs 理論厚さ診断プロット
    mu_0.30/
      ...
```

μ スイープ（`sweep_mu.py`）は `outputs/<case>/` 以下に同じ構造で出力し、サマリー CSV も書き出す：

```
outputs/
  rim-vents-real-S/
    mu_0.20/
    mu_0.25/
    mu_0.30/
    mu_sweep_summary.csv
```

## シナリオ一覧

| config | vents_mode | DEM | μ | τ_y (Pa) |
|---|---|---|---|---|
| `multi-vents-N.yml` | manual | RL2025N | 0.30 | — |
| `multi-vents-S.yml` | manual | RL2025N | 0.30 | — |
| `rim-vents-N.yml` | rim (shift=0) | RL2025N | 0.25 | 3×10⁴ |
| `rim-vents-S.yml` | rim (shift=0) | RL2025N | 0.30 | 3×10⁴ |
| `rim-vents-real-N.yml` | rim (shift=20m) | RL2025N | 0.25 | 3×10⁴ |
| `rim-vents-real-S.yml` | rim (shift=20m) | RL2025S | 0.25 | 3×10⁴ |
| `rim-vents-real-N-tah10h.yml` | rim (shift=20m) | 2025N_V1 | 0.25 | 3×10⁵ |
| `rim-vents-real-S-tah10h.yml` | rim (shift=20m) | 2025S_V1 | 0.25 | 3×10⁵ |
| `test1.yml` | rim (shift=20m) | RL2025S | 0.25 | 3×10⁴ |

`tah10h` シナリオは `tau_y` を通常の 10 倍（3×10⁵ Pa）に設定した高降伏応力ケース。
`zoffset_vs_theory.png` の理論厚さ Hs = τ_y / (ρg sin θ) に直接影響する。

## YAML 設定の主要パラメータ

```yaml
vents_mode: rim          # "manual" または "rim"
dem_with_lava: ../data/demShinmoeRL2025N.tif
dem_no_lava:  ../data/demShinmoe2025_nolava.tif  # rim モード時必須
mu: 0.25                 # H/L 比（見かけ摩擦係数）
tau_y: 30000.0           # 降伏応力 [Pa]（zoffset 診断プロット用）
zoffset_mode: thickness  # "fixed" または "thickness"
zoffset_scale: 1.0       # 厚さへのスケール係数
zoffset_cap_m: null      # zoffset 上限 [m]（null で無制限）
rim_spacing_m: 50.0      # リムベント間隔 [m]
vent_inward_shift_m: 20.0 # ベントを内側にシフトする距離 [m]
thickness_threshold_m: 0.5
crs_epsg: EPSG:6689
az_step_deg: 1.0
output_dir: ../output/rim-vents-real-N  # mu_X サブディレクトリが自動作成される
```

## ノートブックとの整合性

リファクタリングはノートブックのロジックを保持している：

- 同一のレイキャスト停止条件（`terrain >= cone`）
- 同一の方位角ステップと DEM 由来のラジアルステップデフォルト
- 同一の DEM 差分閾値によるリム抽出フロー
- 固定または厚さ由来の z オフセット両方に対応

---

## Code Review メモ（2026-04-29 実施・修正済み）

| 項目 | 状態 |
|---|---|
| `pyproject.toml` プロジェクト名 `"kirishima-energy-cone"` | 修正済 → `"shinmoe-energy-cone"` |
| `pyyaml` / `pytest` が依存関係に未記載 | 修正済 |
| `main.py` スキャフォールディング残骸 | 削除済 |
| `vents.py` `rim.interpolate(d)` の二重呼び出し | 修正済 |
| `pipeline.py` zoffset 一意判定のセット演算 | 修正済 → `max - min > 1e-6` |
| `shift_vents_inward` deprecated 関数 | 削除済 |
| スクリプト・テストの `sys.path.insert` 手動追加 | 削除済（editable install に移行） |
| `auto.sh` / `auto-real.sh` の実行方法不一致 | 統一済・`run_*.sh` に置換 |
| 出力ファイル名にパラメータをハードコード | 修正済 → フォルダ構造でパラメータを表現 |
| `sweep_mu.py` の相対 DEM パス解決バグ | 修正済 |
| `test_sampling.py` ピクセル中心/左上隅の混同 | 修正済 |
| `test_vents_shift.py` 薄ポリゴンテストのフィクスチャ | 修正済 |
