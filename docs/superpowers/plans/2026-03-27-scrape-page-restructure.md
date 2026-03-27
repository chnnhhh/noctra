# Scrape Page Restructure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the frontend from 3 tabs (scan/scrape/history) to 2 tabs (scan/scrape), replacing the incorrectly added scrape dashboard with a properly structured scrape page that mirrors the scan page.

**Architecture:** In-place refactor of 6 frontend files. The scrape page uses the same Alpine.js state-driven pattern as the scan page, with separate state variables (`scrapeFiles`, `scrapeSelectedFiles`, etc.) that follow identical computed property and method patterns.

**Tech Stack:** Alpine.js 3.x (CDN), vanilla JS (no build step), CSS (dark theme, existing design system)

**Spec:** `docs/superpowers/specs/2026-03-27-scrape-page-restructure-design.md`

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `static/js/render.js` | Display helpers, icons, status text | Modify |
| `static/js/state.js` | Alpine.js reactive state | Modify |
| `static/js/features.js` | User interactions, view switching, API calls | Modify |
| `static/js/scrape.js` | Scrape API module | Rewrite |
| `static/index.html` | Page structure, Alpine.js templates | Rewrite |
| `static/css/index.css` | Remove history-mode styles | Modify |

---

### Task 1: Update status labels, filter labels, and add sparkles icon in render.js

**Files:**
- Modify: `static/js/render.js`

- [ ] **Step 1: Update `getStatusText` to use new labels**

Replace `getStatusText` method body:

```javascript
getStatusText(status) {
    const map = {
        'pending': '待整理',
        'duplicate': '重复',
        'target_exists': '已存在',
        'processed': '已整理',
        'scraped': '已刮削',
        'skipped': '未识别',
        'failed': '失败'
    };
    return map[status] || status;
},
```

- [ ] **Step 2: Update `getBatchItemStatusText` to use new labels**

Replace `getBatchItemStatusText` method body:

```javascript
getBatchItemStatusText(status) {
    const map = {
        pending: '待整理',
        processing: '处理中',
        success: '已整理',
        skipped: '已跳过',
        failed: '失败'
    };
    return map[status] || status;
},
```

- [ ] **Step 3: Update `getFilterLabel` to use new labels**

Replace `getFilterLabel` method body:

```javascript
getFilterLabel(filter) {
    const map = {
        all: '全部',
        identified: '已识别',
        unidentified: '未识别',
        pending: '待整理',
        duplicate: '重复',
        target_exists: '已存在',
        processed: '已整理'
    };
    return map[filter] || filter;
},
```

- [ ] **Step 4: Update `getSelectionDisabledReason` label**

Change `'仅待处理项可加入整理集合'` to `'仅待整理项可加入整理集合'`.

- [ ] **Step 5: Add `sparkles` icon to `getUiIcon`**

Add inside the `icons` object (after the `cancel` entry):

```javascript
sparkles: `
    <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 2l1.1 3.4L16.5 7l-3.4 1.6L12 12l-1.1-3.4L7.5 7l3.4-1.6z"/>
        <path d="M5 14l.6 1.8L7.5 17l-1.9.7L5 19.5l-.6-1.8L2.5 17l1.9-.7z"/>
        <path d="M17 13l.7 2.2L20 16.5l-2.3.8L17 19.5l-.7-2.2L14.5 16.5l2.3-.8z"/>
    </svg>
`,
```

- [ ] **Step 6: Add scrape render helpers**

Add these methods after `getDisplayStatusText`:

```javascript
getScrapeStatusText(file) {
    const map = {
        'pending': '待刮削',
        'success': '已刮削',
        'failed': '刮削失败'
    };
    return map[file.scrape_status] || file.scrape_status || '-';
},

getScrapeBadgeClass(file) {
    const map = {
        'pending': 'pending',
        'success': 'processed',
        'failed': 'failed'
    };
    return map[file.scrape_status] || 'pending';
},

canSelectScrapeFile(file) {
    return this.view === 'scrape' &&
        file.scrape_status === 'pending';
},

getScrapeStatusActions(file) {
    if (file.scrape_status === 'pending' || file.scrape_status === 'failed') {
        return [
            { key: 'scrape', label: '刮削', icon: 'sparkles' }
        ];
    }
    return [];
},

hasScrapeStatusAction(file) {
    return this.view === 'scrape' && this.getScrapeStatusActions(file).length > 0;
},

getScrapeFilterLabel(filter) {
    const map = {
        all: '全部',
        pending: '待刮削',
        success: '已刮削',
        failed: '刮削失败'
    };
    return map[filter] || filter;
},
```

