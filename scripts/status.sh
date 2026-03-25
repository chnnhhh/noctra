#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/noctra.sh"

noctra_load_env

echo "================================"
echo "Noctra status"
echo "================================"
noctra_print_config
echo "================================"

if noctra_is_running; then
    echo "Process: running (PID $(noctra_pid))"
else
    rm -f "$NOCTRA_PID_FILE"
    echo "Process: not running"
fi

if curl -fsS "$NOCTRA_HEALTHCHECK_URL" > /dev/null 2>&1; then
    echo "Health: ok"
else
    echo "Health: unavailable"
fi
