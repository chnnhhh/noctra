# app/scrapers/base.py
"""Base crawler class."""

import asyncio
from abc import ABC, abstractmethod
from typing import Optional
from curl_cffi import requests

from .metadata import ScrapingMetadata

class BaseCrawler(ABC):
    """爬虫基类 (MVP - 简化版)"""

    name: str  # 子类必须定义

    def __init__(self):
        self._session = None

    @abstractmethod
    async def crawl(self, code: str) -> Optional[ScrapingMetadata]:
        """爬取指定番号的元数据

        Args:
            code: 番号,如 "SSIS-123"

        Returns:
            ScrapingMetadata 对象,失败返回 None
        """
        pass

    async def _request(self, url: str) -> Optional[str]:
        """HTTP GET 请求封装 (MVP - 固定延迟,无代理/Cookie)

        Args:
            url: 目标 URL

        Returns:
            响应文本,失败返回 None
        """
        try:
            # 固定延迟 2 秒
            await asyncio.sleep(2)

            # 创建 session
            if self._session is None:
                self._session = requests.Session()

            # 执行请求
            response = self._session.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
                timeout=25,
                verify=False,
                impersonate="chrome",  # 模拟 Chrome 浏览器指纹
            )

            if response.status_code == 200:
                return response.text
            else:
                return None

        except Exception as e:
            print(f"{self.name} request error: {e}")
            return None
