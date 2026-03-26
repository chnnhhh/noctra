# Noctra

Noctra is a local/NAS-focused JAV file organizer. It scans a source directory, detects codes, previews the normalized target path, and only moves files after you confirm. The backend is FastAPI + SQLite, and the frontend is a no-build static shell powered by Alpine.js and plain JavaScript modules.

## Highlights

- Recursive scanning with automatic skipping of the output directory
- JAV code detection with filename cleanup and suffix normalization
- Preview-first workflow instead of silent background moving
- Clear scan states: `pending`, `unidentified`, `target exists`, `processed`
- Unified scan-page toolbar for filters, selection state, sorting, page size, and pagination
- Batch organize panel that appears immediately and stays visible after completion until manually collapsed
- History view for processed items
- Local run, Docker run, and NAS-oriented deployment flows

## Quick Start

### Local

```bash
cd /Users/liujiejian/git/noctra
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./start.sh
```

Default local profile values:

- `SOURCE_DIR=/Users/liujiejian/git/noctra/test_data/source`
- `DIST_DIR=/Users/liujiejian/git/noctra/test_data/dist`
- `DB_PATH=/Users/liujiejian/git/noctra/data/noctra.db`
- UI: `http://127.0.0.1:4020`

### Docker

```bash
docker run -d \
  --name noctra \
  -p 4020:8000 \
  -v /path/to/source:/source \
  -v /path/to/dist:/dist \
  -v /path/to/data:/app/data \
  -e SOURCE_DIR=/source \
  -e DIST_DIR=/dist \
  -e DB_PATH=/app/data/noctra.db \
  acyua/noctra:latest
```

## Typical Workflow

1. Open `http://127.0.0.1:4020`
2. Click `扫描目录`
3. Review detected codes and target-path previews
4. Filter, sort, paginate, and select pending rows from the scan toolbar
5. Run organize and monitor progress from the batch panel
6. Review completed records in the History view

## Repository Layout

```text
app/                    FastAPI backend
static/                 No-build frontend assets
  index.html            Page shell
  css/index.css         Styles
  js/*.js               State, rendering, and UI behavior
tests/                  Smoke tests and parser checks
test_data/              Example source/dist trees
scripts/                Start, stop, deploy helpers
config/profiles/        Local and NAS profile examples
docs/                   Runtime, deployment, and design notes
data/                   Local SQLite data directory
```

## Useful Commands

```bash
curl http://127.0.0.1:4020/api/health
./.venv/bin/python tests/test_local.py
```

## Related Docs

- [README (Chinese)](/Users/liujiejian/git/noctra/README.md)
- [Local startup](/Users/liujiejian/git/noctra/docs/local-startup.md)
- [Runtime workflow](/Users/liujiejian/git/noctra/docs/runtime-workflow.md)
- [NAS deployment](/Users/liujiejian/git/noctra/docs/nas-deployment.md)
