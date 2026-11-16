#!/usr/bin/env bash
# Run from any directory, with the project virtual environment activated.
set -euo pipefail
cd "$(dirname "$0")/.."
PYTHON="${PYTHON:-python}"
"$PYTHON" -c 'import sys, rbp, streamlit, ortools; assert sys.version_info[:2] == (3, 12), "Use Python 3.12 for the reference reproduction"'
REV=$(git rev-parse --short=12 HEAD)
ROOT="${RBP_REPRO_ROOT:-results/reproduction/$REV}"
printf 'Reproducing commit %s into %s\n' "$REV" "$ROOT"
"$PYTHON" -m pytest
"$PYTHON" scripts/gate_wis.py
"$PYTHON" scripts/release_check.py
for experiment in e1 e2 e3; do
  "$PYTHON" -m rbp.experiments.runner "config/experiments/$experiment.yaml" --output-root "$ROOT/primary"
done
for experiment in e1 e2 e3; do
  "$PYTHON" -m rbp.experiments.runner "config/experiments/$experiment.yaml" --output-root "$ROOT/repeat"
done
"$PYTHON" scripts/make_report.py --results-root "$ROOT/primary" --repeat-root "$ROOT/repeat" --output "$ROOT/reports"
"$PYTHON" scripts/compare_summaries.py --actual "$ROOT/reports"
printf 'Reproduction complete. Reports: %s/reports\n' "$ROOT"
