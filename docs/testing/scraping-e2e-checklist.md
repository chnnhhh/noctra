# Scraping E2E Testing Checklist

This document provides step-by-step instructions for manually verifying the scraping pipeline end-to-end.

## Prerequisites

1. **Running Server**: Noctra application is running and accessible
   ```bash
   docker-compose up --build
   # or locally:
   uvicorn app.main:app --reload
   ```

2. **Test Data**: At least one file has been scanned and organized
   - File must have `status = 'organized'` in the database
   - File must have a valid `identified_code` (e.g., `SSIS-743`)
   - File must have a valid `target_path`

3. **Database Access**: Ability to query the SQLite database
   ```bash
   docker-compose exec app sqlite3 /app/data/noctra.db
   ```

4. **Network Access**: Server can reach `javdb.com` (for real tests)

---

## Test 1: Frontend UI Verification

### 1.1 Access Scrape Tab
- [ ] Open the Noctra web UI in a browser
- [ ] Click on the "Scrape" (刮削) tab
- [ ] Verify the scrape list loads without errors
- [ ] Verify organized files are displayed with code, path, and scrape status

### 1.2 Filter and Sort
- [ ] Click "pending" filter -- only pending files shown
- [ ] Click "success" filter -- only success files shown
- [ ] Click "failed" filter -- only failed files shown
- [ ] Click "all" filter -- all organized files shown
- [ ] Sort by "code" -- files sorted alphabetically by code
- [ ] Sort by "scrape time" -- files sorted by last_scrape_at descending

### 1.3 Scrape Button
- [ ] Click "scrape" button on a pending file
- [ ] Verify button shows loading state
- [ ] Verify status updates to "success" or "failed"
- [ ] Verify error message shown if scrape fails
- [ ] Single-file scrape opens the same progress panel as batch scrape (`1 / 1`)
- [ ] Panel shows current file, current stage, current source, and recent logs
- [ ] Refresh during an active scrape restores the panel and keeps polling
- [ ] Failed badge click opens a modal with readable reason, stage, source, logs, and technical details
- [ ] Failed rows cannot be batch-selected, but still expose row-level retry

---

## Test 2: API Endpoint Verification

### 2.1 GET /api/scrape -- List Organized Files

```bash
# Default: all organized files, sorted by code
curl -s http://localhost:8000/api/scrape | python3 -m json.tool

# Filter by scrape_status
curl -s "http://localhost:8000/api/scrape?filter=pending"
curl -s "http://localhost:8000/api/scrape?filter=success"
curl -s "http://localhost:8000/api/scrape?filter=failed"

# Sort options
curl -s "http://localhost:8000/api/scrape?sort=code"
curl -s "http://localhost:8000/api/scrape?sort=scrape_time"

# Pagination
curl -s "http://localhost:8000/api/scrape?page=1&per_page=10"
```

Verify:
- [ ] Response has `total` and `items` fields
- [ ] Each item has: `file_id`, `code`, `target_path`, `scrape_status`, `last_scrape_at`
- [ ] Filter works correctly
- [ ] Sort order is correct
- [ ] Pagination returns correct slice

### 2.2 POST /api/scrape/{file_id} -- Scrape Single File

```bash
# Replace {file_id} with an actual organized file ID
curl -s -X POST http://localhost:8000/api/scrape/1 | python3 -m json.tool
```

Verify:
- [ ] Success response: `{"success": true, "code": "SSIS-743", "error": null}`
- [ ] Error response: `{"success": false, "code": null, "error": "..."}`

### 2.3 Error Cases

```bash
# Non-existent file ID
curl -s -X POST http://localhost:8000/api/scrape/99999 | python3 -m json.tool

# File with wrong status (not organized)
# First find a non-organized file ID, then:
curl -s -X POST http://localhost:8000/api/scrape/{pending_file_id} | python3 -m json.tool
```

Verify:
- [ ] Non-existent ID returns error with "not found" message
- [ ] Wrong status returns error with "organized" message

---

## Test 3: NFO File Verification

After scraping, verify the NFO file was created correctly.

### 3.1 Find the NFO File

```bash
# Find NFO file by code
find /dist -name "SSIS-743.nfo"
```

Verify:
- [ ] NFO file exists at `{target_dir}/{code}.nfo`

### 3.2 Validate NFO Content

```bash
cat /dist/SSIS-743/SSIS-743.nfo
```

Verify all 7 fields are present:
- [ ] `<?xml version="1.0" encoding="utf-8" standalone="yes"?>` -- XML declaration
- [ ] `<movie>` -- Root element
- [ ] `<plot>` -- Plot/description (wrapped in CDATA)
- [ ] `<title>` -- Video title
- [ ] `<actor><name>` -- Actor names (one per actor)
- [ ] `<premiered>` -- Release date in YYYY-MM-DD format
- [ ] `<studio>` -- Studio/maker name
- [ ] `<poster>` -- Poster filename (e.g., `SSIS-743-poster.jpg`)

### 3.3 Validate XML Syntax

```bash
# Check XML is well-formed
xmllint --noout /dist/SSIS-743/SSIS-743.nfo
```

Verify:
- [ ] No XML parsing errors
- [ ] File is valid XML

---

## Test 4: Poster Image Verification

### 4.1 Find the Poster File

```bash
find /dist -name "SSIS-743-poster.jpg"
```