- [ ] **Step 7: Remove `history` branch from `compareStatusSort`**

In `compareStatusSort`, remove the `if (this.view === 'history')` branch and always use `return this.compareCodeSort(a, b, 1);` as the tiebreaker:

```javascript
compareStatusSort(a, b, direction = this.sortDirection) {
    const multiplier = direction === 'asc' ? 1 : -1;
    const diff = (this.getStatusSortWeight(a) - this.getStatusSortWeight(b)) * multiplier;
    if (diff !== 0) {
        return diff;
    }
    return this.compareCodeSort(a, b, 1);
},
```

- [ ] **Step 8: Remove `historyFilesCache` reference from `getResultLabel`**

```javascript
getResultLabel(result) {
    const match = this.scanFilesCache.find(file => file.id === result.file_id);
    return match?.identified_code || this.getFilename(result.original_path);
},
```

- [ ] **Step 9: Commit**

```bash
git add static/js/render.js
git commit -m "refactor: update status labels and add scrape render helpers"
```

---

### Task 2: Add scrape-specific state and computed properties in state.js

**Files:**
- Modify: `static/js/state.js`

- [ ] **Step 1: Replace history state with scrape state**

Replace the state initialization section. Remove `historyFilesCache`, `historyLoaded`. Change `view` comment. Replace `scrapeFilter`/`scrapeSort` with expanded scrape state:

```javascript
            files: [],
            scanFilesCache: [],
            scrapeFilesCache: [],
            selectedFiles: {},
            stats: {
                total_files: 0,
                identified: 0,
                unidentified: 0,
                pending: 0,
                processed: 0
            },
            scanLoaded: false,
            scrapeLoaded: false,
            view: 'scan', // 'scan' or 'scrape'
            currentFilter: 'all',
            sortField: 'default',
            sortDirection: 'asc',
            scrapeFilter: 'all',
            scrapeSortField: 'code',
            scrapeSortDirection: 'asc',
            scrapeSelectedFiles: {},
            scrapePage: 1,
```

- [ ] **Step 2: Add scrape-specific computed properties**

After the existing `selectedEntries` getter, add:

