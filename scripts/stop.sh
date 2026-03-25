#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/noctra.sh"

noctra_load_env

if noctra_is_running; then
    echo "Stopping Noctra..."
    noctra_stop_process
    echo "✓ Noctra stopped"
else
    echo "No running Noctra process found for profile: $NOCTRA_PROFILE"
    rm -f "$NOCTRA_PID_FILE"
fi
