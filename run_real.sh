#!/usr/bin/env bash
set -euo pipefail

LOG="output/run_real_$(date +%Y%m%d_%H%M%S).log"
mkdir -p output

echo "=== Energy cone: rim-vents-real scenarios ===" | tee "$LOG"
echo "Started: $(date)" | tee -a "$LOG"
echo "" | tee -a "$LOG"

for f in configs/rim-vents-real-*.yml; do
  echo "--- $f ---" | tee -a "$LOG"
  uv run python scripts/run_energy_cone.py --config "$f" 2>&1 | tee -a "$LOG"
  echo "" | tee -a "$LOG"
done

echo "Finished: $(date)" | tee -a "$LOG"
echo "Log: $LOG"
