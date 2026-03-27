"""Async image downloader for poster images."""

from pathlib import Path

import aiofiles
import aiohttp

DOWNLOAD_TIMEOUT = 30  # seconds
CHUNK_SIZE = 8192  # 8 KB
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ja;q=0.6",
}


async def download_poster(url: str, output_path: Path) -> None:
    """Download poster image from url to output_path asynchronously.

    Args:
        url: Poster image URL.
        output_path: Full filesystem path where image will be saved
            (including filename).

    Raises:
        aiohttp.ClientError: On network/HTTP errors.
        OSError: On file system errors.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    timeout = aiohttp.ClientTimeout(total=DOWNLOAD_TIMEOUT)
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(
        timeout=timeout,
        headers=DEFAULT_HEADERS,
        connector=connector,
    ) as session:
        async with session.get(url) as response:
            response.raise_for_status()
            async with aiofiles.open(output_path, "wb") as f:
                async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                    await f.write(chunk)
