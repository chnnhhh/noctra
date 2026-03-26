#!/usr/bin/env bash

set -euo pipefail

noctra_repo_root() {
    cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd
}

export NOCTRA_REPO_ROOT="${NOCTRA_REPO_ROOT:-$(noctra_repo_root)}"
export NOCTRA_PROFILE="${NOCTRA_PROFILE:-local}"
export NOCTRA_PROFILE_FILE="${NOCTRA_PROFILE_FILE:-$NOCTRA_REPO_ROOT/config/profiles/${NOCTRA_PROFILE}.env}"

noctra_load_env() {
    if [ -f "$NOCTRA_PROFILE_FILE" ]; then
        set -a
        # shellcheck disable=SC1090
        source "$NOCTRA_PROFILE_FILE"
        set +a
    fi

    export NOCTRA_BIND_HOST="${NOCTRA_BIND_HOST:-127.0.0.1}"
    export NOCTRA_HEALTHCHECK_HOST="${NOCTRA_HEALTHCHECK_HOST:-127.0.0.1}"
    export NOCTRA_PORT="${NOCTRA_PORT:-4020}"
    export NOCTRA_SOURCE_DIR="${NOCTRA_SOURCE_DIR:-$NOCTRA_REPO_ROOT/test_data/source}"
    export NOCTRA_DIST_DIR="${NOCTRA_DIST_DIR:-$NOCTRA_REPO_ROOT/test_data/dist}"
    export NOCTRA_DATA_DIR="${NOCTRA_DATA_DIR:-$NOCTRA_REPO_ROOT/data}"
    export NOCTRA_LOG_DIR="${NOCTRA_LOG_DIR:-$NOCTRA_REPO_ROOT/logs}"
    export NOCTRA_PID_FILE="${NOCTRA_PID_FILE:-$NOCTRA_LOG_DIR/noctra.pid}"
    export NOCTRA_DB_PATH="${NOCTRA_DB_PATH:-$NOCTRA_DATA_DIR/noctra.db}"
    export NOCTRA_PYTHON_BASE_IMAGE="${NOCTRA_PYTHON_BASE_IMAGE:-python:3.11-slim}"
    export NOCTRA_PIP_INDEX_URL="${NOCTRA_PIP_INDEX_URL:-}"
    export NOCTRA_PIP_TRUSTED_HOST="${NOCTRA_PIP_TRUSTED_HOST:-}"
    export NOCTRA_DOCKER_IMAGE="${NOCTRA_DOCKER_IMAGE:-acyua/noctra:latest}"
    export NOCTRA_DOCKER_PULL_POLICY="${NOCTRA_DOCKER_PULL_POLICY:-always}"
    export NOCTRA_WATCHTOWER_IMAGE="${NOCTRA_WATCHTOWER_IMAGE:-containrrr/watchtower:latest}"
    export NOCTRA_WATCHTOWER_INTERVAL="${NOCTRA_WATCHTOWER_INTERVAL:-86400}"
    export NOCTRA_WATCHTOWER_HTTP_PROXY="${NOCTRA_WATCHTOWER_HTTP_PROXY:-}"
    export NOCTRA_WATCHTOWER_HTTPS_PROXY="${NOCTRA_WATCHTOWER_HTTPS_PROXY:-}"
    export NOCTRA_WATCHTOWER_NO_PROXY="${NOCTRA_WATCHTOWER_NO_PROXY:-}"
    export NOCTRA_TIMEZONE="${NOCTRA_TIMEZONE:-Asia/Shanghai}"
    export NOCTRA_HEALTHCHECK_URL="${NOCTRA_HEALTHCHECK_URL:-http://${NOCTRA_HEALTHCHECK_HOST}:${NOCTRA_PORT}/api/health}"
    export NOCTRA_REMOTE_HOST="${NOCTRA_REMOTE_HOST:-}"
    export NOCTRA_REMOTE_PATH="${NOCTRA_REMOTE_PATH:-}"
    export NOCTRA_REMOTE_PYTHON_BIN="${NOCTRA_REMOTE_PYTHON_BIN:-python3}"
    export NOCTRA_REMOTE_PROFILE="${NOCTRA_REMOTE_PROFILE:-$NOCTRA_PROFILE}"
    export NOCTRA_REMOTE_PROFILE_FILE="${NOCTRA_REMOTE_PROFILE_FILE:-$NOCTRA_REMOTE_PATH/config/profiles/${NOCTRA_REMOTE_PROFILE}.env}"
    export NOCTRA_REMOTE_DEPLOY_MODE="${NOCTRA_REMOTE_DEPLOY_MODE:-python}"
    export NOCTRA_REMOTE_COMPOSE_FILE="${NOCTRA_REMOTE_COMPOSE_FILE:-docker-compose.nas.yml}"
    export NOCTRA_REMOTE_DOCKER_PROJECT_NAME="${NOCTRA_REMOTE_DOCKER_PROJECT_NAME:-noctra}"
    export NOCTRA_SKIP_ENSURE_DIRS="${NOCTRA_SKIP_ENSURE_DIRS:-0}"
    export NOCTRA_SYNC_PROFILE="${NOCTRA_SYNC_PROFILE:-1}"

    if [ "$NOCTRA_SKIP_ENSURE_DIRS" != "1" ]; then
        mkdir -p "$NOCTRA_DATA_DIR" "$NOCTRA_LOG_DIR" "$(dirname "$NOCTRA_DB_PATH")"
    fi

    export SOURCE_DIR="$NOCTRA_SOURCE_DIR"
    export DIST_DIR="$NOCTRA_DIST_DIR"
    export DB_PATH="$NOCTRA_DB_PATH"
    export PYTHONPATH="$NOCTRA_REPO_ROOT${PYTHONPATH:+:$PYTHONPATH}"

    if [ -n "${NOCTRA_PYTHON_BIN:-}" ]; then
        export NOCTRA_PYTHON_BIN
    elif [ -x "$NOCTRA_REPO_ROOT/.venv/bin/python" ]; then
        export NOCTRA_PYTHON_BIN="$NOCTRA_REPO_ROOT/.venv/bin/python"
    elif [ -x "$NOCTRA_REPO_ROOT/venv/bin/python" ]; then
        export NOCTRA_PYTHON_BIN="$NOCTRA_REPO_ROOT/venv/bin/python"
    else
        export NOCTRA_PYTHON_BIN="$(command -v python3)"
    fi
}