```javascript
            get scrapeHasSelected() {
                return Object.values(this.scrapeSelectedFiles).some(v => v);
            },

            get scrapeSelectedCount() {
                return Object.values(this.scrapeSelectedFiles).filter(v => v).length;
            },

            get scrapeSelectedEntries() {
                return this.scrapeFilesCache.filter(file => this.scrapeSelectedFiles[file.id]);
            },

            get scrapeFilteredFiles() {
                if (this.scrapeFilter === 'all') {
                    return this.scrapeFilesCache;
                }
                return this.scrapeFilesCache.filter(f => f.scrape_status === this.scrapeFilter);
            },

            get scrapeSortFieldOptions() {
                return [
                    { value: 'code', label: '番号' },
                    { value: 'scrape_time', label: '刮削时间' },
                    { value: 'status', label: '状态' }
                ];
            },

            get scrapeSortedFiles() {
                const files = [...this.scrapeFilteredFiles];
                const dir = this.scrapeSortDirection === 'asc' ? 1 : -1;

                return files.sort((a, b) => {
                    if (this.scrapeSortField === 'code') {
                        return this.compareNatural(a.identified_code || '', b.identified_code || '') * dir;
                    }
                    if (this.scrapeSortField === 'scrape_time') {
                        const aTime = Date.parse(a.last_scrape_at || '') || 0;
                        const bTime = Date.parse(b.last_scrape_at || '') || 0;
                        const diff = (aTime - bTime) * dir;
                        if (diff !== 0) return diff;
                        return this.compareNatural(a.identified_code || '', b.identified_code || '');
                    }
                    if (this.scrapeSortField === 'status') {
                        const statusOrder = { pending: 0, success: 1, failed: 2 };
                        const diff = ((statusOrder[a.scrape_status] ?? 9) - (statusOrder[b.scrape_status] ?? 9)) * dir;
                        if (diff !== 0) return diff;
                        return this.compareNatural(a.identified_code || '', b.identified_code || '');
                    }
                    return 0;
                });
            },

            get scrapeTotalPages() {
                return Math.max(1, Math.ceil(this.scrapeSortedFiles.length / this.pageSize));
            },

            get scrapeCurrentPageValue() {
                return Math.min(this.scrapePage, this.scrapeTotalPages);
            },

            get scrapePageRangeStart() {
                if (this.scrapeSortedFiles.length === 0) return 0;
                return ((this.scrapeCurrentPageValue - 1) * this.pageSize) + 1;
            },

            get scrapePageRangeEnd() {
                if (this.scrapeSortedFiles.length === 0) return 0;
                return Math.min(this.scrapePageRangeStart + this.pageSize - 1, this.scrapeSortedFiles.length);
            },

            get scrapePaginatedFiles() {
                const start = (this.scrapeCurrentPageValue - 1) * this.pageSize;
                return this.scrapeSortedFiles.slice(start, start + this.pageSize);
            },

            get scrapeCurrentPageSelectableFiles() {
                return this.scrapePaginatedFiles.filter(file => this.canSelectScrapeFile(file));
            },

            get scrapePageSelectedCount() {
                return this.scrapeCurrentPageSelectableFiles.filter(file => this.scrapeSelectedFiles[file.id]).length;
            },

            get scrapeAllSelected() {
                return this.scrapeCurrentPageSelectableFiles.length > 0 &&
                       this.scrapePageSelectedCount === this.scrapeCurrentPageSelectableFiles.length;
            },

            get scrapePageSelectionState() {
                if (this.scrapePageSelectedCount === 0) return 'none';
                if (this.scrapePageSelectedCount === this.scrapeCurrentPageSelectableFiles.length) return 'all';
                return 'partial';
            },
```

- [ ] **Step 3: Remove history branch from `sortFieldOptions`**

Replace `sortFieldOptions` getter:

```javascript
            get sortFieldOptions() {
                return [
                    { value: 'default', label: '默认排序' },
                    { value: 'code', label: '番号' },
                    { value: 'status', label: '状态' }
                ];
            },
```

- [ ] **Step 4: Commit**

```bash
git add static/js/state.js
git commit -m "refactor: replace history state with scrape page state and computed properties"
```

---

### Task 3: Add scrape page interaction methods in features.js

**Files:**
- Modify: `static/js/features.js`

- [ ] **Step 1: Replace `resetSortForView` — remove history branch**

```javascript
            resetSortForView(viewName = this.view) {
                if (viewName === 'scrape') {
                    return;
                }
                this.sortField = 'default';
                this.sortDirection = 'asc';
            },
```

- [ ] **Step 2: Remove `historyLoaded` references**

Remove `this.historyLoaded = false;` from `refreshAfterBatchCompletion` and `executeDelete`.

- [ ] **Step 3: Replace `switchVisibleFiles` — remove history**

```javascript
            switchVisibleFiles() {
                this.files = this.scanFilesCache;
                this.selectedFiles = {};
                this.currentPage = 1;
                this.closeStatusMenu();
            },
```

- [ ] **Step 4: Replace `switchView` — remove history, use Alpine-driven scrape**

```javascript
            async switchView(viewName) {
                this.view = viewName;
                this.resetSortForView(viewName);
                this.currentFilter = 'all';
                this.error = null;
                this.success = null;

                if (viewName === 'scrape') {
                    if (!this.scrapeLoaded) {
                        await this.loadScrapeFiles();
                        return;
                    }
                    return;
                }

                if (!this.scanLoaded) {
                    await this.scanFiles();
                    return;
                }

                this.files = this.scanFilesCache;
                this.selectedFiles = {};
                this.currentPage = 1;
                this.closeStatusMenu();
            },
```

- [ ] **Step 5: Replace `loadHistory` with `loadScrapeFiles`**

Delete the `loadHistory` method. Add in its place:

