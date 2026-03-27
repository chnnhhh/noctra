"""Metadata models for scraping."""

from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class ScrapingMetadata:
    """Scraped metadata used by NFO and artwork writers."""

    # 基础信息
    code: str
    title: str
    plot: str
    original_title: str = ""
    website: str = ""

    # 制作信息
    actors: List[str] = field(default_factory=list)
    studio: str = ""
    release: str = ""
    runtime_minutes: Optional[int] = None
    directors: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    rating: str = ""
    votes: Optional[int] = None

    # 媒体资源
    poster_url: str = ""
    fanart_url: str = ""
    preview_urls: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to a simple dictionary for template-style consumers."""
        return {
            "code": self.code,
            "title": self.title,
            "original_title": self.original_title,
            "plot": self.plot,
            "website": self.website,
            "actors": self.actors,
            "studio": self.studio,
            "release": self.release,
            "runtime_minutes": self.runtime_minutes,
            "directors": self.directors,
            "tags": self.tags,
            "rating": self.rating,
            "votes": self.votes,
            "poster": f"{self.code}-poster.jpg" if self.poster_url else None,
            "fanart": f"{self.code}-fanart.jpg" if self.fanart_url else None,
            "previews": [
                f"{self.code}-preview-{index:02d}.jpg"
                for index, _ in enumerate(self.preview_urls, start=1)
            ],
        }
