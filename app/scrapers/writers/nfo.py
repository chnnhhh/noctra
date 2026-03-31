"""NFO writer for generating richer Emby/Kodi-compatible XML metadata."""

from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

from app.scrapers.metadata import ScrapingMetadata

XML_DECLARATION = '<?xml version="1.0" encoding="utf-8" standalone="yes"?>'


def write_nfo(metadata: ScrapingMetadata, output_path: Path) -> None:
    """Write a movie NFO next to the organized media file."""
    output_path = Path(output_path)
    artifact_base_name = output_path.stem
    movie = ET.Element("movie")

    _text_element(movie, "outline", metadata.plot or "")
    _text_element(movie, "lockdata", "false")
    _text_element(movie, "dateadded", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    _text_element(movie, "title", metadata.title or metadata.code)
    _text_element(movie, "originaltitle", metadata.original_title or metadata.title or metadata.code)

    for actor_name in metadata.actors:
        actor_elem = ET.SubElement(movie, "actor")
        _text_element(actor_elem, "name", actor_name or "")
        _text_element(actor_elem, "type", "Actor")

    _text_element(movie, "year", _release_year(metadata.release))
    _text_element(movie, "sorttitle", metadata.code or "")
    _text_element(movie, "imdbid", metadata.code or "")
    _text_element(movie, "premiered", metadata.release or "")
    _text_element(movie, "releasedate", metadata.release or "")
    _text_element(movie, "runtime", str(metadata.runtime_minutes) if metadata.runtime_minutes is not None else "")
    _text_element(movie, "rating", metadata.rating or "")
    _text_element(movie, "votes", str(metadata.votes) if metadata.votes is not None else "")

    normalized_genres = _normalized_genres(metadata.tags, artifact_base_name)
    for genre in normalized_genres:
        _text_element(movie, "genre", genre or "")
    for tag in normalized_genres:
        _text_element(movie, "tag", tag or "")

    _text_element(movie, "studio", metadata.studio or "")

    for director_name in metadata.directors:
        _text_element(movie, "director", director_name or "")

    unique_id = _text_element(movie, "uniqueid", metadata.code or "")
    unique_id.set("type", "imdb")

    _text_element(movie, "id", metadata.code or "")

    fileinfo = ET.SubElement(movie, "fileinfo")
    ET.SubElement(fileinfo, "streamdetails")

    _text_element(movie, "website", metadata.website or "")

    poster_filename = _poster_filename(metadata, artifact_base_name)
    _text_element(movie, "poster", poster_filename or "")
    _text_element(movie, "cover", poster_filename or "")

    if metadata.fanart_url:
        fanart = ET.SubElement(movie, "fanart")
        _text_element(fanart, "thumb", _fanart_filename(metadata, artifact_base_name))
        for index, _ in enumerate(metadata.preview_urls, start=1):
            _text_element(fanart, "thumb", _preview_filename(metadata, artifact_base_name, index))

    ET.indent(movie, space="  ")
    raw = ET.tostring(movie, encoding="unicode")
    raw = _inject_plot_cdata(raw, metadata.plot)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file_obj:
        file_obj.write(XML_DECLARATION + "\n")
        file_obj.write(raw + "\n")


def _text_element(parent: ET.Element, tag: str, text: str) -> ET.Element:
    element = ET.SubElement(parent, tag)
    if text:
        element.text = text
    return element


def _release_year(release_date: str) -> str:
    if len(release_date or "") >= 4:
        return release_date[:4]
    return ""


def _normalized_genres(tags: list[str], artifact_base_name: str) -> list[str]:
    genres: list[str] = []
    for genre in tags:
        normalized = (genre or "").strip()
        if normalized and normalized not in genres:
            genres.append(normalized)

    upper_name = artifact_base_name.upper()
    extra_genres: list[str] = []
    if upper_name.endswith("-UC"):
        extra_genres = ["中字", "无码破解"]
    elif upper_name.endswith("-C"):
        extra_genres = ["中字"]

    for genre in extra_genres:
        if genre not in genres:
            genres.append(genre)

    return genres


def _poster_filename(metadata: ScrapingMetadata, artifact_base_name: str) -> str:
    if metadata.poster_url:
        return f"{artifact_base_name}-poster.jpg"
    return ""


def _fanart_filename(metadata: ScrapingMetadata, artifact_base_name: str) -> str:
    return f"{artifact_base_name}-fanart.jpg"


def _preview_filename(metadata: ScrapingMetadata, artifact_base_name: str, index: int) -> str:
    return f"{artifact_base_name}-preview-{index:02d}.jpg"


def _escape_cdata_end(text: str) -> str:
    return (text or "").replace("]]>", "]]]]><![CDATA[>")


def _inject_plot_cdata(xml_string: str, plot_text: str) -> str:
    safe_text = _escape_cdata_end(plot_text or "")
    plot_tag = f"<plot><![CDATA[{safe_text}]]></plot>"
    if "<movie>\n" in xml_string:
        return xml_string.replace("<movie>\n", f"<movie>\n  {plot_tag}\n", 1)
    return xml_string.replace("<movie>", f"<movie>\n  {plot_tag}\n", 1)
