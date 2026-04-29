import sys
from pathlib import Path

from scripts import run_energy_cone


def test_run_energy_cone_default_mu(monkeypatch, tmp_path):
    config_path = tmp_path / "case.yml"
    config_path.write_text(
        f"vents_mode: manual\ndem_with_lava: fake.tif\nvents:\n  - [0.0, 0.0]\n"
        f"output_dir: {tmp_path / 'output'}\n",
        encoding="utf-8",
    )

    calls = []

    def fake_load_config(p):
        return {
            "vents_mode": "manual",
            "dem_with_lava": str(tmp_path / "fake.tif"),
            "vents": [[0.0, 0.0]],
            "output_dir": str(tmp_path / "output"),
        }

    def fake_run(cfg):
        calls.append(cfg)
        mu_tag = f"{cfg['mu']:.2f}"
        out_dir = Path(cfg["output_dir"]) / f"mu_{mu_tag}"
        out_dir.mkdir(parents=True, exist_ok=True)
        return {
            "n_vents": 1,
            "az_step": 1.0,
            "dr_m": 10.0,
            "area_m2": 1000.0 * cfg["mu"],
            "bounds_minx": 0.0,
            "bounds_miny": 0.0,
            "bounds_maxx": 1.0,
            "bounds_maxy": 1.0,
            "output_dir": str(out_dir),
        }

    monkeypatch.setattr(run_energy_cone, "load_config", fake_load_config)
    monkeypatch.setattr(run_energy_cone, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["run_energy_cone.py", "--config", str(config_path)])

    code = run_energy_cone.main()
    assert code == 0

    assert [c["mu"] for c in calls] == run_energy_cone.DEFAULT_MU

    summary = tmp_path / "output" / "mu_sweep_summary.csv"
    assert summary.exists()
    lines = summary.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0].startswith("mu,n_vents,")
    assert len(lines) == len(run_energy_cone.DEFAULT_MU) + 1


def test_run_energy_cone_custom_mu(monkeypatch, tmp_path):
    config_path = tmp_path / "case.yml"
    config_path.write_text("", encoding="utf-8")

    def fake_load_config(p):
        return {
            "dem_with_lava": str(tmp_path / "fake.tif"),
            "output_dir": str(tmp_path / "output"),
        }

    def fake_run(cfg):
        mu_tag = f"{cfg['mu']:.2f}"
        out_dir = Path(cfg["output_dir"]) / f"mu_{mu_tag}"
        out_dir.mkdir(parents=True, exist_ok=True)
        return {
            "n_vents": 1, "az_step": 1.0, "dr_m": 10.0,
            "area_m2": cfg["mu"], "bounds_minx": 0.0, "bounds_miny": 0.0,
            "bounds_maxx": 1.0, "bounds_maxy": 1.0, "output_dir": str(out_dir),
        }

    monkeypatch.setattr(run_energy_cone, "load_config", fake_load_config)
    monkeypatch.setattr(run_energy_cone, "run", fake_run)
    monkeypatch.setattr(sys, "argv", [
        "run_energy_cone.py", "--config", str(config_path), "--mu", "0.25", "0.30",
    ])

    code = run_energy_cone.main()
    assert code == 0

    lines = (tmp_path / "output" / "mu_sweep_summary.csv").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3  # header + 2 rows
