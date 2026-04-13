#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
export NOCTRA_PROFILE="${1:-${NOCTRA_PROFILE:-nas}}"
export NOCTRA_SKIP_ENSURE_DIRS=1

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

ssh "$NOCTRA_REMOTE_HOST" bash <<EOF
set -euo pipefail
cd '$NOCTRA_REMOTE_PATH'
source './scripts/lib/noctra.sh'
export NOCTRA_PROFILE='$NOCTRA_REMOTE_PROFILE'
export NOCTRA_PROFILE_FILE='$REMOTE_PROFILE_FILE'
noctra_load_env
eval "\$("\$NOCTRA_REMOTE_PYTHON_BIN" ./scripts/resolve_nas_mounts.py \
    --source-dir "\$NOCTRA_SOURCE_DIR" \
    --dist-dir "\$NOCTRA_DIST_DIR" \
    --compose-file "\$NOCTRA_REMOTE_COMPOSE_FILE" \
    --mount-mode "\$NOCTRA_REMOTE_MOUNT_MODE" \
    \${NOCTRA_MEDIA_BIND_ROOT:+--media-bind-root "\$NOCTRA_MEDIA_BIND_ROOT"})"
echo "Selected mount mode: \$NOCTRA_SELECTED_MOUNT_MODE"
echo "Selected compose file: \$NOCTRA_SELECTED_COMPOSE_FILE"
if [ -n "\${NOCTRA_MEDIA_BIND_ROOT:-}" ]; then
    echo "Selected media bind root: \$NOCTRA_MEDIA_BIND_ROOT"
fi
LEGACY_UVICORN_PATTERN="\$NOCTRA_REMOTE_PATH/.venv/bin/uvicorn app.main:app"

if [ "\$NOCTRA_REMOTE_DEPLOY_MODE" = "docker" ]; then
    command -v docker >/dev/null 2>&1 || {
        echo "Docker is required for docker deploy mode." >&2
        exit 1
    }

    if pgrep -af "\$LEGACY_UVICORN_PATTERN" >/dev/null 2>&1; then
        echo "Stopping legacy uvicorn process before switching to Docker..."
        pkill -f "\$LEGACY_UVICORN_PATTERN" || true
        sleep 2
    fi

    docker compose -p "\$NOCTRA_REMOTE_DOCKER_PROJECT_NAME" -f "\$NOCTRA_SELECTED_COMPOSE_FILE" up -d --build
elif [ "\$NOCTRA_REMOTE_DEPLOY_MODE" = "docker-image" ]; then
    command -v docker >/dev/null 2>&1 || {
        echo "Docker is required for docker-image deploy mode." >&2
        exit 1
    }

    if pgrep -af "\$LEGACY_UVICORN_PATTERN" >/dev/null 2>&1; then
        echo "Stopping legacy uvicorn process before switching to Docker..."
        pkill -f "\$LEGACY_UVICORN_PATTERN" || true
        sleep 2
    fi

    docker compose -p "\$NOCTRA_REMOTE_DOCKER_PROJECT_NAME" -f "\$NOCTRA_SELECTED_COMPOSE_FILE" pull
    docker compose -p "\$NOCTRA_REMOTE_DOCKER_PROJECT_NAME" -f "\$NOCTRA_SELECTED_COMPOSE_FILE" up -d
else
    if [ ! -x '.venv/bin/python' ]; then
        '$NOCTRA_REMOTE_PYTHON_BIN' -m venv .venv
    fi
    .venv/bin/pip install -r requirements.txt
    NOCTRA_PROFILE='$NOCTRA_REMOTE_PROFILE' NOCTRA_PROFILE_FILE='$REMOTE_PROFILE_FILE' ./scripts/start.sh
fi
EOF

echo "✓ Deployment finished"
