#!/usr/bin/env bash
# Starts the service. It must listen on $PORT (default 8080) and read the
# upstream base URL from $FX_UPSTREAM_BASE — we point that at a fake upstream
# when we review your work, so nothing here may hardcode frankfurter.dev.
set -euo pipefail

if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

PORT="${PORT:-8080}"

if command -v uvicorn >/dev/null 2>&1; then
  exec uvicorn app:app --host 0.0.0.0 --port "$PORT"
elif command -v python >/dev/null 2>&1; then
  exec python -m uvicorn app:app --host 0.0.0.0 --port "$PORT"
elif command -v python3 >/dev/null 2>&1; then
  exec python3 -m uvicorn app:app --host 0.0.0.0 --port "$PORT"
elif command -v py >/dev/null 2>&1; then
  exec py -m uvicorn app:app --host 0.0.0.0 --port "$PORT"
else
  echo "Python with uvicorn is required to start the service" >&2
  exit 1
fi
