"""Tests for scraping API endpoints (GET /api/scrape, POST /api/scrape/{file_id})."""

# NOTE: Heavy third-party dependencies (curl_cffi, aiofiles, aiohttp) are
# stubbed in tests/conftest.py so that app.main can be imported without the
# full scraping runtime.

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_rows():
    """Return a list of Row-like dicts as the database would return for organized files."""
    return [
        {
            'id': 1,
            'identified_code': 'ABC-001',
            'target_path': '/dist/ABC-001/ABC-001.mp4',
            'scrape_status': 'pending',
            'last_scrape_at': None,
        },
        {
            'id': 2,
            'identified_code': 'ABC-002',
            'target_path': '/dist/ABC-002/ABC-002.mp4',
            'scrape_status': 'success',
            'last_scrape_at': '2025-01-01T12:00:00',
        },
        {
            'id': 3,
            'identified_code': 'DEF-100',
            'target_path': '/dist/DEF-100/DEF-100.mp4',
            'scrape_status': 'failed',
            'last_scrape_at': '2025-01-02T08:00:00',
        },
        {
            'id': 4,
            'identified_code': 'GHI-500',
            'target_path': '/dist/GHI-500/GHI-500.mp4',
            'scrape_status': 'success',
            'last_scrape_at': '2025-01-03T15:00:00',
        },
    ]


def _make_mock_row(d):
    """Create an aiosqlite.Row-like object from a dict."""
    class MockRow(dict):
        def __getattr__(self, key):
            try:
                return self[key]
            except KeyError:
                raise AttributeError(key)
    return MockRow(d)


def _rows_to_mock(rows):
    return [_make_mock_row(r) for r in rows]


# ---------------------------------------------------------------------------
# GET /api/scrape tests
# ---------------------------------------------------------------------------

@patch('app.main.aiosqlite.connect')
def test_get_scrape_list_all(mock_connect, sample_rows):
    """GET /api/scrape with filter=all returns all organized files."""
    from app.main import app

    mock_db = AsyncMock()
    mock_connect.return_value.__aenter__.return_value = mock_db

    # First call: COUNT(*), returns 4
    count_cursor = MagicMock()
    count_cursor.fetchone = AsyncMock(return_value=(4,))
    # Second call: data query
    data_cursor = MagicMock()
    data_cursor.fetchall = AsyncMock(return_value=_rows_to_mock(sample_rows))

    mock_db.execute = AsyncMock(side_effect=[count_cursor, data_cursor])
    mock_db.row_factory = None  # will be set by the endpoint

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get('/api/scrape?filter=all&sort=code')

    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 4
    assert len(data['items']) == 4


@patch('app.main.aiosqlite.connect')
def test_get_scrape_list_filter_pending(mock_connect, sample_rows):
    """GET /api/scrape with filter=pending only returns pending items."""
    from app.main import app

    pending_rows = [r for r in sample_rows if r['scrape_status'] == 'pending']

    mock_db = AsyncMock()
    mock_connect.return_value.__aenter__.return_value = mock_db

    count_cursor = MagicMock()
    count_cursor.fetchone = AsyncMock(return_value=(1,))
    data_cursor = MagicMock()
    data_cursor.fetchall = AsyncMock(return_value=_rows_to_mock(pending_rows))

    mock_db.execute = AsyncMock(side_effect=[count_cursor, data_cursor])

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get('/api/scrape?filter=pending')

    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 1
    assert len(data['items']) == 1
    assert data['items'][0]['file_id'] == 1
    assert data['items'][0]['scrape_status'] == 'pending'


@patch('app.main.aiosqlite.connect')
def test_get_scrape_list_filter_success(mock_connect, sample_rows):
    """GET /api/scrape with filter=success only returns success items."""
    from app.main import app

    success_rows = [r for r in sample_rows if r['scrape_status'] == 'success']

    mock_db = AsyncMock()
    mock_connect.return_value.__aenter__.return_value = mock_db

    count_cursor = MagicMock()
    count_cursor.fetchone = AsyncMock(return_value=(2,))
    data_cursor = MagicMock()
    data_cursor.fetchall = AsyncMock(return_value=_rows_to_mock(success_rows))

    mock_db.execute = AsyncMock(side_effect=[count_cursor, data_cursor])

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get('/api/scrape?filter=success')

    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 2
    assert len(data['items']) == 2


@patch('app.main.aiosqlite.connect')
def test_get_scrape_list_filter_failed(mock_connect, sample_rows):
    """GET /api/scrape with filter=failed only returns failed items."""
    from app.main import app

    failed_rows = [r for r in sample_rows if r['scrape_status'] == 'failed']

    mock_db = AsyncMock()
    mock_connect.return_value.__aenter__.return_value = mock_db

    count_cursor = MagicMock()
    count_cursor.fetchone = AsyncMock(return_value=(1,))
    data_cursor = MagicMock()
    data_cursor.fetchall = AsyncMock(return_value=_rows_to_mock(failed_rows))

    mock_db.execute = AsyncMock(side_effect=[count_cursor, data_cursor])

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get('/api/scrape?filter=failed')

    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 1
    assert len(data['items']) == 1
    assert data['items'][0]['scrape_status'] == 'failed'


