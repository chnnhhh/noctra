"""Scraper scheduler that orchestrates crawl -> NFO -> poster flow."""

import json
import inspect
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite

from app.models import ScrapeResponse
from app.scrapers.javdb import JavDBCrawler
from app.scrapers.writers.nfo import write_nfo
from app.scrapers.writers.image import download_poster

DB_PATH = os.getenv("DB_PATH", "/app/data/noctra.db")
SCRAPE_ELIGIBLE_STATUSES = {"processed", "organized"}
MAX_SCRAPE_LOGS = 30
SCRAPE_SOURCE_JAVDB = "javdb"
logger = logging.getLogger("uvicorn.error")


def _utcnow_iso() -> str:
    return datetime.now().isoformat()


def _source_label(source: str | None) -> str:
    mapping = {
        SCRAPE_SOURCE_JAVDB: "JavDB",
        "javtrailers": "JavTrailers",
    }
    return mapping.get(source or "", source or "")


def _map_failure(stage: str | None, source: str | None, technical_error: str | None) -> str:
    source_label = _source_label(source)
    text = (technical_error or "").lower()

    if stage == "querying_source":
        if "cloudflare" in text or "just a moment" in text or "http 403" in text:
            return f"{source_label} 当前拦截了程序化访问，请稍后重试"
        if "没有找到匹配番号" in (technical_error or ""):
            return f"在 {source_label} 没有找到这个番号的元数据"
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


class ScraperScheduler:
    """Orchestrates the full scraping pipeline for a single file.

    Flow: query DB -> verify status -> crawl metadata -> write NFO ->
          download poster -> update DB status.
    """

    async def scrape_single(self, file_id: int, progress_callback=None) -> ScrapeResponse:
        """Scrape metadata for a single已整理 file.

        Args:
            file_id: Database ID of the file to scrape.

        Returns:
            ScrapeResponse with success status, code, or error message.
        """
        logs: list[dict] = []
        current_stage: str | None = None
        current_source = None

        async def emit(
            stage: str,
            message: str,
            *,
            source: str | None = None,
            level: str = "info",
            persist: bool = True,
        ) -> None:
            nonlocal current_stage, current_source

            event_source = current_source if source is None else source
            current_stage = stage
            current_source = event_source

            event = {
                "at": _utcnow_iso(),
                "level": level,
                "stage": stage,
                "source": event_source,
                "message": message,
            }
            logs.append(event)
            if len(logs) > MAX_SCRAPE_LOGS:
                del logs[:-MAX_SCRAPE_LOGS]

            source_label = event_source or "-"
            log_line = f"scrape file_id={file_id} stage={stage} source={source_label} {message}"
            if level == "error":
                logger.error(log_line)
            elif level == "warning":
                logger.warning(log_line)
            else:
                logger.info(log_line)

            if progress_callback:
                callback_result = progress_callback(event)
                if inspect.isawaitable(callback_result):
                    await callback_result

            if persist:
                await self._persist_attempt_update(
                    file_id,
                    scrape_stage=stage,
                    scrape_source=event_source,
                    scrape_logs=json.dumps(logs, ensure_ascii=False),
                )

        async def emit_crawler_diagnostics(crawler, *, stage: str, source: str) -> None:
            diagnostics = getattr(crawler, "diagnostics", None)
            if not isinstance(diagnostics, list):
                diagnostics = []
            for item in diagnostics:
                await emit(
                    stage,
                    item.get("message", ""),
                    source=source,
                    level=item.get("level", "info"),
                )

        try:
            # Step 1: Query database for file record
            record = await self._get_file(file_id)
            if record is None:
                return ScrapeResponse(
                    success=False,
                    error=f"File record with id={file_id} not found",
                    user_message="文件信息不完整，无法开始刮削",
                    stage=current_stage,
                    source=current_source,
                    logs=logs,
                )

            started_at = _utcnow_iso()
            await self._persist_attempt_update(
                file_id,
                scrape_status="pending",
                scrape_started_at=started_at,
                scrape_finished_at=None,
                scrape_stage=None,
                scrape_source=None,
                scrape_error=None,
                scrape_error_user_message=None,
                scrape_logs=json.dumps(logs, ensure_ascii=False),
            )
            await emit("validating", "正在检查文件信息")

            # Step 2: Verify file has a processed-like status. We keep
            # compatibility with both the historical `processed` status and
            # the newer `organized` wording used by the scraping design docs.
            if record["status"] not in SCRAPE_ELIGIBLE_STATUSES:
                raise ValueError(
                    f"File status is '{record['status']}', expected one of {sorted(SCRAPE_ELIGIBLE_STATUSES)}"
                )

            code = record["identified_code"]
            target_path = record["target_path"]

            if not code:
                raise ValueError("File has no identified_code")

            if not target_path:
                raise ValueError("File has no target_path")

            # Step 3: Crawl metadata
            await emit(
                "querying_source",
                "正在查询 JavDB",
                source=SCRAPE_SOURCE_JAVDB,
            )
            crawler = JavDBCrawler()
            metadata = await crawler.crawl(code)
            await emit_crawler_diagnostics(
                crawler,
                stage="querying_source",
                source=SCRAPE_SOURCE_JAVDB,
            )

            if metadata is None:
                crawler_error = getattr(crawler, "last_error", None)
                if not isinstance(crawler_error, str) or not crawler_error.strip():
                    crawler_error = None
                raise ValueError(
                    crawler_error or f"Failed to crawl metadata for code '{code}'"
                )

            await emit(
                "parsing_metadata",
                "详情页读取成功，正在解析元数据",
                source=SCRAPE_SOURCE_JAVDB,
            )

            # Step 4: Derive output paths
            target_dir = Path(target_path).parent
            nfo_path = target_dir / f"{code}.nfo"
            poster_path = target_dir / f"{code}-poster.jpg"

            # Step 5: Write NFO file
            await emit("writing_nfo", "元数据解析成功，正在生成 NFO 文件")
            write_nfo(metadata, nfo_path)

            # Step 6: Download poster image
            if metadata.poster_url:
                await emit("downloading_poster", "NFO 已生成，正在下载封面图片")
                await download_poster(metadata.poster_url, poster_path)
            else:
                await emit("downloading_poster", "未提供封面图片，跳过下载")

            await emit("finalizing", "正在保存刮削结果")

            # Step 7: Update database with success
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

        except Exception as exc:
            logger.error(
                "ScraperScheduler.scrape_single failed file_id=%s stage=%s source=%s error=%s",
                file_id,
                current_stage,
                current_source,
                exc,
            )
            user_message = _map_failure(current_stage, current_source, str(exc))
            finished_at = _utcnow_iso()
            try:
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
            except Exception as db_err:
                logger.error(
                    "Failed to update scrape_status to failed file_id=%s db_error=%s",
                    file_id,
                    db_err,
                )
            return ScrapeResponse(
                success=False,
                error=str(exc),
                user_message=user_message,
                stage=current_stage,
                source=current_source,
                logs=logs,
            )

    async def _get_file(self, file_id: int) -> Optional[dict]:
        """Query database for a single file record by ID."""
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM files WHERE id = ?",
                (file_id,),
            )
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def _update_scrape_status(self, file_id: int, status: str) -> None:
        """Update the scrape_status column for a file record."""
        await self._persist_attempt_update(file_id, scrape_status=status)

    async def _persist_attempt_update(self, file_id: int, **fields) -> None:
        """Persist only the supported scrape attempt fields."""
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
