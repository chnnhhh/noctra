"""Firecrawl-based metadata provider using search + scrape."""

import json
import logging
import os
import re
from dataclasses import replace as _replace
from typing import Any, Optional

import aiohttp

from .metadata import ScrapingMetadata

logger = logging.getLogger("uvicorn.error")

FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY", "")
FIRECRAWL_SEARCH_URL = "https://api.firecrawl.dev/v2/search"
FIRECRAWL_SCRAPE_URL = "https://api.firecrawl.dev/v2/scrape"

# LLM translation config
LLM_BASE_URL = os.getenv("NOCTRA_LLM_BASE_URL", "http://acyua.com:18082")
LLM_MODEL = os.getenv("NOCTRA_LLM_MODEL", "qwen3.7-max")
LLM_TIMEOUT = int(os.getenv("NOCTRA_LLM_TIMEOUT_SECONDS", "60"))


class FirecrawlMetadataProvider:
    """Metadata provider that uses Firecrawl search to find JAV info."""

    def __init__(self) -> None:
        self.diagnostics: list[dict] = []
        self.last_error: str | None = None

    def _record(self, message: str, level: str = "info") -> None:
        self.diagnostics.append({"message": message, "level": level})
        if level == "error":
            logger.error("firecrawl: %s", message)
        elif level == "warning":
            logger.warning("firecrawl: %s", message)
        else:
            logger.info("firecrawl: %s", message)

    async def crawl(self, code: str) -> Optional[ScrapingMetadata]:
        """Search for a JAV code via Firecrawl and parse metadata from results."""
        self.diagnostics = []
        self.last_error = None

        api_key = FIRECRAWL_API_KEY or os.getenv("FIRECRAWL_API_KEY", "")
        if not api_key:
            self._set_error("未配置 FIRECRAWL_API_KEY")
            return None

        code_upper = code.strip().upper()
        self._record(f"正在搜索 {code_upper}")

        # Step 1: Search
        search_results = await self._search(api_key, code_upper)
        if search_results is None:
            return None

        self._record(f"搜索结果: {len(search_results)} 条")

        # Step 2: Parse metadata from search results
        metadata = self._extract_metadata(search_results, code_upper)
        if metadata is None:
            self._set_error(f"Firecrawl 搜索未找到 {code_upper} 的有效元数据")
            return None

        self._record(f"元数据提取成功: {metadata.title}")

        # If plot is empty, use title as plot (javtrailers title contains the description)
        if not metadata.plot and metadata.title:
            metadata = _replace(metadata, plot=metadata.title)

        # Step 3: Translate Japanese fields to Chinese
        translated = await self._translate_metadata(metadata)
        if translated:
            self._record("中文翻译完成")
            return translated

        return metadata

    def _set_error(self, message: str) -> None:
        self.last_error = message
        self._record(message, level="error")

    # --- Search ---

    async def _search(self, api_key: str, code: str) -> list[dict] | None:
        """Call Firecrawl search API with scrapeOptions."""
        payload = {
            "query": f"{code} JAV",
            "country": "JP",
            "location": "Japan",
            "limit": 5,
            "scrapeOptions": {
                "formats": ["markdown"],
            },
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=90)
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.post(FIRECRAWL_SEARCH_URL, json=payload) as resp:
                    if resp.status >= 400:
                        text = await resp.text()
                        self._set_error(f"Firecrawl search HTTP {resp.status}: {text[:200]}")
                        return None
                    body = await resp.json()
        except Exception as exc:
            self._set_error(f"Firecrawl search 异常: {exc}")
            return None

        if not body.get("success"):
            self._set_error(f"Firecrawl search 返回失败")
            return None

        return body.get("data", {}).get("web", [])

    # --- Metadata extraction ---

    def _extract_metadata(self, results: list[dict], code: str) -> Optional[ScrapingMetadata]:
        """Extract metadata from search results, prioritizing javtrailers and av-wiki."""
        javtrailers_data = None
        avwiki_data = None
        other_data = None

        for result in results:
            url = result.get("url", "")
            md = result.get("markdown", "")
            if not md:
                continue

            if "javtrailers.com" in url:
                javtrailers_data = self._parse_javtrailers(md, code)
            elif "av-wiki.net" in url:
                avwiki_data = self._parse_avwiki(md, code)
            elif other_data is None:
                other_data = self._parse_generic(md, code)

        # Merge: javtrailers as primary, av-wiki as supplement
        if javtrailers_data or avwiki_data:
            merged = self._merge_sources(javtrailers_data, avwiki_data, other_data)
            if merged and merged.title:
                return merged

        # Fallback to any parseable result
        if other_data and other_data.title:
            return other_data

        return None

    def _parse_javtrailers(self, md: str, code: str) -> dict[str, Any] | None:
        """Parse javtrailers.com markdown for structured metadata."""
        data: dict[str, Any] = {}

        # Title from h1
        title_match = re.search(r"^# (.+)$", md, re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()
            # Remove the code prefix if present
            title = re.sub(r"^" + re.escape(code) + r"\s*", "", title, flags=re.IGNORECASE)
            data["title"] = title

        # Key-value fields
        for pattern, key in [
            (r"DVD ID:\s*(.+)", "dvd_id"),
            (r"Content ID:\s*(.+)", "content_id"),
            (r"Release Date:\s*(.+)", "release_date"),
            (r"Duration:\s*(\d+)\s*mins?", "duration"),
            (r"Director:\s*(.+)", "director"),
            (r"Studio:\s*\[(.+?)\]", "studio"),
            (r"Series:\s*\[(.+?)\]", "series"),
        ]:
            m = re.search(pattern, md)
            if m:
                data[key] = m.group(1).strip()

        # Cast: Cast(s): [Name1](url) [Name2](url)
        cast_match = re.search(r"Cast\(s\):\s*(.+?)(?:\n|$)", md)
        if cast_match:
            actors = re.findall(r"\[([^\]]+)\]\(", cast_match.group(1))
            # Extract Japanese names: "Mina Kitano 北野未奈" -> "北野未奈"
            cleaned = []
            for actor in actors:
                # Try to get Japanese name (last part after space)
                parts = actor.strip().split()
                jp_name = None
                for part in reversed(parts):
                    if re.search(r"[\u3040-\u9fff]", part):
                        jp_name = part
                        break
                cleaned.append(jp_name or actor.strip())
            data["actors"] = cleaned

        # Categories
        cat_match = re.search(r"Categories:\s*(.+?)(?:\n|$)", md)
        if cat_match:
            tags = re.findall(r"\[([^\]]+)\]\(", cat_match.group(1))
            data["tags"] = tags

        # Cover image
        img_match = re.search(r"https://images\.javtrailers\.com/[^\s\)]+\.(?:webp|jpg|png)", md)
        if img_match:
            data["poster_url"] = img_match.group(0)

        return data if data.get("title") or data.get("dvd_id") else None

    def _parse_avwiki(self, md: str, code: str) -> dict[str, Any] | None:
        """Parse av-wiki.net markdown for Japanese metadata."""
        data: dict[str, Any] = {}

        # Title from h1 or first bold
        title_match = re.search(r"【" + re.escape(code) + r"】(.+)", md, re.IGNORECASE)
        if title_match:
            data["title"] = title_match.group(1).strip()

        # Structured table-like fields
        for pattern, key in [
            (r"メーカー\s*(.+?)(?:レーベル|$)", "studio"),
            (r"レーベル\s*(.+?)(?:シリーズ|$)", "label"),
            (r"シリーズ\s*(.+?)(?:AV女優|$)", "series"),
            (r"メーカー品番\s*(\S+)", "product_code"),
            (r"FANZA品番\s*(\S+)", "fanza_code"),
            (r"配信開始日\s*(\d{4}-\d{2}-\d{2})", "release_date"),
        ]:
            m = re.search(pattern, md)
            if m:
                data[key] = m.group(1).strip()

        # Actors: links to av-actress pages
        actors = re.findall(r"\[([^\]]+)\]\(https://av-wiki\.net/av-actress/", md)
        if actors:
            data["actors"] = actors

        return data if data.get("title") or data.get("product_code") else None

    def _parse_generic(self, md: str, code: str) -> dict[str, Any] | None:
        """Try to extract basic metadata from any markdown result."""
        data: dict[str, Any] = {}
        code_lower = code.lower().replace("-", "")

        # Look for release date
        date_match = re.search(r"(?:Release Date|配信開始日|発売日)[:\s]*(\d{4}[-/]\d{2}[-/]\d{2}|\d{2}\s+\w+\s+\d{4})", md)
        if date_match:
            data["release_date"] = date_match.group(1)

        # Look for studio
        studio_match = re.search(r"(?:Studio|メーカー|制作)[:\s]*(.+?)(?:\n|$)", md)
        if studio_match:
            data["studio"] = studio_match.group(1).strip()[:50]

        return data if data else None

    def _merge_sources(
        self,
        jt: dict[str, Any] | None,
        aw: dict[str, Any] | None,
        other: dict[str, Any] | None,
    ) -> Optional[ScrapingMetadata]:
        """Merge metadata from multiple sources into ScrapingMetadata."""
        jt = jt or {}
        aw = aw or {}
        other = other or {}

        # Title: prefer av-wiki Japanese title
        original_title = aw.get("title") or jt.get("title", "")
        title = original_title  # Will be translated later

        # Actors: prefer av-wiki (Japanese names), supplement from javtrailers
        actors = aw.get("actors") or jt.get("actors", [])

        # Studio
        studio = aw.get("studio") or jt.get("studio", "")

        # Release date
        release = aw.get("release_date") or jt.get("release_date") or other.get("release_date", "")
        # Normalize date format
        if release:
            # "02 Jan 2026" -> "2026-01-02"
            from datetime import datetime
            for fmt in ["%d %b %Y", "%Y-%m-%d", "%Y/%m/%d"]:
                try:
                    dt = datetime.strptime(release.strip(), fmt)
                    release = dt.strftime("%Y-%m-%d")
                    break
                except ValueError:
                    continue

        # Duration
        runtime = None
        dur = jt.get("duration")
        if dur:
            try:
                runtime = int(dur)
            except (ValueError, TypeError):
                pass

        # Director
        directors = []
        director = jt.get("director", "")
        if director:
            directors = [director]

        # Series
        series = aw.get("series") or jt.get("series", "")

        # Tags
        tags = jt.get("tags", [])

        # Label
        label = aw.get("label", "")

        # Images
        poster_url = jt.get("poster_url", "")

        # Code
        code = jt.get("dvd_id") or aw.get("product_code") or other.get("dvd_id", "")

        return ScrapingMetadata(
            code=code,
            title=title,
            original_title=original_title,
            plot="",
            actors=actors,
            studio=studio,
            release=release,
            runtime_minutes=runtime,
            directors=directors,
            tags=tags,
            label=label,
            series=series,
            poster_url=poster_url,
        )

    # --- LLM Translation ---

    async def _translate_metadata(self, metadata: ScrapingMetadata) -> Optional[ScrapingMetadata]:
        """Translate Japanese/English metadata fields to Chinese using LLM."""
        # Skip if title already looks like Chinese
        if metadata.title and re.search(r"[\u4e00-\u9fff]", metadata.title):
            # Title has Chinese characters, likely already translated
            return None

        # Check if there's anything to translate
        if not metadata.title and not metadata.actors and not metadata.tags:
            return None

        try:
            translated = await self._call_llm_translation(metadata)
            if translated:
                return _replace(
                    metadata,
                    title=translated.get("title", metadata.title),
                    plot=translated.get("plot", metadata.plot),
                    tags=translated.get("tags", metadata.tags),
                    series=translated.get("series", metadata.series),
                )
        except Exception as exc:
            self._record(f"翻译失败: {type(exc).__name__}: {exc}", level="warning")

        return None

    async def _call_llm_translation(self, metadata: ScrapingMetadata) -> dict | None:
        """Call LLM for translation via Chat Completions API."""
        source = {
            "title": metadata.title,
            "plot": metadata.plot,
            "tags": metadata.tags,
            "series": metadata.series,
        }

        prompt = f"""你是影视资料库元数据翻译器。请把输入 JSON 中的元数据（可能是日文或英文）翻译成简体中文。

要求：
- 只翻译已有字段，不要搜索，不要补充新情节，不要添加来源外信息。
- 保持资料库中性的表达；成人题材只做克制、概括式翻译，不扩写露骨细节。
- 不翻译番号、人名、厂商名、厂牌名、URL、日期、时长。
- 如果某个字段无法翻译或你不确定，就返回空字符串或空数组。
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

        base_url = LLM_BASE_URL.rstrip("/")
        url = f"{base_url}/v1/chat/completions" if not base_url.endswith("/v1") else f"{base_url}/chat/completions"

        payload = {
            "model": LLM_MODEL,
            "messages": [
                {"role": "system", "content": "You are a JSON-only translator. Respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 1600,
            "response_format": {"type": "json_object"},
        }

        timeout = aiohttp.ClientTimeout(total=LLM_TIMEOUT)
        headers = {"Content-Type": "application/json"}

        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.post(url, json=payload) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    self._record(f"LLM 翻译 HTTP {resp.status}: {text[:120]}", level="warning")
                    return None
                body = await resp.json()
                self._record(f"LLM 响应: {json.dumps(body, ensure_ascii=False)[:200]}")

        # Parse Chat Completions response
        choices = body.get("choices", [])
        if choices and isinstance(choices[0], dict):
            content = choices[0].get("message", {}).get("content", "")
        else:
            content = ""

        if not content:
            return None

        # Strip markdown code blocks
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r"^```(?:json)?\s*", "", content)
            content = re.sub(r"\s*```$", "", content)

        # Extract JSON
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", content, re.DOTALL)
            if match:
                try:
                    return json.loads(match.group(0))
                except json.JSONDecodeError:
                    pass
            self._record(f"LLM 翻译返回非 JSON: {content[:100]}", level="warning")
            return None