noctra_print_config() {
    local profile_state
    if [ -f "$NOCTRA_PROFILE_FILE" ]; then
        profile_state="loaded"
    else
        profile_state="missing (using defaults)"
    fi

    cat <<EOF
Profile: $NOCTRA_PROFILE
Profile file: $NOCTRA_PROFILE_FILE [$profile_state]
Repo root: $NOCTRA_REPO_ROOT
Python: $NOCTRA_PYTHON_BIN
Host: $NOCTRA_BIND_HOST
Port: $NOCTRA_PORT
Source: $NOCTRA_SOURCE_DIR
Dist: $NOCTRA_DIST_DIR
DB: $NOCTRA_DB_PATH
PID file: $NOCTRA_PID_FILE
Log dir: $NOCTRA_LOG_DIR
EOF
}

noctra_require_remote() {
    if [ -z "$NOCTRA_REMOTE_HOST" ] || [ -z "$NOCTRA_REMOTE_PATH" ]; then
        echo "NOCTRA_REMOTE_HOST and NOCTRA_REMOTE_PATH must be set for deployment." >&2
        exit 1
    fi
}

noctra_pid() {
    if [ -f "$NOCTRA_PID_FILE" ]; then
        cat "$NOCTRA_PID_FILE"
    fi
}

noctra_is_running() {
    local pid
    pid="$(noctra_pid || true)"
    if [ -z "$pid" ]; then
        return 1
    fi
    ps -p "$pid" > /dev/null 2>&1
}

noctra_wait_for_health() {
    local attempt
    for attempt in $(seq 1 20); do
        if curl -fsS "$NOCTRA_HEALTHCHECK_URL" > /dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    return 1
}

noctra_stop_process() {
    local pid
    pid="$(noctra_pid || true)"
    if [ -z "$pid" ]; then
        return 0
    fi

    if ps -p "$pid" > /dev/null 2>&1; then
        kill "$pid" 2>/dev/null || true
        sleep 2
        if ps -p "$pid" > /dev/null 2>&1; then
            kill -9 "$pid" 2>/dev/null || true
        fi
    fi

    rm -f "$NOCTRA_PID_FILE"
}
