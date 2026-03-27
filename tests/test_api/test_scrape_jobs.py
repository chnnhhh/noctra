"""Tests for scrape job APIs."""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient


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
        "recent_logs": [],
        "items": [
            {
                "id": 1,
                "code": "ALDN-480",
                "target_path": "/dist/ALDN-480/ALDN-480.mp4",
                "status": "pending",
                "stage": None,
                "source": None,
                "user_message": None,
                "technical_error": None,
                "started_at": None,
                "finished_at": None,
            }
        ],
    }
    job.update(overrides)
    return job


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
