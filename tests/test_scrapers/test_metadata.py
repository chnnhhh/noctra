"""Tests for metadata models."""

import pytest
from app.scrapers.metadata import ScrapingMetadata

def test_metadata_creation():
    """测试元数据创建"""
    metadata = ScrapingMetadata(
        code="SSIS-123",
        title="テストタイトル",
        plot="テストプロット",
        actors=["女優1", "女優2"],
        studio="S1 NO.1 STYLE",
        release="2023-06-27",
        poster_url="https://example.com/poster.jpg"
    )

    assert metadata.code == "SSIS-123"
    assert metadata.title == "テストタイトル"
    assert len(metadata.actors) == 2

def test_metadata_to_dict():
    """测试转换为字典"""
    metadata = ScrapingMetadata(
        code="SSIS-123",
        title="タイトル",
        plot="プロット",
        poster_url="https://example.com/poster.jpg"
    )

    result = metadata.to_dict()

    assert result["code"] == "SSIS-123"
    assert result["poster"] == "SSIS-123-poster.jpg"
    assert result["studio"] == ""  # 默认值