Verify:
- [ ] Poster file exists at `{target_dir}/{code}-poster.jpg`
- [ ] File size is greater than 0

### 4.2 Verify Poster is Valid Image

```bash
# Check file is a valid JPEG
file /dist/SSIS-743/SSIS-743-poster.jpg
# Expected: JPEG image data, ...

# Check dimensions
sips -g pixelWidth -g pixelHeight /dist/SSIS-743/SSIS-743-poster.jpg
```

Verify:
- [ ] File is identified as a JPEG image
- [ ] Image has reasonable dimensions

---

## Test 5: Database State Verification

### 5.1 Check Scrape Status

```bash
sqlite3 /app/data/noctra.db "SELECT id, identified_code, status, scrape_status, last_scrape_at FROM files WHERE identified_code = 'SSIS-743';"
```

After successful scrape:
- [ ] `status` = `organized`
- [ ] `scrape_status` = `success`
- [ ] `last_scrape_at` is set to a valid ISO timestamp

### 5.2 Check Failed Scrape

After a failed scrape:
- [ ] `scrape_status` = `failed`
- [ ] `last_scrape_at` may or may not be set (depends on failure point)

---

## Test 6: Emby Integration Verification

### 6.1 Setup
1. Ensure Emby is running and configured
2. Emby media library points to the `/dist` directory
3. Trigger a library scan in Emby after scraping

### 6.2 Verify Emby Reads Metadata

- [ ] Open Emby web UI
- [ ] Navigate to the media library
- [ ] Find the scraped video by code
- [ ] Verify title is displayed correctly
- [ ] Verify release date is shown
- [ ] Verify studio/maker is shown
- [ ] Verify actor names are listed
- [ ] Verify plot/description is displayed
- [ ] Verify poster image is displayed (not a placeholder)

### 6.3 Verify NFO Parsing

In Emby logs, look for NFO parsing confirmation:
```
grep -i "nfo" /path/to/emby/logs/*.log
```

- [ ] No NFO parsing errors in Emby logs

---

## Test 7: Real Code Tests

Test with real JavDB codes to verify end-to-end with actual website data.

### Recommended Test Codes

| Code | Notes |
|------|-------|
| `SSIS-743` | Popular title, multiple actors |
| `ABW-100` | Single actor |
| `WAAA-585` | English locale support |
| `MIDE-900` | Verify different code prefix |
| `IPX-500` | Another common prefix |

### Test Procedure

```bash
# For each test code:
# 1. Verify file is organized
sqlite3 /app/data/noctra.db "SELECT id, identified_code, status FROM files WHERE identified_code = 'SSIS-743';"

# 2. Scrape
curl -s -X POST http://localhost:8000/api/scrape/{file_id}

# 3. Verify NFO
cat /dist/SSIS-743/SSIS-743.nfo

# 4. Verify poster
file /dist/SSIS-743/SSIS-743-poster.jpg

# 5. Verify DB
sqlite3 /app/data/noctra.db "SELECT scrape_status, last_scrape_at FROM files WHERE identified_code = 'SSIS-743';"
```

For each code verify:
- [ ] Scrape succeeds
- [ ] NFO contains correct title
- [ ] NFO contains correct release date
- [ ] NFO contains actor names
- [ ] NFO contains studio name
- [ ] NFO contains plot description
- [ ] Poster image is downloaded and valid
- [ ] Database status updated to 'success'

---

## Test 8: Edge Cases

### 8.1 Re-scrape Already Scraped File
```bash
# Scrape the same file again
curl -s -X POST http://localhost:8000/api/scrape/{already_scraped_file_id}
```
- [ ] Second scrape succeeds
- [ ] NFO and poster are overwritten
- [ ] `last_scrape_at` is updated

### 8.2 File Without Poster
Some JavDB entries may not have a cover image.
- [ ] Scrape succeeds even without poster
- [ ] NFO has empty `<poster/>` element
- [ ] No poster file is created

### 8.3 Special Characters in Title/Plot
- [ ] NFO handles HTML entities correctly
- [ ] NFO handles CData sections for plot text
- [ ] Emby displays special characters correctly

### 8.4 Non-existent Code on JavDB
```bash
# Try scraping a code that doesn't exist
curl -s -X POST http://localhost:8000/api/scrape/{file_with_fake_code_id}
```
- [ ] Scrape fails with "Failed to crawl metadata" error
- [ ] `scrape_status` set to 'failed'

---

## Test 9: Automated Test Suite

Run the full automated test suite:

```bash
# Run all tests
python3 -m pytest tests/ -v

# Run only E2E scraping tests
python3 -m pytest tests/test_e2e/test_scraping_flow.py -v

# Run with coverage (if pytest-cov installed)
python3 -m pytest tests/test_e2e/test_scraping_flow.py --cov=app.scrapers --cov=app.scraper -v
```

Expected:
- [ ] All tests pass (97+ total tests)
- [ ] No test warnings (except expected ones)
- [ ] No test failures or errors

---

## Test Results Log

| Test | Date | Result | Notes |
|------|------|--------|-------|
| Frontend UI | | [ ] | |
| GET /api/scrape | | [ ] | |
| POST /api/scrape | | [ ] | |
| NFO content | | [ ] | |
| Poster download | | [ ] | |
| DB status update | | [ ] | |
| Emby integration | | [ ] | |
| SSIS-743 real code | | [ ] | |
| Error handling | | [ ] | |
| Automated tests | | [ ] | |
