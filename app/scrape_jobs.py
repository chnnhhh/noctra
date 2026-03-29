import asyncio
import uuid
from datetime import datetime
from typing import Optional

from app.models import ScrapeResponse

MAX_RECENT_JOB_LOGS = 10
STAGE_PROGRESS_PERCENTS = {
    "queued": 6,
    "validating": 10,
    "querying_source": 35,
    "fetching_detail": 50,
    "parsing_metadata": 65,
    "writing_nfo": 82,
    "downloading_poster": 92,
    "finalizing": 97,
    "success": 100,
    "failed": 100,
}

scrape_jobs: dict[str, dict] = {}
scrape_jobs_lock = asyncio.Lock()


def _now_iso() -> str:
    return datetime.now().isoformat()


def _clone_scrape_job(job: dict) -> dict:
    return {
        **job,
        "recent_logs": [dict(entry) for entry in job.get("recent_logs", [])],
        "items": [dict(item) for item in job.get("items", [])],
    }


def _trim_recent_logs(entries: list[dict]) -> list[dict]:
    return entries[-MAX_RECENT_JOB_LOGS:]


def _stage_progress_percent(stage: Optional[str]) -> int:
    return STAGE_PROGRESS_PERCENTS.get(stage or "", 0)


def _advance_progress_percent(
    current_percent: Optional[int],
    stage: Optional[str],
    explicit_percent: Optional[int] = None,
) -> int:
    target_percent = (
        int(explicit_percent)
        if explicit_percent is not None
        else _stage_progress_percent(stage)
    )
    return max(int(current_percent or 0), target_percent)


async def get_active_scrape_job() -> Optional[dict]:
    async with scrape_jobs_lock:
        for job in scrape_jobs.values():
            if job.get("status") in {"queued", "running"}:
                return _clone_scrape_job(job)
    return None


async def get_scrape_job(job_id: str) -> Optional[dict]:
    async with scrape_jobs_lock:
        job = scrape_jobs.get(job_id)
        return _clone_scrape_job(job) if job else None


async def create_scrape_job(rows: list[dict]) -> Optional[dict]:
    async with scrape_jobs_lock:
        if any(job.get("status") in {"queued", "running"} for job in scrape_jobs.values()):
            return None

        job_id = uuid.uuid4().hex[:12]
        now = _now_iso()
        items = [
            {
                "id": row["id"],
                "code": row.get("identified_code"),
                "target_path": row.get("target_path"),
                "status": "pending",
                "stage": None,
                "source": None,
                "progress_percent": 0,
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
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "cancel_requested": False,
            "current_file_id": None,
            "current_file_code": None,
            "current_stage": None,
            "current_source": None,
            "current_progress_percent": 0,
            "recent_logs": [],
            "items": items,
        }
        scrape_jobs[job_id] = job
        return _clone_scrape_job(job)


async def cancel_scrape_job(job_id: str) -> Optional[dict]:
    async with scrape_jobs_lock:
        job = scrape_jobs.get(job_id)
        if not job:
            return None
        if job.get("status") not in {"queued", "running"}:
            return _clone_scrape_job(job)
        job["cancel_requested"] = True
        return _clone_scrape_job(job)


async def _mark_job_finished(job_id: str) -> None:
    async with scrape_jobs_lock:
        job = scrape_jobs.get(job_id)
        if not job:
            return
        if job["failed"] == job["total"] and job["total"] > 0:
            job["status"] = "failed"
        else:
            job["status"] = "completed"
        job["finished_at"] = _now_iso()
        job["current_file_id"] = None
        job["current_file_code"] = None
        job["current_stage"] = "success" if job["status"] == "completed" else job.get("current_stage")
        job["current_progress_percent"] = max(int(job.get("current_progress_percent") or 0), 100 if job["status"] == "completed" else int(job.get("current_progress_percent") or 0))


async def run_scrape_job(job_id: str) -> None:
    from app.scraper import ScraperScheduler

    scheduler = ScraperScheduler()

    async with scrape_jobs_lock:
        job = scrape_jobs.get(job_id)
        if not job:
            return
        job["status"] = "running"
        job["started_at"] = _now_iso()

    while True:
        async with scrape_jobs_lock:
            job = scrape_jobs.get(job_id)
            if not job:
                return

            if job["cancel_requested"]:
                job["status"] = "cancelled"
                job["finished_at"] = _now_iso()
                job["current_file_id"] = None
                job["current_file_code"] = None
                return

            pending_item = next((item for item in job["items"] if item["status"] == "pending"), None)
            if pending_item is None:
                break

            file_id = pending_item["id"]
            file_code = pending_item.get("code")
            pending_item["status"] = "processing"
            pending_item["started_at"] = _now_iso()
            pending_item["progress_percent"] = 0
            job["current_file_id"] = file_id
            job["current_file_code"] = file_code
            job["current_stage"] = None
            job["current_source"] = None
            job["current_progress_percent"] = 0

        async def recorder(event: dict) -> None:
            async with scrape_jobs_lock:
                current = scrape_jobs.get(job_id)
                if not current:
                    return
                current["current_stage"] = event.get("stage")
                current["current_source"] = event.get("source")
                current["recent_logs"] = _trim_recent_logs(current["recent_logs"] + [dict(event)])
                target = next((item for item in current["items"] if item["id"] == file_id), None)
                if not target:
                    return
                target["stage"] = event.get("stage")
                target["source"] = event.get("source")
                target["progress_percent"] = _advance_progress_percent(
                    target.get("progress_percent"),
                    event.get("stage"),
                    event.get("progress_percent"),
                )
                current["current_progress_percent"] = max(
                    int(current.get("current_progress_percent") or 0),
                    int(target.get("progress_percent") or 0),
                )

        try:
            result = await scheduler.scrape_single(file_id, progress_callback=recorder)
        except Exception as exc:
            result = ScrapeResponse(
                success=False,
                error=str(exc),
                user_message="刮削过程中发生未知错误",
            )

        finished_at = _now_iso()
        async with scrape_jobs_lock:
            current = scrape_jobs.get(job_id)
            if not current:
                return

            target = next((item for item in current["items"] if item["id"] == file_id), None)
            if not target:
                continue

            target["status"] = "success" if result.success else "failed"
            target["stage"] = result.stage
            target["source"] = result.source
            target["progress_percent"] = _advance_progress_percent(
                target.get("progress_percent"),
                result.stage,
            )
            target["user_message"] = result.user_message
            target["technical_error"] = result.error
            target["finished_at"] = finished_at
            current["current_stage"] = result.stage
            current["current_source"] = result.source
            current["current_progress_percent"] = max(
                int(current.get("current_progress_percent") or 0),
                int(target.get("progress_percent") or 0),
            )
            current["processed"] += 1
            if result.success:
                current["succeeded"] += 1
            else:
                current["failed"] += 1

            if result.logs:
                current["recent_logs"] = _trim_recent_logs(
                    [dict(entry) for entry in result.logs]
                )

    await _mark_job_finished(job_id)
