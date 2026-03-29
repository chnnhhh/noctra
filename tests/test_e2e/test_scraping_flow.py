"""End-to-end tests for the scraping flow.

These tests verify the complete pipeline from database record to generated
NFO/poster files, using a real SQLite database and real file system.
Only external HTTP calls (JavDB website, image downloads) are mocked.

Test categories:
  1. Complete scraping flow (organized -> scraped)
  2. NFO file format and Emby compatibility
  3. API endpoint integration (real DB queries)
  4. Error handling
"""

import asyncio
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.scrapers.metadata import ScrapingMetadata
from app.scrapers.writers.nfo import write_nfo
from app.scraper import ScraperScheduler
from app.models import ScrapeResponse


# ---------------------------------------------------------------------------
# Database schema (mirrors init_db + add_scraping migration)
# ---------------------------------------------------------------------------

DB_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_path TEXT UNIQUE NOT NULL,
    identified_code TEXT,
    target_path TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    file_size INTEGER NOT NULL,
    file_mtime REAL NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    scrape_status TEXT DEFAULT 'pending',
    last_scrape_at TEXT,
    scrape_started_at TEXT,
    scrape_finished_at TEXT,
    scrape_stage TEXT,
    scrape_source TEXT,
    scrape_error TEXT,
    scrape_error_user_message TEXT,
    scrape_logs TEXT
);
CREATE INDEX IF NOT EXISTS idx_files_scrape_status ON files(scrape_status);
"""


# ---------------------------------------------------------------------------
# Mock HTML fixtures (fake JavDB responses)
# ---------------------------------------------------------------------------

SEARCH_HTML = """
<html>
<body>
  <div class="movie-list">
    <a class="box" href="/v/ssis743">
      <div class="uid">SSIS-743</div>
      <div class="title">Test Video Title</div>
    </a>
  </div>
</body>
</html>
"""

DETAIL_HTML = """
<html>
<body>
  <div class="container">
    <h2 class="title">
      <strong class="current-title">Beautiful Actress - Test Title SSIS-743</strong>
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
          <a href="/actors/1">Actress Alpha</a>
          <a href="/actors/2">Actress Beta</a>
          <a href="/actors/3">Actress Gamma</a>
        </span>
      </div>
      <div class="panel-block">
        <strong>簡介:</strong>
        <p>SSIS-743 的劇情簡介：這是一部精彩的作品，描述了三位女主角之間的友情與冒險故事。內容精彩，不容錯過！</p>
      </div>
    </div>
    <div class="video-cover-panel">
      <img class="video-cover" src="https://javdb.com/covers/abc/SSIS-743.jpg" />
    </div>
  </div>
</body>
</html>
"""

# Detail page for ABW-100 (second test code)
SEARCH_HTML_ABW = """
<html>
<body>
  <div class="movie-list">
    <a class="box" href="/v/abw100">
      <div class="uid">ABW-100</div>
    </a>
  </div>
</body>
</html>
"""

DETAIL_HTML_ABW = """
<html>
<body>
  <div class="container">
    <h2 class="title">
      <strong class="current-title">Premium Actress Collection</strong>
    </h2>
    <div class="video-meta-panel">
      <div class="panel-block">
        <strong>ID:</strong>
        <span class="value">ABW-100</span>
      </div>
      <div class="panel-block">
        <strong>Released Date:</strong>
        <span>2023-12-01</span>
      </div>
      <div class="panel-block">
        <strong>Maker:</strong>
        <span>
          <a href="/makers/2">Prestige</a>
        </span>
      </div>
      <div class="panel-block">
        <strong>Actors:</strong>
        <span>
          <a href="/actors/5">Solo Actress</a>
        </span>
      </div>
      <div class="panel-block">
        <strong>Description:</strong>
        <p>A premium collection featuring the most talented actress of the year.</p>
      </div>
    </div>
    <div class="video-cover-panel">
      <img class="video-cover" src="https://javdb.com/covers/xyz/ABW-100.jpg" />
    </div>
  </div>
