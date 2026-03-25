# Local Startup Guide

## Which scripts matter

For daily local development, only use these:

- `./start.sh`: foreground run. Best for development and debugging.
- `./scripts/start.sh`: background run.
- `./scripts/status.sh`: show the active profile, source/dist/db paths, process status, and health.
- `./scripts/stop.sh`: stop the background process.

You usually do **not** need these locally:

- `scripts/start-local.sh`: compatibility wrapper around `scripts/start.sh`.
- `scripts/run.sh`: implementation detail used by `./start.sh`.
- `scripts/start-noctra-nas.sh` / `scripts/stop-noctra-nas.sh`: NAS-profile wrappers.
- `scripts/deploy.sh`: deploy from this machine to NAS.
- `scripts/add-ssh-key.sh`, `scripts/add-to-docker-group.sh`, `scripts/fix-docker-registry.sh`: old one-off infra helpers, not part of normal local startup.

## Local defaults

If you do nothing, the local profile uses repo-relative defaults:

- source: `test_data/source`
- dist: `test_data/dist`
- database: `data/noctra.db`
- host: `127.0.0.1`
- port: `8888`

That is enough to boot the project on this machine.

## First-time setup

```bash
cd /Users/liujiejian/git/noctra
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

The scripts will auto-detect `.venv/bin/python` if it exists.

## Start locally

Foreground:

```bash
./start.sh
```

Background:

```bash
NOCTRA_PROFILE=local ./scripts/start.sh
NOCTRA_PROFILE=local ./scripts/status.sh
NOCTRA_PROFILE=local ./scripts/stop.sh
```

Health check:

```bash
curl http://127.0.0.1:8888/api/health
```

`/api/health` returns the current `profile`, `source_dir`, `dist_dir`, and `db_path`. Check that first if behavior looks wrong.

## When you need custom paths

Only create a local profile file if you want to override the defaults:

```bash
cp config/profiles/local.env.example config/profiles/local.env
```

Typical fields to change:

- `NOCTRA_SOURCE_DIR`
- `NOCTRA_DIST_DIR`
- `NOCTRA_DATA_DIR`
- `NOCTRA_DB_PATH`
- `NOCTRA_PORT`
- `NOCTRA_PYTHON_BIN`

Example:

```bash
NOCTRA_SOURCE_DIR=/path/to/ChaosJAV
NOCTRA_DIST_DIR=/path/to/OrderedJAV
NOCTRA_DATA_DIR="$NOCTRA_REPO_ROOT/data-local"
NOCTRA_DB_PATH="$NOCTRA_DATA_DIR/noctra.db"
NOCTRA_PORT=8890
```

## Recommended local workflow

1. Use `./start.sh` when actively debugging code.
2. Use `./scripts/start.sh` only when you need the service in the background.
3. Run `./scripts/status.sh` before testing to confirm the service is using the expected source/dist/db paths.
4. Keep local-only overrides in `config/profiles/local.env`. Do not hardcode machine paths back into scripts or code.
