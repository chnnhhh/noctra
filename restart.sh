#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/scripts/lib/noctra.sh"

noctra_load_env

cd "$NOCTRA_REPO_ROOT"

echo "================================"
echo "Restarting Noctra"
echo "================================"

# Stop if running
if noctra_is_running; then
    echo "Stopping Noctra..."
    noctra_stop_process
    sleep 1
fi

# Start Noctra
echo "Starting Noctra..."
echo "================================"
noctra_print_config
echo "================================"

if command -v setsid > /dev/null 2>&1; then
    setsid "$NOCTRA_PYTHON_BIN" -m uvicorn app.main:app --host "$NOCTRA_BIND_HOST" --port "$NOCTRA_PORT" > "$NOCTRA_LOG_DIR/server.log" 2>&1 < /dev/null &
else
    nohup "$NOCTRA_PYTHON_BIN" -m uvicorn app.main:app --host "$NOCTRA_BIND_HOST" --port "$NOCTRA_PORT" > "$NOCTRA_LOG_DIR/server.log" 2>&1 < /dev/null &
fi
echo $! > "$NOCTRA_PID_FILE"

if noctra_wait_for_health; then
    echo "================================"
    echo "✓ Noctra restarted successfully"
    echo "================================"
    echo "Health: $NOCTRA_HEALTHCHECK_URL"
    echo "Logs: tail -f $NOCTRA_LOG_DIR/server.log"
else
    echo "================================"
    echo "✗ Noctra failed to restart"
    echo "================================"
    echo "Last logs:"
    tail -20 "$NOCTRA_LOG_DIR/server.log" || true
    exit 1
fi
