# tests/test_scrapers/test_javdb.py
"""Tests for JavDB crawler."""

import pytest
from unittest.mock import AsyncMock, patch
from bs4 import BeautifulSoup

from app.scrapers.javdb import JavDBCrawler
from app.scrapers.metadata import ScrapingMetadata


# ---------------------------------------------------------------------------
# Mock HTML fixtures
# ---------------------------------------------------------------------------

SEARCH_HTML_SUCCESS = """
<html>
<body>
  <div class="movie-list">
    <a class="box" href="/v/abcdefg">
      <div class="uid">SSIS-743</div>
      <div class="title">Test Video Title</div>
    </a>
  </div>
</body>
</html>
"""

SEARCH_HTML_EMPTY = """
<html>
<body>
  <div class="movie-list"></div>
</body>
</html>
"""

SEARCH_HTML_TITLE_CODE_ONLY = """
<html>
<body>
  <div class="movie-list">
    <a class="box" href="/v/title-only">
      <div class="video-title">
        <strong>EBOD-829</strong>
        Test Video Title
      </div>
    </a>
  </div>
</body>
</html>
"""

DETAIL_HTML_SUCCESS = """
<html>
<body>
  <div class="container">
    <h2 class="title">
      <strong class="current-title">Test Title - Beautiful Actress</strong>
    </h2>

    <div class="video-meta-panel">
      <div class="panel-block">
        <strong>識別碼:</strong>
        <span class="value">SSIS-743</span>
      </div>
      <div class="panel-block">
        <strong>日期:</strong>
        <span>2024-06-15</span>
      </div>
      <div class="panel-block">
        <strong>片商:</strong>
        <span>
          <a href="/makers/1">S1 NO.1 STYLE</a>
        </span>
      </div>
      <div class="panel-block">
        <strong>演員:</strong>
        <span>
          <a href="/actors/1">Actress A</a>
          <a href="/actors/2">Actress B</a>
        </span>
      </div>
      <div class="panel-block">
        <strong>簡介:</strong>
        <p>這是一段詳細的劇情簡介，描述了這部影片的故事情節和精彩內容。</p>
      </div>
    </div>

    <div class="video-cover-panel">
      <img class="video-cover" src="https://javdb.com/covers/abc/SSIS-743.jpg" />
    </div>
  </div>
</body>
</html>
"""

DETAIL_HTML_ENGLISH_LOCALE = """
<html>
<body>
  <div class="container">
    <h2 class="title">
      <strong class="current-title">English Title Here</strong>
    </h2>

    <div class="video-meta-panel">
      <div class="panel-block">
        <strong>ID:</strong>
        <span class="value">WAAA-585</span>
      </div>
      <div class="panel-block">
        <strong>Released Date:</strong>
        <span>2025-03-21</span>
      </div>
      <div class="panel-block">
        <strong>Maker:</strong>
        <span>
          <a href="/makers/2">Wanz Factory</a>
        </span>
      </div>
      <div class="panel-block">
        <strong>Actors:</strong>
        <span>
          <a href="/actors/3">Performer X</a>
        </span>
      </div>
      <div class="panel-block">
        <strong>Description:</strong>
        <p>A detailed plot description about this wonderful video production.</p>
      </div>
    </div>

    <div class="video-cover-panel">
      <img class="video-cover" src="https://javdb.com/covers/xyz/WAAA-585.jpg" />
    </div>
  </div>
</body>
</html>
"""

DETAIL_HTML_MISSING_FIELDS = """
<html>
<body>
  <div class="container">
    <h2 class="title">
      <strong class="current-title">Partial Title Only</strong>
    </h2>

    <div class="video-meta-panel">
      <div class="panel-block">
        <strong>識別碼:</strong>
        <span class="value">ABC-123</span>
      </div>
    </div>
  </div>
</body>
</html>
"""

DETAIL_HTML_CODE_MISMATCH = """
<html>
<body>
  <div class="container">
    <h2 class="title">
      <strong class="current-title">Wrong Video Title</strong>
    </h2>

    <div class="video-meta-panel">
      <div class="panel-block">
        <strong>識別碼:</strong>
        <span class="value">XYZ-999</span>
      </div>
    </div>
  </div>
</body>
</html>
"""

