#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/noctra.sh"

noctra_load_env

cd "$NOCTRA_REPO_ROOT"

echo "================================"
echo "Noctra foreground run"
echo "================================"
noctra_print_config
echo "Web: http://${NOCTRA_HEALTHCHECK_HOST}:${NOCTRA_PORT}"
echo "================================"

exec "$NOCTRA_PYTHON_BIN" -m uvicorn app.main:app --host "$NOCTRA_BIND_HOST" --port "$NOCTRA_PORT"
