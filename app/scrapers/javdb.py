# app/scrapers/javdb.py
"""JavDB crawler implementation (MVP - single source)."""

import re
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import BaseCrawler
from .metadata import ScrapingMetadata


class JavDBCrawler(BaseCrawler):
    """JavDB metadata crawler.

    Scrapes video metadata from javdb.com detail pages.
    Uses search to find the detail URL, then extracts fields from HTML.
    """

    name = "javdb"

    BASE_URL = "https://javdb.com"

    # --- Label sets used for metadata extraction ---
    # These handle both Chinese (zh-CN / zh-TW) and English locales
    _LABEL_CODE = ["識別碼:", "识别码:", "ID:", "品番:", "番号:", "番號:"]
    _LABEL_ACTORS = ["演員:", "演员:", "Actors:"]
    _LABEL_STUDIO = ["片商:", "Maker:"]
    _LABEL_RELEASE = ["日期:", "Released Date:"]
    _LABEL_PLOT = ["簡介", "简介", "Description", "Storyline", "剧情", "劇情"]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def crawl(self, code: str) -> Optional[ScrapingMetadata]:
        """Scrape metadata for *code* from JavDB.

        Flow:
        1. Search javdb.com for the code
        2. Open the first matching detail page
        3. Parse and return a ScrapingMetadata (or None on any failure)

        Args:
            code: Video code, e.g. "SSIS-743"

        Returns:
            ScrapingMetadata if successful, None otherwise
        """
        self._reset_diagnostics()
        code = code.strip().upper()

        # Step 1 - search for the code
        search_url = f"{self.BASE_URL}/search?q={code}&locale=zh"
        search_html = await self._request_with_context(search_url, context="搜索页")
        if not search_html:
            if not self.last_error:
                self._set_error("JavDB 搜索页请求失败")
            return None

        detail_url = self._find_first_detail_url(search_html, code)
        if not detail_url:
            self._set_error(f"JavDB 搜索结果中没有找到匹配番号 {code} 的详情页")
            return None
        detail_path = detail_url.replace(self.BASE_URL, "", 1) or detail_url
        self._record_diagnostic(f"JavDB 搜索命中详情页：{detail_path}")

        # Step 2 - fetch the detail page
        detail_html = await self._request_with_context(detail_url, context="详情页")
        if not detail_html:
            if not self.last_error:
                self._set_error("JavDB 详情页请求失败")
            return None
        self._record_diagnostic("JavDB 详情页请求成功，正在解析元数据")

        # Step 3 - parse
        metadata = self._parse_detail(detail_html, code)
        if metadata is None:
            self._set_error("JavDB 详情页已返回，但元数据解析失败")
            return None

        self._record_diagnostic("JavDB 元数据解析成功")
        return metadata

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _request_with_context(self, url: str, *, context: str) -> Optional[str]:
        try:
            return await self._request(url, context=context)
        except TypeError as exc:
            if "unexpected keyword argument 'context'" not in str(exc):
                raise
            return await self._request(url)

    def _find_first_detail_url(self, html: str, code: str) -> Optional[str]:
        """Find the first detail URL from a JavDB search results page."""
        try:
            soup = BeautifulSoup(html, "lxml")
            boxes = soup.select("a.box")
            if not boxes:
                return None

            want = code.upper().replace("-", "-").strip()

            # Prefer exact code match from the result card's UID
            for a in boxes:
                uid_el = a.select_one(".uid")
                if uid_el:
                    uid_txt = uid_el.get_text(" ", strip=True).upper()
                    if uid_txt and uid_txt == want:
                        href = a.get("href")
                        if href:
                            return urljoin(self.BASE_URL, href)

            # Fallback: accept a title that contains the code
            for a in boxes:
                title = (a.get_text(" ", strip=True) or "").upper()
                if want and want in title:
                    href = a.get("href")
                    if href:
                        return urljoin(self.BASE_URL, href)

            # Last resort: first result
            href = boxes[0].get("href")
            return urljoin(self.BASE_URL, href) if href else None

        except Exception:
            return None

    def _parse_detail(
        self, html: str, code: str
    ) -> Optional[ScrapingMetadata]:
        """Parse a JavDB detail page and extract metadata.

        Returns None if the page ID does not match *code* or on parse errors.
        """
        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception:
            return None

        # --- Validate page code matches requested code ---
        raw_id = self._text_after_label(soup, self._LABEL_CODE)
        if raw_id:
            m = re.search(r"[A-Za-z0-9]+-[A-Za-z0-9]+", raw_id)
            page_code = m.group(0).upper() if m else raw_id.upper()
            if page_code and page_code != code.upper():
                return None

        # --- Title ---
        title = self._pick_text(soup, "h2.title strong.current-title") or self._pick_text(
            soup, "h2.title"
        )
        if not title:
            return None

        # --- Plot ---
        plot = self._extract_plot(soup)

        # --- Actors ---
        actors = self._links_after_label(soup, self._LABEL_ACTORS)

        # --- Studio ---
        studio_links = self._links_after_label(soup, self._LABEL_STUDIO)
        studio = studio_links[0] if studio_links else ""

        # --- Release date ---
        release_raw = self._text_after_label(soup, self._LABEL_RELEASE).strip()
        release = self._normalize_release(release_raw) if release_raw else ""

        # --- Poster URL ---
        poster_url = self._extract_poster_url(soup)

        return ScrapingMetadata(
            code=code,
            title=title,
            plot=plot,
            actors=actors,
            studio=studio,
            release=release,
            poster_url=poster_url,
        )

    # --- Field extraction helpers ---

    @staticmethod
    def _pick_text(soup: BeautifulSoup, selector: str) -> str:
        """Get stripped text of the first element matching *selector*."""
        el = soup.select_one(selector)
        return el.get_text(" ", strip=True) if el else ""

    def _text_after_label(self, soup: BeautifulSoup, labels: List[str]) -> str:
        """Return text following a <strong> element whose text contains one of *labels*."""
        for label in labels:
            node = soup.find(
                "strong", string=lambda s: isinstance(s, str) and label in s
            )
            if not node or not node.parent:
                continue
            parent = node.parent
            span = parent.find("span")
            if span:
                return span.get_text(" ", strip=True)
            return parent.get_text(" ", strip=True)
        return ""

    def _links_after_label(self, soup: BeautifulSoup, labels: List[str]) -> List[str]:
        """Return link texts following a <strong> element matching one of *labels*."""
        for label in labels:
            node = soup.find(
                "strong", string=lambda s: isinstance(s, str) and label in s
            )
            if not node or not node.parent:
                continue
            parent = node.parent
            span = parent.find("span")
            scope = span or parent
            links = [a.get_text(" ", strip=True) for a in scope.find_all("a")]
            links = [x for x in links if x]
            if links:
                return list(dict.fromkeys(links))
        return []

    def _extract_plot(self, soup: BeautifulSoup) -> str:
        """Extract the plot/description from the detail page."""
        for label in self._LABEL_PLOT:
            node = soup.find(
                "strong", string=lambda s: isinstance(s, str) and label in s
            )
            if not node or not node.parent:
                continue
            txt = node.parent.get_text(" ", strip=True)
            if not txt:
                continue
            lab_txt = node.get_text(" ", strip=True)
            txt = txt.replace(lab_txt, "", 1).strip().lstrip(":：").strip()
            if txt and len(txt) >= 10:
                return txt
        return ""

    def _extract_poster_url(self, soup: BeautifulSoup) -> str:
        """Extract the poster/cover image URL from the detail page."""
        cover_el = soup.select_one("img.video-cover")
        if cover_el and cover_el.get("src"):
            src = cover_el["src"]
            poster_url = src
            # Derive poster (thumbnail) from cover URL if possible
            if "/covers/" in src:
                poster_url = src.replace("/covers/", "/thumbs/")
            return urljoin(self.BASE_URL, poster_url)
        return ""

    @staticmethod
    def _normalize_release(raw: str) -> str:
        """Normalize a release date string to YYYY-MM-DD format."""
        # Common patterns: "2024-01-15", "2024-01-15 ", "2025-03-21"
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        # Fallback: try YYYY/MM/DD
        m = re.search(r"(\d{4})/(\d{2})/(\d{2})", raw)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        return raw.strip()
