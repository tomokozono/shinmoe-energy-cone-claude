#!/usr/bin/env python
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_pipeline_functions():
    from energy_cone.pipeline import load_config, run

    return load_config, run


def _format_mu(mu: float) -> str:
    return f"{mu:.2f}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Shinmoedake energy cone pipeline for multiple mu values")
    parser.add_argument("--config", required=True, help="Path to YAML config")
    parser.add_argument("--mu", required=True, nargs="+", type=float, help="Mu values to sweep")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    load_config, run = _load_pipeline_functions()
    cfg = load_config(config_path)
    case_name = config_path.stem

    base_output_dir = ROOT / "outputs" / case_name
    base_output_dir.mkdir(parents=True, exist_ok=True)

    cfg_base = config_path.parent

    rows = []
    for mu in args.mu:
        mu_tag = _format_mu(mu)
        cfg_run = dict(cfg)
        cfg_run["mu"] = float(mu)
        cfg_run["output_dir"] = str(base_output_dir)

        for key in ("dem_with_lava", "dem_no_lava"):
            if key in cfg_run:
                p = Path(cfg_run[key])
                if not p.is_absolute():
                    cfg_run[key] = str((cfg_base / p).resolve())

        result = run(cfg_run)
        rows.append(
            {
                "mu": float(mu),
                "n_vents": int(result["n_vents"]),
                "az_step": float(result["az_step"]),
                "dr_m": float(result["dr_m"]),
                "vent_inward_shift_m": float(result.get("vent_inward_shift_m", cfg_run.get("vent_inward_shift_m", 0.0))),
                "area_m2": float(result["area_m2"]),
                "bounds_minx": float(result["bounds_minx"]),
                "bounds_miny": float(result["bounds_miny"]),
                "bounds_maxx": float(result["bounds_maxx"]),
                "bounds_maxy": float(result["bounds_maxy"]),
                "output_dir": str(result["output_dir"]),
            }
        )

    summary_path = base_output_dir / "mu_sweep_summary.csv"
    columns = [
        "mu",
        "n_vents",
        "az_step",
        "dr_m",
        "vent_inward_shift_m",
        "area_m2",
        "bounds_minx",
        "bounds_miny",
        "bounds_maxx",
        "bounds_maxy",
        "output_dir",
    ]
    with summary_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)

    print(json.dumps({"case_name": case_name, "summary_csv": str(summary_path), "runs": rows}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
