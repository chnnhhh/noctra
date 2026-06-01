"""Official/DMM metadata provider with optional LLM-assisted extraction."""

import asyncio
import json
import os
import re
from dataclasses import dataclass, field, replace
from typing import Any

import aiohttp
from bs4 import BeautifulSoup
from curl_cffi import requests

from .base import BaseCrawler
from .metadata import ScrapingMetadata
from .proxy import get_proxy_for_url


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "ja,en-US;q=0.8,en;q=0.7,zh-CN;q=0.6,zh;q=0.5",
}
DMM_HEADERS = {
    **DEFAULT_HEADERS,
    "Cookie": "age_check_done=1",
}


@dataclass(frozen=True)
class CodeVariants:
    code_with_hyphen: str
    plain_code: str
    mono_cid: str
    digital_cid: str
    lower_hyphen_code: str


@dataclass
class ExtractedMetadata:
    title: str = ""
    plot: str = ""
    actors: list[str] = field(default_factory=list)
    release_date: str = ""
    runtime_minutes: int | None = None
    director: str = ""
    maker: str = ""
    label: str = ""
    series: str = ""
    tags: list[str] = field(default_factory=list)
    rating: str = ""
    votes: int | None = None
    cover_image_urls: list[str] = field(default_factory=list)
    product_page_urls: list[str] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    confidence: str = "low"


@dataclass
class TranslatedMetadata:
    title: str = ""
    plot: str = ""
    tags: list[str] = field(default_factory=list)
    series: str = ""


