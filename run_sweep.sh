#!/usr/bin/env bash
# Usage: ./run_sweep.sh [config] [mu values...]
# Example: ./run_sweep.sh configs/rim-vents-real-S.yml 0.20 0.25 0.30 0.35 0.40
# Default: runs both rim-vents-real configs with mu = 0.20 0.25 0.30 0.35 0.40
set -euo pipefail

DEFAULT_MU=(0.20 0.25 0.30 0.35 0.40)

LOG="output/run_sweep_$(date +%Y%m%d_%H%M%S).log"
mkdir -p output

echo "=== Energy cone: mu sweep ===" | tee "$LOG"
echo "Started: $(date)" | tee -a "$LOG"
echo "" | tee -a "$LOG"

if [ $# -ge 1 ]; then
  CONFIG="$1"
  shift
  MU_VALS=("${@:-${DEFAULT_MU[@]}}")
  echo "--- $CONFIG  mu: ${MU_VALS[*]} ---" | tee -a "$LOG"
  uv run python scripts/sweep_mu.py --config "$CONFIG" --mu "${MU_VALS[@]}" 2>&1 | tee -a "$LOG"
else
  MU_VALS=("${DEFAULT_MU[@]}")
  for f in configs/rim-vents-real-*.yml; do
    echo "--- $f  mu: ${MU_VALS[*]} ---" | tee -a "$LOG"
    uv run python scripts/sweep_mu.py --config "$f" --mu "${MU_VALS[@]}" 2>&1 | tee -a "$LOG"
    echo "" | tee -a "$LOG"
  done
fi

echo "Finished: $(date)" | tee -a "$LOG"
echo "Log: $LOG"
