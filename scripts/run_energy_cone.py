#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from energy_cone.pipeline import load_config, run

DEFAULT_MU = [0.20, 0.25, 0.30, 0.35, 0.40, 0.45]


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

    print(
        json.dumps(
            {
                "config": str(config_path),
                "mu_values": args.mu,
                "summary_csv": str(summary_path),
                "runs": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
