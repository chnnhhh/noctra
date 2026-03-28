"""Tests for async poster image downloader."""

from pathlib import Path
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from PIL import Image

from app.scrapers.metadata import ScrapingMetadata
from app.scrapers.writers.image import (
    CHUNK_SIZE,
    DEFAULT_HEADERS,
    crop_poster_from_fanart,
    download_additional_artwork,
    download_poster,
)

FAKE_IMAGE_DATA = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # fake JPEG header + padding


@pytest.fixture
def poster_url() -> str:
    return "https://example.com/posters/SSIS-743.jpg"


async def _iter_chunked(chunk_size: int) -> AsyncIterator[bytes]:
    """Real async generator that yields fake image data in chunks."""
    for i in range(0, len(FAKE_IMAGE_DATA), chunk_size):
        yield FAKE_IMAGE_DATA[i : i + chunk_size]


def _make_async_context_manager(obj):
    """Wrap *obj* so it can be used as ``async with X as y: ...``."""
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=obj)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _build_mock_session_and_response():
    """Build a fully mocked aiohttp session whose get() returns a valid response.

    Returns:
        (mock_cm, mock_response) where *mock_cm* is an async-context-manager
        that yields the session, and *mock_response* is the response object.
    """
    # Build the response -----------------------------------------------
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()  # sync, no-op on 200
    mock_response.content.iter_chunked = _iter_chunked  # real async generator

    response_cm = _make_async_context_manager(mock_response)

    # Build the session ------------------------------------------------
    mock_session = MagicMock()
    mock_session.get = MagicMock(return_value=response_cm)

    session_cm = _make_async_context_manager(mock_session)
    return session_cm, mock_response


class TestDownloadPoster:
    """Tests for download_poster."""

    @pytest.mark.asyncio
    async def test_uses_browser_headers_and_relaxed_ssl(self, tmp_path: Path, poster_url: str):
        """Poster downloads should use browser-like headers and disable strict SSL verification."""
        output_path = tmp_path / "poster.jpg"
        session_cm, _ = _build_mock_session_and_response()
        mock_connector = MagicMock()

        with patch("app.scrapers.writers.image.aiohttp.ClientSession", return_value=session_cm) as mock_client_session, \
             patch("app.scrapers.writers.image.aiohttp.TCPConnector", return_value=mock_connector) as mock_connector_cls, \
             patch("app.scrapers.writers.image.aiofiles.open", create=True) as mock_open:

            mock_file = _make_async_context_manager(AsyncMock())
            mock_open.return_value = mock_file

            await download_poster(poster_url, output_path)

        mock_connector_cls.assert_called_once_with(ssl=False)
        session_kwargs = mock_client_session.call_args.kwargs
        assert session_kwargs["headers"] == DEFAULT_HEADERS
        assert session_kwargs["connector"] is mock_connector

    @pytest.mark.asyncio
    async def test_successful_download(self, tmp_path: Path, poster_url: str):
        """Verify image data is written to the output file."""
        output_path = tmp_path / "posters" / "SSIS-743-poster.jpg"
        session_cm, _ = _build_mock_session_and_response()

        with patch("app.scrapers.writers.image.aiohttp.ClientSession", return_value=session_cm), \
             patch("app.scrapers.writers.image.aiofiles.open", create=True) as mock_open:

            mock_file = _make_async_context_manager(AsyncMock())
            mock_open.return_value = mock_file

            await download_poster(poster_url, output_path)

        # aiofiles.open should have been called with the correct path and mode
        mock_open.assert_called_once_with(output_path, "wb")

        # Collect all bytes written to the file
        write_calls = mock_file.__aenter__.return_value.write.call_args_list
        written = b"".join(c.args[0] for c in write_calls)
        assert written == FAKE_IMAGE_DATA

    @pytest.mark.asyncio
    async def test_creates_parent_directories(self, tmp_path: Path, poster_url: str):
        """Verify nested parent directories are created automatically."""
        output_path = tmp_path / "a" / "b" / "c" / "poster.jpg"
        session_cm, _ = _build_mock_session_and_response()

        with patch("app.scrapers.writers.image.aiohttp.ClientSession", return_value=session_cm), \
             patch("app.scrapers.writers.image.aiofiles.open", create=True):

            mock_file = _make_async_context_manager(AsyncMock())
            with patch("app.scrapers.writers.image.aiofiles.open", return_value=mock_file, create=True):
                await download_poster(poster_url, output_path)

        assert output_path.parent.exists()

    @pytest.mark.asyncio
    async def test_network_error_raises(self, tmp_path: Path, poster_url: str):
        """Verify aiohttp.ClientError propagates on network failure."""
        output_path = tmp_path / "poster.jpg"

        # session.get() raises immediately
        mock_session = MagicMock()
        mock_session.get = MagicMock(side_effect=aiohttp.ClientError("connection refused"))
        session_cm = _make_async_context_manager(mock_session)

        with patch("app.scrapers.writers.image.aiohttp.ClientSession", return_value=session_cm):
            with pytest.raises(aiohttp.ClientError, match="connection refused"):
                await download_poster(poster_url, output_path)

    @pytest.mark.asyncio
    async def test_http_error_raises(self, tmp_path: Path, poster_url: str):
        """Verify HTTP error status (e.g. 404) propagates."""
        output_path = tmp_path / "poster.jpg"

        # response.raise_for_status() raises
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock(
            side_effect=aiohttp.ClientResponseError(
                request_info=MagicMock(),
                history=(),
                status=404,
                message="Not Found",
            )
        )
        response_cm = _make_async_context_manager(mock_response)

        mock_session = MagicMock()
        mock_session.get = MagicMock(return_value=response_cm)
        session_cm = _make_async_context_manager(mock_session)

        with patch("app.scrapers.writers.image.aiohttp.ClientSession", return_value=session_cm):
            with pytest.raises(aiohttp.ClientResponseError):
                await download_poster(poster_url, output_path)

    @pytest.mark.asyncio
    async def test_filesystem_error_raises(self, tmp_path: Path, poster_url: str):
        """Verify OSError/PermissionError propagates when file write fails."""
        output_path = tmp_path / "poster.jpg"
        session_cm, _ = _build_mock_session_and_response()

        with patch("app.scrapers.writers.image.aiohttp.ClientSession", return_value=session_cm), \
             patch("app.scrapers.writers.image.aiofiles.open", create=True) as mock_open:

            mock_open.side_effect = PermissionError("access denied")

            with pytest.raises(PermissionError):
                await download_poster(poster_url, output_path)


