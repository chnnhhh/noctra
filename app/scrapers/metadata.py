"""Metadata models for scraping."""

from dataclasses import dataclass, field
from typing import List

@dataclass
class ScrapingMetadata:
    """最小化元数据模型 (MVP)"""

    # 基础信息
    code: str                          # 番号 "SSIS-123"
    title: str                         # 标题
    plot: str                          # 剧情简介

    # 制作信息
    actors: List[str] = field(default_factory=list)     # 演员列表
    studio: str = ""                   # 制作商
    release: str = ""                  # 发布日期 YYYY-MM-DD

    # 媒体资源
    poster_url: str = ""               # 封面图 URL

    def to_dict(self) -> dict:
        """转换为字典,用于 NFO 生成"""
        return {
            "code": self.code,
            "title": self.title,
            "plot": self.plot,
            "actors": self.actors,
            "studio": self.studio,
            "release": self.release,
            "poster": f"{self.code}-poster.jpg" if self.poster_url else None,
        }
