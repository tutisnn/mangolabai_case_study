#!/usr/bin/env bash
# Runs your tests. They must pass with no network at all: we run this with
# FX_UPSTREAM_BASE pointing at a closed port.
set -euo pipefail

if command -v python >/dev/null 2>&1; then
  python -m pytest -s -v tests
elif command -v python3 >/dev/null 2>&1; then
  python3 -m pytest -s -v tests
elif command -v py >/dev/null 2>&1; then
  py -m pytest -s -v tests
elif command -v pytest >/dev/null 2>&1; then
  pytest -s -v tests
else
  echo "Python with pytest is required to run tests" >&2
  exit 1
fi