```javascript
            async loadScrapeFiles() {
                this.loading = true;
                this.loadingText = '正在加载刮削列表...';
                this.error = null;
                this.success = null;

                try {
                    const response = await fetch('/api/scrape');
                    const data = await response.json();

                    if (!response.ok) {
                        throw new Error(data.detail || '加载刮削列表失败');
                    }

                    this.scrapeFilesCache = (data.items || []).map(item => ({
                        id: item.file_id,
                        identified_code: item.code,
                        target_path: item.target_path || '',
                        scrape_status: item.scrape_status || 'pending',
                        last_scrape_at: item.last_scrape_at || null,
                        original_path: item.original_path || '',
                        status: item.status || 'processed'
                    }));
                    this.scrapeLoaded = true;
                    this.scrapeSelectedFiles = {};
                    this.scrapePage = 1;
                    this.closeStatusMenu();
                } catch (e) {
                    this.error = '加载刮削列表失败: ' + e.message;
                } finally {
                    this.loading = false;
                }
            },
```

- [ ] **Step 6: Add scrape interaction methods**

Add after `loadScrapeFiles`:

```javascript
            setScrapeFilter(filter) {
                this.scrapeFilter = filter;
                this.scrapePage = 1;
                this.closeStatusMenu();
            },

            setScrapeSortField(field) {
                this.scrapeSortField = field;
                this.scrapePage = 1;
                this.closeStatusMenu();
            },

            toggleScrapeSortDirection() {
                this.scrapeSortDirection = this.scrapeSortDirection === 'desc' ? 'asc' : 'desc';
                this.scrapePage = 1;
                this.closeStatusMenu();
            },

            setScrapeFileSelected(file, checked) {
                if (!this.canSelectScrapeFile(file)) return;
                const next = { ...this.scrapeSelectedFiles };
                if (checked) { next[file.id] = true; } else { delete next[file.id]; }
                this.scrapeSelectedFiles = next;
            },

            toggleScrapeFileSelection(file) {
                if (!this.canSelectScrapeFile(file)) return;
                this.setScrapeFileSelected(file, !this.scrapeSelectedFiles[file.id]);
            },

            toggleScrapeCurrentPageSelection(forceChecked = null) {
                const shouldSelect = forceChecked === null ? this.scrapePageSelectionState !== 'all' : forceChecked;
                const next = { ...this.scrapeSelectedFiles };
                this.scrapeCurrentPageSelectableFiles.forEach(file => {
                    if (shouldSelect) { next[file.id] = true; } else { delete next[file.id]; }
                });
                this.scrapeSelectedFiles = next;
            },

            clearScrapeSelection() {
                this.scrapeSelectedFiles = {};
            },

            async handleScrapeAction(file) {
                this.closeStatusMenu();
                try {
                    const response = await fetch(`/api/scrape/${file.id}`, { method: 'POST' });
                    const result = await response.json();
                    if (!response.ok) {
                        throw new Error(result.detail || '刮削失败');
                    }
                    this.success = `${file.identified_code} 刮削成功`;
                    await this.loadScrapeFiles();
                } catch (e) {
                    this.error = '刮削失败: ' + e.message;
                }
            },

            async confirmBatchScrape() {
                const entries = this.scrapeSelectedEntries.filter(file => this.canSelectScrapeFile(file));
                if (entries.length === 0) return;
                this.scrapeSelectedFiles = {};
                let succeeded = 0;
                let failed = 0;

                for (const file of entries) {
                    try {
                        const response = await fetch(`/api/scrape/${file.id}`, { method: 'POST' });
                        const result = await response.json();
                        if (!response.ok) throw new Error(result.detail || '刮削失败');
                        succeeded++;
                    } catch (e) {
                        failed++;
                    }
                }

                if (failed === 0) {
                    this.success = `批量刮削完成：${succeeded} 项成功`;
                } else {
                    this.success = `批量刮削完成：${succeeded} 项成功，${failed} 项失败`;
                }
                await this.loadScrapeFiles();
            },

            goToScrapePage(page) {
                const nextPage = Math.max(1, Math.min(this.scrapeTotalPages, page));
                this.scrapePage = nextPage;
                this.closeStatusMenu();
            },
```

- [ ] **Step 7: Commit**

```bash
git add static/js/features.js
git commit -m "feat: add scrape page interactions, remove history view logic"
```

---

### Task 4: Rewrite scrape.js to API-only module

**Files:**
- Modify: `static/js/scrape.js`

- [ ] **Step 1: Replace entire file**

