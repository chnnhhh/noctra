"""Writers for Emby-compatible metadata files and poster images."""

from .image import download_poster
from .nfo import write_nfo

__all__ = ["download_poster", "write_nfo"]
