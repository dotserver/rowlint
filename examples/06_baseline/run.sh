#!/usr/bin/env bash
# Decision 5: compare a batch against a saved baseline report.
# Expected: null-fraction and distinct-count changes fail, exit code 1.
set -euo pipefail
cd "$(dirname "$0")"
python make_batches.py
python -m rowlint orders_2026-09-01.csv --format json --output baseline.json
python -m rowlint orders_2026-09-02.csv --baseline baseline.json --config baseline_rules.yaml --concise
