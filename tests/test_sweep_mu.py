import sys
from pathlib import Path

from scripts import sweep_mu


def test_sweep_mu_writes_summary_and_overrides_output(monkeypatch, tmp_path):
    config_path = tmp_path / "case.yml"
    config_path.write_text("mu: 0.1\n", encoding="utf-8")

    monkeypatch.setattr(sweep_mu, "ROOT", tmp_path)
    calls = []

    def fake_run(cfg):
        calls.append(cfg)
        # Simulate pipeline: creates mu_X subdir under output_dir
        mu_tag = f"{cfg['mu']:.2f}"
        out_dir = Path(cfg["output_dir"]) / f"mu_{mu_tag}"
        out_dir.mkdir(parents=True, exist_ok=True)
        return {
            "n_vents": 3,
            "az_step": 1.0,
            "dr_m": 5.0,
            "area_m2": 123.0 + cfg["mu"],
            "bounds_minx": 1.0,
            "bounds_miny": 2.0,
            "bounds_maxx": 3.0,
            "bounds_maxy": 4.0,
            "output_dir": str(out_dir),
        }

    fake_load_config = lambda p: {"mu": 0.1, "dem_with_lava": "fake.tif"}
    monkeypatch.setattr(sweep_mu, "_load_pipeline_functions", lambda: (fake_load_config, fake_run))
    monkeypatch.setattr(sys, "argv", [
        "sweep_mu.py",
        "--config",
        str(config_path),
        "--mu",
        "0.25",
        "0.30",
    ])

    code = sweep_mu.main()
    assert code == 0

    assert len(calls) == 2
    assert calls[0]["mu"] == 0.25
    assert calls[1]["mu"] == 0.30
    # sweep passes the base dir; pipeline appends mu_X internally
    assert calls[0]["output_dir"].endswith("outputs/case")
    assert calls[1]["output_dir"].endswith("outputs/case")

    summary_path = tmp_path / "outputs" / "case" / "mu_sweep_summary.csv"
    assert summary_path.exists()

    lines = summary_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines[0] == "mu,n_vents,az_step,dr_m,vent_inward_shift_m,area_m2,bounds_minx,bounds_miny,bounds_maxx,bounds_maxy,output_dir"
    assert "0.25,3,1.0,5.0,0.0,123.25,1.0,2.0,3.0,4.0," in lines[1]
    assert "0.3,3,1.0,5.0,0.0,123.3,1.0,2.0,3.0,4.0," in lines[2]
