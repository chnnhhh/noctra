# Scrape Feedback And Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Noctra's scrape page show real progress, source-aware stage copy, readable persisted failure reasons, and a single unified task panel for both single-file and batch scrape.

**Architecture:** Keep the existing scrape pipeline (`crawl -> parse -> write NFO -> download poster`) but refactor it into a stage-aware runner that records structured progress events. Persist the latest scrape attempt details on `files`, add one in-memory scrape-job registry for live polling, and update the frontend to treat single-file and batch scrape as one job flow instead of two ad hoc code paths.

**Tech Stack:** Python 3.11, FastAPI, aiosqlite, SQLite, Alpine.js, vanilla JS, existing no-build static frontend, pytest

**Spec:** `docs/superpowers/specs/2026-03-27-scrape-feedback-observability-design.md`

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `app/models.py` | Expand scrape list models and add scrape-job API models | Modify |
| `app/main.py` | Backfill new scrape columns, expand `/api/scrape`, add scrape-job routes | Modify |
| `app/scraper.py` | Emit stages, sources, logs, readable failures, and persist latest-attempt details | Modify |
| `app/scrape_jobs.py` | Hold in-memory scrape job registry and cooperative job runner | Create |
| `tests/test_db_init.py` | Verify startup schema backfill adds new scrape columns | Modify |
| `tests/test_scraper.py` | Verify stage recording, failure mapping, and latest-attempt persistence | Modify |
| `tests/test_api/test_scrape_endpoints.py` | Verify expanded `/api/scrape` payload and legacy scrape compatibility | Modify |
| `tests/test_api/test_scrape_jobs.py` | Verify scrape-job create/get/cancel routes | Create |
| `tests/test_e2e/test_scraping_flow.py` | Verify persisted scrape detail fields and active job payloads | Modify |
| `static/js/scrape.js` | Replace sync scrape helpers with job-oriented API methods | Modify |
| `static/js/state.js` | Store live scrape-job state and computed UI helpers | Modify |
| `static/js/render.js` | Render readable failure text, source labels, stage labels, and scrape icon | Modify |
| `static/js/features.js` | Remove duplicated scrape methods and add job polling / refresh recovery | Modify |
| `static/index.html` | Show real scrape panel data and richer failure modal sections | Modify |
| `static/css/index.css` | Style panel logs, stage/source metadata, and failure detail blocks | Modify |
| `docs/testing/scraping-e2e-checklist.md` | Update manual verification steps for the new observable flow | Modify |

## Task 1: Extend startup schema and API models for persisted scrape details

**Files:**
- Modify: `app/models.py`
- Modify: `app/main.py`
- Modify: `tests/test_db_init.py`

- [ ] **Step 1: Add a failing startup-schema test for the new scrape columns**

Append this test to `tests/test_db_init.py`:

```python
def test_init_db_backfills_scrape_observability_columns(tmp_path):
    db_path = tmp_path / "noctra.db"

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_path TEXT UNIQUE NOT NULL,
            identified_code TEXT,
            target_path TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            file_size INTEGER NOT NULL,
            file_mtime REAL NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            scrape_status TEXT DEFAULT 'pending',
            last_scrape_at TEXT
        )
        """
    )
    conn.commit()
    conn.close()

    with patch.dict("os.environ", {"DB_PATH": str(db_path)}):
        import app.main as main
        asyncio.run(main.init_db())

    conn = sqlite3.connect(db_path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(files)").fetchall()}
    conn.close()

    assert "scrape_started_at" in columns
    assert "scrape_finished_at" in columns
    assert "scrape_stage" in columns
    assert "scrape_source" in columns
    assert "scrape_error" in columns
    assert "scrape_error_user_message" in columns
    assert "scrape_logs" in columns
```

- [ ] **Step 2: Run the schema test and confirm it fails**

Run:

```bash
python3 -m pytest tests/test_db_init.py::test_init_db_backfills_scrape_observability_columns -v
```

Expected:

```text
FAILED tests/test_db_init.py::test_init_db_backfills_scrape_observability_columns
E   AssertionError: assert 'scrape_started_at' in ...
```

- [ ] **Step 3: Expand startup schema backfill in `app/main.py`**

Update `ensure_scrape_schema()` in `app/main.py` to add the new columns:

```python
    if 'scrape_started_at' not in existing_columns:
        await db.execute("ALTER TABLE files ADD COLUMN scrape_started_at TEXT")

    if 'scrape_finished_at' not in existing_columns:
        await db.execute("ALTER TABLE files ADD COLUMN scrape_finished_at TEXT")

    if 'scrape_stage' not in existing_columns:
        await db.execute("ALTER TABLE files ADD COLUMN scrape_stage TEXT")

    if 'scrape_source' not in existing_columns:
        await db.execute("ALTER TABLE files ADD COLUMN scrape_source TEXT")

    if 'scrape_error' not in existing_columns:
        await db.execute("ALTER TABLE files ADD COLUMN scrape_error TEXT")

    if 'scrape_error_user_message' not in existing_columns:
        await db.execute("ALTER TABLE files ADD COLUMN scrape_error_user_message TEXT")

    if 'scrape_logs' not in existing_columns:
        await db.execute("ALTER TABLE files ADD COLUMN scrape_logs TEXT")
```

- [ ] **Step 4: Expand scrape API models in `app/models.py`**

Replace the current scrape section with these model additions:

