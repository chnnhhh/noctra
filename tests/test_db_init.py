"""Tests for database initialization and schema backfills."""

import asyncio
import os
import sqlite3
from unittest.mock import patch


def test_init_db_backfills_scrape_columns(tmp_path):
    """Existing databases should gain scrape observability columns on startup."""
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
            updated_at TEXT NOT NULL,
            scrape_status TEXT DEFAULT 'pending',
            last_scrape_at TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO files (
            original_path, identified_code, target_path, status,
            file_size, file_mtime, created_at, updated_at, scrape_status, last_scrape_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            "pending",
            None,
        )
    )
    conn.commit()
    conn.close()

    with patch.dict(os.environ, {"DB_PATH": str(db_path)}):
        import app.main as main

        asyncio.run(main.init_db())

    conn = sqlite3.connect(db_path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(files)").fetchall()}
    conn.close()

    assert "scrape_started_at" in columns
    assert "scrape_finished_at" in columns
    assert "scrape_stage" in columns
    assert "scrape_source" in columns
    assert "scrape_error" in columns
    assert "scrape_error_user_message" in columns
    assert "scrape_logs" in columns
