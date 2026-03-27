"""NFO writer for generating Emby-compatible XML metadata files."""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from app.scrapers.metadata import ScrapingMetadata

XML_DECLARATION = '<?xml version="1.0" encoding="utf-8" standalone="yes"?>'


def write_nfo(metadata: ScrapingMetadata, output_path: Path) -> None:
    """Write an Emby-compatible NFO file from ScrapingMetadata.

    Generates a minimal NFO XML file containing the 7 core fields:
    title, plot, actor(s), premiered, studio, and poster.

    Args:
        metadata: The scraped metadata to convert to NFO.
        output_path: Filesystem path where the NFO file will be written.
    """
    movie = ET.Element("movie")

    # title
    title_elem = ET.SubElement(movie, "title")
    title_elem.text = metadata.title or ""

    # actors (only add <actor> tags if the list is non-empty)
    for actor_name in metadata.actors:
        actor_elem = ET.SubElement(movie, "actor")
        name_elem = ET.SubElement(actor_elem, "name")
        name_elem.text = actor_name or ""

    # premiered (release date)
    premiered_elem = ET.SubElement(movie, "premiered")
    premiered_elem.text = metadata.release or ""

    # studio
    studio_elem = ET.SubElement(movie, "studio")
    studio_elem.text = metadata.studio or ""

    # poster (filename only)
    poster_elem = ET.SubElement(movie, "poster")
    poster_elem.text = _compute_poster_filename(metadata)

    # Serialize to string. We intentionally skip plot in the ElementTree
    # so that ElementTree does not escape special characters. Instead, we
    # inject the <plot> element with a CDATA-wrapped value manually.
    raw = ET.tostring(movie, encoding="unicode")
    raw = _inject_plot_cdata(raw, metadata.plot)

    # Write file with XML declaration prepended
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(XML_DECLARATION + "\n")
        f.write(raw + "\n")


def _compute_poster_filename(metadata: ScrapingMetadata) -> Optional[str]:
    """Derive the poster filename from metadata code and poster_url.

    Returns "{code}-poster.jpg" when poster_url is truthy, otherwise None.
    """
    if metadata.poster_url:
        return f"{metadata.code}-poster.jpg"
    return None


def _escape_cdata_end(text: str) -> str:
    """Escape the CDATA end marker if it appears inside text.

    CDATA sections cannot contain the literal string "]]>".
    The standard workaround is to split it into two adjacent CDATA blocks.
    """
    return text.replace("]]>", "]]]]><![CDATA[>")


def _inject_plot_cdata(xml_string: str, plot_text: str) -> str:
    """Inject a <plot> element with CDATA content after the opening <movie> tag.

    We place plot right after <movie> (before <title>) for consistency with
    the reference format, and to keep it near the top of the file.

    Args:
        xml_string: XML string produced by ElementTree (without plot element).
        plot_text: The raw plot text to wrap in CDATA.

    Returns:
        XML string with <plot><![CDATA[...]]></plot> injected.
    """
    safe_text = _escape_cdata_end(plot_text)
    plot_tag = f"<plot><![CDATA[{safe_text}]]></plot>"

    # Insert after <movie> opening tag
    return xml_string.replace("<movie>", f"<movie>\n  {plot_tag}", 1)