DETAIL_HTML_CODE_WITH_SPLIT_HYPHEN = """
<html>
<body>
  <div class="container">
    <h2 class="title is-4">
      <strong>EBOD-829</strong>
      <strong class="current-title">Split Code Title</strong>
    </h2>

    <div class="video-meta-panel">
      <div class="panel-block first-block">
        <strong>番號:</strong>
        <span class="value"><a href="/video_codes/EBOD">EBOD</a>-829</span>
      </div>
      <div class="panel-block">
        <strong>日期:</strong>
        <span>2021-06-13</span>
      </div>
      <div class="panel-block">
        <strong>片商:</strong>
        <span>
          <a href="/makers/1">E-BODY</a>
        </span>
      </div>
      <div class="panel-block">
        <strong>演員:</strong>
        <span>
          <a href="/actors/1">北野未奈</a>
        </span>
      </div>
    </div>

    <div class="video-cover-panel">
      <img class="video-cover" src="https://javdb.com/covers/5d/5D8OB.jpg" />
    </div>
  </div>
</body>
</html>
"""

DETAIL_HTML_RICH_METADATA = """
<html>
<body>
  <div class="container">
    <h2 class="title is-4">
      <strong>EBOD-829 </strong>
      <strong class="current-title">輸給女友耳邊呢喃淫語胸部緊貼誘惑中出的我。 北野未奈 </strong>
      <a class="meta-link" href="javascript:;">顯示原標題</a>
      <span class="origin-title" style="display: none">彼女の巨乳お姉さんの囁き淫語と密着おっぱい誘惑に敗北なま中出ししちゃった僕。 北野未奈</span>
    </h2>

    <div class="video-meta-panel">
      <nav class="panel movie-panel-info">
        <div class="panel-block first-block">
          <strong>番號:</strong>
          <span class="value"><a href="/video_codes/EBOD">EBOD</a>-829</span>
        </div>
        <div class="panel-block">
          <strong>日期:</strong>
          <span class="value">2021-06-13</span>
        </div>
        <div class="panel-block">
          <strong>時長:</strong>
          <span class="value">140 分鍾</span>
        </div>
        <div class="panel-block">
          <strong>導演:</strong>
          <span class="value"><a href="/directors/xvV">三島六三郎</a></span>
        </div>
        <div class="panel-block">
          <strong>片商:</strong>
          <span class="value"><a href="/makers/bgA?f=download">E-BODY</a></span>
        </div>
        <div class="panel-block">
          <strong>評分:</strong>
          <span class="value">4.09分, 由487人評價</span>
        </div>
        <div class="panel-block">
          <strong>類別:</strong>
          <span class="value">
            <a href="/tags?c2=48">蕩婦</a>,
            <a href="/tags?c4=17">巨乳</a>,
            <a href="/tags?c7=28">單體作品</a>
          </span>
        </div>
        <div class="panel-block">
          <strong>演員:</strong>
          <span class="value">
            <a href="/actors/1">河奈亜依</a>
            <a href="/actors/2">北野未奈</a>
          </span>
        </div>
      </nav>
    </div>

    <div class="video-cover-panel">
      <img class="video-cover" src="https://c0.jdbstatic.com/covers/5d/5D8OB.jpg" />
    </div>

    <div class="tile-images preview-images">
      <a class="tile-item" href="https://c0.jdbstatic.com/samples/5d/5D8OB_l_0.jpg">
        <img src="https://c0.jdbstatic.com/samples/5d/5D8OB_s_0.jpg" />
      </a>
      <a class="tile-item" href="https://c0.jdbstatic.com/samples/5d/5D8OB_l_1.jpg">
        <img src="https://c0.jdbstatic.com/samples/5d/5D8OB_s_1.jpg" />
      </a>
    </div>
  </div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestJavDBCrawlerInit:
    """Test crawler instantiation."""

    def test_crawler_name(self):
        crawler = JavDBCrawler()
        assert crawler.name == "javdb"

    def test_crawler_base_url(self):
        assert JavDBCrawler.BASE_URL == "https://javdb.com"


class TestJavDBCrawlerCrawlSuccess:
    """Test successful crawl flow."""

    @pytest.mark.asyncio
    async def test_crawl_returns_metadata(self):
        """Full flow: search -> detail -> parse returns ScrapingMetadata."""
        crawler = JavDBCrawler()

        # Mock _request to return search HTML first, then detail HTML
        async def mock_request(url):
            if "/search?" in url:
                return SEARCH_HTML_SUCCESS
            return DETAIL_HTML_SUCCESS

        crawler._request = AsyncMock(side_effect=mock_request)

        result = await crawler.crawl("SSIS-743")

        assert result is not None
        assert isinstance(result, ScrapingMetadata)
        assert result.code == "SSIS-743"
        assert result.title == "SSIS-743"
        assert result.original_title == "Test Title - Beautiful Actress"
        assert result.plot == "這是一段詳細的劇情簡介，描述了這部影片的故事情節和精彩內容。"
        assert result.actors == ["Actress A", "Actress B"]
        assert result.studio == "S1 NO.1 STYLE"
        assert result.release == "2024-06-15"
        assert "/covers/" in result.poster_url
        assert "SSIS-743" in result.poster_url
        assert result.website == "https://javdb.com/v/abcdefg?locale=zh"

    @pytest.mark.asyncio
    async def test_crawl_english_locale(self):
        """Test parsing with English locale labels."""
        crawler = JavDBCrawler()

        async def mock_request(url):
            if "/search?" in url:
                return SEARCH_HTML_SUCCESS
            return DETAIL_HTML_ENGLISH_LOCALE

        crawler._request = AsyncMock(side_effect=mock_request)

        result = await crawler.crawl("WAAA-585")

        assert result is not None
        assert result.title == "WAAA-585"
        assert result.original_title == "English Title Here"
        assert result.studio == "Wanz Factory"
        assert result.actors == ["Performer X"]
        assert result.release == "2025-03-21"
        assert result.plot == "A detailed plot description about this wonderful video production."


class TestJavDBCrawlerCrawlFailure:
    """Test failure cases."""

    @pytest.mark.asyncio
    async def test_crawl_search_returns_none(self):
        """If search request fails, return None."""
        crawler = JavDBCrawler()
        crawler._request = AsyncMock(return_value=None)

        result = await crawler.crawl("SSIS-743")
        assert result is None

    @pytest.mark.asyncio
    async def test_crawl_no_search_results(self):
        """If search returns no results, return None."""
        crawler = JavDBCrawler()

        async def mock_request(url):
            if "/search?" in url:
                return SEARCH_HTML_EMPTY
            return DETAIL_HTML_SUCCESS

        crawler._request = AsyncMock(side_effect=mock_request)

        result = await crawler.crawl("SSIS-743")
        assert result is None

    @pytest.mark.asyncio
    async def test_crawl_detail_returns_none(self):
        """If detail request fails, return None."""
        crawler = JavDBCrawler()

        async def mock_request(url):
            if "/search?" in url:
                return SEARCH_HTML_SUCCESS
            return None  # detail page fails

        crawler._request = AsyncMock(side_effect=mock_request)

        result = await crawler.crawl("SSIS-743")
        assert result is None

    @pytest.mark.asyncio
    async def test_crawl_code_mismatch(self):
        """If detail page code does not match, return None."""
        crawler = JavDBCrawler()

        async def mock_request(url):
            if "/search?" in url:
                return SEARCH_HTML_SUCCESS
            return DETAIL_HTML_CODE_MISMATCH

        crawler._request = AsyncMock(side_effect=mock_request)

        result = await crawler.crawl("SSIS-743")
        assert result is None


class TestJavDBCrawlerPartialFields:
    """Test parsing when some fields are missing."""

    @pytest.mark.asyncio
    async def test_crawl_missing_optional_fields(self):
        """Missing optional fields should have defaults, not fail."""
        crawler = JavDBCrawler()

        async def mock_request(url):
            if "/search?" in url:
                return SEARCH_HTML_SUCCESS
            return DETAIL_HTML_MISSING_FIELDS

        crawler._request = AsyncMock(side_effect=mock_request)

        result = await crawler.crawl("ABC-123")

        assert result is not None
        assert result.code == "ABC-123"
        assert result.title == "ABC-123"
        assert result.original_title == "Partial Title Only"
        assert result.plot == ""
        assert result.actors == []
        assert result.studio == ""
        assert result.release == ""
        assert result.poster_url == ""
        assert result.tags == []
        assert result.directors == []
        assert result.runtime_minutes is None
        assert result.website == "https://javdb.com/v/abcdefg?locale=zh"

    def test_parse_detail_extracts_richer_metadata(self):
        crawler = JavDBCrawler()

        result = crawler._parse_detail(DETAIL_HTML_RICH_METADATA, "EBOD-829")

        assert result is not None
        assert result.title == "EBOD-829"
        assert result.original_title == "彼女の巨乳お姉さんの囁き淫語と密着おっぱい誘惑に敗北なま中出ししちゃった僕。 北野未奈"
        assert result.plot == "輸給女友耳邊呢喃淫語胸部緊貼誘惑中出的我。"
        assert result.release == "2021-06-13"
        assert result.runtime_minutes == 140
        assert result.directors == ["三島六三郎"]
        assert result.tags == ["蕩婦", "巨乳", "單體作品"]
        assert result.rating == "4.09"
        assert result.votes == 487
        assert result.website == "https://javdb.com/v/EBOD-829?locale=zh"
        assert result.poster_url == "https://c0.jdbstatic.com/covers/5d/5D8OB.jpg"
        assert result.fanart_url == "https://c0.jdbstatic.com/covers/5d/5D8OB.jpg"
        assert result.preview_urls == [
            "https://c0.jdbstatic.com/samples/5d/5D8OB_l_0.jpg",
            "https://c0.jdbstatic.com/samples/5d/5D8OB_l_1.jpg",
        ]


class TestJavDBCrawlerNormalizeRelease:
    """Test release date normalization."""

    def test_normalize_standard_format(self):
        assert JavDBCrawler._normalize_release("2024-06-15") == "2024-06-15"

    def test_normalize_with_spaces(self):
        assert JavDBCrawler._normalize_release("2024-06-15 ") == "2024-06-15"

    def test_normalize_slash_format(self):
        assert JavDBCrawler._normalize_release("2024/06/15") == "2024-06-15"

    def test_normalize_embedded_in_text(self):
        result = JavDBCrawler._normalize_release("Released: 2024-06-15")
        assert result == "2024-06-15"


class TestJavDBCrawlerFindFirstDetailUrl:
    """Test detail URL extraction from search results."""

    def test_exact_uid_match(self):
        crawler = JavDBCrawler()
        url = crawler._find_first_detail_url(SEARCH_HTML_SUCCESS, "SSIS-743")
        assert url == "https://javdb.com/v/abcdefg"

    def test_no_results(self):
        crawler = JavDBCrawler()
        url = crawler._find_first_detail_url(SEARCH_HTML_EMPTY, "SSIS-743")
        assert url is None

    def test_case_insensitive_code(self):
        """Code matching should be case-insensitive."""
        crawler = JavDBCrawler()
        url = crawler._find_first_detail_url(SEARCH_HTML_SUCCESS, "ssis-743")
        assert url == "https://javdb.com/v/abcdefg"

    def test_video_title_code_match_when_uid_is_missing(self):
        """Newer JavDB search cards expose code in video-title strong instead of .uid."""
        crawler = JavDBCrawler()
        url = crawler._find_first_detail_url(SEARCH_HTML_TITLE_CODE_ONLY, "EBOD-829")
        assert url == "https://javdb.com/v/title-only"


class TestJavDBCrawlerCodeNormalization:
    """Test normalization for codes rendered with extra spaces."""

    def test_normalize_code_text_strips_spaces_around_hyphen(self):
        assert JavDBCrawler._normalize_code_text(" EBOD -829 ") == "EBOD-829"

    def test_parse_detail_accepts_split_code_rendering(self):
        crawler = JavDBCrawler()
        result = crawler._parse_detail(DETAIL_HTML_CODE_WITH_SPLIT_HYPHEN, "EBOD-829")

        assert result is not None
        assert result.code == "EBOD-829"
        assert result.title == "EBOD-829"
        assert result.original_title == "Split Code Title"
        assert result.release == "2021-06-13"
        assert result.studio == "E-BODY"
        assert result.actors == ["北野未奈"]


class TestJavDBCrawlerExtractCoverUrl:
    """Test cover URL extraction."""

    def test_cover_uses_full_quality_image(self):
        crawler = JavDBCrawler()
        soup = BeautifulSoup(DETAIL_HTML_SUCCESS, "lxml")
        poster = crawler._extract_cover_url(soup)
        assert poster == "https://javdb.com/covers/abc/SSIS-743.jpg"

    def test_no_cover_image(self):
        crawler = JavDBCrawler()
        html = "<html><body><div>No cover here</div></body></html>"
        soup = BeautifulSoup(html, "lxml")
        poster = crawler._extract_cover_url(soup)
        assert poster == ""