class TestDownloadAdditionalArtwork:
    """Tests for downloading fanart and preview images."""

    @pytest.mark.asyncio
    async def test_downloads_fanart_and_preview_images(self, tmp_path: Path):
        metadata = ScrapingMetadata(
            code="EBOD-829",
            title="Title",
            plot="",
            poster_url="https://example.com/poster.jpg",
            fanart_url="https://example.com/fanart.jpg",
            preview_urls=[
                "https://example.com/preview-1.jpg",
                "https://example.com/preview-2.jpg",
            ],
        )

        session_cm, _ = _build_mock_session_and_response()
        with patch("app.scrapers.writers.image.aiohttp.ClientSession", return_value=session_cm), \
             patch("app.scrapers.writers.image.aiofiles.open", create=True) as mock_open, \
             patch("app.scrapers.writers.image.crop_poster_from_fanart", return_value=tmp_path / "EBOD-829-poster.jpg") as mock_crop:
            mock_open.return_value = _make_async_context_manager(AsyncMock())

            downloaded = await download_additional_artwork(
                metadata,
                tmp_path,
                poster_output_path=tmp_path / "EBOD-829-poster.jpg",
            )

        assert downloaded["fanart"] == tmp_path / "EBOD-829-fanart.jpg"
        assert downloaded["poster"] == tmp_path / "EBOD-829-poster.jpg"
        assert downloaded["previews"] == [
            tmp_path / "EBOD-829-preview-01.jpg",
            tmp_path / "EBOD-829-preview-02.jpg",
        ]
        mock_crop.assert_called_once_with(
            tmp_path / "EBOD-829-fanart.jpg",
            tmp_path / "EBOD-829-poster.jpg",
        )

    @pytest.mark.asyncio
    async def test_reports_progress_events_for_fanart_crop_and_previews(self, tmp_path: Path):
        metadata = ScrapingMetadata(
            code="EBOD-829",
            title="Title",
            plot="",
            poster_url="https://example.com/poster.jpg",
            fanart_url="https://example.com/fanart.jpg",
            preview_urls=[
                "https://example.com/preview-1.jpg",
                "https://example.com/preview-2.jpg",
            ],
        )

        events = []

        async def recorder(event):
            events.append(event)

        session_cm, _ = _build_mock_session_and_response()
        with patch("app.scrapers.writers.image.aiohttp.ClientSession", return_value=session_cm), \
             patch("app.scrapers.writers.image.aiofiles.open", create=True) as mock_open, \
             patch("app.scrapers.writers.image.crop_poster_from_fanart", return_value=tmp_path / "EBOD-829-poster.jpg"):
            mock_open.return_value = _make_async_context_manager(AsyncMock())

            await download_additional_artwork(
                metadata,
                tmp_path,
                poster_output_path=tmp_path / "EBOD-829-poster.jpg",
                progress_callback=recorder,
            )

        assert events == [
            {"kind": "fanart_started"},
            {"kind": "fanart_downloaded"},
            {"kind": "poster_cropped"},
            {"kind": "preview_downloaded", "index": 1, "total": 2},
            {"kind": "preview_downloaded", "index": 2, "total": 2},
        ]


class TestCropPosterFromFanart:
    def test_crops_right_cover_panel_into_portrait_poster(self, tmp_path: Path):
        fanart_path = tmp_path / "EBOD-829-fanart.jpg"
        poster_path = tmp_path / "EBOD-829-poster.jpg"

        image = Image.new("RGB", (800, 538), "red")
        image.paste("green", (380, 0, 420, 538))
        image.paste("blue", (420, 0, 800, 538))
        image.save(fanart_path, format="JPEG", quality=95)

        cropped = crop_poster_from_fanart(fanart_path, poster_path)

        assert cropped == poster_path
        with Image.open(poster_path) as poster:
            assert poster.size == (380, 538)
            center = poster.getpixel((poster.size[0] // 2, poster.size[1] // 2))
            assert center[2] > center[0]
