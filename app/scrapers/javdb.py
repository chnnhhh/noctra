# app/scrapers/javdb.py
"""JavDB crawler implementation (MVP - single source)."""

import re
from typing import List, Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

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
    _LABEL_RUNTIME = ["時長:", "时长:", "Duration:"]
    _LABEL_DIRECTORS = ["導演:", "导演:", "Director:"]
    _LABEL_TAGS = ["類別:", "类别:", "Tags:"]
    _LABEL_RATING = ["評分:", "评分:", "Rating:"]
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
        detail_url = self._with_locale(detail_url, "zh")
        detail_html = await self._request_with_context(detail_url, context="详情页")
        if not detail_html:
            if not self.last_error:
                self._set_error("JavDB 详情页请求失败")
            return None
        self._record_diagnostic("JavDB 详情页请求成功，正在解析元数据")

        # Step 3 - parse
        metadata = self._parse_detail(detail_html, code, detail_url=detail_url)
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

    @staticmethod
    def _normalize_code_text(raw: str) -> str:
        """Normalize Jav codes like 'EBOD -829' to 'EBOD-829' for reliable matching."""
        normalized = re.sub(r"\s*-\s*", "-", (raw or "").strip().upper())
        normalized = re.sub(r"\s+", " ", normalized).strip()
        match = re.search(r"[A-Z0-9]+-[A-Z0-9]+", normalized)
        if match:
            return match.group(0)
        return normalized

    def _find_first_detail_url(self, html: str, code: str) -> Optional[str]:
        """Find the first detail URL from a JavDB search results page."""
        try:
            soup = BeautifulSoup(html, "lxml")
            boxes = soup.select("a.box")
            if not boxes:
                return None

            want = self._normalize_code_text(code)

            # Prefer exact code match from explicit code nodes on the result card.
            for a in boxes:
                code_el = a.select_one(".uid") or a.select_one(".video-title strong")
                if code_el:
                    result_code = self._normalize_code_text(
                        code_el.get_text(" ", strip=True)
                    )
                    if result_code and result_code == want:
                        href = a.get("href")
                        if href:
                            return urljoin(self.BASE_URL, href)

            # Fallback: accept a title that contains the code
            for a in boxes:
                title = self._normalize_code_text(a.get_text(" ", strip=True) or "")
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
        self,
        html: str,
        code: str,
        *,
        detail_url: str | None = None,
    ) -> Optional[ScrapingMetadata]:
        """Parse a JavDB detail page and extract metadata."""
        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception:
            return None

        want_code = self._normalize_code_text(code)

        raw_id = self._text_after_label(soup, self._LABEL_CODE)
        if raw_id:
            page_code = self._normalize_code_text(raw_id)
            if page_code and page_code != want_code:
                return None

        current_title = self._pick_text(soup, "h2.title strong.current-title")
        fallback_title = self._pick_text(soup, "h2.title")
        title_text = current_title or fallback_title
        if not title_text:
            return None

        actors = self._links_after_label(soup, self._LABEL_ACTORS)
        plot = self._extract_plot(soup, title_text=title_text, code=want_code)
        studio_links = self._links_after_label(soup, self._LABEL_STUDIO)
        studio = studio_links[0] if studio_links else ""
        release_raw = self._text_after_label(soup, self._LABEL_RELEASE).strip()
        runtime_raw = self._text_after_label(soup, self._LABEL_RUNTIME).strip()
        rating_raw = self._text_after_label(soup, self._LABEL_RATING).strip()

        return ScrapingMetadata(
            code=want_code,
            title=want_code,
            original_title=self._extract_original_title(soup, code=want_code, title_text=title_text),
            plot=plot,
            website=self._normalize_detail_url(detail_url, want_code),
            actors=actors,
            studio=studio,
            release=self._normalize_release(release_raw) if release_raw else "",
            runtime_minutes=self._extract_runtime_minutes(runtime_raw),
            directors=self._links_after_label(soup, self._LABEL_DIRECTORS),
            tags=self._links_after_label(soup, self._LABEL_TAGS),
            rating=self._extract_rating_value(rating_raw),
            votes=self._extract_vote_count(rating_raw),
            poster_url=self._extract_cover_url(soup),
            fanart_url=self._extract_cover_url(soup),
            preview_urls=self._extract_preview_urls(soup),
        )

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

    def _extract_plot(self, soup: BeautifulSoup, *, title_text: str, code: str) -> str:
        """Extract plot, preferring explicit description blocks and then title sentence."""
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

        title_based_plot = self._extract_plot_from_title(title_text, code)
        if title_based_plot:
            return title_based_plot
        return ""

    def _extract_cover_url(self, soup: BeautifulSoup) -> str:
        """Extract the high-quality cover image URL from the detail page."""
        cover_el = soup.select_one("img.video-cover")
        if cover_el and cover_el.get("src"):
            return urljoin(self.BASE_URL, cover_el["src"])
        return ""

    def _extract_preview_urls(self, soup: BeautifulSoup) -> list[str]:
        preview_urls: list[str] = []
        for anchor in soup.select("div.preview-images a.tile-item"):
            href = (anchor.get("href") or "").strip()
            if href:
                preview_urls.append(urljoin(self.BASE_URL, href))
                continue
            image = anchor.select_one("img")
            src = (image.get("src") or "").strip() if image else ""
            if src:
                preview_urls.append(urljoin(self.BASE_URL, src))
        return list(dict.fromkeys(preview_urls))

    @staticmethod
    def _extract_runtime_minutes(raw: str) -> int | None:
        match = re.search(r"(\d+)", raw or "")
        return int(match.group(1)) if match else None

    @staticmethod
    def _extract_rating_value(raw: str) -> str:
        match = re.search(r"([0-9]+(?:\.[0-9]+)?)", raw or "")
        return match.group(1) if match else ""

    @staticmethod
    def _extract_vote_count(raw: str) -> int | None:
        for pattern in (r"由\s*(\d+)\s*人", r"(\d+)\s*人評價", r"(\d+)\s*votes?"):
            match = re.search(pattern, raw or "", re.IGNORECASE)
            if match:
                return int(match.group(1))
        return None

    @staticmethod
    def _extract_plot_from_title(title_text: str, code: str) -> str:
        text = re.sub(r"\s+", " ", title_text or "").strip()
        if not text:
            return ""

        want_code = (code or "").strip().upper()
        if want_code and text.upper().startswith(want_code):
            text = text[len(want_code):].strip().lstrip("-:： ").strip()

        sentence_match = re.search(r"^(.+?[。！？!?])(?:\s|$)", text)
        if sentence_match:
            candidate = sentence_match.group(1).strip()
            if candidate and candidate.upper() != want_code:
                return candidate

        return ""

    def _extract_original_title(self, soup: BeautifulSoup, *, code: str, title_text: str) -> str:
        original_title = self._pick_text(soup, "h2.title span.origin-title")
        if original_title:
            return original_title

        normalized = re.sub(r"\s+", " ", title_text or "").strip()
        if normalized and normalized.upper() != (code or "").upper():
            return normalized
        return code

    def _normalize_detail_url(self, detail_url: str | None, code: str) -> str:
        if detail_url:
            return self._with_locale(detail_url, "zh")
        return self._with_locale(f"{self.BASE_URL}/v/{code}", "zh")

    @staticmethod
    def _with_locale(url: str, locale: str) -> str:
        parsed = urlparse(urljoin(JavDBCrawler.BASE_URL, url))
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query["locale"] = locale
        return urlunparse(parsed._replace(query=urlencode(query)))

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
