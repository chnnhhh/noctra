"""Scraper scheduler that orchestrates crawl -> NFO -> poster flow."""

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


class ScraperScheduler:
    """Orchestrates the full scraping pipeline for a single file.

    Flow: query DB -> verify status -> crawl metadata -> write NFO ->
          download poster -> update DB status.
    """

    async def scrape_single(self, file_id: int) -> ScrapeResponse:
        """Scrape metadata for a single已整理 file.

        Args:
            file_id: Database ID of the file to scrape.

        Returns:
            ScrapeResponse with success status, code, or error message.
        """
        try:
            # Step 1: Query database for file record
            record = await self._get_file(file_id)
            if record is None:
                return ScrapeResponse(
                    success=False,
                    error=f"File record with id={file_id} not found",
                )

            # Step 2: Verify file has a processed-like status. We keep
            # compatibility with both the historical `processed` status and
            # the newer `organized` wording used by the scraping design docs.
            if record["status"] not in SCRAPE_ELIGIBLE_STATUSES:
                return ScrapeResponse(
                    success=False,
                    error=f"File status is '{record['status']}', expected one of {sorted(SCRAPE_ELIGIBLE_STATUSES)}",
                )

            code = record["identified_code"]
            target_path = record["target_path"]

            if not code:
                await self._update_scrape_status(file_id, "failed")
                return ScrapeResponse(
                    success=False,
                    error="File has no identified_code",
                )

            if not target_path:
                await self._update_scrape_status(file_id, "failed")
                return ScrapeResponse(
                    success=False,
                    error="File has no target_path",
                )

            # Step 3: Crawl metadata
            crawler = JavDBCrawler()
            metadata = await crawler.crawl(code)

            if metadata is None:
                await self._update_scrape_status(file_id, "failed")
                return ScrapeResponse(
                    success=False,
                    error=f"Failed to crawl metadata for code '{code}'",
                )

            # Step 4: Derive output paths
            target_dir = Path(target_path).parent
            nfo_path = target_dir / f"{code}.nfo"
            poster_path = target_dir / f"{code}-poster.jpg"

            # Step 5: Write NFO file
            write_nfo(metadata, nfo_path)

            # Step 6: Download poster image
            if metadata.poster_url:
                await download_poster(metadata.poster_url, poster_path)

            # Step 7: Update database with success
            now = datetime.now().isoformat()
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "UPDATE files SET scrape_status = ?, last_scrape_at = ? WHERE id = ?",
                    ("success", now, file_id),
                )
                await db.commit()

            return ScrapeResponse(success=True, code=code)

        except Exception as e:
            print(f"ScraperScheduler.scrape_single error for file_id={file_id}: {e}")
            try:
                await self._update_scrape_status(file_id, "failed")
            except Exception as db_err:
                print(f"Failed to update scrape_status to 'failed' for file_id={file_id}: {db_err}")
            return ScrapeResponse(success=False, error=str(e))

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
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE files SET scrape_status = ? WHERE id = ?",
                (status, file_id),
            )
            await db.commit()