@patch('app.main.aiosqlite.connect')
def test_get_scrape_list_sort_code(mock_connect, sample_rows):
    """GET /api/scrape with sort=code sorts by identified_code ASC."""
    from app.main import app

    mock_db = AsyncMock()
    mock_connect.return_value.__aenter__.return_value = mock_db

    count_cursor = MagicMock()
    count_cursor.fetchone = AsyncMock(return_value=(4,))

    # When sorted by code ASC: ABC-001, ABC-002, DEF-100, GHI-500
    sorted_rows = sorted(sample_rows, key=lambda r: r['identified_code'])
    data_cursor = MagicMock()
    data_cursor.fetchall = AsyncMock(return_value=_rows_to_mock(sorted_rows))

    mock_db.execute = AsyncMock(side_effect=[count_cursor, data_cursor])

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get('/api/scrape?sort=code')

    assert response.status_code == 200
    data = response.json()
    codes = [item['code'] for item in data['items']]
    assert codes == ['ABC-001', 'ABC-002', 'DEF-100', 'GHI-500']


@patch('app.main.aiosqlite.connect')
def test_get_scrape_list_sort_scrape_time(mock_connect, sample_rows):
    """GET /api/scrape with sort=scrape_time sorts by last_scrape_at DESC."""
    from app.main import app

    mock_db = AsyncMock()
    mock_connect.return_value.__aenter__.return_value = mock_db

    count_cursor = MagicMock()
    count_cursor.fetchone = AsyncMock(return_value=(4,))

    # When sorted by scrape_time DESC (non-null first): GHI-500, DEF-100, ABC-002, ABC-001
    sorted_rows = sorted(
        sample_rows,
        key=lambda r: r['last_scrape_at'] or '',
        reverse=True,
    )
    data_cursor = MagicMock()
    data_cursor.fetchall = AsyncMock(return_value=_rows_to_mock(sorted_rows))

    mock_db.execute = AsyncMock(side_effect=[count_cursor, data_cursor])

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get('/api/scrape?sort=scrape_time')

    assert response.status_code == 200
    data = response.json()
    assert data['items'][0]['code'] == 'GHI-500'


@patch('app.main.aiosqlite.connect')
def test_get_scrape_list_pagination(mock_connect, sample_rows):
    """GET /api/scrape with page=2&per_page=2 returns correct slice."""
    from app.main import app

    mock_db = AsyncMock()
    mock_connect.return_value.__aenter__.return_value = mock_db

    count_cursor = MagicMock()
    count_cursor.fetchone = AsyncMock(return_value=(4,))

    # Page 2, per_page 2 => should return items 3 and 4
    paged_rows = sample_rows[2:4]
    data_cursor = MagicMock()
    data_cursor.fetchall = AsyncMock(return_value=_rows_to_mock(paged_rows))

    mock_db.execute = AsyncMock(side_effect=[count_cursor, data_cursor])

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get('/api/scrape?page=2&per_page=2')

    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 4
    assert len(data['items']) == 2


@patch('app.main.aiosqlite.connect')
def test_get_scrape_list_default_params(mock_connect, sample_rows):
    """GET /api/scrape with no query params uses defaults (page=1, per_page=50, filter=all, sort=code)."""
    from app.main import app

    mock_db = AsyncMock()
    mock_connect.return_value.__aenter__.return_value = mock_db

    count_cursor = MagicMock()
    count_cursor.fetchone = AsyncMock(return_value=(4,))
    data_cursor = MagicMock()
    data_cursor.fetchall = AsyncMock(return_value=_rows_to_mock(sample_rows))

    mock_db.execute = AsyncMock(side_effect=[count_cursor, data_cursor])

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get('/api/scrape')

    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 4
    assert len(data['items']) == 4


def test_get_scrape_list_invalid_filter():
    """GET /api/scrape with invalid filter returns 400."""
    from app.main import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get('/api/scrape?filter=invalid')

    assert response.status_code == 400
    assert 'Invalid filter' in response.json()['detail']


def test_get_scrape_list_invalid_sort():
    """GET /api/scrape with invalid sort returns 400."""
    from app.main import app

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get('/api/scrape?sort=invalid')

    assert response.status_code == 400
    assert 'Invalid sort' in response.json()['detail']


@patch('app.main.aiosqlite.connect')
def test_get_scrape_list_empty_result(mock_connect):
    """GET /api/scrape returns empty items when no organized files exist."""
    from app.main import app

    mock_db = AsyncMock()
    mock_connect.return_value.__aenter__.return_value = mock_db

    count_cursor = MagicMock()
    count_cursor.fetchone = AsyncMock(return_value=(0,))
    data_cursor = MagicMock()
    data_cursor.fetchall = AsyncMock(return_value=[])

    mock_db.execute = AsyncMock(side_effect=[count_cursor, data_cursor])

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get('/api/scrape')

    assert response.status_code == 200
    data = response.json()
    assert data['total'] == 0
    assert data['items'] == []