```python
from pydantic import BaseModel, Field


class ScrapeLogEntry(BaseModel):
    at: str
    level: str
    stage: str
    source: Optional[str] = None
    message: str


class ScrapeListItem(BaseModel):
    file_id: int
    code: str
    target_path: str
    original_path: str = ""
    status: str = "processed"
    scrape_status: str
    last_scrape_at: Optional[str] = None
    scrape_started_at: Optional[str] = None
    scrape_finished_at: Optional[str] = None
    scrape_stage: Optional[str] = None
    scrape_source: Optional[str] = None
    scrape_error: Optional[str] = None
    scrape_error_user_message: Optional[str] = None
    scrape_logs: list[ScrapeLogEntry] = Field(default_factory=list)


class ScrapeJobCreateRequest(BaseModel):
    file_ids: list[int]


class ScrapeJobItem(BaseModel):
    id: int
    code: Optional[str] = None
    target_path: Optional[str] = None
    status: str
    stage: Optional[str] = None
    source: Optional[str] = None
    user_message: Optional[str] = None
    technical_error: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class ScrapeJobSnapshot(BaseModel):
    id: str
    status: str
    total: int
    processed: int
    succeeded: int
    failed: int
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    current_file_id: Optional[int] = None
    current_file_code: Optional[str] = None
    current_stage: Optional[str] = None
    current_source: Optional[str] = None
    recent_logs: list[ScrapeLogEntry] = Field(default_factory=list)
    items: list[ScrapeJobItem] = Field(default_factory=list)


class ScrapeJobCancelResult(BaseModel):
    id: str
    status: str
    message: str
```

- [ ] **Step 5: Re-run the schema test**

Run:

```bash
python3 -m pytest tests/test_db_init.py::test_init_db_backfills_scrape_observability_columns -v
```

Expected:

```text
PASSED tests/test_db_init.py::test_init_db_backfills_scrape_observability_columns
```

- [ ] **Step 6: Commit the schema and model groundwork**

```bash
git add app/models.py app/main.py tests/test_db_init.py
git commit -m "feat: add persisted scrape observability fields"
```

## Task 2: Refactor `ScraperScheduler` into a stage-aware, source-aware runner

**Files:**
- Modify: `app/scraper.py`
- Modify: `tests/test_scraper.py`

- [ ] **Step 1: Add a failing stage-and-persistence test**

Append this test to `tests/test_scraper.py`:

```python
@pytest.mark.asyncio
async def test_scrape_single_records_stage_source_and_logs_on_success():
    record = _make_file_record(code="ALDN-480")
    metadata = _make_metadata(code="ALDN-480")

    scheduler = ScraperScheduler()
    scheduler._get_file = AsyncMock(return_value=record)

    observed = []

    def recorder(event):
        observed.append(event)

    mock_crawler = AsyncMock()
    mock_crawler.crawl = AsyncMock(return_value=metadata)

    with (
        patch("app.scraper.JavDBCrawler", return_value=mock_crawler),
        patch("app.scraper.write_nfo"),
        patch("app.scraper.download_poster", new_callable=AsyncMock),
        patch.object(scheduler, "_persist_attempt_update", new_callable=AsyncMock) as mock_persist,
        patch("app.scraper.aiosqlite") as mock_aiosqlite,
    ):
        mock_conn_cm = AsyncMock()
        mock_conn = AsyncMock()
        mock_conn_cm.__aenter__.return_value = mock_conn
        mock_aiosqlite.connect.return_value = mock_conn_cm

        result = await scheduler.scrape_single(1, progress_callback=recorder)

    assert result.success is True
    assert any(event["stage"] == "querying_source" for event in observed)
    assert any(event["stage"] == "writing_nfo" for event in observed)
    assert any(event["source"] == "javdb" for event in observed)
    assert mock_persist.await_count >= 3
```

- [ ] **Step 2: Add a failing readable-failure test**

Append this test to `tests/test_scraper.py`:

```python
@pytest.mark.asyncio
async def test_scrape_single_maps_poster_failure_to_user_message():
    record = _make_file_record(code="EBOD-829")
    metadata = _make_metadata(code="EBOD-829")

    scheduler = ScraperScheduler()
    scheduler._get_file = AsyncMock(return_value=record)

    mock_crawler = AsyncMock()
    mock_crawler.crawl = AsyncMock(return_value=metadata)

    with (
        patch("app.scraper.JavDBCrawler", return_value=mock_crawler),
        patch("app.scraper.write_nfo"),
        patch("app.scraper.download_poster", new_callable=AsyncMock, side_effect=Exception("poster timeout")),
        patch.object(scheduler, "_persist_attempt_update", new_callable=AsyncMock) as mock_persist,
    ):
        result = await scheduler.scrape_single(1)

    assert result.success is False
    assert result.user_message == "NFO 已生成，但封面图片下载失败"
    assert result.stage == "downloading_poster"
    persisted = mock_persist.await_args_list[-1].kwargs
    assert persisted["scrape_error_user_message"] == "NFO 已生成，但封面图片下载失败"
```

- [ ] **Step 3: Run the new scraper tests and confirm they fail**

Run:

```bash
python3 -m pytest \
  tests/test_scraper.py::test_scrape_single_records_stage_source_and_logs_on_success \
  tests/test_scraper.py::test_scrape_single_maps_poster_failure_to_user_message \
  -v
```

Expected:

```text
FAILED ... got an unexpected keyword argument 'progress_callback'
FAILED ... 'ScrapeResponse' object has no attribute 'user_message'
```

- [ ] **Step 4: Add richer scrape response data in `app/models.py`**

Extend `ScrapeResponse` to carry stage/source/readable failure text:

```python
class ScrapeResponse(BaseModel):
    success: bool
    code: Optional[str] = None
    error: Optional[str] = None
    user_message: Optional[str] = None
    stage: Optional[str] = None
    source: Optional[str] = None
    logs: list[ScrapeLogEntry] = Field(default_factory=list)
```

- [ ] **Step 5: Add stage, source, and log helpers in `app/scraper.py`**

Add these helpers near the top of `app/scraper.py`:

