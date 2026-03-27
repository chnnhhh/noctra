"""Async image downloader for poster images."""

from pathlib import Path

import aiofiles
import aiohttp

DOWNLOAD_TIMEOUT = 30  # seconds
CHUNK_SIZE = 8192  # 8 KB


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
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as response:
            response.raise_for_status()
            async with aiofiles.open(output_path, "wb") as f:
                async for chunk in response.content.iter_chunked(CHUNK_SIZE):
                    await f.write(chunk)