</body>
</html>
"""

# Fake poster image bytes (minimal valid JPEG header)
FAKE_POSTER_BYTES = (
    b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
    b'\xff\xdb\x00C\x00\x03\x02\x02\x03\x02\x02\x03\x03\x03\x03\x04\x03'
    b'\x03\x04\x05\x08\x05\x05\x04\x04\x05\n\x07\x07\x06\x08\x0c\n\x0c\x0c'
    b'\x0b\n\x0b\x0b\r\x0e\x12\x10\r\x0e\x11\x0e\x0b\x0b\x10\x16\x10\x11'
    b'\x13\x14\x15\x15\x15\x0c\x0f\x17\x18\x16\x14\x18\x12\x14\x15\x14\xff'
    b'\xd9'
)


# ---------------------------------------------------------------------------
# Sync helpers for real database and file system operations
# ---------------------------------------------------------------------------

_SENTINEL = object()  # Used to distinguish "not passed" from None




def _init_db(db_path: str) -> None:
    """Create a real SQLite database with the full schema (sync)."""
    conn = sqlite3.connect(db_path)
    conn.executescript(DB_SCHEMA_SQL)
    conn.close()


def _insert_file_record(db_path: str, *, code: str, status: str = "organized",
                        scrape_status: str = "pending",
                        last_scrape_at: str | None = None,
                        file_size: int = 1024,
                        target_path: object = _SENTINEL,
                        identified_code: object = _SENTINEL) -> int:
    """Insert a file record and return its ID (sync).

    Use identified_code=None or target_path=None to explicitly set NULL,
    or omit to use defaults (code for identified_code, /dist/{code}/{code}.mp4 for target_path).
    """
    if target_path is _SENTINEL:
        target_path = f"/dist/{code}/{code}.mp4"
    if identified_code is _SENTINEL:
        identified_code = code
    now = datetime.now().isoformat()

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            """
            INSERT INTO files
            (original_path, identified_code, target_path, status, file_size,
             file_mtime, created_at, updated_at, scrape_status, last_scrape_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"/source/{code}.mp4",
                identified_code,
                target_path,
                status,
                file_size,
                1700000000.0,
                now,
                now,
                scrape_status,
                last_scrape_at,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def _query_file(db_path: str, file_id: int) -> dict | None:
    """Query a single file record by ID (sync)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute("SELECT * FROM files WHERE id = ?", (file_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def _update_scrape_status_direct(db_path: str, file_id: int, status: str,
                                  last_scrape_at: str | None = None) -> None:
    """Directly update scrape_status in real DB (sync)."""
    conn = sqlite3.connect(db_path)
    try:
        if last_scrape_at:
            conn.execute(
                "UPDATE files SET scrape_status = ?, last_scrape_at = ? WHERE id = ?",
                (status, last_scrape_at, file_id),
            )
        else:
            conn.execute(
                "UPDATE files SET scrape_status = ? WHERE id = ?",
                (status, file_id),
            )
        conn.commit()
    finally:
        conn.close()


def _count_files(db_path: str, where: str = "1=1", params: tuple = ()) -> int:
    """Count files matching WHERE clause (sync)."""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(f"SELECT COUNT(*) FROM files WHERE {where}", params)
        return cursor.fetchone()[0]
    finally:
        conn.close()


def _query_codes_ordered(db_path: str) -> list[str]:
    """Query identified_codes ordered ASC (sync)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(
            "SELECT identified_code FROM files WHERE status='organized' ORDER BY identified_code ASC"
        )
        return [row["identified_code"] for row in cursor.fetchall()]
    finally:
        conn.close()


async def _fake_download_poster(url, output_path):
    """Fake poster download that writes FAKE_POSTER_BYTES to disk."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(FAKE_POSTER_BYTES)


def _make_mock_conn_cm_for_real_db(db_path: str):
    """Create a mock aiosqlite connection manager that writes to the real DB."""
    mock_conn_cm = AsyncMock()
    mock_conn = AsyncMock()

    async def real_execute(sql, params=None):
        _direct_execute(db_path, sql, params)
        mock_cursor = MagicMock()
        return mock_cursor

    mock_conn.execute = real_execute
    mock_conn_cm.__aenter__.return_value = mock_conn
    mock_conn_cm.__aexit__.return_value = None
    return mock_conn_cm


def _direct_execute(db_path: str, sql: str, params=None):
    """Execute SQL on the real database synchronously (bridges async->sync)."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Fixtures (all synchronous for compatibility)
# ---------------------------------------------------------------------------

@pytest.fixture
def test_db(tmp_path):
    """Create a real SQLite database with the full schema (sync fixture)."""
    db_path = str(tmp_path / "test_e2e.db")
    _init_db(db_path)
    yield db_path


@pytest.fixture
def test_dist_dir(tmp_path):
    """Create a temporary distribution directory for test files."""
    dist = tmp_path / "dist"
    dist.mkdir()
    yield dist


@pytest.fixture
def client(test_db, monkeypatch):
    """Create a TestClient pointed at the real test database."""
    import app.main as main_module

    monkeypatch.setattr(main_module, "DB_PATH", test_db)

    with TestClient(main_module.app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def organized_record(test_db, test_dist_dir):
    """Insert an organized file record with SSIS-743 into the real test database.

    Returns a dict with the record details including file_id.
    """
    code = "SSIS-743"
    target_dir = test_dist_dir / code
    target_dir.mkdir()
    target_path = target_dir / f"{code}.mp4"
    target_path.write_bytes(b"\x00" * 1024)

    file_id = _insert_file_record(test_db, code=code, target_path=str(target_path))

    return {
        "file_id": file_id,
        "code": code,
        "target_path": str(target_path),
        "nfo_path": str(target_dir / f"{code}.nfo"),
        "poster_path": str(target_dir / f"{code}-poster.jpg"),
        "db_path": test_db,
        "dist_dir": test_dist_dir,
    }


@pytest.fixture
def organized_record_abw(test_db, test_dist_dir):
    """Insert a second organized file record (ABW-100)."""
    code = "ABW-100"
    target_dir = test_dist_dir / code
    target_dir.mkdir()
    target_path = target_dir / f"{code}.mp4"
    target_path.write_bytes(b"\x00" * 2048)

    file_id = _insert_file_record(test_db, code=code, target_path=str(target_path),
                                  file_size=2048)

    return {
        "file_id": file_id,
        "code": code,
        "target_path": str(target_path),
        "nfo_path": str(target_dir / f"{code}.nfo"),
        "poster_path": str(target_dir / f"{code}-poster.jpg"),
        "db_path": test_db,
        "dist_dir": test_dist_dir,
    }


# ===========================================================================
# Test 1: Complete scraping flow (organized -> scraped)
# ===========================================================================


class TestCompleteScrapingFlow:
    """Verify the end-to-end pipeline: DB record -> crawl -> NFO -> poster -> DB update."""

    @pytest.mark.asyncio
    async def test_full_flow_creates_nfo_and_poster(self, organized_record):
        """Scrape creates NFO file, downloads poster, and triggers DB update."""
        file_id = organized_record["file_id"]
        db_path = organized_record["db_path"]

        scheduler = ScraperScheduler()

        # Create a mock _get_file that reads from the real test database
        async def get_real_file(fid):
            record = _query_file(db_path, fid)
            return record

        with (
            patch.object(scheduler, "_get_file", new_callable=AsyncMock) as mock_get,
            patch("app.scraper.JavDBCrawler") as MockCrawler,
            patch("app.scraper.write_nfo") as mock_write_nfo,
            patch("app.scraper.download_poster", new_callable=AsyncMock) as mock_download,
            patch("app.scraper.aiosqlite") as mock_aiosqlite,
        ):
            mock_get.side_effect = get_real_file

            # Mock crawler to return parsed metadata
            mock_crawler_instance = AsyncMock()
            mock_crawler_instance.crawl = AsyncMock(
                return_value=ScrapingMetadata(
                    code="SSIS-743",
                    title="Beautiful Actress - Test Title SSIS-743",
                    plot="SSIS-743 的劇情簡介：這是一部精彩的作品",
                    actors=["Actress Alpha", "Actress Beta", "Actress Gamma"],
                    studio="S1 NO.1 STYLE",
                    release="2024-06-15",
                    poster_url="https://javdb.com/thumbs/abc/SSIS-743.jpg",
                )
            )
            MockCrawler.return_value = mock_crawler_instance

            # Use real write_nfo and fake poster download
            mock_write_nfo.side_effect = lambda meta, path: write_nfo(meta, Path(path))
            mock_download.side_effect = _fake_download_poster

            # Wire the mock aiosqlite to write to the real test DB
            mock_aiosqlite.connect.return_value = _make_mock_conn_cm_for_real_db(db_path)

            result = await scheduler.scrape_single(file_id)

        # Verify response
        assert result.success is True
        assert result.code == "SSIS-743"
        assert result.error is None

        # Verify NFO file was created with real content
        nfo_path = Path(organized_record["nfo_path"])
        assert nfo_path.exists(), f"NFO file not found at {nfo_path}"
        nfo_content = nfo_path.read_text(encoding="utf-8")
        assert "Beautiful Actress - Test Title SSIS-743" in nfo_content
        assert "Actress Alpha" in nfo_content
        assert "S1 NO.1 STYLE" in nfo_content
        assert "2024-06-15" in nfo_content

        # Verify poster file was created
        poster_path = Path(organized_record["poster_path"])
        assert poster_path.exists(), f"Poster file not found at {poster_path}"
        assert len(poster_path.read_bytes()) > 0

        # Verify DB state was updated in the real database
        record = _query_file(db_path, file_id)
        assert record["scrape_status"] == "success"
        assert record["last_scrape_at"] is not None
        datetime.fromisoformat(record["last_scrape_at"])

    @pytest.mark.asyncio
    async def test_full_flow_multiple_files(self, organized_record, organized_record_abw):
        """Verify scraping works for multiple files independently."""
        for rec, code in [
            (organized_record, "SSIS-743"),
            (organized_record_abw, "ABW-100"),
        ]:
            file_id = rec["file_id"]
            db_path = rec["db_path"]

            scheduler = ScraperScheduler()

            async def get_real_file(fid, _db_path=db_path):
                return _query_file(_db_path, fid)

            with (
                patch.object(scheduler, "_get_file", new_callable=AsyncMock) as mock_get,
                patch("app.scraper.JavDBCrawler") as MockCrawler,
                patch("app.scraper.write_nfo") as mock_write_nfo,
                patch("app.scraper.download_poster", new_callable=AsyncMock) as mock_download,
                patch("app.scraper.aiosqlite") as mock_aiosqlite,
            ):
                mock_get.side_effect = get_real_file

                mock_crawler_instance = AsyncMock()
                mock_crawler_instance.crawl = AsyncMock(
                    return_value=ScrapingMetadata(
                        code=code,
                        title=f"Title for {code}",
                        plot=f"Plot for {code}",
                        actors=["Actor1"],
                        studio="Studio1",
                        release="2024-01-01",
                        poster_url=f"https://javdb.com/thumbs/{code}.jpg",
                    )
                )
                MockCrawler.return_value = mock_crawler_instance

                mock_write_nfo.side_effect = lambda meta, path: write_nfo(meta, Path(path))
                mock_download.side_effect = _fake_download_poster

                mock_aiosqlite.connect.return_value = _make_mock_conn_cm_for_real_db(db_path)

                result = await scheduler.scrape_single(file_id)

            assert result.success is True
            assert result.code == code
            assert Path(rec["nfo_path"]).exists()
            assert Path(rec["poster_path"]).exists()

    def test_nfo_content_has_all_7_fields(self, organized_record):
        """NFO file must contain all 7 metadata fields: title, plot, actors, premiered, studio, poster."""
        nfo_path = Path(organized_record["nfo_path"])
        metadata = ScrapingMetadata(
            code="SSIS-743",
            title="Full Title Here",
            plot="A detailed plot description with characters and events.",
            actors=["Alice", "Bob", "Charlie"],
            studio="Test Studio",
            release="2024-06-15",
            poster_url="https://javdb.com/thumbs/abc/SSIS-743.jpg",
        )
        write_nfo(metadata, nfo_path)

        content = nfo_path.read_text(encoding="utf-8")

        # All 7 fields must be present
        assert "<movie>" in content
        assert "<title>Full Title Here</title>" in content
        assert "A detailed plot description" in content
        assert "<name>Alice</name>" in content
        assert "<name>Bob</name>" in content
        assert "<name>Charlie</name>" in content
        assert "<premiered>2024-06-15</premiered>" in content
        assert "<studio>Test Studio</studio>" in content
        assert "<poster>SSIS-743-poster.jpg</poster>" in content
        assert "<?xml" in content  # XML declaration

    def test_no_poster_url_skips_download(self, organized_record):
        """When metadata has no poster_url, NFO should have empty poster element."""
        nfo_path = Path(organized_record["nfo_path"])
        metadata = ScrapingMetadata(
            code="SSIS-743",
            title="No Poster Video",
            plot="Some plot",
            actors=[],
            studio="Studio",
            release="2024-01-01",
            poster_url="",  # empty - no poster
        )
        write_nfo(metadata, nfo_path)

        content = nfo_path.read_text(encoding="utf-8")
        assert "<poster/>" in content or "<poster />" in content or "<poster></poster>" in content


# ===========================================================================
# Test 2: NFO format and Emby compatibility
# ===========================================================================


class TestNfoEmbyCompatibility:
    """Verify NFO files are valid XML that Emby can parse."""

    def test_nfo_is_valid_xml(self, tmp_path):
        """NFO file must be parseable by ElementTree without errors."""
        nfo_path = tmp_path / "test.nfo"
        metadata = ScrapingMetadata(
            code="TEST-001",
            title="Valid XML Title",
            plot="Plot with <special> & characters \" and ' quotes",
            actors=["Actor1", "Actor2"],
            studio="XML Studio",
            release="2024-03-15",
            poster_url="https://example.com/cover.jpg",
        )
        write_nfo(metadata, nfo_path)

        tree = ET.parse(nfo_path)
        root = tree.getroot()
        assert root.tag == "movie"

    def test_nfo_all_elements_present_and_correct(self, tmp_path):
        """All NFO elements must be present and have correct values."""
        nfo_path = tmp_path / "test.nfo"
        metadata = ScrapingMetadata(
            code="ABW-100",
            title="Premium Collection",
            plot="A story about premium content.",
            actors=["Alpha", "Beta"],
            studio="Prestige",
            release="2023-12-01",
            poster_url="https://javdb.com/thumbs/xyz/ABW-100.jpg",
        )
        write_nfo(metadata, nfo_path)

        tree = ET.parse(nfo_path)
        root = tree.getroot()

        # Title
        title_elem = root.find("title")
        assert title_elem is not None
        assert title_elem.text == "Premium Collection"

        # Plot
        plot_elem = root.find("plot")
        assert plot_elem is not None
        assert "premium content" in plot_elem.text

        # Actors
        actor_elems = root.findall("actor")
        assert len(actor_elems) == 2
        actor_names = [a.find("name").text for a in actor_elems]
        assert "Alpha" in actor_names
        assert "Beta" in actor_names

        # Premiered
        premiered_elem = root.find("premiered")
        assert premiered_elem is not None
        assert premiered_elem.text == "2023-12-01"

        # Studio
        studio_elem = root.find("studio")
        assert studio_elem is not None
        assert studio_elem.text == "Prestige"

        # Poster
        poster_elem = root.find("poster")
        assert poster_elem is not None
        assert poster_elem.text == "ABW-100-poster.jpg"

    def test_nfo_plot_with_special_characters(self, tmp_path):
        """NFO must handle special XML characters in plot text (CDATA)."""
        nfo_path = tmp_path / "special.nfo"
        plot_text = "Story with <html> tags, & ampersands, 'quotes' and \"double quotes\""
        metadata = ScrapingMetadata(
            code="SPC-001",
            title="Special Characters Test",
            plot=plot_text,
            actors=[],
            studio="Test",
            release="2024-01-01",
            poster_url="",
        )
        write_nfo(metadata, nfo_path)

        tree = ET.parse(nfo_path)
        root = tree.getroot()
        plot_elem = root.find("plot")
        assert plot_elem is not None
        assert "html" in plot_elem.text

    def test_nfo_no_actors(self, tmp_path):
        """NFO with no actors should not contain any <actor> elements."""
        nfo_path = tmp_path / "no_actors.nfo"
        metadata = ScrapingMetadata(
            code="NAC-001",
            title="No Actors Video",
            plot="Some plot",
            actors=[],
            studio="Studio",
            release="2024-01-01",
            poster_url="https://example.com/poster.jpg",
        )
        write_nfo(metadata, nfo_path)

        tree = ET.parse(nfo_path)
        root = tree.getroot()
        actor_elems = root.findall("actor")
        assert len(actor_elems) == 0

    def test_nfo_single_actor(self, tmp_path):
        """NFO with one actor should have exactly one <actor> element."""
        nfo_path = tmp_path / "single_actor.nfo"
        metadata = ScrapingMetadata(
            code="SAC-001",
            title="Single Actor Video",
            plot="Some plot",
            actors=["Solo Performer"],
            studio="Studio",
            release="2024-01-01",
            poster_url="https://example.com/poster.jpg",
        )
        write_nfo(metadata, nfo_path)

        tree = ET.parse(nfo_path)
        root = tree.getroot()
        actor_elems = root.findall("actor")
        assert len(actor_elems) == 1
        assert actor_elems[0].find("name").text == "Solo Performer"

    def test_nfo_has_xml_declaration(self, tmp_path):
        """NFO must start with XML declaration for Emby compatibility."""
        nfo_path = tmp_path / "decl.nfo"
        metadata = ScrapingMetadata(
            code="DCL-001",
            title="Declaration Test",
            plot="Plot",
            actors=[],
            studio="Studio",
            release="2024-01-01",
            poster_url="",
        )
        write_nfo(metadata, nfo_path)

        first_line = nfo_path.read_text(encoding="utf-8").split("\n")[0]
        assert first_line.startswith("<?xml")
        assert 'encoding="utf-8"' in first_line
        assert 'standalone="yes"' in first_line

    def test_nfo_empty_fields_use_defaults(self, tmp_path):
        """Empty metadata fields should produce empty elements, not missing ones."""
        nfo_path = tmp_path / "empty.nfo"
        metadata = ScrapingMetadata(
            code="EMP-001",
            title="",
            plot="",
            actors=[],
            studio="",
            release="",
            poster_url="",
        )
        write_nfo(metadata, nfo_path)

        tree = ET.parse(nfo_path)
        root = tree.getroot()

        assert root.find("title") is not None
        assert root.find("plot") is not None
        assert root.find("premiered") is not None
        assert root.find("studio") is not None
        assert root.find("poster") is not None


# ===========================================================================
# Test 3: API endpoint integration (real DB queries)
# ===========================================================================


class TestApiIntegration:
    """Test GET/POST /api/scrape data layer with real database state."""

    def test_get_scrape_list_returns_organized_files(self, test_db):
        """Organized files should be queryable from the database."""
        now = datetime.now().isoformat()

        for code in ["CODE-001", "CODE-002", "CODE-003"]:
            _insert_file_record(test_db, code=code, status="organized")

        # Insert a non-organized file (should not count)
        _insert_file_record(test_db, code="PEND-001", status="pending")

        count = _count_files(test_db, "status = 'organized'")
        assert count == 3

    def test_get_scrape_filter_by_status(self, test_db):
        """Filter organized files by scrape_status."""
        now = datetime.now().isoformat()

        _insert_file_record(test_db, code="AAA-001", scrape_status="pending")
        _insert_file_record(test_db, code="BBB-002", scrape_status="success",
                           last_scrape_at=now)
        _insert_file_record(test_db, code="CCC-003", scrape_status="failed",
                           last_scrape_at=now)

        for status, expected_count in [("pending", 1), ("success", 1), ("failed", 1)]:
            count = _count_files(
                test_db,
                "status='organized' AND scrape_status=?",
                (status,),
            )
            assert count == expected_count, (
                f"Expected {expected_count} for scrape_status={status}, got {count}"
            )

    def test_get_scrape_sort_by_code(self, test_db):
        """Organized files sorted by code should be in alphabetical order."""
        for code in ["ZEBRA-001", "APPLE-002", "MANGO-003"]:
            _insert_file_record(test_db, code=code)

        sorted_codes = _query_codes_ordered(test_db)
        assert sorted_codes == ["APPLE-002", "MANGO-003", "ZEBRA-001"]

    @pytest.mark.asyncio
    async def test_post_scrape_updates_db_successfully(self, test_db, test_dist_dir):
        """Scrape updates scrape_status to 'success' in the real database."""
        code = "UPD-001"
        target_dir = test_dist_dir / code
        target_dir.mkdir()
        target_path = target_dir / f"{code}.mp4"
        target_path.write_bytes(b"\x00" * 512)

        file_id = _insert_file_record(test_db, code=code,
                                      target_path=str(target_path))

        scheduler = ScraperScheduler()

        async def get_real_file(fid):
            return _query_file(test_db, fid)

        with (
            patch.object(scheduler, "_get_file", side_effect=get_real_file),
            patch("app.scraper.JavDBCrawler") as MockCrawler,
            patch("app.scraper.write_nfo", side_effect=lambda m, p: write_nfo(m, Path(p))),
            patch("app.scraper.download_poster", new_callable=AsyncMock,
                  side_effect=_fake_download_poster),
            patch("app.scraper.aiosqlite") as mock_aiosqlite,
        ):
            mock_aiosqlite.connect.return_value = _make_mock_conn_cm_for_real_db(test_db)

            mock_crawler_instance = AsyncMock()
            mock_crawler_instance.crawl = AsyncMock(
                return_value=ScrapingMetadata(
                    code=code,
                    title="Update Test Title",
                    plot="Update test plot",
                    actors=["TestActor"],
                    studio="TestStudio",
                    release="2024-01-01",
                    poster_url="https://javdb.com/thumbs/abc.jpg",
                )
            )
            MockCrawler.return_value = mock_crawler_instance

            result = await scheduler.scrape_single(file_id)

        assert result.success is True

        # Verify actual database state
        record = _query_file(test_db, file_id)
        assert record["scrape_status"] == "success"
        assert record["last_scrape_at"] is not None
        datetime.fromisoformat(record["last_scrape_at"])

    @patch("app.main.get_active_scrape_job", new_callable=AsyncMock)
    def test_scrape_list_includes_active_job_snapshot(self, mock_active_job, client, test_db):
        """GET /api/scrape should surface the active scrape job snapshot."""
        _insert_file_record(test_db, code="FPRE-055")

        mock_active_job.return_value = {
            "id": "job-active-1",
            "status": "running",
            "total": 2,
            "processed": 1,
            "succeeded": 1,
            "failed": 0,
            "created_at": "2026-03-27T10:00:00",
            "started_at": "2026-03-27T10:00:01",
            "finished_at": None,
            "current_file_id": 2,
            "current_file_code": "FPRE-055",
            "current_stage": "querying_source",
            "current_source": "javdb",
            "recent_logs": [
                {
                    "at": "2026-03-27T10:00:02",
                    "level": "info",
                    "stage": "querying_source",
                    "source": "javdb",
                    "message": "正在查询 JavDB",
                }
            ],
            "items": [],
        }

        response = client.get("/api/scrape")

        assert response.status_code == 200
        payload = response.json()
        assert payload["active_job"]["current_file_code"] == "FPRE-055"
        assert payload["active_job"]["recent_logs"][0]["message"] == "正在查询 JavDB"


# ===========================================================================
# Test 4: Error handling
# ===========================================================================


class TestErrorHandling:
    """Verify error cases are handled gracefully."""

    @pytest.mark.asyncio
    async def test_nonexistent_file_id(self):
        """Scraping a non-existent file_id should return an error."""
        scheduler = ScraperScheduler()

        async def get_none(fid):
            return None

        with patch.object(scheduler, "_get_file", side_effect=get_none):
            result = await scheduler.scrape_single(99999)

        assert result.success is False
        assert "not found" in result.error
        assert "99999" in result.error

    @pytest.mark.asyncio
    async def test_wrong_status_pending(self, test_db):
        """File with 'pending' status should be rejected."""
        file_id = _insert_file_record(test_db, code="PEND-001", status="pending")

        scheduler = ScraperScheduler()

        async def get_real(fid):
            return _query_file(test_db, fid)

        with (
            patch.object(scheduler, "_get_file", side_effect=get_real),
            patch("app.scraper.aiosqlite") as mock_aiosqlite,
        ):
            mock_aiosqlite.connect.return_value = _make_mock_conn_cm_for_real_db(test_db)
            result = await scheduler.scrape_single(file_id)

        assert result.success is False
        assert "pending" in result.error
        assert "organized" in result.error
        record = _query_file(test_db, file_id)
        assert record["scrape_status"] == "failed"
        assert record["scrape_stage"] == "validating"
        assert record["scrape_error_user_message"] == "文件信息不完整，无法开始刮削"

    @pytest.mark.asyncio
    async def test_wrong_status_processed(self, test_db):
        """Historical 'processed' status should remain scrapeable."""
        file_id = _insert_file_record(test_db, code="PROC-001", status="processed")

        scheduler = ScraperScheduler()

        async def get_real(fid):
            return _query_file(test_db, fid)

        with (
            patch.object(scheduler, "_get_file", side_effect=get_real),
            patch("app.scraper.JavDBCrawler") as MockCrawler,
            patch("app.scraper.aiosqlite") as mock_aiosqlite,
        ):
            mock_crawler_instance = AsyncMock()
            mock_crawler_instance.crawl = AsyncMock(return_value=None)
            MockCrawler.return_value = mock_crawler_instance
            mock_aiosqlite.connect.return_value = _make_mock_conn_cm_for_real_db(test_db)
            result = await scheduler.scrape_single(file_id)

        assert result.success is False
        assert "Failed to crawl" in result.error
        record = _query_file(test_db, file_id)
        assert record["scrape_status"] == "failed"
        assert record["scrape_stage"] == "querying_source"

    @pytest.mark.asyncio
    async def test_crawl_failure_updates_scrape_status(self, test_db, test_dist_dir):
        """When crawl fails, scrape_status should be set to 'failed'."""
        code = "FAIL-001"
        target_dir = test_dist_dir / code
        target_dir.mkdir()
        target_path = target_dir / f"{code}.mp4"
        target_path.write_bytes(b"\x00" * 256)

        file_id = _insert_file_record(test_db, code=code,
                                      target_path=str(target_path))

        scheduler = ScraperScheduler()

        async def get_real(fid):
            return _query_file(test_db, fid)

        with (
            patch.object(scheduler, "_get_file", side_effect=get_real),
            patch("app.scraper.JavDBCrawler") as MockCrawler,
            patch("app.scraper.aiosqlite") as mock_aiosqlite,
        ):
            mock_aiosqlite.connect.return_value = _make_mock_conn_cm_for_real_db(test_db)
            mock_crawler_instance = AsyncMock()
            mock_crawler_instance.crawl = AsyncMock(return_value=None)
            MockCrawler.return_value = mock_crawler_instance

            result = await scheduler.scrape_single(file_id)

        assert result.success is False
        assert "Failed to crawl" in result.error
        record = _query_file(test_db, file_id)
        assert record["scrape_status"] == "failed"
        assert record["scrape_stage"] == "querying_source"
        assert record["scrape_error_user_message"] == "在 JavDB 没有找到这个番号的元数据"

    @pytest.mark.asyncio
    async def test_failed_scrape_persists_last_attempt_details(self, test_db, test_dist_dir):
        """A scrape failure should persist the latest readable details and logs."""
        code = "FPRE-004"
        target_dir = test_dist_dir / code
        target_dir.mkdir()
        target_path = target_dir / f"{code}.mp4"
        target_path.write_bytes(b"\x00" * 256)

        file_id = _insert_file_record(test_db, code=code, target_path=str(target_path))
        scheduler = ScraperScheduler()

        async def get_real(fid):
            return _query_file(test_db, fid)

        with (
            patch.object(scheduler, "_get_file", side_effect=get_real),
            patch("app.scraper.JavDBCrawler") as MockCrawler,
            patch("app.scraper.aiosqlite") as mock_aiosqlite,
        ):
            mock_aiosqlite.connect.return_value = _make_mock_conn_cm_for_real_db(test_db)

            mock_crawler_instance = AsyncMock()
            mock_crawler_instance.crawl = AsyncMock(return_value=None)
            MockCrawler.return_value = mock_crawler_instance

            result = await scheduler.scrape_single(file_id)

        record = _query_file(test_db, file_id)

        assert result.success is False
        assert record["scrape_status"] == "failed"
        assert record["scrape_source"] == "javdb"
        assert record["scrape_stage"] == "querying_source"
        assert record["scrape_error_user_message"] == "在 JavDB 没有找到这个番号的元数据"
        assert record["scrape_logs"]

    @pytest.mark.asyncio
    async def test_no_identified_code_in_record(self, test_db):
        """File record without identified_code should fail gracefully."""
        file_id = _insert_file_record(test_db, code="NOCODE-001",
                                      identified_code=None)

        scheduler = ScraperScheduler()

        async def get_real(fid):
            return _query_file(test_db, fid)

        with (
            patch.object(scheduler, "_get_file", side_effect=get_real),
            patch("app.scraper.aiosqlite") as mock_aiosqlite,
        ):
            mock_aiosqlite.connect.return_value = _make_mock_conn_cm_for_real_db(test_db)
            result = await scheduler.scrape_single(file_id)

        assert result.success is False
        assert "no identified_code" in result.error
        record = _query_file(test_db, file_id)
        assert record["scrape_status"] == "failed"
        assert record["scrape_stage"] == "validating"
        assert record["scrape_error_user_message"] == "文件信息不完整，无法开始刮削"

    @pytest.mark.asyncio
    async def test_no_target_path_in_record(self, test_db):
        """File record without target_path should fail gracefully."""
        file_id = _insert_file_record(test_db, code="PATH-001", target_path=None)

        scheduler = ScraperScheduler()

        async def get_real(fid):
            return _query_file(test_db, fid)

        with (
            patch.object(scheduler, "_get_file", side_effect=get_real),
            patch("app.scraper.aiosqlite") as mock_aiosqlite,
        ):
            mock_aiosqlite.connect.return_value = _make_mock_conn_cm_for_real_db(test_db)
            result = await scheduler.scrape_single(file_id)

        assert result.success is False
        assert "no target_path" in result.error
        record = _query_file(test_db, file_id)
        assert record["scrape_status"] == "failed"
        assert record["scrape_stage"] == "validating"
        assert record["scrape_error_user_message"] == "文件信息不完整，无法开始刮削"

    @pytest.mark.asyncio
    async def test_exception_during_nfo_write_marks_failed(self, test_db, test_dist_dir):
        """If write_nfo raises, scrape_status should be set to 'failed'."""
        code = "ERR-001"
        target_dir = test_dist_dir / code
        target_dir.mkdir()
        target_path = target_dir / f"{code}.mp4"
        target_path.write_bytes(b"\x00" * 128)

        file_id = _insert_file_record(test_db, code=code,
                                      target_path=str(target_path))

        scheduler = ScraperScheduler()

        async def get_real(fid):
            return _query_file(test_db, fid)

        with (
            patch.object(scheduler, "_get_file", side_effect=get_real),
            patch("app.scraper.JavDBCrawler") as MockCrawler,
            patch("app.scraper.write_nfo", side_effect=OSError("Permission denied")),
            patch("app.scraper.aiosqlite") as mock_aiosqlite,
        ):
            mock_aiosqlite.connect.return_value = _make_mock_conn_cm_for_real_db(test_db)
            mock_crawler_instance = AsyncMock()
            mock_crawler_instance.crawl = AsyncMock(
                return_value=ScrapingMetadata(
                    code=code, title="T", plot="P", actors=[], studio="S",
                    release="2024-01-01", poster_url="",
                )
            )
            MockCrawler.return_value = mock_crawler_instance

            result = await scheduler.scrape_single(file_id)

        assert result.success is False
        assert "Permission denied" in result.error
        record = _query_file(test_db, file_id)
        assert record["scrape_status"] == "failed"
        assert record["scrape_stage"] == "writing_nfo"
        assert record["scrape_error_user_message"] == "元数据已获取，但写入 NFO 文件失败"

    @pytest.mark.asyncio
    async def test_already_scraped_file_can_be_re_scraped(self, test_db, test_dist_dir):
        """A file with scrape_status='success' can be re-scraped."""
        code = "RESC-001"
        target_dir = test_dist_dir / code
        target_dir.mkdir()
        target_path = target_dir / f"{code}.mp4"
        target_path.write_bytes(b"\x00" * 512)

        now = datetime.now().isoformat()
        file_id = _insert_file_record(test_db, code=code,
                                      target_path=str(target_path),
                                      scrape_status="success",
                                      last_scrape_at=now)

        scheduler = ScraperScheduler()

        async def get_real(fid):
            return _query_file(test_db, fid)

        with (
            patch.object(scheduler, "_get_file", side_effect=get_real),
            patch("app.scraper.JavDBCrawler") as MockCrawler,
            patch("app.scraper.write_nfo",
                  side_effect=lambda m, p: write_nfo(m, Path(p))),
            patch("app.scraper.download_poster", new_callable=AsyncMock,
                  side_effect=_fake_download_poster),
            patch("app.scraper.aiosqlite") as mock_aiosqlite,
        ):
            mock_aiosqlite.connect.return_value = _make_mock_conn_cm_for_real_db(test_db)

            mock_crawler_instance = AsyncMock()
            mock_crawler_instance.crawl = AsyncMock(
                return_value=ScrapingMetadata(
                    code=code, title="Re-scraped Title", plot="Re-scraped plot",
                    actors=["NewActor"], studio="NewStudio", release="2024-06-15",
                    poster_url="https://javdb.com/thumbs/resc.jpg",
                )
            )
            MockCrawler.return_value = mock_crawler_instance

            result = await scheduler.scrape_single(file_id)

        # Should succeed because status is still 'organized'
        assert result.success is True
        assert result.code == code

    def test_empty_scrape_list(self, test_db):
        """Database with no organized files should return count 0."""
        count = _count_files(test_db, "status = 'organized'")
        assert count == 0