```python
MAX_SCRAPE_LOGS = 30
SCRAPE_SOURCE_JAVDB = "javdb"


def _utcnow_iso() -> str:
    return datetime.now().isoformat()


def _source_label(source: str | None) -> str:
    mapping = {
        "javdb": "JavDB",
        "javtrailers": "JavTrailers",
    }
    return mapping.get(source or "", source or "")


def _map_failure(stage: str, source: str | None, technical_error: str | None) -> str:
    source_label = _source_label(source)
    text = (technical_error or "").lower()
    if stage == "querying_source":
        if "not found" in text or "failed to crawl metadata" in text:
            return f"在 {source_label} 没有找到这个番号的元数据"
        return f"连接 {source_label} 失败，请稍后重试"
    if stage == "parsing_metadata":
        return f"{source_label} 返回了页面，但元数据解析失败"
    if stage == "writing_nfo":
        return "元数据已获取，但写入 NFO 文件失败"
    if stage == "downloading_poster":
        return "NFO 已生成，但封面图片下载失败"
    if stage == "validating":
        return "文件信息不完整，无法开始刮削"
    return "刮削过程中发生未知错误"
```

- [ ] **Step 6: Add a persistence helper in `app/scraper.py`**

Add this method on `ScraperScheduler`:

```python
    async def _persist_attempt_update(self, file_id: int, **fields) -> None:
        allowed = {
            "scrape_status",
            "last_scrape_at",
            "scrape_started_at",
            "scrape_finished_at",
            "scrape_stage",
            "scrape_source",
            "scrape_error",
            "scrape_error_user_message",
            "scrape_logs",
        }
        payload = {key: value for key, value in fields.items() if key in allowed}
        if not payload:
            return

        assignments = ", ".join(f"{key} = ?" for key in payload)
        values = list(payload.values()) + [file_id]

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                f"UPDATE files SET {assignments} WHERE id = ?",
                tuple(values),
            )
            await db.commit()
```

- [ ] **Step 7: Refactor `scrape_single()` to emit recorder events**

Replace the current function shape with this signature and event pattern:

```python
    async def scrape_single(self, file_id: int, progress_callback=None) -> ScrapeResponse:
        logs: list[dict] = []

        async def emit(stage: str, message: str, *, source: str | None = None, level: str = "info", persist: bool = True):
            event = {
                "at": _utcnow_iso(),
                "level": level,
                "stage": stage,
                "source": source,
                "message": message,
            }
            logs.append(event)
            if len(logs) > MAX_SCRAPE_LOGS:
                del logs[:-MAX_SCRAPE_LOGS]
            if progress_callback:
                progress_callback(event)
            if persist:
                await self._persist_attempt_update(
                    file_id,
                    scrape_stage=stage,
                    scrape_source=source,
                    scrape_logs=json.dumps(logs, ensure_ascii=False),
                )
```

Then use it in order:

```python
        await self._persist_attempt_update(
            file_id,
            scrape_status="pending",
            scrape_started_at=_utcnow_iso(),
            scrape_finished_at=None,
            scrape_error=None,
            scrape_error_user_message=None,
        )
        await emit("validating", "正在检查文件信息")
        await emit("querying_source", "正在查询 JavDB", source=SCRAPE_SOURCE_JAVDB)
        metadata = await crawler.crawl(code)
        await emit("parsing_metadata", "详情页读取成功，正在解析元数据", source=SCRAPE_SOURCE_JAVDB)
        await emit("writing_nfo", "元数据解析成功，正在生成 NFO 文件")
        await emit("downloading_poster", "NFO 已生成，正在下载封面图片")
        await emit("finalizing", "正在保存刮削结果")
```

- [ ] **Step 8: Persist success and failure details through one path**

On success, end with:

```python
        finished_at = _utcnow_iso()
        await self._persist_attempt_update(
            file_id,
            scrape_status="success",
            last_scrape_at=finished_at,
            scrape_finished_at=finished_at,
            scrape_stage="success",
            scrape_source=SCRAPE_SOURCE_JAVDB,
            scrape_error=None,
            scrape_error_user_message=None,
            scrape_logs=json.dumps(logs, ensure_ascii=False),
        )
        return ScrapeResponse(
            success=True,
            code=code,
            user_message="刮削完成",
            stage="success",
            source=SCRAPE_SOURCE_JAVDB,
            logs=logs,
        )
```

On failure, end with:

```python
        user_message = _map_failure(current_stage, current_source, str(exc))
        finished_at = _utcnow_iso()
        await self._persist_attempt_update(
            file_id,
            scrape_status="failed",
            last_scrape_at=finished_at,
            scrape_finished_at=finished_at,
            scrape_stage=current_stage,
            scrape_source=current_source,
            scrape_error=str(exc),
            scrape_error_user_message=user_message,
            scrape_logs=json.dumps(logs, ensure_ascii=False),
        )
        return ScrapeResponse(
            success=False,
            error=str(exc),
            user_message=user_message,
            stage=current_stage,
            source=current_source,
            logs=logs,
        )
```

- [ ] **Step 9: Run the focused scraper tests**

Run:

```bash
python3 -m pytest tests/test_scraper.py -v
```

Expected:

```text
PASSED tests/test_scraper.py::test_scrape_single_records_stage_source_and_logs_on_success
PASSED tests/test_scraper.py::test_scrape_single_maps_poster_failure_to_user_message
...
```

- [ ] **Step 10: Commit the observable runner refactor**

```bash
git add app/models.py app/scraper.py tests/test_scraper.py
git commit -m "feat: add stage-aware scrape progress recording"
```

## Task 3: Add scrape-job registry and live polling routes

**Files:**
- Create: `app/scrape_jobs.py`
- Modify: `app/main.py`
- Modify: `tests/test_api/test_scrape_endpoints.py`
- Create: `tests/test_api/test_scrape_jobs.py`

- [ ] **Step 1: Add a failing create-job API test**

