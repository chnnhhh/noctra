#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export NOCTRA_PROFILE="${NOCTRA_PROFILE:-nas}"

exec "$SCRIPT_DIR/stop.sh" "$@"