```javascript
// static/js/scrape.js
/** Scrape API module — state and rendering handled by Alpine.js */

const ScrapeAPI = {
    async getList(params = {}) {
        const searchParams = new URLSearchParams({
            page: (params.page || 1).toString(),
            per_page: (params.perPage || 50).toString(),
            filter: params.filter || 'all',
            sort: params.sort || 'code'
        });

        const response = await fetch(`/api/scrape?${searchParams}`);
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || `HTTP ${response.status}`);
        }
        return await response.json();
    },

    async scrapeSingle(fileId) {
        const response = await fetch(`/api/scrape/${fileId}`, {
            method: 'POST'
        });
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.detail || `HTTP ${response.status}`);
        }
        return await response.json();
    }
};
```

- [ ] **Step 2: Commit**

```bash
git add static/js/scrape.js
git commit -m "refactor: strip scrape.js to API-only module"
```

---

### Task 5: Rewrite index.html — 2 tabs, remove dashboard, add scrape page

**Files:**
- Modify: `static/index.html`

- [ ] **Step 1: Update header nav to 2 tabs**

Replace the `header-nav` div:

```html
            <div class="header-nav">
                <a href="#" @click.prevent="switchView('scan')" :class="{ 'active': view === 'scan' }">📂 扫描</a>
                <a href="#" @click.prevent="switchView('scrape')" :class="{ 'active': view === 'scrape' }">
                    <span x-html="getUiIcon('sparkles')" style="width: 16px; height: 16px; display: inline-block; vertical-align: -2px;"></span> 刮削
                </a>
            </div>
```

- [ ] **Step 2: Update stat cards to use new labels**

Change "待处理" → "待整理" and "已处理" → "已整理" in the stat cards section.

- [ ] **Step 3: Change panel-surface visibility to `view === 'scan'` only**

Replace `x-show="view !== 'scrape'"` with `x-show="view === 'scan'"`. Remove all history text from table-header, toolbar-pill, filter buttons.

- [ ] **Step 4: Update scan filter labels**

Change "待处理" → "待整理" in filter buttons.

- [ ] **Step 5: Clean scan table — remove history references**

Remove `history-mode` class, `history-row` class, `col-time` header with `x-show="view === 'history'"`, and `cell-time` with `history-time` divs.

- [ ] **Step 6: Update empty state**

Remove history empty state text.

- [ ] **Step 7: Replace old scrape tab with new scrape page structure**

Replace the entire `<!-- Scrape Tab -->` section with the new Alpine.js-driven scrape page. The new section includes:
- Page header with title/subtitle
- Actions bar with batch scrape button + select/deselect page buttons
- Toolbar with filter pills (全部/待刮削/已刮削/刮削失败), selection rail, sort (番号/刮削时间/状态), per-page, pagination
- Table with columns: checkbox, 番号, 整理后路径, 刮削状态, 上次刮削
- Empty state
- Loading state

The complete replacement HTML is in the spec document section 3.1-3.5. Use identical CSS classes and Alpine.js patterns as the scan page.

- [ ] **Step 8: Commit**

```bash
git add static/index.html
git commit -m "feat: restructure HTML to 2 tabs, add scrape page mirroring scan page"
```

---

### Task 6: Clean up CSS — remove history-mode rules

**Files:**
- Modify: `static/css/index.css`

- [ ] **Step 1: Remove all `.table-container.history-mode` CSS rules**

Remove selectors matching `.table-container.history-mode ...` and `tbody tr.row.history-row`. Keep `.history-time`, `.history-time-main`, `.history-time-sub` (reused by scrape page).

- [ ] **Step 2: Commit**

```bash
git add static/css/index.css
git commit -m "chore: remove history-mode CSS rules"
```

---

### Task 7: Visual verification

- [ ] **Step 1: Start local server and verify in browser**

```bash
cd /Users/liujiejian/git/noctra && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 4020
```

Open `http://127.0.0.1:4020` and verify:
1. Only 2 tabs: 扫描 and 刮削
2. Scan page shows 待整理/已整理 labels
3. Scrape page has proper layout (no dashboard cards)
4. Scrape page toolbar, table, pagination work
5. No "历史" text anywhere
6. Status badges display correctly

- [ ] **Step 2: Fix any issues found and commit**

```bash
git add -A
git commit -m "fix: visual adjustments from scrape page restructure verification"
```
