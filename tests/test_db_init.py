"""Tests for database initialization and schema backfills."""

import asyncio
import sqlite3

import app.main as main_mod


def test_init_db_backfills_scrape_columns(tmp_path):
    """Existing databases should gain scrape columns on startup."""
    db_path = tmp_path / "noctra.db"

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_path TEXT UNIQUE NOT NULL,
            identified_code TEXT,
            target_path TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            file_size INTEGER NOT NULL,
            file_mtime REAL NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        INSERT INTO files (
            original_path, identified_code, target_path, status,
            file_size, file_mtime, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "/source/SSIS-123.mp4",
            "SSIS-123",
            "/dist/SSIS-123/SSIS-123.mp4",
            "processed",
            1024,
            1700000000.0,
            "2024-01-01T00:00:00",
            "2024-01-01T00:00:00",
        )
    )
    conn.commit()
    conn.close()

    original_db_path = main_mod.DB_PATH
    try:
        main_mod.DB_PATH = str(db_path)
        asyncio.run(main_mod.init_db())

        conn = sqlite3.connect(db_path)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(files)").fetchall()}
        scrape_status = conn.execute("SELECT scrape_status FROM files").fetchone()[0]
        conn.close()

        assert "scrape_status" in columns
        assert "last_scrape_at" in columns
        assert scrape_status == "pending"
    finally:
        main_mod.DB_PATH = original_db_path
