# Runtime Workflow

## Goals

- Keep one codebase for every environment.
- Change behavior only through environment variables or profile files.
- Make it obvious which source, dist, and database paths a running service is using.

## Profiles

All process scripts load a profile file from `config/profiles/<profile>.env` when it exists.

- `local`: defaults to repo-relative paths and works without a profile file.
- `nas`: intended for NAS deployment and remote restart.

Example files:

- `config/profiles/local.env.example`
- `config/profiles/nas.env.example`

Copy them to untracked files when you need overrides:

```bash
cp config/profiles/local.env.example config/profiles/local.env
cp config/profiles/nas.env.example config/profiles/nas.env
```

For the concrete local startup checklist and script map, see `docs/local-startup.md`.

## Local Workflow

Foreground run:

```bash
./start.sh
```

Background run:

```bash
NOCTRA_PROFILE=local ./scripts/start.sh
./scripts/status.sh
./scripts/stop.sh
```

## NAS Deployment

Set `NOCTRA_REMOTE_HOST` and `NOCTRA_REMOTE_PATH` in `config/profiles/nas.env`, then deploy from this machine:

```bash
./scripts/deploy.sh nas
```

The deploy script syncs the repo, optionally syncs the selected profile file, installs Python dependencies on the remote host, and restarts the service there with the same scripts.

## Debugging

`GET /api/health` now returns:

- `profile`
- `source_dir`
- `dist_dir`
- `db_path`
- `cwd`

That should be your first check whenever behavior and filesystem state do not line up.
