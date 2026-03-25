#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export NOCTRA_PROFILE="${1:-${NOCTRA_PROFILE:-nas}}"

# shellcheck disable=SC1091
source "$SCRIPT_DIR/lib/noctra.sh"

noctra_load_env
noctra_require_remote

REMOTE_PROFILE_FILE="$NOCTRA_REMOTE_PROFILE_FILE"

echo "================================"
echo "Deploying Noctra"
echo "================================"
echo "Profile: $NOCTRA_PROFILE"
echo "Remote host: $NOCTRA_REMOTE_HOST"
echo "Remote path: $NOCTRA_REMOTE_PATH"
echo "Remote profile file: $REMOTE_PROFILE_FILE"
echo "================================"

ssh "$NOCTRA_REMOTE_HOST" "mkdir -p '$NOCTRA_REMOTE_PATH'"

rsync -az --delete \
    --exclude '.git/' \
    --exclude '.venv/' \
    --exclude 'venv/' \
    --exclude '__pycache__/' \
    --exclude '.pytest_cache/' \
    --exclude '.mypy_cache/' \
    --exclude '.ruff_cache/' \
    --exclude 'logs/' \
    --exclude 'data/' \
    --exclude 'config/profiles/*.env' \
    --exclude '*.pyc' \
    --exclude '.DS_Store' \
    --exclude 'noctra.db' \
    "$NOCTRA_REPO_ROOT/" "$NOCTRA_REMOTE_HOST:$NOCTRA_REMOTE_PATH/"

if [ "$NOCTRA_SYNC_PROFILE" = "1" ] && [ -f "$NOCTRA_PROFILE_FILE" ]; then
    ssh "$NOCTRA_REMOTE_HOST" "mkdir -p '$(dirname "$REMOTE_PROFILE_FILE")'"
    scp "$NOCTRA_PROFILE_FILE" "$NOCTRA_REMOTE_HOST:$REMOTE_PROFILE_FILE"
fi

ssh "$NOCTRA_REMOTE_HOST" "
set -euo pipefail
cd '$NOCTRA_REMOTE_PATH'
if [ ! -x '.venv/bin/python' ]; then
    '$NOCTRA_REMOTE_PYTHON_BIN' -m venv .venv
fi
.venv/bin/pip install -r requirements.txt
NOCTRA_PROFILE='$NOCTRA_REMOTE_PROFILE' NOCTRA_PROFILE_FILE='$REMOTE_PROFILE_FILE' ./scripts/start.sh
"

echo "✓ Deployment finished"