Create `tests/test_api/test_scrape_jobs.py` with:

```python
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


@patch("app.main.create_scrape_job")
@patch("app.main.get_scrape_candidates_for_job", new_callable=AsyncMock)
def test_post_scrape_jobs_returns_job_snapshot(mock_candidates, mock_create_job):
    from app.main import app

    mock_candidates.return_value = [
        {"id": 1, "identified_code": "ALDN-480", "target_path": "/dist/ALDN-480/ALDN-480.mp4", "scrape_status": "pending", "status": "organized"}
    ]
    mock_create_job.return_value = {
        "id": "job123",
        "status": "queued",
        "total": 1,
        "processed": 0,
        "succeeded": 0,
        "failed": 0,
        "created_at": "2026-03-27T10:00:00",
        "started_at": None,
        "finished_at": None,
        "current_file_id": None,
        "current_file_code": None,
        "current_stage": None,
        "current_source": None,
        "recent_logs": [],
        "items": [{"id": 1, "code": "ALDN-480", "status": "pending"}],
    }

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/scrape/jobs", json={"file_ids": [1]})

    assert response.status_code == 200
    assert response.json()["id"] == "job123"
```

- [ ] **Step 2: Add a failing expanded-list test**

Append this to `tests/test_api/test_scrape_endpoints.py`:

```python
@patch('app.main.aiosqlite.connect')
@patch('app.main.get_active_scrape_job', new_callable=AsyncMock)
def test_get_scrape_list_returns_failure_details_and_active_job(mock_active_job, mock_connect, sample_rows):
    from app.main import app

    enriched_rows = [
        {
            **sample_rows[0],
            'original_path': '/source/ABC-001.mp4',
            'status': 'organized',
            'scrape_stage': 'querying_source',
            'scrape_source': 'javdb',
            'scrape_error': 'timeout',
            'scrape_error_user_message': '连接 JavDB 失败，请稍后重试',
            'scrape_logs': '[{\"at\":\"2026-03-27T10:00:00\",\"level\":\"info\",\"stage\":\"querying_source\",\"source\":\"javdb\",\"message\":\"正在查询 JavDB\"}]',
            'scrape_started_at': '2026-03-27T10:00:00',
            'scrape_finished_at': '2026-03-27T10:00:10',
        }
    ]

    mock_db = AsyncMock()
    mock_connect.return_value.__aenter__.return_value = mock_db
    _mock_scrape_list_queries(
        mock_db,
        total=1,
        rows=enriched_rows,
        stats_rows=_build_stats_row(enriched_rows),
    )
    mock_active_job.return_value = {"id": "job123", "status": "running"}

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get('/api/scrape')

    assert response.status_code == 200
    payload = response.json()
    assert payload["active_job"]["id"] == "job123"
    assert payload["items"][0]["scrape_error_user_message"] == '连接 JavDB 失败，请稍后重试'
    assert payload["items"][0]["scrape_logs"][0]["message"] == '正在查询 JavDB'
```

- [ ] **Step 3: Run the new API tests and confirm they fail**

Run:

```bash
python3 -m pytest \
  tests/test_api/test_scrape_jobs.py::test_post_scrape_jobs_returns_job_snapshot \
  tests/test_api/test_scrape_endpoints.py::test_get_scrape_list_returns_failure_details_and_active_job \
  -v
```

Expected:

```text
FAILED ... 404 != 200
FAILED ... KeyError: 'active_job'
```

- [ ] **Step 4: Create `app/scrape_jobs.py`**

Add this initial structure:

```python
import asyncio
import uuid
from datetime import datetime
from typing import Optional


scrape_jobs: dict[str, dict] = {}
scrape_jobs_lock = asyncio.Lock()


def _clone(job: dict) -> dict:
    return {
        **job,
        "recent_logs": [dict(entry) for entry in job.get("recent_logs", [])],
        "items": [dict(item) for item in job.get("items", [])],
    }


async def get_active_scrape_job() -> Optional[dict]:
    async with scrape_jobs_lock:
        for job in scrape_jobs.values():
            if job["status"] in {"queued", "running"}:
                return _clone(job)
    return None


async def get_scrape_job(job_id: str) -> Optional[dict]:
    async with scrape_jobs_lock:
        job = scrape_jobs.get(job_id)
        return _clone(job) if job else None
```

- [ ] **Step 5: Add job creation and runner helpers in `app/scrape_jobs.py`**

Add:

```python
async def create_scrape_job(rows: list[dict]) -> dict:
    job_id = uuid.uuid4().hex[:12]
    items = [
        {
            "id": row["id"],
            "code": row["identified_code"],
            "target_path": row["target_path"],
            "status": "pending",
            "stage": None,
            "source": None,
            "user_message": None,
            "technical_error": None,
            "started_at": None,
            "finished_at": None,
        }
        for row in rows
    ]
    job = {
        "id": job_id,
        "status": "queued",
        "total": len(items),
        "processed": 0,
        "succeeded": 0,
        "failed": 0,
        "created_at": datetime.now().isoformat(),
        "started_at": None,
        "finished_at": None,
        "cancel_requested": False,
        "current_file_id": None,
        "current_file_code": None,
        "current_stage": None,
        "current_source": None,
        "recent_logs": [],
        "items": items,
    }
    async with scrape_jobs_lock:
        scrape_jobs[job_id] = job
    return _clone(job)
```

and:

```python
async def cancel_scrape_job(job_id: str) -> Optional[dict]:
    async with scrape_jobs_lock:
        job = scrape_jobs.get(job_id)
        if not job:
            return None
        job["cancel_requested"] = True
        return _clone(job)
```

and add the cooperative runner:

