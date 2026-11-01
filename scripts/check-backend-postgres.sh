#!/usr/bin/env bash
# Full backend matrix against an owned PostgreSQL 17 container on a random loopback port.
set -euo pipefail
cd "$(dirname "$0")/.."
BACKEND_PYTHON=${BACKEND_PYTHON:-.venv-backend/bin/python}
exec "$BACKEND_PYTHON" -I scripts/backend-postgres-test.py "$@"
