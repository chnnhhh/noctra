"""Tests for scrape job APIs."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import pytest

from app.models import ScrapeResponse
from app.scrape_jobs import cancel_scrape_job, create_scrape_job, scrape_jobs


@pytest.fixture(autouse=True)
def clear_scrape_jobs_registry():
    scrape_jobs.clear()
    yield
    scrape_jobs.clear()


def _scrape_job_snapshot(**overrides):
    job = {
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
        "current_progress_percent": 0,
        "recent_logs": [],
        "items": [
            {
                "id": 1,
                "code": "ALDN-480",
                "target_path": "/dist/ALDN-480/ALDN-480.mp4",
                "status": "pending",
                "stage": None,
                "source": None,
                "progress_percent": 0,
                "user_message": None,
                "technical_error": None,
                "started_at": None,
                "finished_at": None,
            }
        ],
    }
    job.update(overrides)
    return job


def _scrape_row(file_id=1, code="ALDN-480"):
    return {
        "id": file_id,
        "identified_code": code,
        "target_path": f"/dist/{code}/{code}.mp4",
    }


@patch("app.main.create_scrape_job", new_callable=AsyncMock)
@patch("app.main.run_scrape_job", new_callable=AsyncMock)
@patch("app.main.get_scrape_candidates_for_job", new_callable=AsyncMock)
@patch("app.main.get_active_scrape_job", new_callable=AsyncMock)
def test_post_scrape_jobs_returns_job_snapshot(
    mock_active_job,
    mock_candidates,
    mock_run_scrape_job,
    mock_create_job,
):
    from app.main import app

    mock_active_job.return_value = None
    mock_candidates.return_value = [
        {
            "id": 1,
            "identified_code": "ALDN-480",
            "target_path": "/dist/ALDN-480/ALDN-480.mp4",
            "scrape_status": "pending",
            "status": "organized",
        }
    ]
    mock_create_job.return_value = _scrape_job_snapshot()

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/scrape/jobs", json={"file_ids": [1]})

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "job123"
    assert payload["status"] == "queued"
    assert payload["items"][0]["code"] == "ALDN-480"
    mock_active_job.assert_awaited_once()
    mock_candidates.assert_awaited_once_with([1])
    mock_create_job.assert_awaited_once()
    mock_run_scrape_job.assert_called_once_with("job123")


@patch("app.main.create_scrape_job", new_callable=AsyncMock)
@patch("app.main.run_scrape_job", new_callable=AsyncMock)
@patch("app.main.get_scrape_candidates_for_job", new_callable=AsyncMock)
@patch("app.main.get_active_scrape_job", new_callable=AsyncMock)
def test_post_scrape_jobs_returns_409_when_active_job_exists(
    mock_active_job,
    mock_candidates,
    mock_run_scrape_job,
    mock_create_job,
):
    from app.main import app

    mock_active_job.return_value = {"id": "job-old", "status": "running"}

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/scrape/jobs", json={"file_ids": [1]})

    assert response.status_code == 409
    assert response.json()["detail"] == "已有刮削任务正在运行，请等待当前任务完成"
    mock_candidates.assert_not_called()
    mock_create_job.assert_not_called()
    mock_run_scrape_job.assert_not_called()


@patch("app.main.get_scrape_job", new_callable=AsyncMock)
def test_get_scrape_job_returns_snapshot(mock_get_scrape_job):
    from app.main import app

    mock_get_scrape_job.return_value = _scrape_job_snapshot(
        status="running",
        started_at="2026-03-27T10:00:01",
        current_file_id=1,
        current_file_code="ALDN-480",
        current_stage="querying_source",
        current_source="javdb",
        current_progress_percent=35,
        recent_logs=[
            {
                "at": "2026-03-27T10:00:02",
                "level": "info",
                "stage": "querying_source",
                "source": "javdb",
                "message": "正在查询 JavDB",
            }
        ],
    )

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/scrape/jobs/job123")

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] == "job123"
    assert payload["status"] == "running"
    assert payload["current_stage"] == "querying_source"
    assert payload["current_progress_percent"] == 35
    assert payload["recent_logs"][0]["message"] == "正在查询 JavDB"
    mock_get_scrape_job.assert_awaited_once_with("job123")


@patch("app.main.get_scrape_job", new_callable=AsyncMock)
def test_get_scrape_job_returns_404_when_missing(mock_get_scrape_job):
    from app.main import app

    mock_get_scrape_job.return_value = None

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/api/scrape/jobs/job-missing")

    assert response.status_code == 404
    assert response.json()["detail"] == "刮削任务不存在"
    mock_get_scrape_job.assert_awaited_once_with("job-missing")


@patch("app.main.cancel_scrape_job", new_callable=AsyncMock)
def test_cancel_scrape_job_returns_cancel_requested(mock_cancel_scrape_job):
    from app.main import app

    mock_cancel_scrape_job.return_value = _scrape_job_snapshot(status="running")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/scrape/jobs/job123/cancel")

    assert response.status_code == 200
    assert response.json() == {
        "id": "job123",
        "status": "cancel_requested",
        "message": "已请求取消当前刮削任务",
    }
    mock_cancel_scrape_job.assert_awaited_once_with("job123")


@patch("app.main.cancel_scrape_job", new_callable=AsyncMock)
def test_cancel_scrape_job_returns_404_when_missing(mock_cancel_scrape_job):
    from app.main import app

    mock_cancel_scrape_job.return_value = None

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/scrape/jobs/job-missing/cancel")

    assert response.status_code == 404
    assert response.json()["detail"] == "刮削任务不存在"
    mock_cancel_scrape_job.assert_awaited_once_with("job-missing")


@patch("app.main.cancel_scrape_job", new_callable=AsyncMock)
def test_cancel_scrape_job_returns_terminal_status_when_job_is_done(mock_cancel_scrape_job):
    from app.main import app

    mock_cancel_scrape_job.return_value = _scrape_job_snapshot(status="completed")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/api/scrape/jobs/job123/cancel")

    assert response.status_code == 200
    assert response.json() == {
        "id": "job123",
        "status": "completed",
        "message": "刮削任务当前不可取消",
    }
    mock_cancel_scrape_job.assert_awaited_once_with("job123")


@pytest.mark.asyncio
async def test_create_scrape_job_rejects_second_active_job():
    first = await create_scrape_job([_scrape_row()])
    second = await create_scrape_job([_scrape_row(file_id=2, code="BBAN-347")])

    assert first is not None
    assert second is None


@pytest.mark.asyncio
async def test_cancel_scrape_job_keeps_terminal_job_unchanged():
    job = await create_scrape_job([_scrape_row()])
    assert job is not None

    scrape_jobs[job["id"]]["status"] = "completed"
    cancelled = await cancel_scrape_job(job["id"])

    assert cancelled is not None
    assert cancelled["status"] == "completed"
    assert cancelled["cancel_requested"] is False


@pytest.mark.asyncio
async def test_run_scrape_job_progress_percent_never_regresses_when_source_retries():
    job = await create_scrape_job([_scrape_row()])
    assert job is not None

    class FakeScheduler:
        async def scrape_single(self, file_id, progress_callback=None):
            assert file_id == 1
            if progress_callback:
                await progress_callback({
                    "at": "2026-03-29T10:00:00",
                    "level": "info",
                    "stage": "validating",
                    "source": None,
                    "message": "正在检查文件信息",
                })
                await progress_callback({
                    "at": "2026-03-29T10:00:01",
                    "level": "info",
                    "stage": "querying_source",
                    "source": "javdb",
                    "message": "正在查询 JavDB",
                })
                await progress_callback({
                    "at": "2026-03-29T10:00:02",
                    "level": "warning",
                    "stage": "fetching_detail",
                    "source": "javdb",
                    "message": "JavDB 已返回结果，正在读取详情页",
                })
                await progress_callback({
                    "at": "2026-03-29T10:00:03",
                    "level": "warning",
                    "stage": "querying_source",
                    "source": "javtrailers",
                    "message": "正在查询 JavTrailers",
                })
                await progress_callback({
                    "at": "2026-03-29T10:00:04",
                    "level": "info",
                    "stage": "parsing_metadata",
                    "source": "javtrailers",
                    "message": "详情页读取成功，正在解析元数据",
                })
            return ScrapeResponse(
                success=True,
                code="ALDN-480",
                user_message="刮削完成",
                stage="success",
                source="javtrailers",
                logs=[],
            )

    with patch("app.scraper.ScraperScheduler", return_value=FakeScheduler()):
        from app.scrape_jobs import run_scrape_job

        await run_scrape_job(job["id"])

    snapshot = scrape_jobs[job["id"]]
    item = snapshot["items"][0]
    assert snapshot["status"] == "completed"
    assert snapshot["current_progress_percent"] == 100
    assert item["progress_percent"] == 100
    assert item["source"] == "javtrailers"
