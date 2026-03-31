"""Tests for NFO writer - Emby-compatible XML generation."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from app.scrapers.metadata import ScrapingMetadata
from app.scrapers.writers.nfo import write_nfo


def _make_metadata(**overrides) -> ScrapingMetadata:
    """Create a ScrapingMetadata with sensible defaults, overridden as needed."""
    defaults = {
        "code": "SSIS-743",
        "title": "SSIS-743 テストタイトル",
        "original_title": "SSIS-743 オリジナルタイトル",
        "plot": "テストプロット内容",
        "actors": ["女優A", "女優B", "女優C"],
        "studio": "S1 NO.1 STYLE",
        "release": "2023-06-27",
        "website": "https://javdb.com/v/abc123?locale=zh",
        "runtime_minutes": 140,
        "directors": ["監督A"],
        "tags": ["巨乳", "單體作品"],
        "rating": "4.09",
        "votes": 487,
        "poster_url": "https://example.com/poster.jpg",
        "fanart_url": "https://example.com/fanart.jpg",
        "preview_urls": [
            "https://example.com/preview-1.jpg",
            "https://example.com/preview-2.jpg",
        ],
    }
    defaults.update(overrides)
    return ScrapingMetadata(**defaults)


def test_write_nfo_creates_file(tmp_path: Path):
    """Test that write_nfo creates the output file."""
    metadata = _make_metadata()
    output_path = tmp_path / "SSIS-743.nfo"

    write_nfo(metadata, output_path)

    assert output_path.exists()


def test_write_nfo_xml_declaration(tmp_path: Path):
    """Test that the XML declaration is correct with standalone='yes'."""
    metadata = _make_metadata()
    output_path = tmp_path / "SSIS-743.nfo"

    write_nfo(metadata, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert content.startswith('<?xml version="1.0" encoding="utf-8" standalone="yes"?>')


def test_write_nfo_root_element(tmp_path: Path):
    """Test that the root element is <movie>."""
    metadata = _make_metadata()
    output_path = tmp_path / "SSIS-743.nfo"

    write_nfo(metadata, output_path)

    tree = ET.parse(output_path)
    root = tree.getroot()
    assert root.tag == "movie"


def test_write_nfo_all_fields_present(tmp_path: Path):
    """Test that all 7 core fields are present in the generated XML."""
    metadata = _make_metadata()
    output_path = tmp_path / "SSIS-743.nfo"

    write_nfo(metadata, output_path)

    tree = ET.parse(output_path)
    root = tree.getroot()

    assert root.find("title").text == "SSIS-743 テストタイトル"
    assert root.find("plot").text == "テストプロット内容"
    assert root.find("premiered").text == "2023-06-27"
    assert root.find("studio").text == "S1 NO.1 STYLE"
    assert root.find("poster").text == "SSIS-743-poster.jpg"


def test_write_nfo_multiple_actors(tmp_path: Path):
    """Test that multiple actors generate multiple <actor> tags."""
    metadata = _make_metadata(actors=["女優A", "女優B", "女優C"])
    output_path = tmp_path / "SSIS-743.nfo"

    write_nfo(metadata, output_path)

    tree = ET.parse(output_path)
    root = tree.getroot()
    actors = root.findall("actor")
    assert len(actors) == 3
    assert actors[0].find("name").text == "女優A"
    assert actors[1].find("name").text == "女優B"
    assert actors[2].find("name").text == "女優C"


def test_write_nfo_empty_actors(tmp_path: Path):
    """Test that no <actor> tags are generated when actors list is empty."""
    metadata = _make_metadata(actors=[])
    output_path = tmp_path / "SSIS-743.nfo"

    write_nfo(metadata, output_path)

    tree = ET.parse(output_path)
    root = tree.getroot()
    actors = root.findall("actor")
    assert len(actors) == 0


def test_write_nfo_plot_uses_cdata(tmp_path: Path):
    """Test that plot content is wrapped in CDATA section."""
    metadata = _make_metadata()
    output_path = tmp_path / "SSIS-743.nfo"

    write_nfo(metadata, output_path)

    content = output_path.read_text(encoding="utf-8")
    assert "<![CDATA[テストプロット内容]]>" in content


def test_write_nfo_plot_special_characters_with_cdata(tmp_path: Path):
    """Test that special characters in plot are safely wrapped in CDATA."""
    special_plot = "出演: <女優A> & <女優B> 「特殊」文字 'テスト'"
    metadata = _make_metadata(plot=special_plot)
    output_path = tmp_path / "SSIS-743.nfo"

    write_nfo(metadata, output_path)

    content = output_path.read_text(encoding="utf-8")
    # CDATA should contain the raw special characters without escaping
    assert "<![CDATA[" in content
    assert "]]>" in content
    # Verify the special characters are preserved literally inside CDATA
    cdata_match = re.search(r"<!\[CDATA\[(.*?)\]\]>", content, re.DOTALL)
    assert cdata_match is not None
    assert cdata_match.group(1) == special_plot


def test_write_nfo_no_poster_url(tmp_path: Path):
    """Test that poster is None when poster_url is empty."""
    metadata = _make_metadata(poster_url="")
    output_path = tmp_path / "SSIS-743.nfo"

    write_nfo(metadata, output_path)

    tree = ET.parse(output_path)
    root = tree.getroot()
    assert root.find("poster").text is None


def test_write_nfo_creates_parent_directories(tmp_path: Path):
    """Test that write_nfo creates parent directories if they don't exist."""
    metadata = _make_metadata()
    output_path = tmp_path / "subdir" / "nested" / "SSIS-743.nfo"

    write_nfo(metadata, output_path)

    assert output_path.exists()


