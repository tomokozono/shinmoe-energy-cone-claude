#!/usr/bin/env python
from __future__ import annotations

import argparse
import json

from energy_cone.pipeline import run


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Shinmoedake energy cone pipeline")
    parser.add_argument("--config", required=True, help="Path to YAML config")
    args = parser.parse_args()

    result = run(args.config)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
