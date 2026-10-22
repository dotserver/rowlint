#!/usr/bin/env bash
# Decision 4: treat exit codes as an API.
# Routes rowlint's exit code: 0 = load, 1 = quarantine, anything else = broken check.
# Usage: ./gate.sh [batch.csv]   (defaults to the orders extract from example 01)
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

BATCH="${1:-$SCRIPT_DIR/../01_eight_rows_seven_problems/orders.csv}"
RULES="$SCRIPT_DIR/../01_eight_rows_seven_problems/rules.yaml"

status=0
python -m rowlint "$BATCH" --config "$RULES" --format json --output "$SCRIPT_DIR/report.json" || status=$?

case "$status" in
  0) echo "load $BATCH" ;;                           # passed: load it
  1) echo "quarantine $BATCH"; exit 1 ;;             # failed: hold it back, alert the data owner
  *) echo "validation could not run" >&2; exit 2 ;;  # broken check: alert the pipeline owner
esac
