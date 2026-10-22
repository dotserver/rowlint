#!/usr/bin/env bash
# Validate a rules file without loading any data.
# Expected: broken.yaml is rejected with a ConfigError and exit code 2.
set -euo pipefail
cd "$(dirname "$0")"
python -m rowlint --check-config broken.yaml
