# Scrape Page Restructure Design

Date: 2026-03-27

## Summary

Restructure the frontend from 3 tabs (scan/scrape/history) to 2 tabs (scan/scrape). Replace the old "history" tab and the incorrectly added scrape dashboard with a properly structured scrape page that mirrors the scan page layout.

## Constraints

- Only modify frontend files (HTML, JS, CSS)
- Do not modify backend API routes, database schema, or scraping logic
- Do not add new pages or dashboard-style layouts
- The scrape page must be a structural mirror of the scan page

## 1. Tab Structure

**Before**: 3 tabs — 扫描, 刮削, 历史

**After**: 2 tabs — 扫描, 刮削

- 扫描 tab: unchanged, uses folder icon
- 刮削 tab: replaces old "历史" tab, uses sparkles icon (3 small starbursts conveying metadata enrichment)

The sparkles icon SVG:
```svg
<svg viewBox="0 0 24 24">
  <path d="M12 2l1.1 3.4L16.5 7l-3.4 1.6L12 12l-1.1-3.4L7.5 7l3.4-1.6z"/>
  <path d="M5 14l.6 1.8L7.5 17l-1.9.7L5 19.5l-.6-1.8L2.5 17l1.9-.7z"/>
  <path d="M17 13l.7 2.2L20 16.5l-2.3.8L17 19.5l-.7-2.2L14.5 16.5l2.3-.8z"/>
</svg>
```

## 2. Status Label Mapping

| Internal status | Old label | New label |
|---|---|---|
| `pending` | 待处理 | **待整理** |
| `processed` | 已处理 | **已整理** |
| `scraped` | — | **已刮削** |
| `duplicate` | 重复 | 重复 |
| `target_exists` | 已存在 | 已存在 |
| `skipped` | 未识别 | 未识别 |
| `failed` | 失败 | 失败 |

The word "历史" and its semantics are completely removed from the UI.

## 3. Scrape Page Structure

The scrape page mirrors the scan page structure exactly. No dashboard cards, no native selects, no independent layout.

### 3.1 Page Header

- Title: "刮削管理"
- Subtitle: "对已整理的文件进行元数据刮削，补全影片信息。"

Uses existing `table-title` and `table-subtitle` CSS classes.

### 3.2 Actions Bar

Same `actions` container pattern as scan page:

- Left group (primary):
  - "批量刮削" button with sparkles icon, disabled when no items selected
  - Shows selected count: `批量刮削 (N)`
- Right group (secondary):
  - "选中本页" button
  - "取消本页" button

### 3.3 Toolbar

Same `table-meta toolbar` structure as scan page:

- **Filter pills** (left): 全部 / 已整理 / 已刮削 / 刮削失败
  - Uses existing `filter-button` / `filter-subtle` classes
- **Selection status rail** (right): "已选 X 项" + inline actions
  - Uses existing `page-inline-status` / `selection-inline-count` classes
- **Sort control rail**: 番号 / 刮削时间 / 状态
  - Uses existing `control-rail` / `sort-composer` classes
- **Per-page rail**: 20 / 50 / 100
  - Uses existing `control-rail` / `rail-button` classes
- **Pagination rail**: range display + mini-pager
  - Uses existing `mini-pager` classes

### 3.4 Table

Same `table-container` and `table` structure as scan page:

| Column | Width class | Content |
|---|---|---|
| Checkbox | `col-select` | Same checkbox widget as scan page |
| 番号 (Code) | `col-code` | `identified_code` badge |
| 整理后路径 (Output) | `col-target` | `target_path` with copy-on-click |
| 刮削状态 (Status) | `col-status` | Status badge with hover actions |
| 上次刮削 (Scraped) | `col-time` | `last_scrape_at` formatted date/time |
| 操作 (Action) | — | Row-level "刮削" button |

Row interaction patterns:
- Checkbox selection identical to scan page
- Status hover reveals action buttons (same `status-action` pattern)
- Row-level "刮削" button uses same icon-action styling as scan page's "整理/删除"
- Row hover glow effect (`updateRowGlow`) identical to scan page

### 3.5 Empty State

Same `.empty` container with:
- Icon
- "暂无已整理文件" text
- "完成扫描和整理后，可以在此进行刮削" subtext

### 3.6 Data Flow

- Separate state variables: `scrapeFilesCache`, `scrapeFiles`, `scrapeSelectedFiles`, `scrapeFilter`, `scrapeSort`, `scrapePage`, `scrapeLoaded`
- `switchView('scrape')` triggers data load from existing API (`/api/scrape`)
- Selection and pagination follow identical patterns to scan page
- `canSelectScrapeFile(file)` determines which rows are selectable (已整理 items)

## 4. File Changes

| File | Changes |
|---|---|
| `static/index.html` | 2-tab navigation; remove scrape dashboard; remove history references; add full scrape page structure (title, actions, toolbar, table, empty state) using scan page template |
| `static/js/state.js` | Add scrape-specific state; remove `historyFilesCache`, `historyLoaded`; simplify `view` to `'scan'`/`'scrape'` |
| `static/js/render.js` | Update `getStatusText` labels; add scrape status renderers; add sparkles icon; remove history renderers |
| `static/js/features.js` | Add scrape page interaction methods; simplify `switchView`; remove `loadHistory` |
| `static/js/scrape.js` | Rewrite from vanilla DOM to Alpine.js state-driven; keep `ScrapeAPI`, remove `ScrapePage` |
| `static/css/index.css` | Remove `.scrape-stats-cards` styles; adjust table column widths for scrape page if needed |

## 5. Placeholder Items (Future Work)

These are included as UI entry points but with simplified logic:

- Single-file scrape action: calls existing API, refreshes list on completion
- Batch scrape progress panel: will reuse batch-panel pattern, polling logic to be added later
- Retry failed scrapes: UI entry exists, retry logic deferred
- `last_scrape_at` column: uses API field if available, shows `-` if not present

## 6. What This Change Does NOT Do

- Does not modify backend API routes or scraping execution logic
- Does not add new database fields
- Does not implement NFO file handling
- Does not add new pages or navigation items
- Does not implement batch scrape polling/progress (structure only)
