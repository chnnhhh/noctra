from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.scraper import ScraperScheduler
from app.scrapers.javdb import JavDBCrawler


def _scrapeable_row(file_id: int = 1, code: str = "EBOD-829") -> dict:
    return {
        "id": file_id,
        "status": "organized",
        "identified_code": code,
        "target_path": f"/dist/{code}/{code}.mp4",
        "original_path": f"/source/{code}.mp4",
    }


def test_javdb_http_error_message_identifies_cloudflare_challenge():
    crawler = JavDBCrawler()

    message = crawler._build_http_error_message(
        status_code=403,
        body="""
        <!DOCTYPE html>
        <html><head><title>Just a moment...</title></head><body></body></html>
        """,
        context="搜索页",
    )

    assert "HTTP 403" in message
    assert "Cloudflare" in message
    assert "搜索页" in message
    assert "Just a moment..." in message


@pytest.mark.asyncio
async def test_scrape_single_surfaces_crawler_diagnostics_on_source_block():
    scheduler = ScraperScheduler()
    scheduler._get_file = AsyncMock(return_value=_scrapeable_row())
    scheduler._persist_attempt_update = AsyncMock()

    mock_crawler = MagicMock()
    mock_crawler.crawl = AsyncMock(return_value=None)
    mock_crawler.last_error = "JavDB 搜索页返回 HTTP 403，疑似被 Cloudflare 拦截（Just a moment...）"
    mock_crawler.diagnostics = [
        {"level": "info", "message": "正在请求 JavDB 搜索页"},
        {"level": "error", "message": mock_crawler.last_error},
    ]

    with patch("app.scraper.JavDBCrawler", return_value=mock_crawler):
        result = await scheduler.scrape_single(1)

    assert result.success is False
    assert result.error == mock_crawler.last_error
    assert result.user_message == "JavDB 当前拦截了程序化访问，请稍后重试"
    assert [entry.message for entry in result.logs][-2:] == [
        "正在请求 JavDB 搜索页",
        "JavDB 搜索页返回 HTTP 403，疑似被 Cloudflare 拦截（Just a moment...）",
    ]