```python
async def run_scrape_job(job_id: str) -> None:
    from app.scraper import ScraperScheduler

    scheduler = ScraperScheduler()

    async with scrape_jobs_lock:
        job = scrape_jobs.get(job_id)
        if not job:
            return
        job["status"] = "running"
        job["started_at"] = datetime.now().isoformat()

    for item in list(job["items"]):
        async with scrape_jobs_lock:
            job = scrape_jobs.get(job_id)
            if not job:
                return
            if job["cancel_requested"]:
                job["status"] = "cancelled"
                job["finished_at"] = datetime.now().isoformat()
                return
            item["status"] = "processing"
            item["started_at"] = datetime.now().isoformat()
            job["current_file_id"] = item["id"]
            job["current_file_code"] = item["code"]

        def recorder(event: dict) -> None:
            async def _apply():
                async with scrape_jobs_lock:
                    current = scrape_jobs.get(job_id)
                    if not current:
                        return
                    current["current_stage"] = event["stage"]
                    current["current_source"] = event.get("source")
                    current["recent_logs"].append(event)
                    current["recent_logs"] = current["recent_logs"][-10:]
                    target = next(candidate for candidate in current["items"] if candidate["id"] == item["id"])
                    target["stage"] = event["stage"]
                    target["source"] = event.get("source")
            asyncio.create_task(_apply())

        result = await scheduler.scrape_single(item["id"], progress_callback=recorder)

        async with scrape_jobs_lock:
            current = scrape_jobs.get(job_id)
            if not current:
                return
            target = next(candidate for candidate in current["items"] if candidate["id"] == item["id"])
            target["status"] = "success" if result.success else "failed"
            target["user_message"] = result.user_message
            target["technical_error"] = result.error
            target["finished_at"] = datetime.now().isoformat()
            current["processed"] += 1
            if result.success:
                current["succeeded"] += 1
            else:
                current["failed"] += 1

    async with scrape_jobs_lock:
        current = scrape_jobs.get(job_id)
        if not current:
            return
        current["status"] = "failed" if current["failed"] == current["total"] and current["total"] else "completed"
        current["finished_at"] = datetime.now().isoformat()
```

- [ ] **Step 6: Add scrape-job routes in `app/main.py`**

Import the new helpers:

```python
from app.scrape_jobs import (
    cancel_scrape_job,
    create_scrape_job,
    get_active_scrape_job,
    get_scrape_job,
    run_scrape_job,
)
```

Add the create route:

```python
async def get_scrape_candidates_for_job(file_ids: list[int]) -> list[dict]:
    if not file_ids:
        return []

    allowed_scrape_statuses = ("pending", "failed") if len(file_ids) == 1 else ("pending",)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        placeholders = ",".join("?" * len(file_ids))
        status_placeholders = ",".join("?" * len(PROCESSED_LIKE_STATUSES))
        scrape_placeholders = ",".join("?" * len(allowed_scrape_statuses))
        cursor = await db.execute(
            f"""
            SELECT *
            FROM files
            WHERE id IN ({placeholders})
              AND status IN ({status_placeholders})
              AND COALESCE(scrape_status, 'pending') IN ({scrape_placeholders})
            ORDER BY id ASC
            """,
            (*file_ids, *PROCESSED_LIKE_STATUSES, *allowed_scrape_statuses),
        )
        rows = await cursor.fetchall()
    return [dict(row) for row in rows]


@app.post("/api/scrape/jobs", response_model=ScrapeJobSnapshot)
async def create_scrape_job_route(request: ScrapeJobCreateRequest):
    active_job = await get_active_scrape_job()
    if active_job:
        raise HTTPException(status_code=409, detail="已有刮削任务正在运行，请等待当前任务完成")

    rows = await get_scrape_candidates_for_job(request.file_ids)
    if not rows:
        raise HTTPException(status_code=400, detail="没有可刮削的文件")

    job = await create_scrape_job(rows)
    asyncio.create_task(run_scrape_job(job["id"]))
    return job
```

Add `GET /api/scrape/jobs/{job_id}` and cancel:

```python
@app.get("/api/scrape/jobs/{job_id}", response_model=ScrapeJobSnapshot)
async def get_scrape_job_route(job_id: str):
    job = await get_scrape_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="刮削任务不存在")
    return job


@app.post("/api/scrape/jobs/{job_id}/cancel", response_model=ScrapeJobCancelResult)
async def cancel_scrape_job_route(job_id: str):
    job = await cancel_scrape_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="刮削任务不存在")
    return {
        "id": job_id,
        "status": "cancel_requested",
        "message": "已请求取消当前刮削任务",
    }
```

- [ ] **Step 7: Expand `GET /api/scrape` to return persisted detail fields and `active_job`**

Change the select list to include the new columns:

```python
SELECT
    id,
    original_path,
    identified_code,
    target_path,
    status,
    COALESCE(scrape_status, 'pending') AS scrape_status,
    last_scrape_at,
    scrape_started_at,
    scrape_finished_at,
    scrape_stage,
    scrape_source,
    scrape_error,
    scrape_error_user_message,
    scrape_logs
FROM files
```

Build each item with parsed logs:

```python
def _parse_scrape_logs(raw: str | None) -> list[dict]:
    if not raw:
        return []
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return []
```

Return:

```python
active_job = await get_active_scrape_job()
return {"total": total, "items": items, "stats": stats, "active_job": active_job}
```

- [ ] **Step 8: Run the API suite**

Run:

```bash
python3 -m pytest tests/test_api/test_scrape_endpoints.py tests/test_api/test_scrape_jobs.py -v
```

Expected:

```text
PASSED tests/test_api/test_scrape_jobs.py::test_post_scrape_jobs_returns_job_snapshot
PASSED tests/test_api/test_scrape_endpoints.py::test_get_scrape_list_returns_failure_details_and_active_job
...
```

- [ ] **Step 9: Commit the scrape-job API layer**

