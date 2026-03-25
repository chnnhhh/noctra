# Repository Guidelines

## Project Structure & Module Organization
`app/` contains the application code: `main.py` defines the FastAPI routes and SQLite bootstrap, `scanner.py` handles filename detection, `organizer.py` handles target path generation and moves, and `models.py` holds Pydantic schemas. `static/index.html` is the no-build frontend. `tests/` contains automated checks and local smoke scripts. `test_data/` provides sample source/dist trees plus a SQLite fixture. Use `scripts/` and root `start.sh` for local or NAS-oriented startup helpers, and keep design/deployment notes in `docs/`.

## Build, Test, and Development Commands
`python3 -m pip install -r requirements.txt` installs runtime dependencies.

`python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8888` starts the app locally; set `SOURCE_DIR`, `DIST_DIR`, and `DB_PATH` first.

`./start.sh` starts against `test_data/` defaults and writes logs to `logs/server.log`.

`docker build -t noctra:latest .` builds the container image.

`docker compose up --build` starts the containerized stack from `docker-compose.yml`.

`python3 tests/test_local.py` runs the script-based smoke checks.

`python3 -m pytest tests/test_scanner.py -v` runs the pytest suite; install `pytest` in your virtualenv first because it is not pinned in `requirements.txt`.

## Coding Style & Naming Conventions
Use 4-space indentation, `snake_case` for functions, modules, and variables, and `PascalCase` for classes such as `JAVScanner`. Preserve existing type hints and short docstrings, especially around filesystem and API behavior. Keep new modules in `app/` focused on one responsibility. No formatter or linter is configured in-repo, so match the current style and keep imports grouped as standard library, third-party, then local.

## Testing Guidelines
Name new tests `test_*.py`. Extend `tests/test_scanner.py` when changing parsing or skip logic, and add organizer or API coverage when touching move behavior or routes. There is no enforced coverage gate, but every PR should include at least one automated check plus manual verification for file-moving flows.

## Commit & Pull Request Guidelines
Recent history mostly uses short Conventional Commit subjects like `feat: add NAS deployment scripts and docs` and `fix: improve filename handling and UI optimizations`; prefer `feat:`, `fix:`, or `docs:` with an imperative summary. PRs should describe user-visible behavior, list the commands you ran, note any env var or port changes, and include screenshots for changes to `static/index.html`.

## Configuration Notes
Core runtime settings come from `SOURCE_DIR`, `DIST_DIR`, and `DB_PATH`. Do not commit personal absolute paths, real media files, or generated logs/databases. If you change ports, update `start.sh`, `Dockerfile`, and `docker-compose.yml` together, because local and container defaults currently differ (`8888` vs `8000`).
