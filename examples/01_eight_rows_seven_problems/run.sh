#!/usr/bin/env bash
# Eight rows, seven problems: validate a small orders extract against rules.yaml.
# Expected: seven failed checks and exit code 1.
set -euo pipefail
cd "$(dirname "$0")"
python -m rowlint orders.csv --config rules.yaml --concise