class OfficialMetadataProvider(BaseCrawler):
    """Fetch known official/DMM pages and convert them to ScrapingMetadata."""

    name = "official"

    TAKARA_BASE_URL = "https://takara-tv.jp"
    DMM_DETAIL_URL = "https://www.dmm.co.jp/mono/dvd/-/detail/=/cid={mono_cid}/"
    DMM_VIDEO_DETAIL_URL = "https://video.dmm.co.jp/av/content/?id={digital_cid}"
    TAKARA_DETAIL_URL = "https://takara-tv.jp/dvd_detail.php?code={code}"
    TAKARA_COVER_URL = "https://takara-tv.jp/product/l/{lower_hyphen_code}.jpg"
    DMM_MONO_COVER_URL = (
        "https://pics.dmm.co.jp/mono/movie/adult/{mono_cid}/{mono_cid}pl.jpg"
    )
    DMM_DIGITAL_COVER_URL = (
        "https://pics.dmm.co.jp/digital/video/{digital_cid}/{digital_cid}pl.jpg"
    )
    DMM_LEADING_ONE_DIGITAL_PREFIXES = {"FSDSS"}

    REQUEST_TIMEOUT_SECONDS = 25
    LLM_TIMEOUT_SECONDS = 60

    async def crawl(self, code: str) -> ScrapingMetadata | None:
        self._reset_diagnostics()
        try:
            variants = normalize_code_variants(code)
        except ValueError as exc:
            self._set_error(str(exc))
            return None

        self._record_diagnostic(
            f"已标准化番号：{variants.code_with_hyphen} / {variants.digital_cid}"
        )

        page_html: dict[str, str] = {}
        page_urls: dict[str, str] = {}

        takara_html, takara_url = await self._fetch_takara_detail(variants)
        if takara_html and takara_url:
            page_html["takara"] = takara_html
            page_urls["takara"] = takara_url

        dmm_html, dmm_url = await self._fetch_dmm_detail(variants)
        if dmm_html and dmm_url:
            page_html["dmm"] = dmm_html
            page_urls["dmm"] = dmm_url

        validated_covers = await self._validated_cover_urls(variants, page_html)
        deterministic = self._extract_deterministic(
            variants,
            page_html=page_html,
            page_urls=page_urls,
            cover_urls=validated_covers,
        )

        llm_result = await self._extract_with_llm(
            variants,
            page_html=page_html,
            page_urls=page_urls,
            cover_urls=validated_covers,
        )
        extracted = merge_metadata(deterministic, llm_result)

        if not extracted.title and not extracted.actors and not extracted.cover_image_urls:
            self._set_error(
                f"官方/DMM 来源没有找到匹配番号 {variants.code_with_hyphen} 的元数据"
            )
            return None

        metadata = self._to_scraping_metadata(variants, extracted)
        metadata = await self._translate_for_nfo(metadata)

        self._record_diagnostic("官方/DMM 元数据抽取成功")
        return metadata

    async def _fetch_takara_detail(
        self,
        variants: CodeVariants,
    ) -> tuple[str | None, str | None]:
        candidates = [
            self.TAKARA_DETAIL_URL.format(code=variants.code_with_hyphen),
            self.TAKARA_DETAIL_URL.format(code=variants.lower_hyphen_code),
        ]
        for url in candidates:
            html = await self._fetch_text(url, context="Takara 详情页", headers=DEFAULT_HEADERS)
            if html and self._looks_like_takara_product(html, variants):
                return html, url
        return None, None

    async def _fetch_dmm_detail(
        self,
        variants: CodeVariants,
    ) -> tuple[str | None, str | None]:
        for url in self._dmm_detail_candidates(variants):
            html = await self._fetch_text(url, context="DMM 详情页", headers=DMM_HEADERS)
            if html and self._looks_like_dmm_product(html, variants, url):
                return html, url
        return None, None

    async def _fetch_text(
        self,
        url: str,
        *,
        context: str,
        headers: dict[str, str],
    ) -> str | None:
        self._record_diagnostic(f"正在请求 {context}")

        def request() -> str | None:
            if self._session is None:
                self._session = requests.Session()
            kwargs: dict[str, Any] = {
                "headers": headers,
                "timeout": self.REQUEST_TIMEOUT_SECONDS,
                "verify": False,
                "impersonate": "chrome",
            }
            proxy = get_proxy_for_url(url)
            if proxy:
                kwargs["proxy"] = proxy
            response = self._session.get(url, **kwargs)
            if response.status_code != 200:
                self._record_diagnostic(
                    f"{context}返回 HTTP {response.status_code}",
                    level="warning",
                )
                return None
            return response.text

        try:
            text = await asyncio.to_thread(request)
        except Exception as exc:
            self._session = None
            self._record_diagnostic(f"{context}请求异常：{exc}", level="warning")
            return None

        if text:
            self._record_diagnostic(f"{context}请求成功")
        return text

    async def _validated_cover_urls(
        self,
        variants: CodeVariants,
        page_html: dict[str, str],
    ) -> list[str]:
        digital_cover_urls = [
            self.DMM_DIGITAL_COVER_URL.format(digital_cid=digital_cid)
            for digital_cid in self._dmm_digital_cids(variants)
        ]
        candidates = [
            self.TAKARA_COVER_URL.format(lower_hyphen_code=variants.lower_hyphen_code),
        ]
        if self._uses_leading_one_digital_cid(variants):
            candidates.extend(digital_cover_urls)
            candidates.append(self.DMM_MONO_COVER_URL.format(mono_cid=variants.mono_cid))
        else:
            candidates.append(self.DMM_MONO_COVER_URL.format(mono_cid=variants.mono_cid))
            candidates.extend(digital_cover_urls)
        candidates.extend(self._extract_dmm_cover_candidates(page_html.get("dmm", "")))

        validated: list[str] = []
        for url in unique_non_empty(candidates):
            if await self._check_image_url(url):
                validated.append(url)
        if validated:
            self._record_diagnostic(f"已验证封面候选 {len(validated)} 个")
        return validated

    async def _check_image_url(self, url: str) -> bool:
        def request() -> bool:
            if self._session is None:
                self._session = requests.Session()
            kwargs: dict[str, Any] = {
                "headers": DEFAULT_HEADERS,
                "timeout": self.REQUEST_TIMEOUT_SECONDS,
                "verify": False,
                "impersonate": "chrome",
            }
            proxy = get_proxy_for_url(url)
            if proxy:
                kwargs["proxy"] = proxy
            try:
                response = self._session.head(url, **kwargs)
                if response.status_code == 405:
                    response = self._session.get(url, **kwargs)
            except AttributeError:
                response = self._session.get(url, **kwargs)
            content_type = ""
            try:
                content_type = response.headers.get("content-type", "")
            except Exception:
                content_type = ""
            final_url = str(getattr(response, "url", "") or "")
            if "now_printing" in final_url:
                return False
            return response.status_code == 200 and content_type.lower().startswith("image/")

        try:
            return await asyncio.to_thread(request)
        except Exception as exc:
            self._session = None
            self._record_diagnostic(f"封面候选校验失败：{url} ({exc})", level="warning")
            return False

    def _extract_deterministic(
        self,
        variants: CodeVariants,
        *,
        page_html: dict[str, str],
        page_urls: dict[str, str],
        cover_urls: list[str],
    ) -> ExtractedMetadata:
        result = ExtractedMetadata(
            cover_image_urls=cover_urls[:2],
            product_page_urls=[page_urls[key] for key in ("takara", "dmm") if key in page_urls],
        )

        if "takara" in page_html:
            takara = self._parse_takara(page_html["takara"], variants)
            result = merge_metadata(result, takara)

        if "dmm" in page_html:
            dmm = self._parse_dmm(page_html["dmm"], variants, page_urls.get("dmm", ""))
            result = merge_metadata(result, dmm)

        result.cover_image_urls = cover_urls[:2] or result.cover_image_urls
        result.product_page_urls = unique_non_empty(result.product_page_urls)
        if result.title:
            result.confidence = "high" if result.actors or result.maker else "medium"
        return result

    def _parse_takara(self, html: str, variants: CodeVariants) -> ExtractedMetadata:
        soup = BeautifulSoup(html, "lxml")
        table = soup.select_one("table.product_i")
        if not table:
            return ExtractedMetadata()

        fields = {}
        for row in table.select("tr"):
            th = row.find("th")
            td = row.find("td")
            if not th or not td:
                continue
            fields[clean_text(th.get_text(" ", strip=True))] = clean_text(
                td.get_text(" ", strip=True)
            )

        product_code = normalize_code_like(fields.get("品番", ""))
        if product_code and product_code != variants.code_with_hyphen:
            return ExtractedMetadata(
                conflicts=[{
                    "field": "code",
                    "values": [
                        {"source": "takara-tv.jp", "value": product_code},
                        {"source": "input", "value": variants.code_with_hyphen},
                    ],
                }]
            )

        extracted = ExtractedMetadata(
            title=fields.get("タイトル", ""),
            release_date=normalize_japanese_date(fields.get("発売日", "")),
            runtime_minutes=extract_minutes(fields.get("収録時間", "")),
        )
        if extracted.title or extracted.release_date or extracted.runtime_minutes:
            extracted.evidence.append({
                "source": "takara-tv.jp",
                "url": self.TAKARA_DETAIL_URL.format(code=variants.code_with_hyphen),
                "fields": [
                    name
                    for name, value in (
                        ("title", extracted.title),
                        ("releaseDate", extracted.release_date),
                        ("runtimeMinutes", extracted.runtime_minutes),
                    )
                    if value
                ],
            })
        return extracted

    def _parse_dmm(
        self,
        html: str,
        variants: CodeVariants,
        page_url: str = "",
    ) -> ExtractedMetadata:
        soup = BeautifulSoup(html, "lxml")
        title = pick_text(soup, "h1#title") or meta_content(soup, "og:title")

        fields: dict[str, str | list[str]] = {}
        for label_cell in soup.select("td.nw"):
            label = clean_label(label_cell.get_text(" ", strip=True))
            value_cell = label_cell.find_next_sibling("td")
            if not label or not value_cell:
                continue
            links = [
                clean_text(anchor.get_text(" ", strip=True))
                for anchor in value_cell.find_all("a")
            ]
            links = [item for item in links if item]
            if links:
                fields[label] = unique_non_empty(links)
            else:
                fields[label] = clean_text(value_cell.get_text(" ", strip=True))

        product_code = normalize_code_like(str(fields.get("品番", "")))
        if product_code and product_code != variants.code_with_hyphen:
            return ExtractedMetadata(
                conflicts=[{
                    "field": "code",
                    "values": [
                        {"source": "dmm.co.jp", "value": product_code},
                        {"source": "input", "value": variants.code_with_hyphen},
                    ],
                }]
            )

        tags = as_list(fields.get("ジャンル"))
        extracted = ExtractedMetadata(
            title=clean_text(title),
            plot=self._extract_dmm_plot(soup),
            actors=as_list(fields.get("出演者")),
            release_date=normalize_japanese_date(str(fields.get("発売日", ""))),
            runtime_minutes=extract_minutes(str(fields.get("収録時間", ""))),
            director=first_value(fields.get("監督")),
            maker=first_value(fields.get("メーカー")),
            label=first_value(fields.get("レーベル")),
            series=first_value(fields.get("シリーズ")),
            tags=tags,
            rating=self._extract_dmm_rating(soup),
            votes=self._extract_dmm_votes(soup),
            cover_image_urls=unique_non_empty(self._extract_dmm_cover_candidates(html))[:1],
        )
        if any((
            extracted.title,
            extracted.plot,
            extracted.actors,
            extracted.release_date,
            extracted.runtime_minutes,
            extracted.director,
            extracted.maker,
            extracted.label,
            extracted.series,
            extracted.tags,
            extracted.rating,
            extracted.votes,
        )):
            extracted.evidence.append({
                "source": "dmm.co.jp",
                "url": page_url or self.DMM_DETAIL_URL.format(mono_cid=variants.mono_cid),
                "fields": [
                    name
                    for name, value in (
                        ("title", extracted.title),
                        ("plot", extracted.plot),
                        ("actors", extracted.actors),
                        ("releaseDate", extracted.release_date),
                        ("runtimeMinutes", extracted.runtime_minutes),
                        ("director", extracted.director),
                        ("maker", extracted.maker),
                        ("label", extracted.label),
                        ("series", extracted.series),
                        ("tags", extracted.tags),
                        ("rating", extracted.rating),
                        ("votes", extracted.votes),
                    )
                    if value
                ],
            })
        return extracted

    def _extract_dmm_plot(self, soup: BeautifulSoup) -> str:
        for selector in ("p.mg-b20", "div.mg-b20.lh4"):
            for node in soup.select(selector):
                text = clean_plot_text(node.get_text(" ", strip=True))
                if len(text) >= 20:
                    return text
        return ""

    @staticmethod
    def _extract_dmm_rating(soup: BeautifulSoup) -> str:
        rating = pick_text(soup, ".dcd-review__average strong")
        if rating:
            return rating

        for label_cell in soup.select("td.nw"):
            if clean_label(label_cell.get_text(" ", strip=True)) != "平均評価":
                continue
            value_cell = label_cell.find_next_sibling("td")
            image = value_cell.find("img") if value_cell else None
            src = image.get("src", "") if image else ""
            match = re.search(r"/([0-9]{2})\.gif", src)
            if match:
                return str(int(match.group(1)) / 10).rstrip("0").rstrip(".")
        return ""

    @staticmethod
    def _extract_dmm_votes(soup: BeautifulSoup) -> int | None:
        votes = coerce_int(pick_text(soup, ".dcd-review__evaluates strong"))
        if votes is not None:
            return votes
        text = pick_text(soup, ".dcd-review__evaluates")
        match = re.search(r"総評価数\s*(\d+)", text)
        return int(match.group(1)) if match else None

    def _extract_dmm_cover_candidates(self, html: str) -> list[str]:
        if not html:
            return []
        soup = BeautifulSoup(html, "lxml")
        candidates = [
            meta_content(soup, "og:image"),
            pick_attr(soup, "img[name='package-image']", "src"),
            pick_attr(soup, "img[name='package-image']", "data-lazy"),
        ]
        return [
            url
            for url in unique_non_empty(candidates)
            if is_allowed_cover_url(url)
        ]

    async def _extract_with_llm(
        self,
        variants: CodeVariants,
        *,
        page_html: dict[str, str],
        page_urls: dict[str, str],
        cover_urls: list[str],
    ) -> ExtractedMetadata | None:
        if not should_use_llm():
            self._record_diagnostic("未启用 LLM 抽取，使用确定性解析结果")
            return None

        api_key = os.getenv("NOCTRA_LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            self._record_diagnostic("未配置 LLM API key，使用确定性解析结果")
            return None

        prompt = build_llm_prompt(
            variants,
            page_html=page_html,
            page_urls=page_urls,
            cover_urls=cover_urls,
        )
        payload = {
            "model": os.getenv("NOCTRA_LLM_MODEL", "gpt-5.4-mini"),
            "input": prompt,
            "max_output_tokens": int(os.getenv("NOCTRA_LLM_MAX_OUTPUT_TOKENS", "2200")),
        }
        endpoint = responses_endpoint()
        timeout = aiohttp.ClientTimeout(
            total=int(os.getenv("NOCTRA_LLM_TIMEOUT_SECONDS", str(self.LLM_TIMEOUT_SECONDS)))
        )
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.post(endpoint, json=payload) as response:
                    if response.status >= 400:
                        text = await response.text()
                        self._record_diagnostic(
                            f"LLM 抽取请求失败：HTTP {response.status} {text[:120]}",
                            level="warning",
                        )
                        return None
                    body = await response.json()
        except Exception as exc:
            self._record_diagnostic(f"LLM 抽取异常：{exc}", level="warning")
            return None

        text = extract_response_text(body)
        data = parse_json_object(text)
        if not data:
            self._record_diagnostic("LLM 未返回可解析 JSON，使用确定性解析结果", level="warning")
            return None

        extracted = extracted_from_llm(data, variants, cover_urls)
        if extracted:
            self._record_diagnostic("LLM 元数据抽取成功")
        return extracted

    async def _translate_for_nfo(self, metadata: ScrapingMetadata) -> ScrapingMetadata:
        if not has_llm_api_key():
            self._record_diagnostic("未配置 LLM API key，跳过中文翻译")
            return metadata
        if not has_translatable_text(metadata):
            self._record_diagnostic("没有可翻译字段，跳过中文翻译")
            return metadata

        payload = {
            "model": os.getenv("NOCTRA_LLM_MODEL", "gpt-5.4-mini"),
            "input": build_translation_prompt(metadata),
            "max_output_tokens": 1600,
        }
        endpoint = responses_endpoint()
        timeout = aiohttp.ClientTimeout(
            total=int(os.getenv("NOCTRA_LLM_TIMEOUT_SECONDS", str(self.LLM_TIMEOUT_SECONDS)))
        )
        headers = {
            "Authorization": f"Bearer {os.getenv('NOCTRA_LLM_API_KEY') or os.getenv('OPENAI_API_KEY')}",
            "Content-Type": "application/json",
        }

        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.post(endpoint, json=payload) as response:
                    if response.status >= 400:
                        text = await response.text()
                        self._record_diagnostic(
                            f"中文翻译请求失败：HTTP {response.status} {text[:120]}，保留原文",
                            level="warning",
                        )
                        return metadata
                    body = await response.json()
        except Exception as exc:
            self._record_diagnostic(f"中文翻译异常：{exc}，保留原文", level="warning")
            return metadata

        data = parse_json_object(extract_response_text(body))
        translated = translated_from_llm(data, metadata) if data else None
        if not translated:
            self._record_diagnostic("中文翻译未返回可用 JSON，保留原文", level="warning")
            return metadata

        self._record_diagnostic("中文翻译成功")
        return apply_translation(metadata, translated)

    @staticmethod
    def _looks_like_takara_product(html: str, variants: CodeVariants) -> bool:
        if "table" not in html or "product_i" not in html:
            return False
        return variants.code_with_hyphen in html or variants.lower_hyphen_code in html.lower()

    @classmethod
    def _dmm_digital_cids(cls, variants: CodeVariants) -> list[str]:
        if cls._uses_leading_one_digital_cid(variants):
            return [f"1{variants.digital_cid}"]
        return [variants.digital_cid]

    @classmethod
    def _uses_leading_one_digital_cid(cls, variants: CodeVariants) -> bool:
        prefix = variants.code_with_hyphen.split("-", 1)[0]
        return prefix in cls.DMM_LEADING_ONE_DIGITAL_PREFIXES

    @classmethod
    def _dmm_detail_candidates(cls, variants: CodeVariants) -> list[str]:
        candidates = [
            cls.DMM_DETAIL_URL.format(mono_cid=variants.mono_cid),
        ]
        candidates.extend(
            cls.DMM_VIDEO_DETAIL_URL.format(digital_cid=digital_cid)
            for digital_cid in cls._dmm_digital_cids(variants)
        )
        return unique_non_empty(candidates)

    @classmethod
    def _looks_like_dmm_product(
        cls,
        html: str,
        variants: CodeVariants,
        url: str,
    ) -> bool:
        lower_html = html.lower()
        if "年齢認証" in html or "/age_check" in lower_html:
            return False
        identifiers = [variants.mono_cid, *cls._dmm_digital_cids(variants)]
        if variants.code_with_hyphen in html or any(cid in lower_html for cid in identifiers):
            return True
        lower_url = url.lower()
        return (
            lower_url.startswith("https://video.dmm.co.jp/av/content/")
            and any(f"id={cid}" in lower_url for cid in identifiers)
        )

    @staticmethod
    def _to_scraping_metadata(
        variants: CodeVariants,
        extracted: ExtractedMetadata,
    ) -> ScrapingMetadata:
        cover_urls = unique_non_empty(extracted.cover_image_urls)
        poster_url = cover_urls[1] if len(cover_urls) > 1 else (cover_urls[0] if cover_urls else "")
        fanart_url = cover_urls[0] if cover_urls else ""
        website = first_existing_url(extracted.product_page_urls)
        directors = [extracted.director] if extracted.director else []
        return ScrapingMetadata(
            code=variants.code_with_hyphen,
            title=variants.code_with_hyphen,
            original_title=extracted.title or variants.code_with_hyphen,
            plot=extracted.plot,
            website=website,
            actors=extracted.actors,
            studio=extracted.maker,
            release=extracted.release_date,
            runtime_minutes=extracted.runtime_minutes,
            directors=directors,
            tags=extracted.tags,
            label=extracted.label,
            series=extracted.series,
            rating=extracted.rating,
            votes=extracted.votes,
            poster_url=poster_url,
            fanart_url=fanart_url,
            preview_urls=[],
        )


def normalize_code_variants(code: str) -> CodeVariants:
    raw = clean_text(code).upper()
    match = re.search(r"([A-Z]+)[-_ ]?0*([0-9]+)", raw)
    if not match:
        raise ValueError(f"无法标准化番号：{code}")
    prefix = match.group(1)
    number = match.group(2)
    code_with_hyphen = f"{prefix}-{int(number)}"
    plain_code = f"{prefix}{int(number)}"
    mono_cid = plain_code.lower()
    digital_cid = f"{prefix.lower()}{int(number):05d}"
    return CodeVariants(
        code_with_hyphen=code_with_hyphen,
        plain_code=plain_code,
        mono_cid=mono_cid,
        digital_cid=digital_cid,
        lower_hyphen_code=code_with_hyphen.lower(),
    )


def merge_metadata(
    base: ExtractedMetadata | None,
    override: ExtractedMetadata | None,
) -> ExtractedMetadata:
    if base is None:
        return override or ExtractedMetadata()
    if override is None:
        return base
    return ExtractedMetadata(
        title=override.title or base.title,
        plot=override.plot or base.plot,
        actors=override.actors or base.actors,
        release_date=override.release_date or base.release_date,
        runtime_minutes=override.runtime_minutes if override.runtime_minutes is not None else base.runtime_minutes,
        director=override.director or base.director,
        maker=override.maker or base.maker,
        label=override.label or base.label,
        series=override.series or base.series,
        tags=override.tags or base.tags,
        rating=base.rating or override.rating,
        votes=base.votes if base.votes is not None else override.votes,
        cover_image_urls=unique_non_empty(override.cover_image_urls + base.cover_image_urls),
        product_page_urls=unique_non_empty(override.product_page_urls + base.product_page_urls),
        evidence=(base.evidence or []) + (override.evidence or []),
        conflicts=(base.conflicts or []) + (override.conflicts or []),
        confidence=override.confidence if override.confidence != "low" else base.confidence,
    )


def extracted_from_llm(
    data: dict,
    variants: CodeVariants,
    validated_cover_urls: list[str],
) -> ExtractedMetadata | None:
    code = normalize_code_like(str(data.get("code") or variants.code_with_hyphen))
    if code and code != variants.code_with_hyphen:
        return None

    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    cover_allowlist = set(validated_cover_urls)
    cover_urls = [
        url
        for url in as_list(metadata.get("coverImageUrls"))
        if is_allowed_cover_url(url) and (not cover_allowlist or url in cover_allowlist)
    ]
    return ExtractedMetadata(
        title=clean_text(str(metadata.get("title") or "")),
        plot=clean_plot_text(str(metadata.get("plot") or "")),
        actors=as_list(metadata.get("actors")),
        release_date=normalize_japanese_date(str(metadata.get("releaseDate") or "")),
        runtime_minutes=coerce_int(metadata.get("runtimeMinutes")),
        director=clean_text(str(metadata.get("director") or "")),
        maker=clean_text(str(metadata.get("maker") or "")),
        label=clean_text(str(metadata.get("label") or "")),
        series=clean_text(str(metadata.get("series") or "")),
        tags=as_list(metadata.get("tags")),
        rating=clean_text(str(metadata.get("rating") or "")),
        votes=coerce_int(metadata.get("votes")),
        cover_image_urls=cover_urls,
        product_page_urls=[
            url for url in as_list(metadata.get("productPageUrls")) if is_allowed_product_url(url)
        ],
        evidence=data.get("evidence") if isinstance(data.get("evidence"), list) else [],
        conflicts=data.get("conflicts") if isinstance(data.get("conflicts"), list) else [],
        confidence=confidence_value(data.get("confidence")),
    )


def build_llm_prompt(
    variants: CodeVariants,
    *,
    page_html: dict[str, str],
    page_urls: dict[str, str],
    cover_urls: list[str],
) -> str:
    takara = trim_html_snippet(page_html.get("takara", ""), include_patterns=(
        "product_i",
        variants.code_with_hyphen,
        "タイトル",
        "発売日",
        "収録時間",
    ))
    dmm = trim_html_snippet(page_html.get("dmm", ""), include_patterns=(
        "og:title",
        "og:image",
        "h1 id=\"title\"",
        "発売日",
        "収録時間",
        "出演者",
        "監督",
        "シリーズ",
        "メーカー",
        "レーベル",
        "ジャンル",
        "品番",
        "mg-b20",
        "平均評価",
        "総評価数",
        "dcd-review__average",
        "dcd-review__evaluates",
        variants.mono_cid,
        variants.digital_cid,
    ))
    return f"""你是作品元数据抽取器。下面是程序已按规则抓到的官方/Takara 与 DMM HTML 片段，请只从片段和已验证图片 URL 抽取，不要自由发挥，不要输出露骨剧情。

输入番号：{variants.code_with_hyphen}

标准化结果：
- PLAIN_CODE = {variants.plain_code}
- MONO_CID = {variants.mono_cid}
- DIGITAL_CID = {variants.digital_cid}
- LOWER_HYPHEN_CODE = {variants.lower_hyphen_code}

已验证图片 URL：
{chr(10).join(f"- {url}" for url in cover_urls) or "- 无"}

Takara HTML 片段（URL: {page_urls.get("takara", "")}）：
{takara}

DMM HTML 片段（URL: {page_urls.get("dmm", "")}）：
{dmm}

抽取规则：
- takara-tv.jp 的 table.product_i 中按 th/td 抽取 标题、品番、発売日、収録時間。
- DMM 页用 h1#title 或 og:title 抽标题，用 og:image 或 package image 抽封面。
- DMM 详情表按日文 label 抽 発売日、収録時間、出演者、監督、シリーズ、メーカー、レーベル、ジャンル、品番。
- DMM 的 p.mg-b20 可作为官方简介 plot；只摘取原文，不要扩写或润色。
- DMM 的 dcd-review__average / dcd-review__evaluates 可作为 rating / votes。
- 图片 URL 只保留官方页或 pics.dmm.co.jp 的封面图，不抽样张图。
- 不返回磁力、种子、盗版、在线播放地址。

输出 JSON，不要 Markdown，不要输出无来源推断。非空字段必须有 evidence：
{{
  "code": "",
  "normalized": {{
    "plainCode": "",
    "monoCid": "",
    "digitalCid": "",
    "lowerHyphenCode": ""
  }},
  "metadata": {{
    "title": "",
    "plot": "",
    "actors": [],
    "releaseDate": "",
    "runtimeMinutes": null,
    "director": "",
    "maker": "",
    "label": "",
    "series": "",
    "tags": [],
    "rating": "",
    "votes": null,
    "coverImageUrls": [],
    "productPageUrls": []
  }},
  "evidence": [
    {{"source": "", "url": "", "fields": []}}
  ],
  "conflicts": [],
  "confidence": "high | medium | low"
}}"""


def trim_html_snippet(
    html: str,
    *,
    include_patterns: tuple[str, ...],
    max_lines: int = 240,
) -> str:
    if not html:
        return ""
    lines = html.splitlines()
    selected: list[str] = []
    lowered_patterns = tuple(pattern.lower() for pattern in include_patterns if pattern)
    for index, line in enumerate(lines, start=1):
        lower = line.lower()
        if any(pattern.lower() in lower for pattern in lowered_patterns):
            selected.append(f"{index}: {line.strip()}")
        if len(selected) >= max_lines:
            break
    return "\n".join(selected)


def responses_endpoint() -> str:
    base_url = os.getenv("NOCTRA_LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com"
    base_url = base_url.rstrip("/")
    wire_api = (os.getenv("NOCTRA_LLM_WIRE_API") or "responses").strip().lower()
    if wire_api != "responses":
        return f"{base_url}/v1/responses"
    if base_url.endswith("/v1"):
        return f"{base_url}/responses"
    if base_url.endswith("/v1/responses"):
        return base_url
    return f"{base_url}/v1/responses"


def has_llm_api_key() -> bool:
    return bool(os.getenv("NOCTRA_LLM_API_KEY") or os.getenv("OPENAI_API_KEY"))


def should_use_llm() -> bool:
    value = os.getenv("NOCTRA_LLM_ENABLED")
    if value is not None:
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(os.getenv("NOCTRA_LLM_API_KEY") or os.getenv("OPENAI_API_KEY"))


def has_translatable_text(metadata: ScrapingMetadata) -> bool:
    return any((
        metadata.original_title and metadata.original_title != metadata.code,
        metadata.plot,
        metadata.tags,
        metadata.series,
    ))


def build_translation_prompt(metadata: ScrapingMetadata) -> str:
    source = {
        "code": metadata.code,
        "title": metadata.original_title if metadata.original_title != metadata.code else "",
        "plot": metadata.plot,
        "tags": metadata.tags,
        "series": metadata.series,
    }
    return f"""你是影视资料库元数据翻译器。请把输入 JSON 中已有的日文元数据翻译成简体中文。

要求：
- 只翻译已有字段，不要搜索，不要补充新情节，不要添加来源外信息。
- 保持资料库中性的表达；成人题材只做克制、概括式翻译，不扩写露骨细节。
- 不翻译番号、人名、厂商名、厂牌名、URL、日期、时长。
- 如果某个字段无法翻译或你不确定，就返回空字符串或空数组，让程序保留原文。
- tags 必须逐项翻译，并尽量保持与输入 tags 一一对应。
- 只输出 JSON，不要 Markdown。

输入：
{json.dumps(source, ensure_ascii=False)}

输出格式：
{{
  "title": "",
  "plot": "",
  "tags": [],
  "series": ""
}}"""


def translated_from_llm(data: dict | None, metadata: ScrapingMetadata) -> TranslatedMetadata | None:
    if not isinstance(data, dict):
        return None

    title = usable_translation(data.get("title"), metadata.original_title)
    plot = usable_translation(data.get("plot"), metadata.plot)
    series = usable_translation(data.get("series"), metadata.series)
    tags = translated_tags(data.get("tags"), metadata.tags)

    if not any((title, plot, tags, series)):
        return None
    return TranslatedMetadata(title=title, plot=plot, tags=tags, series=series)


def apply_translation(metadata: ScrapingMetadata, translated: TranslatedMetadata) -> ScrapingMetadata:
    return replace(
        metadata,
        title=translated.title or metadata.title,
        plot=translated.plot or metadata.plot,
        tags=translated.tags or metadata.tags,
        series=translated.series or metadata.series,
    )


def translated_tags(value: Any, original_tags: list[str]) -> list[str]:
    tags = [
        item
        for item in as_list(value)
        if usable_translation(item, "")
    ]
    if not tags:
        return []
    if original_tags and len(tags) != len(original_tags):
        return []
    return tags


def usable_translation(value: Any, original: str) -> str:
    text = clean_text(str(value or ""))
    if not text:
        return ""
    if text == clean_text(original):
        return ""
    lower = text.lower()
    refusal_markers = (
        "i can't",
        "i cannot",
        "cannot assist",
        "sorry",
        "无法翻译",
        "不能翻译",
        "无法提供",
        "不能提供",
    )
    if text.startswith(("抱歉", "对不起")) or any(marker in lower for marker in refusal_markers):
        return ""
    return text


def extract_response_text(body: dict) -> str:
    output = body.get("output")
    if isinstance(output, list):
        pieces: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                if isinstance(part.get("text"), str):
                    pieces.append(part["text"])
        if pieces:
            return "\n".join(pieces)
    if isinstance(body.get("output_text"), str):
        return body["output_text"]
    return ""


def parse_json_object(text: str) -> dict | None:
    text = (text or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None


def normalize_code_like(raw: str) -> str:
    match = re.search(r"([A-Z]+)[-_ ]?0*([0-9]+)", (raw or "").upper())
    if not match:
        return ""
    return f"{match.group(1)}-{int(match.group(2))}"


def normalize_japanese_date(raw: str) -> str:
    text = clean_text(raw)
    match = re.search(r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})", text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    match = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"
    return text


def extract_minutes(raw: str) -> int | None:
    match = re.search(r"(\d+)", raw or "")
    return int(match.group(1)) if match else None


def coerce_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return extract_minutes(value)
    return None


def pick_text(soup: BeautifulSoup, selector: str) -> str:
    element = soup.select_one(selector)
    return clean_text(element.get_text(" ", strip=True)) if element else ""


def pick_attr(soup: BeautifulSoup, selector: str, attr: str) -> str:
    element = soup.select_one(selector)
    return clean_text(element.get(attr, "")) if element else ""


def meta_content(soup: BeautifulSoup, property_name: str) -> str:
    element = soup.find("meta", attrs={"property": property_name})
    if not element:
        element = soup.find("meta", attrs={"name": property_name})
    return clean_text(element.get("content", "")) if element else ""


def clean_label(value: str) -> str:
    return clean_text(value).rstrip(":：")


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def clean_plot_text(value: str) -> str:
    text = clean_text(value)
    for marker in (
        "「コンビニ受取」対象商品です。",
        "詳しくはこちら をご覧ください。",
        "詳しくはこちらをご覧ください。",
    ):
        if marker in text:
            text = text.split(marker, 1)[0]
    boilerplate = (
        "中古品",
        "無料サンプル動画を見る",
        "JavaScriptを有効にして",
        "画像をクリックして拡大",
        "安心な梱包でお届け",
    )
    if any(item in text for item in boilerplate):
        return ""
    return clean_text(text)


def unique_non_empty(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        item = clean_text(str(value or ""))
        if item and item not in result:
            result.append(item)
    return result


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return unique_non_empty([str(item) for item in value])
    return unique_non_empty([str(value)])


def first_value(value: Any) -> str:
    values = as_list(value)
    return values[0] if values else ""


def is_allowed_cover_url(url: str) -> bool:
    return (
        url.startswith("https://takara-tv.jp/product/l/")
        or url.startswith("https://pics.dmm.co.jp/mono/movie/adult/")
        or url.startswith("https://pics.dmm.co.jp/digital/video/")
    )


def is_allowed_product_url(url: str) -> bool:
    return (
        url.startswith("https://takara-tv.jp/dvd_detail.php")
        or url.startswith("https://www.dmm.co.jp/mono/dvd/-/detail/")
    )


def first_existing_url(urls: list[str]) -> str:
    return urls[0] if urls else ""


def confidence_value(value: Any) -> str:
    text = str(value or "").strip().lower()
    return text if text in {"high", "medium", "low"} else "low"
