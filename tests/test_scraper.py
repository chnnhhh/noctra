"""Tests for ScraperScheduler."""

import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models import ScrapeResponse
from app.scraper import ScraperScheduler
from app.scrapers.metadata import ScrapingMetadata


def _make_metadata(code="SSIS-123", poster_url="https://example.com/poster.jpg"):
    """Create a ScrapingMetadata instance for testing."""
    return ScrapingMetadata(
        code=code,
        title=f"Test Title {code}",
        plot="Test plot content",
        actors=["Actor A", "Actor B"],
        studio="Test Studio",
        release="2024-01-15",
        poster_url=poster_url,
    )


def _make_file_record(
    file_id=1,
    status="processed",
    code="SSIS-123",
    target_path="/dist/SSIS-123/SSIS-123.mp4",
):
    """Create a mock file record dict."""
    return {
        "id": file_id,
        "original_path": "/source/SSIS-123.mp4",
        "identified_code": code,
        "target_path": target_path,
        "status": status,
        "file_size": 1024,
        "file_mtime": 1700000000.0,
        "created_at": "2024-01-01T00:00:00",
        "updated_at": "2024-01-01T00:00:00",
        "scrape_status": "pending",
        "last_scrape_at": None,
    }


def _mock_db_row(record_dict):
    """Convert a dict to a mock aiosqlite.Row-like object."""
    row = MagicMock()
    row.keys.return_value = record_dict.keys()
    row.__getitem__ = lambda self, key: record_dict[key]
    # Support dict() conversion
    return row


