# app/scrapers/base.py
"""Base crawler class."""

import asyncio
import re
from abc import ABC, abstractmethod
from typing import Optional

from curl_cffi import requests

from .metadata import ScrapingMetadata


class BaseCrawler(ABC):
    """爬虫基类 (MVP - 简化版)"""

    name: str  # 子类必须定义
    MAX_DIAGNOSTICS = 20
    REQUEST_PROFILES = (
        {
            "label": "Chrome",
            "impersonate": "chrome",
            "headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ja;q=0.6",
            },
        },
        {
            "label": "Safari",
            "impersonate": "safari17_0",
            "headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) "
                    "Version/17.0 Safari/605.1.15"
                ),
                "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,ja;q=0.6",
            },
        },
    )

    def __init__(self):
        self._session = None
        self.last_error: Optional[str] = None
        self.diagnostics: list[dict[str, str]] = []

    @abstractmethod
    async def crawl(self, code: str) -> Optional[ScrapingMetadata]:
        """爬取指定番号的元数据

        Args:
            code: 番号,如 "SSIS-123"

        Returns:
            ScrapingMetadata 对象,失败返回 None
        """
        pass

    def _display_name(self) -> str:
        mapping = {
            "javdb": "JavDB",
            "javtrailers": "JavTrailers",
        }
        return mapping.get(getattr(self, "name", "") or "", getattr(self, "name", "Crawler"))

    def _reset_diagnostics(self) -> None:
        self.last_error = None
        self.diagnostics = []

    def _record_diagnostic(self, message: str, *, level: str = "info") -> None:
        self.diagnostics.append({
            "level": level,
            "message": message,
        })
        if len(self.diagnostics) > self.MAX_DIAGNOSTICS:
            del self.diagnostics[:-self.MAX_DIAGNOSTICS]

    def _set_error(self, message: str) -> None:
        self.last_error = message
        self._record_diagnostic(message, level="error")

    def _is_cloudflare_challenge(
        self,
        *,
        status_code: int,
        body: str | None,
    ) -> bool:
        body_lower = (body or "").lower()
        return status_code == 403 and (
            "just a moment" in body_lower or "cloudflare" in body_lower
        )

    def _build_http_error_message(
        self,
        *,
        status_code: int,
        body: str | None,
        context: str | None = None,
    ) -> str:
        label = self._display_name()
        context_label = f" {context}" if context else " 请求"
        title = ""

        if body:
            match = re.search(r"<title>(.*?)</title>", body, re.IGNORECASE | re.DOTALL)
            if match:
                title = re.sub(r"\s+", " ", match.group(1)).strip()

        body_lower = (body or "").lower()
        if status_code == 403 and ("just a moment" in body_lower or "cloudflare" in body_lower):
            challenge_title = title or "Just a moment..."
            return f"{label}{context_label}返回 HTTP 403，疑似被 Cloudflare 拦截（{challenge_title}）"

        if title:
            return f"{label}{context_label}返回 HTTP {status_code}（{title}）"
        return f"{label}{context_label}返回 HTTP {status_code}"

    async def _request(self, url: str, *, context: str | None = None) -> Optional[str]:
        """HTTP GET 请求封装 (MVP - 固定延迟,无代理/Cookie)

        Args:
            url: 目标 URL
            context: 当前请求上下文，如“搜索页”或“详情页”

        Returns:
            响应文本,失败返回 None
        """
        try:
            # 固定延迟 2 秒
            await asyncio.sleep(2)

            label = self._display_name()
            if context:
                self._record_diagnostic(f"正在请求 {label} {context}")

            # 创建 session
            if self._session is None:
                self._session = requests.Session()

            for index, profile in enumerate(self.REQUEST_PROFILES):
                response = self._session.get(
                    url,
                    headers=profile["headers"],
                    timeout=25,
                    verify=False,
                    impersonate=profile["impersonate"],
                )

                if response.status_code == 200:
                    if index > 0:
                        context_label = f" {context}" if context else " 请求"
                        self._record_diagnostic(
                            f"{label}{context_label}已通过 {profile['label']} 浏览器指纹重试成功"
                        )
                    return response.text

                is_cloudflare = self._is_cloudflare_challenge(
                    status_code=response.status_code,
                    body=response.text,
                )
                has_fallback = index < len(self.REQUEST_PROFILES) - 1
                if is_cloudflare and has_fallback:
                    next_profile = self.REQUEST_PROFILES[index + 1]
                    context_label = f" {context}" if context else " 请求"
                    self._record_diagnostic(
                        f"{label}{context_label}遭遇 Cloudflare 挑战，正在切换 {next_profile['label']} 浏览器指纹重试"
                    )
                    continue

                self._set_error(
                    self._build_http_error_message(
                        status_code=response.status_code,
                        body=response.text,
                        context=context,
                    )
                )
                return None

        except Exception as e:
            label = self._display_name()
            context_label = f" {context}" if context else " 请求"
            self._set_error(f"{label}{context_label}异常：{e}")
            print(f"{self.name} request error: {e}")
            return None
