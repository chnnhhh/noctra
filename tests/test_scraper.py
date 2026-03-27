"""Tests for ScraperScheduler."""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.scraper import ScraperScheduler, _utcnow_iso
from app.scrapers.metadata import ScrapingMetadata


def _make_metadata(code="SSIS-123", poster_url="https://example.com/poster.jpg"):
    """Create a ScrapingMetadata instance for testing."""
    return ScrapingMetadata(
        code=code,
        title=f"Test Title {code}",
        original_title=f"Original Title {code}",
        plot="Test plot content",
        actors=["Actor A", "Actor B"],
        studio="Test Studio",
        release="2024-01-15",
        poster_url=poster_url,
        fanart_url="https://example.com/fanart.jpg" if poster_url else "",
        preview_urls=[
            "https://example.com/preview-1.jpg",
            "https://example.com/preview-2.jpg",
        ] if poster_url else [],
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

        scheduler._persist_attempt_update = AsyncMock()

        # Mock JavDBCrawler.crawl
        mock_crawler = AsyncMock()
        mock_crawler.crawl = AsyncMock(return_value=metadata)

        # Mock write_nfo and download_poster
        with (
            patch("app.scraper.JavDBCrawler", return_value=mock_crawler),
            patch("app.scraper.write_nfo") as mock_write_nfo,
            patch("app.scraper.download_poster", new_callable=AsyncMock) as mock_download,
            patch(
                "app.scraper.download_additional_artwork",
                new_callable=AsyncMock,
                create=True,
                return_value={
                    "fanart": Path(record["target_path"]).parent / f"{code}-fanart.jpg",
                    "poster": Path(record["target_path"]).parent / f"{code}-poster.jpg",
                    "previews": [],
                },
            ) as mock_download_additional,
        ):
            result = await scheduler.scrape_single(file_id)

        assert result.success is True
        assert result.code == code
        assert result.error is None
        assert result.user_message == "刮削完成"
        assert result.stage == "success"
        assert result.source == "javdb"

        mock_crawler.crawl.assert_called_once_with(code)
        mock_write_nfo.assert_called_once()
        mock_download.assert_not_called()
        mock_download_additional.assert_called_once_with(
            metadata,
            Path(record["target_path"]).parent,
            poster_output_path=Path(record["target_path"]).parent / f"{code}-poster.jpg",
        )

    @pytest.mark.asyncio
    async def test_scrape_single_records_stage_source_and_logs_on_success(self):
        """Successful scrape should emit stage/source/log progress and persist it."""
        file_id = 1
        code = "ALDN-480"
        record = _make_file_record(file_id=file_id, code=code)
        metadata = _make_metadata(code=code)

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
            patch(
                "app.scraper.download_additional_artwork",
                new_callable=AsyncMock,
                create=True,
                return_value={
                    "fanart": Path(record["target_path"]).parent / f"{code}-fanart.jpg",
                    "poster": Path(record["target_path"]).parent / f"{code}-poster.jpg",
                    "previews": [],
                },
            ),
            patch.object(
                scheduler,
                "_persist_attempt_update",
                create=True,
                new_callable=AsyncMock,
            ) as mock_persist,
        ):
            result = await scheduler.scrape_single(file_id, progress_callback=recorder)

        assert result.success is True
        assert result.code == code
        assert result.user_message == "刮削完成"
        assert result.stage == "success"
        assert result.source == "javdb"

        observed_stages = [event["stage"] for event in observed]
        assert observed_stages == [
            "validating",
            "querying_source",
            "parsing_metadata",
            "writing_nfo",
            "downloading_poster",
            "finalizing",
        ]
        assert any(event["source"] == "javdb" for event in observed)
        assert result.logs[-1].stage == "finalizing"

        final_persisted = mock_persist.await_args_list[-1].kwargs
        assert final_persisted["scrape_status"] == "success"
        assert final_persisted["scrape_stage"] == "success"
        assert final_persisted["scrape_source"] == "javdb"
        persisted_logs = json.loads(final_persisted["scrape_logs"])
        assert persisted_logs[-1]["stage"] == "finalizing"

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
    async def test_database_error_before_validation_maps_to_unknown_error(self):
        """Database failures before the first stage should not masquerade as file-info errors."""
        scheduler = ScraperScheduler()
        scheduler._get_file = AsyncMock(side_effect=RuntimeError("database is locked"))

        result = await scheduler.scrape_single(1)

        assert result.success is False
        assert result.error == "database is locked"
        assert result.user_message == "刮削过程中发生未知错误"

    @pytest.mark.asyncio
    async def test_wrong_status(self):
        """Test when file status is not scrape-eligible."""
        record = _make_file_record(status="pending")

        scheduler = ScraperScheduler()
        scheduler._get_file = AsyncMock(return_value=record)
        scheduler._persist_attempt_update = AsyncMock()

        result = await scheduler.scrape_single(1)

        assert result.success is False
        assert "pending" in result.error
        assert "processed" in result.error
        assert result.stage == "validating"
        assert result.user_message == "文件信息不完整，无法开始刮削"

    @pytest.mark.asyncio
    async def test_processed_status_is_allowed(self):
        """Historical processed records should remain scrapeable."""
        record = _make_file_record(status="processed")
        metadata = _make_metadata()

        scheduler = ScraperScheduler()
        scheduler._get_file = AsyncMock(return_value=record)
        scheduler._persist_attempt_update = AsyncMock()

        mock_crawler = AsyncMock()
        mock_crawler.crawl = AsyncMock(return_value=metadata)

        with (
            patch("app.scraper.JavDBCrawler", return_value=mock_crawler),
            patch("app.scraper.write_nfo"),
            patch("app.scraper.download_poster", new_callable=AsyncMock),
            patch(
                "app.scraper.download_additional_artwork",
                new_callable=AsyncMock,
                create=True,
                return_value={
                    "fanart": Path(record["target_path"]).parent / "SSIS-123-fanart.jpg",
                    "poster": Path(record["target_path"]).parent / "SSIS-123-poster.jpg",
                    "previews": [],
                },
            ),
        ):
            result = await scheduler.scrape_single(1)

        assert result.success is True

    @pytest.mark.asyncio
    async def test_crawl_returns_none(self):
        """Test when crawler fails to find metadata."""
        record = _make_file_record(code="UNKNOWN-999")

        scheduler = ScraperScheduler()
        scheduler._get_file = AsyncMock(return_value=record)
        scheduler._persist_attempt_update = AsyncMock()

        mock_crawler = AsyncMock()
        mock_crawler.crawl = AsyncMock(return_value=None)

        with patch("app.scraper.JavDBCrawler", return_value=mock_crawler):
            result = await scheduler.scrape_single(1)

        assert result.success is False
        assert "Failed to crawl" in result.error
        assert result.stage == "querying_source"
        assert result.user_message == "在 JavDB 没有找到这个番号的元数据"

    @pytest.mark.asyncio
    async def test_no_identified_code(self):
        """Test when file has no identified_code."""
        record = _make_file_record(code=None)

        scheduler = ScraperScheduler()
        scheduler._get_file = AsyncMock(return_value=record)
        scheduler._persist_attempt_update = AsyncMock()

        result = await scheduler.scrape_single(1)

        assert result.success is False
        assert "no identified_code" in result.error
        assert result.stage == "validating"
        assert result.user_message == "文件信息不完整，无法开始刮削"

    @pytest.mark.asyncio
    async def test_no_target_path(self):
        """Test when file has no target_path."""
        record = _make_file_record(target_path=None)

        scheduler = ScraperScheduler()
        scheduler._get_file = AsyncMock(return_value=record)
        scheduler._persist_attempt_update = AsyncMock()

        result = await scheduler.scrape_single(1)

        assert result.success is False
        assert "no target_path" in result.error
        assert result.stage == "validating"
        assert result.user_message == "文件信息不完整，无法开始刮削"

    @pytest.mark.asyncio
    async def test_nfo_write_failure(self):
        """Test when write_nfo raises an exception."""
        record = _make_file_record()
        metadata = _make_metadata()

        scheduler = ScraperScheduler()
        scheduler._get_file = AsyncMock(return_value=record)
        scheduler._persist_attempt_update = AsyncMock()

        mock_crawler = AsyncMock()
        mock_crawler.crawl = AsyncMock(return_value=metadata)

        with (
            patch("app.scraper.JavDBCrawler", return_value=mock_crawler),
            patch("app.scraper.write_nfo", side_effect=OSError("Disk full")),
        ):
            result = await scheduler.scrape_single(1)

        assert result.success is False
        assert "Disk full" in result.error
        assert result.stage == "writing_nfo"
        assert result.user_message == "元数据已获取，但写入 NFO 文件失败"

    @pytest.mark.asyncio
    async def test_poster_download_failure(self):
        """Test when download_poster raises an exception."""
        record = _make_file_record()
        metadata = _make_metadata()

        scheduler = ScraperScheduler()
        scheduler._get_file = AsyncMock(return_value=record)
        scheduler._persist_attempt_update = AsyncMock()

        mock_crawler = AsyncMock()
        mock_crawler.crawl = AsyncMock(return_value=metadata)

        with (
            patch("app.scraper.JavDBCrawler", return_value=mock_crawler),
            patch("app.scraper.write_nfo"),
            patch(
                "app.scraper.download_additional_artwork",
                new_callable=AsyncMock,
                create=True,
                return_value={"fanart": None, "poster": None, "previews": []},
            ),
            patch("app.scraper.download_poster", new_callable=AsyncMock, side_effect=Exception("Network error")),
        ):
            result = await scheduler.scrape_single(1)

        assert result.success is False
        assert "Network error" in result.error
        assert result.stage == "downloading_poster"
        assert result.user_message == "NFO 已生成，但封面图片下载失败"

    @pytest.mark.asyncio
    async def test_scrape_single_maps_poster_failure_to_user_message(self):
        """Poster failures should map to readable stage-aware user messaging."""
        record = _make_file_record(code="EBOD-829")
        metadata = _make_metadata(code="EBOD-829")

        scheduler = ScraperScheduler()
        scheduler._get_file = AsyncMock(return_value=record)

        mock_crawler = AsyncMock()
        mock_crawler.crawl = AsyncMock(return_value=metadata)

        with (
            patch("app.scraper.JavDBCrawler", return_value=mock_crawler),
            patch("app.scraper.write_nfo"),
            patch(
                "app.scraper.download_additional_artwork",
                new_callable=AsyncMock,
                create=True,
                return_value={"fanart": None, "poster": None, "previews": []},
            ),
            patch(
                "app.scraper.download_poster",
                new_callable=AsyncMock,
                side_effect=Exception("poster timeout"),
            ),
            patch.object(
                scheduler,
                "_persist_attempt_update",
                create=True,
                new_callable=AsyncMock,
            ) as mock_persist,
        ):
            result = await scheduler.scrape_single(1)

        assert result.success is False
        assert result.error == "poster timeout"
        assert result.user_message == "NFO 已生成，但封面图片下载失败"
        assert result.stage == "downloading_poster"
        persisted = mock_persist.await_args_list[-1].kwargs
        assert persisted["scrape_stage"] == "downloading_poster"
        assert persisted["scrape_error_user_message"] == "NFO 已生成，但封面图片下载失败"

    @pytest.mark.asyncio
    async def test_no_poster_url_skips_download(self):
        """Test that poster download is skipped when poster_url is empty."""
        file_id = 1
        code = "SSIS-456"
        record = _make_file_record(file_id=file_id, code=code)
        metadata = _make_metadata(code=code, poster_url="")

        scheduler = ScraperScheduler()
        scheduler._get_file = AsyncMock(return_value=record)
        scheduler._persist_attempt_update = AsyncMock()

        mock_crawler = AsyncMock()
        mock_crawler.crawl = AsyncMock(return_value=metadata)

        with (
            patch("app.scraper.JavDBCrawler", return_value=mock_crawler),
            patch("app.scraper.write_nfo"),
            patch("app.scraper.download_poster", new_callable=AsyncMock) as mock_download,
        ):
            result = await scheduler.scrape_single(file_id)

        assert result.success is True
        assert result.code == code
        assert result.stage == "success"
        assert result.source == "javdb"
        # download_poster should NOT have been called since poster_url is empty
        mock_download.assert_not_called()

    @pytest.mark.asyncio
    async def test_persist_attempt_update_uses_parameterized_query(self):
        """Persist helper should use parameterized SQL and ignore unknown fields."""
        scheduler = ScraperScheduler()
        file_id = 42
        timestamp = datetime.now().isoformat()

        captured_sql = None
        captured_params = None

        async def fake_execute(sql, params=None):
            nonlocal captured_sql, captured_params
            captured_sql = sql
            captured_params = params
            mock_cursor = MagicMock()
            return mock_cursor

        with patch("app.scraper.aiosqlite") as mock_aiosqlite:
            mock_conn_cm = AsyncMock()
            mock_conn = AsyncMock()
            mock_conn.execute = fake_execute
            mock_conn_cm.__aenter__.return_value = mock_conn
            mock_conn_cm.__aexit__.return_value = None
            mock_aiosqlite.connect.return_value = mock_conn_cm

            await scheduler._persist_attempt_update(
                file_id,
                scrape_status="success",
                last_scrape_at=timestamp,
                invalid_field="ignored",
            )

        # Verify parameterized query was used
        assert captured_sql is not None
        assert "?" in captured_sql
        assert "UPDATE files SET" in captured_sql
        assert "scrape_status = ?" in captured_sql
        assert "last_scrape_at = ?" in captured_sql
        assert "invalid_field" not in captured_sql
        assert captured_params == ("success", timestamp, file_id)

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
        scheduler._persist_attempt_update = AsyncMock()

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
            patch(
                "app.scraper.download_additional_artwork",
                new_callable=AsyncMock,
                create=True,
                return_value={"fanart": None, "poster": None, "previews": []},
            ),
        ):
            await scheduler.scrape_single(file_id)

        expected_dir = Path("/dist/SSIS-789")
        assert actual_nfo_path == expected_dir / f"{code}.nfo"
        assert actual_poster_path == expected_dir / f"{code}-poster.jpg"


def test_scrape_timestamps_match_app_local_clock():
    """Scrape timestamps should stay consistent with the app's local naive ISO format."""
    class FakeDatetime:
        @staticmethod
        def now():
            return datetime(2026, 3, 27, 12, 0, 0)

        @staticmethod
        def utcnow():
            return datetime(2026, 3, 27, 4, 0, 0)

    with patch("app.scraper.datetime", FakeDatetime):
        assert _utcnow_iso() == "2026-03-27T12:00:00"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