class TestScrapeSingle:
    """Tests for ScraperScheduler.scrape_single."""

    @pytest.mark.asyncio
    async def test_successful_scrape_flow(self):
        """Test complete successful scrape: crawl -> nfo -> poster -> DB update."""
        file_id = 1
        code = "SSIS-123"
        record = _make_file_record(file_id=file_id, code=code)
        metadata = _make_metadata(code=code)

        scheduler = ScraperScheduler()

        # Mock _get_file to return the record
        scheduler._get_file = AsyncMock(return_value=record)

        # Mock _update_scrape_status
        scheduler._update_scrape_status = AsyncMock()

        # Mock JavDBCrawler.crawl
        mock_crawler = AsyncMock()
        mock_crawler.crawl = AsyncMock(return_value=metadata)

        # Mock write_nfo and download_poster
        with (
            patch("app.scraper.JavDBCrawler", return_value=mock_crawler),
            patch("app.scraper.write_nfo") as mock_write_nfo,
            patch("app.scraper.download_poster", new_callable=AsyncMock) as mock_download,
            patch("app.scraper.aiosqlite") as mock_aiosqlite,
        ):
            # Setup the DB context manager for the success update
            mock_conn_cm = AsyncMock()
            mock_conn = AsyncMock()
            mock_conn_cm.__aenter__.return_value = mock_conn
            mock_conn_cm.__aexit__.return_value = None
            mock_aiosqlite.connect.return_value = mock_conn_cm

            result = await scheduler.scrape_single(file_id)

        assert result.success is True
        assert result.code == code
        assert result.error is None

        mock_crawler.crawl.assert_called_once_with(code)
        mock_write_nfo.assert_called_once()
        mock_download.assert_called_once_with(metadata.poster_url, Path(record["target_path"]).parent / f"{code}-poster.jpg")

    @pytest.mark.asyncio
    async def test_file_not_found(self):
        """Test when DB returns None (file record not found)."""
        scheduler = ScraperScheduler()
        scheduler._get_file = AsyncMock(return_value=None)

        result = await scheduler.scrape_single(999)

        assert result.success is False
        assert "not found" in result.error
        assert "999" in result.error

    @pytest.mark.asyncio
    async def test_wrong_status(self):
        """Test when file status is not scrape-eligible."""
        record = _make_file_record(status="pending")

        scheduler = ScraperScheduler()
        scheduler._get_file = AsyncMock(return_value=record)

        result = await scheduler.scrape_single(1)

        assert result.success is False
        assert "pending" in result.error
        assert "processed" in result.error

    @pytest.mark.asyncio
    async def test_processed_status_is_allowed(self):
        """Historical processed records should remain scrapeable."""
        record = _make_file_record(status="processed")
        metadata = _make_metadata()

        scheduler = ScraperScheduler()
        scheduler._get_file = AsyncMock(return_value=record)

        mock_crawler = AsyncMock()
        mock_crawler.crawl = AsyncMock(return_value=metadata)

        with (
            patch("app.scraper.JavDBCrawler", return_value=mock_crawler),
            patch("app.scraper.write_nfo"),
            patch("app.scraper.download_poster", new_callable=AsyncMock),
            patch("app.scraper.aiosqlite") as mock_aiosqlite,
        ):
            mock_conn_cm = AsyncMock()
            mock_conn = AsyncMock()
            mock_conn_cm.__aenter__.return_value = mock_conn
            mock_conn_cm.__aexit__.return_value = None
            mock_aiosqlite.connect.return_value = mock_conn_cm

            result = await scheduler.scrape_single(1)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_crawl_returns_none(self):
        """Test when crawler fails to find metadata."""
        record = _make_file_record(code="UNKNOWN-999")

        scheduler = ScraperScheduler()
        scheduler._get_file = AsyncMock(return_value=record)
        scheduler._update_scrape_status = AsyncMock()

        mock_crawler = AsyncMock()
        mock_crawler.crawl = AsyncMock(return_value=None)

        with patch("app.scraper.JavDBCrawler", return_value=mock_crawler):
            result = await scheduler.scrape_single(1)

        assert result.success is False
        assert "Failed to crawl" in result.error
        scheduler._update_scrape_status.assert_called_once_with(1, "failed")

    @pytest.mark.asyncio
    async def test_no_identified_code(self):
        """Test when file has no identified_code."""
        record = _make_file_record(code=None)

        scheduler = ScraperScheduler()
        scheduler._get_file = AsyncMock(return_value=record)
        scheduler._update_scrape_status = AsyncMock()

        result = await scheduler.scrape_single(1)

        assert result.success is False
        assert "no identified_code" in result.error
        scheduler._update_scrape_status.assert_called_once_with(1, "failed")

    @pytest.mark.asyncio
    async def test_no_target_path(self):
        """Test when file has no target_path."""
        record = _make_file_record(target_path=None)

        scheduler = ScraperScheduler()
        scheduler._get_file = AsyncMock(return_value=record)
        scheduler._update_scrape_status = AsyncMock()

        result = await scheduler.scrape_single(1)

        assert result.success is False
        assert "no target_path" in result.error
        scheduler._update_scrape_status.assert_called_once_with(1, "failed")

    @pytest.mark.asyncio
    async def test_nfo_write_failure(self):
        """Test when write_nfo raises an exception."""
        record = _make_file_record()
        metadata = _make_metadata()

        scheduler = ScraperScheduler()
        scheduler._get_file = AsyncMock(return_value=record)
        scheduler._update_scrape_status = AsyncMock()

        mock_crawler = AsyncMock()
        mock_crawler.crawl = AsyncMock(return_value=metadata)

        with (
            patch("app.scraper.JavDBCrawler", return_value=mock_crawler),
            patch("app.scraper.write_nfo", side_effect=OSError("Disk full")),
        ):
            result = await scheduler.scrape_single(1)

        assert result.success is False
        assert "Disk full" in result.error
        scheduler._update_scrape_status.assert_called_once_with(1, "failed")

    @pytest.mark.asyncio
    async def test_poster_download_failure(self):
        """Test when download_poster raises an exception."""
        record = _make_file_record()
        metadata = _make_metadata()

        scheduler = ScraperScheduler()
        scheduler._get_file = AsyncMock(return_value=record)
        scheduler._update_scrape_status = AsyncMock()

        mock_crawler = AsyncMock()
        mock_crawler.crawl = AsyncMock(return_value=metadata)

        with (
            patch("app.scraper.JavDBCrawler", return_value=mock_crawler),
            patch("app.scraper.write_nfo"),
            patch("app.scraper.download_poster", new_callable=AsyncMock, side_effect=Exception("Network error")),
        ):
            result = await scheduler.scrape_single(1)

        assert result.success is False
        assert "Network error" in result.error
        scheduler._update_scrape_status.assert_called_once_with(1, "failed")

    @pytest.mark.asyncio
    async def test_no_poster_url_skips_download(self):
        """Test that poster download is skipped when poster_url is empty."""
        file_id = 1
        code = "SSIS-456"
        record = _make_file_record(file_id=file_id, code=code)
        metadata = _make_metadata(code=code, poster_url="")

        scheduler = ScraperScheduler()
        scheduler._get_file = AsyncMock(return_value=record)
        scheduler._update_scrape_status = AsyncMock()

        mock_crawler = AsyncMock()
        mock_crawler.crawl = AsyncMock(return_value=metadata)

        with (
            patch("app.scraper.JavDBCrawler", return_value=mock_crawler),
            patch("app.scraper.write_nfo"),
            patch("app.scraper.download_poster", new_callable=AsyncMock) as mock_download,
            patch("app.scraper.aiosqlite") as mock_aiosqlite,
        ):
            mock_conn_cm = AsyncMock()
            mock_conn = AsyncMock()
            mock_conn_cm.__aenter__.return_value = mock_conn
            mock_conn_cm.__aexit__.return_value = None
            mock_aiosqlite.connect.return_value = mock_conn_cm

            result = await scheduler.scrape_single(file_id)

        assert result.success is True
        assert result.code == code
        # download_poster should NOT have been called since poster_url is empty
        mock_download.assert_not_called()

    @pytest.mark.asyncio
    async def test_db_update_on_success_uses_parameterized_query(self):
        """Test that the success DB update uses parameterized queries."""
        file_id = 42
        code = "ABW-100"
        record = _make_file_record(file_id=file_id, code=code)
        metadata = _make_metadata(code=code)

        scheduler = ScraperScheduler()
        scheduler._get_file = AsyncMock(return_value=record)

        mock_crawler = AsyncMock()
        mock_crawler.crawl = AsyncMock(return_value=metadata)

        captured_sql = None
        captured_params = None

        async def fake_execute(sql, params=None):
            nonlocal captured_sql, captured_params
            captured_sql = sql
            captured_params = params
            mock_cursor = MagicMock()
            return mock_cursor

        with (
            patch("app.scraper.JavDBCrawler", return_value=mock_crawler),
            patch("app.scraper.write_nfo"),
            patch("app.scraper.download_poster", new_callable=AsyncMock),
            patch("app.scraper.aiosqlite") as mock_aiosqlite,
        ):
            mock_conn_cm = AsyncMock()
            mock_conn = AsyncMock()
            mock_conn.execute = fake_execute
            mock_conn_cm.__aenter__.return_value = mock_conn
            mock_conn_cm.__aexit__.return_value = None
            mock_aiosqlite.connect.return_value = mock_conn_cm

            await scheduler.scrape_single(file_id)

        # Verify parameterized query was used
        assert captured_sql is not None
        assert "?" in captured_sql
        assert "UPDATE files SET scrape_status" in captured_sql
        assert captured_params == ("success", captured_params[1], file_id)
        # Verify timestamp is ISO format
        datetime.fromisoformat(captured_params[1])

    @pytest.mark.asyncio
    async def test_scrape_single_derives_correct_paths(self):
        """Test that NFO and poster paths are correctly derived from target_path."""
        file_id = 1
        code = "SSIS-789"
        record = _make_file_record(
            file_id=file_id,
            code=code,
            target_path="/dist/SSIS-789/SSIS-789-C.mp4",
        )
        metadata = _make_metadata(code=code)

        scheduler = ScraperScheduler()
        scheduler._get_file = AsyncMock(return_value=record)
        scheduler._update_scrape_status = AsyncMock()

        mock_crawler = AsyncMock()
        mock_crawler.crawl = AsyncMock(return_value=metadata)

        actual_nfo_path = None
        actual_poster_path = None

        def capture_nfo(meta, path):
            nonlocal actual_nfo_path
            actual_nfo_path = path

        async def capture_poster(url, path):
            nonlocal actual_poster_path
            actual_poster_path = path

        with (
            patch("app.scraper.JavDBCrawler", return_value=mock_crawler),
            patch("app.scraper.write_nfo", side_effect=capture_nfo),
            patch("app.scraper.download_poster", new_callable=AsyncMock, side_effect=capture_poster),
            patch("app.scraper.aiosqlite") as mock_aiosqlite,
        ):
            mock_conn_cm = AsyncMock()
            mock_conn = AsyncMock()
            mock_conn_cm.__aenter__.return_value = mock_conn
            mock_conn_cm.__aexit__.return_value = None
            mock_aiosqlite.connect.return_value = mock_conn_cm

            await scheduler.scrape_single(file_id)

        expected_dir = Path("/dist/SSIS-789")
        assert actual_nfo_path == expected_dir / f"{code}.nfo"
        assert actual_poster_path == expected_dir / f"{code}-poster.jpg"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
