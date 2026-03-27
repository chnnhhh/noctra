# tests/test_scrapers/test_base.py
"""Tests for base crawler."""

import pytest
from app.scrapers.base import BaseCrawler

def test_base_crawler_is_abstract():
    """测试基类不能直接实例化"""
    with pytest.raises(TypeError):
        BaseCrawler()
