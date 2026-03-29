from types import SimpleNamespace
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
async def test_javdb_request_retries_with_safari_after_cloudflare_challenge():
    crawler = JavDBCrawler()
    mock_session = MagicMock()
    mock_session.get.side_effect = [
        SimpleNamespace(
            status_code=403,
            text="""
            <!DOCTYPE html>
            <html><head><title>Just a moment...</title></head><body></body></html>
            """,
            headers={"server": "cloudflare"},
        ),
        SimpleNamespace(
            status_code=200,
            text="<html><body>ok</body></html>",
            headers={"server": "cloudflare"},
        ),
    ]

    with patch("app.scrapers.base.requests.Session", return_value=mock_session), \
         patch("app.scrapers.base.asyncio.sleep", new=AsyncMock()):
        result = await crawler._request(
            "https://javdb.com/search?q=EBOD-829&locale=zh",
            context="搜索页",
        )

    assert result == "<html><body>ok</body></html>"
    assert mock_session.get.call_count == 2
    assert mock_session.get.call_args_list[0].kwargs["impersonate"] == "chrome"
    assert mock_session.get.call_args_list[1].kwargs["impersonate"] == "safari17_0"
    assert any(
        "正在切换 Safari 浏览器指纹重试" in entry["message"]
        for entry in crawler.diagnostics
    )
    assert any(
        "已通过 Safari 浏览器指纹重试成功" in entry["message"]
        for entry in crawler.diagnostics
    )


@pytest.mark.asyncio
async def test_javdb_request_uses_normalized_proxy_from_environment():
    crawler = JavDBCrawler()
    mock_session = MagicMock()
    mock_session.get.return_value = SimpleNamespace(
        status_code=200,
        text="<html><body>ok</body></html>",
        headers={},
    )

    with patch.dict(
        "os.environ",
        {"HTTPS_PROXY": "192.168.7.2:7890"},
        clear=False,
    ), patch("app.scrapers.base.requests.Session", return_value=mock_session), \
         patch("app.scrapers.base.asyncio.sleep", new=AsyncMock()):
        result = await crawler._request(
            "https://javdb.com/search?q=EBOD-829&locale=zh",
            context="搜索页",
        )

    assert result == "<html><body>ok</body></html>"
    assert mock_session.get.call_count == 1
    assert mock_session.get.call_args.kwargs["proxy"] == "http://192.168.7.2:7890"


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


@pytest.mark.asyncio
async def test_scrape_single_writes_stage_diagnostics_to_backend_logger():
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

    with patch("app.scraper.JavDBCrawler", return_value=mock_crawler), \
         patch("app.scraper.logger") as mock_logger:
        await scheduler.scrape_single(1)

    info_calls = [call.args[0] for call in mock_logger.info.call_args_list]
    error_calls = [call.args[0] for call in mock_logger.error.call_args_list]

    assert any("正在检查文件信息" in message for message in info_calls)
    assert any("正在查询 JavDB" in message for message in info_calls)
    assert any("正在请求 JavDB 搜索页" in message for message in info_calls)
    assert any("Cloudflare" in message for message in error_calls)