def test_write_nfo_empty_optional_fields(tmp_path: Path):
    """Test that empty optional fields still produce tags with empty content."""
    metadata = _make_metadata(
        actors=[],
        studio="",
        release="",
        poster_url="",
    )
    output_path = tmp_path / "SSIS-743.nfo"

    write_nfo(metadata, output_path)

    tree = ET.parse(output_path)
    root = tree.getroot()

    # Tags should exist even if empty (self-closing tags parse as None text)
    assert root.find("studio") is not None
    assert root.find("studio").text is None
    assert root.find("premiered") is not None
    assert root.find("premiered").text is None
    assert root.find("poster") is not None
    assert root.find("poster").text is None


def test_write_nfo_rich_fields_match_reference_shape(tmp_path: Path):
    """Generated NFO should include richer Kodi/Emby-friendly metadata."""
    metadata = _make_metadata()
    output_path = tmp_path / "SSIS-743.nfo"

    write_nfo(metadata, output_path)

    tree = ET.parse(output_path)
    root = tree.getroot()

    assert root.find("outline").text == "テストプロット内容"
    assert root.find("lockdata").text == "false"
    assert root.find("title").text == "SSIS-743 テストタイトル"
    assert root.find("originaltitle").text == "SSIS-743 オリジナルタイトル"
    assert root.find("year").text == "2023"
    assert root.find("sorttitle").text == "SSIS-743"
    assert root.find("imdbid").text == "SSIS-743"
    assert root.find("uniqueid").text == "SSIS-743"
    assert root.find("id").text == "SSIS-743"
    assert root.find("premiered").text == "2023-06-27"
    assert root.find("releasedate").text == "2023-06-27"
    assert root.find("runtime").text == "140"
    assert root.find("rating").text == "4.09"
    assert root.find("votes").text == "487"
    assert root.find("website").text == "https://javdb.com/v/abc123?locale=zh"
    assert root.find("poster").text == "SSIS-743-poster.jpg"
    assert root.find("cover").text == "SSIS-743-poster.jpg"
    assert root.find("fanart/thumb").text == "SSIS-743-fanart.jpg"
    assert [genre.text for genre in root.findall("genre")] == ["巨乳", "單體作品"]
    assert [director.text for director in root.findall("director")] == ["監督A"]

    actors = root.findall("actor")
    assert actors[0].find("name").text == "女優A"
    assert actors[0].find("type").text == "Actor"


def test_write_nfo_uses_output_stem_for_artifact_references_and_uc_genres(tmp_path: Path):
    metadata = _make_metadata(code="JUR-271", tags=["巨乳", "單體作品"])
    output_path = tmp_path / "JUR-271-UC.nfo"

    write_nfo(metadata, output_path)

    tree = ET.parse(output_path)
    root = tree.getroot()

    assert root.find("poster").text == "JUR-271-UC-poster.jpg"
    assert root.find("cover").text == "JUR-271-UC-poster.jpg"
    assert root.find("fanart/thumb").text == "JUR-271-UC-fanart.jpg"
    assert [thumb.text for thumb in root.findall("fanart/thumb")] == [
        "JUR-271-UC-fanart.jpg",
        "JUR-271-UC-preview-01.jpg",
        "JUR-271-UC-preview-02.jpg",
    ]
    assert [genre.text for genre in root.findall("genre")] == [
        "巨乳",
        "單體作品",
        "中字",
        "无码破解",
    ]


def test_write_nfo_adds_subtitle_genre_for_c_suffix(tmp_path: Path):
    metadata = _make_metadata(code="JUR-271", tags=["熟女"], poster_url="", fanart_url="", preview_urls=[])
    output_path = tmp_path / "JUR-271-C.nfo"

    write_nfo(metadata, output_path)

    tree = ET.parse(output_path)
    root = tree.getroot()

    assert [genre.text for genre in root.findall("genre")] == ["熟女", "中字"]
