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
        "plot": "テストプロット内容",
        "actors": ["女優A", "女優B", "女優C"],
        "studio": "S1 NO.1 STYLE",
        "release": "2023-06-27",
        "poster_url": "https://example.com/poster.jpg",
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