@patch('app.main.aiosqlite.connect')
def test_get_scrape_list_db_error(mock_connect):
    """GET /api/scrape returns 500 on database error."""
    from app.main import app

    mock_db = AsyncMock()
    mock_connect.return_value.__aenter__.return_value = mock_db
    mock_db.execute = AsyncMock(side_effect=Exception('DB connection lost'))

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get('/api/scrape')

    assert response.status_code == 500
    assert 'Database error' in response.json()['detail']


# ---------------------------------------------------------------------------
# POST /api/scrape/{file_id} tests
# ---------------------------------------------------------------------------

@patch('app.main.ScraperScheduler')
def test_post_scrape_success(mock_scheduler_cls):
    """POST /api/scrape/{file_id} returns ScrapeResponse on success."""
    from app.main import app
    from app.models import ScrapeResponse

    mock_scheduler = MagicMock()
    mock_scheduler.scrape_single = AsyncMock(
        return_value=ScrapeResponse(success=True, code='ABC-001')
    )
    mock_scheduler_cls.return_value = mock_scheduler

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post('/api/scrape/1')

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is True
    assert data['code'] == 'ABC-001'
    mock_scheduler.scrape_single.assert_called_once_with(1)


@patch('app.main.ScraperScheduler')
def test_post_scrape_failure(mock_scheduler_cls):
    """POST /api/scrape/{file_id} returns ScrapeResponse with error on failure."""
    from app.main import app
    from app.models import ScrapeResponse

    mock_scheduler = MagicMock()
    mock_scheduler.scrape_single = AsyncMock(
        return_value=ScrapeResponse(success=False, error='File not found')
    )
    mock_scheduler_cls.return_value = mock_scheduler

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post('/api/scrape/999')

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is False
    assert data['error'] == 'File not found'


@patch('app.main.ScraperScheduler')
def test_post_scrape_unexpected_exception(mock_scheduler_cls):
    """POST /api/scrape/{file_id} returns 500 when ScraperScheduler raises unexpected exception."""
    from app.main import app

    mock_scheduler = MagicMock()
    mock_scheduler.scrape_single = AsyncMock(
        side_effect=RuntimeError('Unexpected error')
    )
    mock_scheduler_cls.return_value = mock_scheduler

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post('/api/scrape/1')

    assert response.status_code == 500
    assert 'Unexpected error' in response.json()['detail']


@patch('app.main.ScraperScheduler')
def test_post_scrape_file_not_found(mock_scheduler_cls):
    """POST /api/scrape/{file_id} returns error when file_id does not exist."""
    from app.main import app
    from app.models import ScrapeResponse

    mock_scheduler = MagicMock()
    mock_scheduler.scrape_single = AsyncMock(
        return_value=ScrapeResponse(
            success=False,
            error='File record with id=42 not found'
        )
    )
    mock_scheduler_cls.return_value = mock_scheduler

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post('/api/scrape/42')

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is False
    assert 'not found' in data['error']


@patch('app.main.ScraperScheduler')
def test_post_scrape_wrong_status(mock_scheduler_cls):
    """POST /api/scrape/{file_id} returns error when file status is not 'organized'."""
    from app.main import app
    from app.models import ScrapeResponse

    mock_scheduler = MagicMock()
    mock_scheduler.scrape_single = AsyncMock(
        return_value=ScrapeResponse(
            success=False,
            error="File status is 'pending', expected 'organized'"
        )
    )
    mock_scheduler_cls.return_value = mock_scheduler

    client = TestClient(app, raise_server_exceptions=False)
    response = client.post('/api/scrape/5')

    assert response.status_code == 200
    data = response.json()
    assert data['success'] is False
    assert 'organized' in data['error']


# ---------------------------------------------------------------------------
# Response model field checks
# ---------------------------------------------------------------------------

@patch('app.main.aiosqlite.connect')
def test_scrape_list_item_fields(mock_connect, sample_rows):
    """GET /api/scrape items contain all expected ScrapeListItem fields."""
    from app.main import app

    mock_db = AsyncMock()
    mock_connect.return_value.__aenter__.return_value = mock_db

    count_cursor = MagicMock()
    count_cursor.fetchone = AsyncMock(return_value=(1,))
    data_cursor = MagicMock()
    data_cursor.fetchall = AsyncMock(return_value=_rows_to_mock(sample_rows[:1]))

    mock_db.execute = AsyncMock(side_effect=[count_cursor, data_cursor])

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get('/api/scrape')

    assert response.status_code == 200
    item = response.json()['items'][0]
    assert 'file_id' in item
    assert 'code' in item
    assert 'target_path' in item
    assert 'scrape_status' in item
    assert 'last_scrape_at' in item
