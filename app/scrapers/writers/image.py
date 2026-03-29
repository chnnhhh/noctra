"""Async image download helpers for scraper artwork."""

import inspect
from pathlib import Path
from urllib.parse import urlparse

import aiofiles
import aiohttp
from PIL import Image

from app.scrapers.metadata import ScrapingMetadata
from app.scrapers.proxy import get_proxy_for_url

DOWNLOAD_TIMEOUT = 30
CHUNK_SIZE = 8192
COVER_POSTER_CROP_START_RATIO = 0.525
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ja;q=0.6",
}


def _guess_image_extension(url: str) -> str:
    try:
        suffix = Path(urlparse(url).path).suffix.lower()
    except Exception:
        suffix = ""
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return suffix
    return ".jpg"


async def _write_response_to_path(response: aiohttp.ClientResponse, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiofiles.open(output_path, "wb") as file_obj:
        async for chunk in response.content.iter_chunked(CHUNK_SIZE):
            await file_obj.write(chunk)


async def _download_with_session(
    session: aiohttp.ClientSession,
    url: str,
    output_path: Path,
) -> Path:
    request_kwargs = {}
    proxy = get_proxy_for_url(url)
    if proxy:
        request_kwargs["proxy"] = proxy

    async with session.get(url, **request_kwargs) as response:
        response.raise_for_status()
        await _write_response_to_path(response, output_path)
    return output_path


async def download_poster(url: str, output_path: Path) -> None:
    """Download the main poster image."""
    output_path = Path(output_path)

    timeout = aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT)
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(
        timeout=timeout,
        headers=DEFAULT_HEADERS,
        connector=connector,
    ) as session:
        await _download_with_session(session, url, output_path)


async def download_additional_artwork(
    metadata: ScrapingMetadata,
    output_dir: Path,
    *,
    poster_output_path: Path | None = None,
    progress_callback=None,
) -> dict[str, Path | list[Path] | None]:
    """Download fanart and preview images on a best-effort basis."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    downloaded_previews: list[Path] = []
    fanart_path: Path | None = None
    poster_path: Path | None = None

    timeout = aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT)
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(
        timeout=timeout,
        headers=DEFAULT_HEADERS,
        connector=connector,
    ) as session:
        if metadata.fanart_url:
            fanart_path = output_dir / f"{metadata.code}-fanart{_guess_image_extension(metadata.fanart_url)}"
            try:
                if progress_callback:
                    callback_result = progress_callback({
                        "kind": "fanart_started",
                    })
                    if inspect.isawaitable(callback_result):
                        await callback_result
                await _download_with_session(session, metadata.fanart_url, fanart_path)
                if progress_callback:
                    callback_result = progress_callback({
                        "kind": "fanart_downloaded",
                    })
                    if inspect.isawaitable(callback_result):
                        await callback_result
                if poster_output_path:
                    poster_path = crop_poster_from_fanart(fanart_path, poster_output_path)
                    if progress_callback and poster_path:
                        callback_result = progress_callback({
                            "kind": "poster_cropped",
                        })
                        if inspect.isawaitable(callback_result):
                            await callback_result
            except aiohttp.ClientError:
                fanart_path = None

        total_previews = len(metadata.preview_urls)
        for index, preview_url in enumerate(metadata.preview_urls, start=1):
            preview_path = output_dir / (
                f"{metadata.code}-preview-{index:02d}{_guess_image_extension(preview_url)}"
            )
            try:
                await _download_with_session(session, preview_url, preview_path)
            except aiohttp.ClientError:
                continue
            downloaded_previews.append(preview_path)
            if progress_callback:
                callback_result = progress_callback({
                    "kind": "preview_downloaded",
                    "index": index,
                    "total": total_previews,
                })
                if inspect.isawaitable(callback_result):
                    await callback_result

    return {
        "fanart": fanart_path,
        "poster": poster_path,
        "previews": downloaded_previews,
    }


def crop_poster_from_fanart(
    fanart_path: Path,
    poster_output_path: Path,
) -> Path | None:
    """Crop the right-side front cover from a landscape DVD cover scan."""
    fanart_path = Path(fanart_path)
    poster_output_path = Path(poster_output_path)
    poster_output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with Image.open(fanart_path) as image:
            width, height = image.size
            if width <= height:
                return None

            crop_start_x = int(width * COVER_POSTER_CROP_START_RATIO)
            if crop_start_x >= width - 4:
                return None

            poster = image.crop((crop_start_x, 0, width, height))
            if poster.mode not in {"RGB", "L"}:
                poster = poster.convert("RGB")
            elif poster.mode == "L":
                poster = poster.convert("RGB")

            poster.save(poster_output_path, format="JPEG", quality=95)
            return poster_output_path
    except Exception:
        return None