```bash
git add app/main.py app/scrape_jobs.py tests/test_api/test_scrape_endpoints.py tests/test_api/test_scrape_jobs.py
git commit -m "feat: add observable scrape job endpoints"
```

## Task 4: Replace sync frontend scrape calls with job creation and polling

**Files:**
- Modify: `static/js/scrape.js`
- Modify: `static/js/state.js`
- Modify: `static/js/features.js`

- [ ] **Step 1: Replace sync API helpers in `static/js/scrape.js`**

Rewrite the module to:

```javascript
const ScrapeAPI = {
    async getList(params = {}) {
        const searchParams = new URLSearchParams({
            page: String(params.page || 1),
            per_page: String(params.perPage || 50),
            filter: params.filter || 'all',
            sort: params.sort || 'code'
        });
        const response = await fetch(`/api/scrape?${searchParams}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`);
        return data;
    },

    async createJob(fileIds) {
        const response = await fetch('/api/scrape/jobs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file_ids: fileIds })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || '创建刮削任务失败');
        return data;
    },

    async getJob(jobId) {
        const response = await fetch(`/api/scrape/jobs/${jobId}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || '获取刮削任务失败');
        return data;
    },

    async cancelJob(jobId) {
        const response = await fetch(`/api/scrape/jobs/${jobId}/cancel`, { method: 'POST' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || '取消刮削任务失败');
        return data;
    }
};
```

- [ ] **Step 2: Extend scrape state in `static/js/state.js`**

Add these fields next to the existing scrape state:

```javascript
            scrapeBatchJob: null,
            scrapeBatchItemsIndex: {},
            scrapeBatchPollTimer: null,
            scrapeBatchPollingBusy: false,
            scrapeBatchExpanded: false,
            scrapeBatchSubmitting: false,
            scrapeBatchCancelling: false,
            scrapeBatchVisibleSince: 0,
            scrapeBatchExpandTimer: null,
            scrapeBatchExpanding: false,
```

- [ ] **Step 3: Remove duplicate scrape handlers from `static/js/features.js`**

Delete the first `handleScrapeAction`, `confirmBatchScrape`, and duplicate `clearScrapeSelection` block. Keep only one scrape code path in the file.

- [ ] **Step 4: Add real scrape-job polling methods in `static/js/features.js`**

Add:

```javascript
            setScrapeBatchJob(job) {
                this.scrapeBatchJob = job;
                const index = {};
                (job?.items || []).forEach(item => {
                    index[item.id] = item;
                });
                this.scrapeBatchItemsIndex = index;
            },

            stopScrapeBatchPolling() {
                if (this.scrapeBatchPollTimer) {
                    clearInterval(this.scrapeBatchPollTimer);
                    this.scrapeBatchPollTimer = null;
                }
                this.scrapeBatchPollingBusy = false;
            },

            startScrapeBatchPolling(jobId) {
                this.stopScrapeBatchPolling();
                this.scrapeBatchPollTimer = setInterval(async () => {
                    if (this.scrapeBatchPollingBusy) return;
                    this.scrapeBatchPollingBusy = true;
                    try {
                        const job = await ScrapeAPI.getJob(jobId);
                        this.setScrapeBatchJob(job);
                        if (['completed', 'failed', 'cancelled'].includes(job.status)) {
                            this.stopScrapeBatchPolling();
                            this.scrapeBatchSubmitting = false;
                            this.scrapeBatchCancelling = false;
                            await this.loadScrapeFiles();
                        }
                    } catch (error) {
                        this.stopScrapeBatchPolling();
                        this.scrapeBatchSubmitting = false;
                        this.scrapeBatchCancelling = false;
                        this.error = '刮削任务状态获取失败: ' + error.message;
                    } finally {
                        this.scrapeBatchPollingBusy = false;
                    }
                }, 400);
            },
```

- [ ] **Step 5: Rewrite scrape actions to create jobs instead of waiting synchronously**

Use:

```javascript
            async executeScrapeBatch(fileIds) {
                this.scrapeBatchSubmitting = true;
                this.error = null;
                this.success = null;
                this.scrapeBatchExpanded = true;
                this.animateScrapeBatchPanelExpand();

                try {
                    const job = await ScrapeAPI.createJob(fileIds);
                    this.setScrapeBatchJob(job);
                    this.startScrapeBatchPolling(job.id);
                } catch (e) {
                    this.scrapeBatchSubmitting = false;
                    this.error = '创建刮削任务失败: ' + e.message;
                } finally {
                    this.scrapeSelectedFiles = {};
                }
            },

            async handleScrapeAction(file) {
                this.closeStatusMenu();
                await this.executeScrapeBatch([file.id]);
            },

            async confirmScrapeSelected() {
                const selectedFiles = this.scrapeSelectedEntries.filter(file => this.canSelectScrapeFile(file));
                if (selectedFiles.length === 0) return;
                await this.executeScrapeBatch(selectedFiles.map(file => file.id));
            },
```

- [ ] **Step 6: Restore an active job after page refresh**

In `loadScrapeFiles()`:

```javascript
                    const activeJob = data.active_job || null;
                    if (activeJob) {
                        this.setScrapeBatchJob(activeJob);
                        if (['queued', 'running'].includes(activeJob.status)) {
                            this.scrapeBatchExpanded = true;
                            this.startScrapeBatchPolling(activeJob.id);
                        }
                    } else {
                        this.stopScrapeBatchPolling();
                    }
```

- [ ] **Step 7: Add cancel support in `static/js/features.js`**

Add:

```javascript
            async cancelScrapeBatch() {
                if (!this.scrapeBatchCancelable) return;

                this.scrapeBatchCancelling = true;
                this.error = null;

                try {
                    const result = await ScrapeAPI.cancelJob(this.scrapeBatchJob.id);
                    this.success = result.message;
                } catch (e) {
                    this.error = '取消刮削任务失败: ' + e.message;
                    this.scrapeBatchCancelling = false;
                }
            },
