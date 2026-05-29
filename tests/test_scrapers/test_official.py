"""Tests for the official/DMM metadata provider."""

from unittest.mock import AsyncMock, patch

import pytest

from app.scrapers.official import OfficialMetadataProvider, normalize_code_variants


TAKARA_HTML = """
<html>
<body>
  <table class="product_i">
    <tr><th>タイトル</th><td>家庭内愛人契約　北野未奈</td></tr>
    <tr><th>品番</th><td>ALDN-480</td></tr>
    <tr><th>発売日</th><td>2025年7月8日</td></tr>
    <tr><th>収録時間</th><td>140分</td></tr>
  </table>
</body>
</html>
"""


DMM_HTML = """
<html>
<head>
  <meta property="og:title" content="家庭内愛人契約 北野未奈" />
  <meta property="og:image" content="https://pics.dmm.co.jp/mono/movie/adult/aldn480/aldn480pl.jpg" />
</head>
<body>
  <h1 id="title">家庭内愛人契約 北野未奈</h1>
  <img name="package-image" src="https://pics.dmm.co.jp/mono/movie/adult/aldn480/aldn480pl.jpg" />
  <table>
    <tr><td class="nw">発売日：</td><td>2025/07/08</td></tr>
    <tr><td class="nw">収録時間：</td><td>140分</td></tr>
    <tr><td class="nw">出演者：</td><td><a>北野未奈</a></td></tr>
    <tr><td class="nw">監督：</td><td><a>宝浩史</a></td></tr>
    <tr><td class="nw">シリーズ：</td><td><a>家庭内愛人契約</a></td></tr>
    <tr><td class="nw">メーカー：</td><td><a>タカラ映像</a></td></tr>
    <tr><td class="nw">レーベル：</td><td><a>ALEDDIN</a></td></tr>
    <tr><td class="nw">ジャンル：</td>
      <td><a>熟女</a>&nbsp;<a>人妻・主婦</a>&nbsp;<a>巨乳</a></td></tr>
    <tr><td class="nw">品番：</td><td>aldn480</td></tr>
  </table>
</body>
</html>
"""


def test_normalize_code_variants_for_aldn():
    variants = normalize_code_variants("ALDN-480")

    assert variants.code_with_hyphen == "ALDN-480"
    assert variants.plain_code == "ALDN480"
    assert variants.mono_cid == "aldn480"
    assert variants.digital_cid == "aldn00480"
    assert variants.lower_hyphen_code == "aldn-480"


def test_deterministic_extracts_takara_and_dmm_fields():
    provider = OfficialMetadataProvider()
    variants = normalize_code_variants("ALDN-480")
    cover_url = "https://pics.dmm.co.jp/mono/movie/adult/aldn480/aldn480pl.jpg"

    extracted = provider._extract_deterministic(
        variants,
        page_html={"takara": TAKARA_HTML, "dmm": DMM_HTML},
        page_urls={
            "takara": "https://takara-tv.jp/dvd_detail.php?code=ALDN-480",
            "dmm": "https://www.dmm.co.jp/mono/dvd/-/detail/=/cid=aldn480/",
        },
        cover_urls=[cover_url],
    )

    assert extracted.title == "家庭内愛人契約 北野未奈"
    assert extracted.actors == ["北野未奈"]
    assert extracted.release_date == "2025-07-08"
    assert extracted.runtime_minutes == 140
    assert extracted.director == "宝浩史"
    assert extracted.maker == "タカラ映像"
    assert extracted.label == "ALEDDIN"
    assert extracted.series == "家庭内愛人契約"
    assert extracted.tags == ["熟女", "人妻・主婦", "巨乳"]
    assert extracted.cover_image_urls == [cover_url]


@pytest.mark.asyncio
async def test_crawl_returns_scraping_metadata_without_llm():
    provider = OfficialMetadataProvider()
    cover_urls = [
        "https://takara-tv.jp/product/l/aldn-480.jpg",
        "https://pics.dmm.co.jp/mono/movie/adult/aldn480/aldn480pl.jpg",
    ]

    provider._fetch_takara_detail = AsyncMock(
        return_value=(TAKARA_HTML, "https://takara-tv.jp/dvd_detail.php?code=ALDN-480")
    )
    provider._fetch_text = AsyncMock(return_value=DMM_HTML)
    provider._validated_cover_urls = AsyncMock(return_value=cover_urls)

    with patch.dict("os.environ", {"NOCTRA_LLM_ENABLED": "0"}, clear=False):
        metadata = await provider.crawl("ALDN-480")

    assert metadata is not None
    assert metadata.code == "ALDN-480"
    assert metadata.title == "ALDN-480"
    assert metadata.original_title == "家庭内愛人契約 北野未奈"
    assert metadata.actors == ["北野未奈"]
    assert metadata.release == "2025-07-08"
    assert metadata.runtime_minutes == 140
    assert metadata.directors == ["宝浩史"]
    assert metadata.studio == "タカラ映像"
    assert metadata.tags == ["熟女", "人妻・主婦", "巨乳"]
    assert metadata.fanart_url == cover_urls[0]
    assert metadata.poster_url == cover_urls[1]
    assert metadata.preview_urls == []
