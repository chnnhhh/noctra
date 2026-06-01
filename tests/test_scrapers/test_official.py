"""Tests for the official/DMM metadata provider."""

from unittest.mock import AsyncMock, patch

import pytest

from app.scrapers.metadata import ScrapingMetadata
from app.scrapers.official import (
    ExtractedMetadata,
    OfficialMetadataProvider,
    TranslatedMetadata,
    apply_translation,
    merge_metadata,
    normalize_code_variants,
    translated_from_llm,
)


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
  <p class="mg-b20">家庭内で交わされた契約をめぐる紹介文です。 「コンビニ受取」対象商品です。</p>
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
  <div class="dcd-review__points">
    <p class="dcd-review__average">平均評価 <strong>4.35</strong></p>
    <p class="dcd-review__evaluates">総評価数 <strong>23</strong></p>
  </div>
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


def test_dmm_fsdss_candidates_include_confirmed_fanza_digital_cid():
    provider = OfficialMetadataProvider()
    variants = normalize_code_variants("FSDSS-615")

    assert provider._dmm_digital_cids(variants) == ["1fsdss00615"]
    assert provider._dmm_detail_candidates(variants) == [
        "https://www.dmm.co.jp/mono/dvd/-/detail/=/cid=fsdss615/",
        "https://video.dmm.co.jp/av/content/?id=1fsdss00615",
    ]


def test_dmm_candidates_do_not_add_leading_one_for_other_prefixes():
    provider = OfficialMetadataProvider()
    variants = normalize_code_variants("ALDN-480")

    assert provider._dmm_digital_cids(variants) == ["aldn00480"]
    assert provider._dmm_detail_candidates(variants) == [
        "https://www.dmm.co.jp/mono/dvd/-/detail/=/cid=aldn480/",
        "https://video.dmm.co.jp/av/content/?id=aldn00480",
    ]


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
    assert extracted.plot == "家庭内で交わされた契約をめぐる紹介文です。"
    assert extracted.actors == ["北野未奈"]
    assert extracted.release_date == "2025-07-08"
    assert extracted.runtime_minutes == 140
    assert extracted.director == "宝浩史"
    assert extracted.maker == "タカラ映像"
    assert extracted.label == "ALEDDIN"
    assert extracted.series == "家庭内愛人契約"
    assert extracted.tags == ["熟女", "人妻・主婦", "巨乳"]
    assert extracted.rating == "4.35"
    assert extracted.votes == 23
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

    with patch.dict(
        "os.environ",
        {"NOCTRA_LLM_ENABLED": "0", "NOCTRA_LLM_API_KEY": "", "OPENAI_API_KEY": ""},
        clear=False,
    ):
        metadata = await provider.crawl("ALDN-480")

    assert metadata is not None
    assert metadata.code == "ALDN-480"
    assert metadata.title == "ALDN-480"
    assert metadata.original_title == "家庭内愛人契約 北野未奈"
    assert metadata.plot == "家庭内で交わされた契約をめぐる紹介文です。"
    assert metadata.actors == ["北野未奈"]
    assert metadata.release == "2025-07-08"
    assert metadata.runtime_minutes == 140
    assert metadata.directors == ["宝浩史"]
    assert metadata.studio == "タカラ映像"
    assert metadata.label == "ALEDDIN"
    assert metadata.series == "家庭内愛人契約"
    assert metadata.tags == ["熟女", "人妻・主婦", "巨乳"]
    assert metadata.rating == "4.35"
    assert metadata.votes == 23
    assert metadata.fanart_url == cover_urls[0]
    assert metadata.poster_url == cover_urls[1]
    assert metadata.preview_urls == []


@pytest.mark.asyncio
async def test_validated_cover_urls_checks_fsdss_digital_cover_before_mono():
    provider = OfficialMetadataProvider()
    checked_urls = []

    async def check_image_url(url):
        checked_urls.append(url)
        return False

    provider._check_image_url = check_image_url

    await provider._validated_cover_urls(normalize_code_variants("FSDSS-615"), {})

    assert checked_urls == [
        "https://takara-tv.jp/product/l/fsdss-615.jpg",
        "https://pics.dmm.co.jp/digital/video/1fsdss00615/1fsdss00615pl.jpg",
        "https://pics.dmm.co.jp/mono/movie/adult/fsdss615/fsdss615pl.jpg",
    ]


@pytest.mark.asyncio
async def test_check_image_url_rejects_dmm_now_printing_placeholder():
    class Response:
        status_code = 200
        headers = {"content-type": "image/jpeg"}
        url = "https://imgsrc.dmm.com/pics/mono/movie/n/now_printing/now_printing.jpg"

    class Session:
        def head(self, url, **kwargs):
            return Response()

    provider = OfficialMetadataProvider()
    provider._session = Session()

    assert await provider._check_image_url(
        "https://pics.dmm.co.jp/digital/video/fsdss00615/fsdss00615pl.jpg"
    ) is False


def test_apply_translation_updates_display_fields_only():
    metadata = ScrapingMetadata(
        code="DASD-951",
        title="DASD-951",
        original_title="巨乳で可愛い婚約中の彼女が俺の親父に寝取られ種付けプレスされていた。 北野未奈",
        plot="婚約者である健一の父にあいさつしに来た未奈。",
        actors=["北野未奈"],
        studio="ダスッ！",
        label="ダスッ！",
        series="寝取られ種付けプレス",
        tags=["巨乳", "単体作品"],
    )
    translated = TranslatedMetadata(
        title="可爱的巨乳未婚妻被父亲夺走",
        plot="未奈前去拜访未婚夫的父亲，却卷入一段成人题材剧情。",
        tags=["巨乳", "单体作品"],
        series="被夺走的种付压制",
    )

    result = apply_translation(metadata, translated)

    assert result.title == "可爱的巨乳未婚妻被父亲夺走"
    assert result.original_title == metadata.original_title
    assert result.plot == "未奈前去拜访未婚夫的父亲，却卷入一段成人题材剧情。"
    assert result.tags == ["巨乳", "单体作品"]
    assert result.series == "被夺走的种付压制"
    assert result.actors == ["北野未奈"]
    assert result.studio == "ダスッ！"
    assert result.label == "ダスッ！"


def test_translated_from_llm_rejects_refusal_and_mismatched_tags():
    metadata = ScrapingMetadata(
        code="DASD-951",
        title="DASD-951",
        original_title="日文标题",
        plot="日文简介",
        tags=["巨乳", "単体作品"],
        series="日文系列",
    )

    result = translated_from_llm(
        {
            "title": "抱歉，我无法翻译该内容",
            "plot": "中文简介",
            "tags": ["巨乳"],
            "series": "中文系列",
        },
        metadata,
    )

    assert result is not None
    assert result.title == ""
    assert result.plot == "中文简介"
    assert result.tags == []
    assert result.series == "中文系列"


def test_merge_metadata_keeps_deterministic_rating_and_votes():
    base = ExtractedMetadata(rating="4.35", votes=23)
    override = ExtractedMetadata(rating="4.0", votes=14)

    result = merge_metadata(base, override)

    assert result.rating == "4.35"
    assert result.votes == 23