```

- [ ] **Step 8: Manual browser check for the data plumbing**

Run:

```bash
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 4020
```

Then in the browser:

- open scrape tab
- click one pending row
- confirm the panel appears immediately before work completes
- refresh the page mid-run
- confirm the panel restores automatically

Expected:

- one shared scrape panel
- no duplicate job creation
- no stale global error toast on successful single-file scrape

- [ ] **Step 9: Commit the frontend job plumbing**

```bash
git add static/js/scrape.js static/js/state.js static/js/features.js
git commit -m "refactor: unify scrape actions around live jobs"
```

## Task 5: Render stage/source/log details and fix the scrape UI affordances

**Files:**
- Modify: `static/js/render.js`
- Modify: `static/index.html`
- Modify: `static/css/index.css`

- [ ] **Step 1: Add render helpers for source label, stage label, and readable failure text**

In `static/js/render.js`, add:

```javascript
            canSelectScrapeFile(file) {
                return this.view === 'scrape' &&
                    file.scrape_status === 'pending';
            },

            getScrapeStatusActions(file) {
                if (file.scrape_status === 'pending' || file.scrape_status === 'failed') {
                    return [
                        { key: 'scrape', label: '刮削', icon: 'sparkles' }
                    ];
                }
                return [];
            },

            getScrapeSourceLabel(source) {
                const map = {
                    javdb: 'JavDB',
                    javtrailers: 'JavTrailers'
                };
                return map[source] || source || '-';
            },

            getScrapeStageLabel(stage, source) {
                const sourceLabel = this.getScrapeSourceLabel(source);
                const map = {
                    queued: '已加入刮削队列',
                    validating: '正在检查文件信息',
                    querying_source: `正在查询 ${sourceLabel}`,
                    fetching_detail: `${sourceLabel} 已返回结果，正在读取详情页`,
                    parsing_metadata: '详情页读取成功，正在解析元数据',
                    writing_nfo: '元数据解析成功，正在生成 NFO 文件',
                    downloading_poster: 'NFO 已生成，正在下载封面图片',
                    finalizing: '正在保存刮削结果',
                    success: '刮削完成',
                    failed: '刮削失败'
                };
                return map[stage] || stage || '-';
            },

            getScrapeErrorUserMessage(file) {
                return file?.scrape_error_user_message || '刮削过程中发生未知错误';
            },
```

- [ ] **Step 2: Change the row action icon to `sparkles`**

Replace:

```javascript
{ key: 'scrape', label: '刮削', icon: 'file_search' }
```

with:

```javascript
{ key: 'scrape', label: '刮削', icon: 'sparkles' }
```

- [ ] **Step 3: Expand the scrape batch panel in `static/index.html`**

Inside the scrape panel body, add:

```html
<div class="batch-note">
    当前文件：<strong x-text="scrapeBatchJob?.current_file_code || '-'"></strong>
</div>
<div class="batch-note">
    当前阶段：<strong x-text="getScrapeStageLabel(scrapeBatchJob?.current_stage, scrapeBatchJob?.current_source)"></strong>
</div>
<div class="batch-note">
    当前数据源：<strong x-text="getScrapeSourceLabel(scrapeBatchJob?.current_source)"></strong>
</div>
<div class="batch-log-list" x-show="(scrapeBatchJob?.recent_logs || []).length > 0">
    <template x-for="entry in scrapeBatchJob?.recent_logs || []" :key="`${entry.at}-${entry.message}`">
        <div class="batch-log-line">
            <span class="batch-log-time" x-text="formatProcessedTime(entry.at)"></span>
            <span class="batch-log-message" x-text="entry.message"></span>
        </div>
    </template>
</div>
```

- [ ] **Step 4: Expand the failure modal in `static/index.html`**

Replace the current scrape error modal body with:

```html
<div class="modal-info">
    <div class="modal-info-label">失败原因：</div>
    <div class="modal-info-value" x-text="getScrapeErrorUserMessage(scrapeErrorFile)"></div>
</div>
<div class="modal-info">
    <div class="modal-info-label">失败阶段：</div>
    <div class="modal-info-value" x-text="getScrapeStageLabel(scrapeErrorFile?.scrape_stage, scrapeErrorFile?.scrape_source)"></div>
</div>
<div class="modal-info">
    <div class="modal-info-label">数据源：</div>
    <div class="modal-info-value" x-text="getScrapeSourceLabel(scrapeErrorFile?.scrape_source)"></div>
</div>
<div class="modal-info" x-show="(scrapeErrorFile?.scrape_logs || []).length > 0">
    <div class="modal-info-label">最近日志：</div>
    <div class="modal-info-value modal-log-list">
        <template x-for="entry in scrapeErrorFile?.scrape_logs || []" :key="`${entry.at}-${entry.message}`">
            <div class="modal-log-line" x-text="entry.message"></div>
        </template>
    </div>
</div>
<div class="modal-info" x-show="scrapeErrorFile?.scrape_error">
    <div class="modal-info-label">技术详情：</div>
    <div class="modal-info-value" x-text="scrapeErrorFile?.scrape_error"></div>
</div>
```

- [ ] **Step 5: Add CSS for logs and metadata sections**

Append to `static/css/index.css`:

```css
.batch-log-list,
.modal-log-list {
    display: grid;
    gap: 8px;
    margin-top: 12px;
    padding: 12px;
    border-radius: 12px;
    background: rgba(15, 23, 42, 0.55);
    border: 1px solid rgba(148, 163, 184, 0.18);
}

.batch-log-line,
.modal-log-line {
    font-size: 13px;
    line-height: 1.5;
    color: #dbe7ff;
    word-break: break-word;
}

.batch-log-time {
    color: #93a4c3;
    margin-right: 8px;
}

.batch-log-message {
    color: #e8eefc;
}
```

- [ ] **Step 6: Manual browser check for the visual flow**

Verify in the browser:

- hovering a scrape status pill expands with the same motion feel as organize
- the row action uses the scrape icon, not the organize one
- single-file scrape shows `当前文件 / 当前阶段 / 当前数据源 / 最近日志`
- failed rows open a modal with readable reason first

Expected:

- the scrape panel and failure modal feel like first-class UI, not a skeleton

- [ ] **Step 7: Commit the rendering and styling changes**

```bash
git add static/js/render.js static/index.html static/css/index.css
git commit -m "feat: show scrape stages logs and readable failures"
```

## Task 6: Expand end-to-end verification and refresh-safe behavior checks

**Files:**
- Modify: `tests/test_e2e/test_scraping_flow.py`
- Modify: `docs/testing/scraping-e2e-checklist.md`

- [ ] **Step 1: Add an E2E test for persisted last-attempt details**

Append to `tests/test_e2e/test_scraping_flow.py`:

```python
async def test_failed_scrape_persists_last_attempt_details(self, test_db, test_dist_dir):
    scheduler = ScraperScheduler()
    file_id = _insert_file_record(test_db, code="FPRE-004", scrape_status="pending")

    with patch("app.scraper.JavDBCrawler") as mock_cls:
        mock_crawler = AsyncMock()
        mock_crawler.crawl = AsyncMock(return_value=None)
        mock_cls.return_value = mock_crawler
        result = await scheduler.scrape_single(file_id)

    assert result.success is False
    record = _fetch_file_record(test_db, file_id)
    assert record["scrape_status"] == "failed"
    assert record["scrape_source"] == "javdb"
    assert record["scrape_stage"] == "querying_source"
    assert record["scrape_error_user_message"] == "在 JavDB 没有找到这个番号的元数据"
    assert record["scrape_logs"]
```

- [ ] **Step 2: Add an E2E test for active-job payload shape**

Append:

```python
@patch("app.main.get_active_scrape_job", new_callable=AsyncMock)
def test_scrape_list_includes_active_job_snapshot(mock_active_job, client, monkeypatch):
    mock_active_job.return_value = {
        "id": "job-active-1",
        "status": "running",
        "total": 2,
        "processed": 1,
        "succeeded": 1,
        "failed": 0,
        "created_at": "2026-03-27T10:00:00",
        "started_at": "2026-03-27T10:00:01",
        "finished_at": None,
        "current_file_id": 2,
        "current_file_code": "FPRE-055",
        "current_stage": "querying_source",
        "current_source": "javdb",
        "recent_logs": [
            {"at": "2026-03-27T10:00:02", "level": "info", "stage": "querying_source", "source": "javdb", "message": "正在查询 JavDB"}
        ],
        "items": [],
    }

    response = client.get("/api/scrape")
    assert response.status_code == 200
    assert response.json()["active_job"]["current_file_code"] == "FPRE-055"
```

- [ ] **Step 3: Run the E2E scraping tests**

Run:

```bash
python3 -m pytest tests/test_e2e/test_scraping_flow.py -v
```

Expected:

```text
PASSED ... persists_last_attempt_details
PASSED ... includes_active_job_snapshot
```

- [ ] **Step 4: Update the manual checklist document**

Add these checks to `docs/testing/scraping-e2e-checklist.md`:

```markdown
- [ ] Single-file scrape opens the same progress panel as batch scrape (`1 / 1`)
- [ ] Panel shows current file, current stage, current source, and recent logs
- [ ] Refresh during an active scrape restores the panel and keeps polling
- [ ] Failed badge click opens a modal with readable reason, stage, source, logs, and technical details
- [ ] Failed rows cannot be batch-selected, but still expose row-level retry
```

- [ ] **Step 5: Run the full regression slice for this feature**

Run:

```bash
python3 -m pytest \
  tests/test_db_init.py \
  tests/test_scraper.py \
  tests/test_api/test_scrape_endpoints.py \
  tests/test_api/test_scrape_jobs.py \
  tests/test_e2e/test_scraping_flow.py \
  -v
```

Expected:

```text
all selected tests PASS
```

- [ ] **Step 6: Final smoke run against the local app**

Run the app:

```bash
python3 -m uvicorn app.main:app --host 127.0.0.1 --port 4020
```

Smoke flow:

- scrape one pending item and confirm a live `1 / 1` panel
- scrape multiple pending items and confirm current file increments
- force one failure and confirm the modal shows readable reason first
- refresh mid-job and confirm panel recovery
- cancel a running batch and confirm no new file starts after cancellation

- [ ] **Step 7: Commit the verification updates**

```bash
git add tests/test_e2e/test_scraping_flow.py docs/testing/scraping-e2e-checklist.md
git commit -m "test: cover scrape observability workflow"
```

## Self-Review

### Spec coverage

- Persisted latest-attempt detail fields: covered by Task 1 and Task 2.
- Unified single-file and batch scrape job model: covered by Task 3 and Task 4.
- Source-aware stage copy and readable failures: covered by Task 2 and Task 5.
- Failed rows retry-only, not batch-selectable: covered by Task 4 and Task 5.
- Active-job restore after refresh: covered by Task 3, Task 4, and Task 6.

### Placeholder scan

- No unresolved placeholder wording remains.
- Every changed module has an explicit task and concrete code snippet.
- Every task has exact commands and expected outcomes.

### Type consistency

- Backend job types use `ScrapeJobSnapshot`, `ScrapeJobItem`, and `ScrapeLogEntry` consistently.
- Frontend job state uses `scrapeBatchJob` as the single live panel source.
- Persisted fields use one naming scheme across backend and frontend: `scrape_stage`, `scrape_source`, `scrape_error_user_message`, `scrape_logs`.
