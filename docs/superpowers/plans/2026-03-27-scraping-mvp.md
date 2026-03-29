# Scraping v1 MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Noctra 添加最小可行的元数据刮削能力,支持单源(JavDB)刮削,生成 Emby 兼容的 NFO 文件和封面图。

**Architecture:**
- 在现有整理流程基础上,新增独立的刮削子系统
- 数据库新增 `scrape_status` 字段,状态独立管理
- JavDB 爬虫使用 curl_cffi 模拟浏览器,固定延迟 2 秒
- 前端新增"刮削" tab,只支持单条刮削,不支持批量

**Tech Stack:**
- Backend: Python 3.10+, FastAPI, aiosqlite
- Scraping: curl-cffi, BeautifulSoup4, aiohttp
- Database: SQLite (schema 扩展)
- Frontend: Vanilla JS + Alpine.js

**MVP Scope:**
- 单源刮削: 仅 JavDB
- 核心字段: title, plot, actors, release, studio, poster_url
- 图片: 仅 poster
- 刮削方式: 仅单条,不支持批量
- NFO: 简化版,仅包含必需字段

**明确不在本期:**
- 多源爬取、元数据合并、批量刮削、fanart/preview 图片、重试机制、缓存、代理支持

---

## File Structure

### New Files

```
app/
├── scrapers/
│   ├── __init__.py
│   ├── base.py                    # 爬虫基类
│   ├── metadata.py                # 元数据模型
│   ├── javdb.py                   # JavDB 爬虫
│   └── writers/
│       ├── __init__.py
│       ├── nfo.py                 # NFO 生成器
│       └── image.py               # 图片下载器

tests/
├── test_scrapers/
│   ├── test_base.py
│   ├── test_metadata.py
│   ├── test_javdb.py
│   └── test_writers.py

migrations/
└── add_scraping.sql               # 数据库升级脚本
```

### Modified Files

```
app/
├── main.py                        # 新增刮削 API 路由
├── models.py                      # 新增刮削相关 Pydantic 模型

static/
├── index.html                     # 新增"刮削" tab
├── js/
│   ├── app.js                     # 注册刮削相关模块
│   ├── state.js                   # 新增刮削状态
│   └── scrape.js                  # 刮削页逻辑(new file)
```

---

## Phase 1: 数据模型 & 状态扩展

### Task 1.1: 创建数据库迁移脚本

**Files:**
- Create: `migrations/add_scraping.sql`

**Description:** 添加刮削相关字段到 `files` 表,创建索引,迁移现有状态。

- [ ] **Step 1: 创建迁移脚本文件**

```sql
-- migrations/add_scraping.sql

-- 添加刮削相关字段
ALTER TABLE files ADD COLUMN scrape_status TEXT DEFAULT 'pending';
ALTER TABLE files ADD COLUMN last_scrape_at TEXT;

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_files_scrape_status ON files(scrape_status);

-- 迁移现有状态: processed -> organized
UPDATE files SET status = 'organized' WHERE status = 'processed';

-- 验证迁移
SELECT 'Migration completed' as status,
       (SELECT COUNT(*) FROM files WHERE status = 'organized') as organized_count,
       (SELECT COUNT(*) FROM files WHERE scrape_status = 'pending') as pending_count;
```

- [ ] **Step 2: 本地测试迁移脚本**

```bash
# 备份数据库
cp data/noctra.db data/noctra.db.backup

# 执行迁移
sqlite3 data/noctra.db < migrations/add_scraping.sql

# 验证结果
sqlite3 data/noctra.db "SELECT status, scrape_status, COUNT(*) FROM files GROUP BY status, scrape_status;"
```

Expected output: 应该看到 `organized` 状态的记录,且 `scrape_status` 为 `pending`

- [ ] **Step 3: 提交**

```bash
git add migrations/add_scraping.sql
git commit -m "feat: add scraping fields to database schema"
```

---

### Task 1.2: 定义元数据模型

**Files:**
- Create: `app/scrapers/__init__.py`
- Create: `app/scrapers/metadata.py`
- Test: `tests/test_scrapers/test_metadata.py`

**Description:** 定义最小化的元数据数据类,只包含 7 个核心字段。

- [ ] **Step 1: 创建 scrapers 包**

```python
# app/scrapers/__init__.py
"""Scraping subsystem for Noctra."""

from .metadata import ScrapingMetadata

__all__ = ['ScrapingMetadata']
```

- [ ] **Step 2: 定义元数据模型**

```python
# app/scrapers/metadata.py
"""Metadata models for scraping."""

from dataclasses import dataclass, field
from typing import List

@dataclass
class ScrapingMetadata:
    """最小化元数据模型 (MVP)"""

    # 基础信息
    code: str                          # 番号 "SSIS-123"
    title: str                         # 标题
    plot: str                          # 剧情简介

    # 制作信息
    actors: List[str] = field(default_factory=list)     # 演员列表
    studio: str = ""                   # 制作商
    release: str = ""                  # 发布日期 YYYY-MM-DD

    # 媒体资源
    poster_url: str = ""               # 封面图 URL

    def to_dict(self) -> dict:
        """转换为字典,用于 NFO 生成"""
        return {
            "code": self.code,
            "title": self.title,
            "plot": self.plot,
            "actors": self.actors,
            "studio": self.studio,
            "release": self.release,
            "poster": f"{self.code}-poster.jpg" if self.poster_url else None,
        }
```

- [ ] **Step 3: 编写测试**

```python
# tests/test_scrapers/test_metadata.py
"""Tests for metadata models."""

import pytest
from app.scrapers.metadata import ScrapingMetadata

def test_metadata_creation():
    """测试元数据创建"""
    metadata = ScrapingMetadata(
        code="SSIS-123",
        title="テストタイトル",
        plot="テストプロット",
        actors=["女優1", "女優2"],
        studio="S1 NO.1 STYLE",
        release="2023-06-27",
        poster_url="https://example.com/poster.jpg"
    )

    assert metadata.code == "SSIS-123"
    assert metadata.title == "テストタイトル"
    assert len(metadata.actors) == 2

def test_metadata_to_dict():
    """测试转换为字典"""
    metadata = ScrapingMetadata(
        code="SSIS-123",
        title="タイトル",
        plot="プロット",
        poster_url="https://example.com/poster.jpg"
    )

    result = metadata.to_dict()

    assert result["code"] == "SSIS-123"
    assert result["poster"] == "SSIS-123-poster.jpg"
    assert result["studio"] == ""  # 默认值
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/test_scrapers/test_metadata.py -v
```

Expected: 所有测试通过

- [ ] **Step 5: 提交**

```bash
git add app/scrapers/ tests/test_scrapers/test_metadata.py
git commit -m "feat: add scraping metadata model"
```

---

### Task 1.3: 扩展 Pydantic API 模型

**Files:**
- Modify: `app/models.py`

**Description:** 添加刮削相关的请求/响应模型。

- [ ] **Step 1: 在 models.py 末尾添加刮削模型**

```python
# app/models.py (在文件末尾添加)

# ===== Scraping Models (MVP) =====

class ScrapeListItem(BaseModel):
    """刮削列表项"""
    file_id: int
    code: str
    target_path: str
    scrape_status: str  # pending, success, failed
    last_scrape_at: Optional[str] = None

class ScrapeResponse(BaseModel):
    """单条刮削响应"""
    success: bool
    code: Optional[str] = None
    error: Optional[str] = None
```

- [ ] **Step 2: 验证导入**

```bash
python3 -c "from app.models import ScrapeListItem, ScrapeResponse; print('OK')"
```

Expected: 无错误输出 "OK"

- [ ] **Step 3: 提交**

```bash
git add app/models.py
git commit -m "feat: add scraping API models"
```

---

## Phase 2: 刮削页 UI (最小版)

### Task 2.1: 更新前端状态管理

**Files:**
- Modify: `static/js/state.js`

**Description:** 在状态管理中添加刮削相关状态和计算属性。

- [ ] **Step 1: 在 state.js 中添加刮削状态**

找到 `const state = {` 定义,在适当位置添加:

```javascript
// static/js/state.js

const state = {
    // ... 现有状态 ...

    // 刮削状态
    scrapeFilter: 'all',  // all, pending, success, failed
    scrapeSort: 'code',   // code, scrape_time
};
```

- [ ] **Step 2: 提交**

```bash
git add static/js/state.js
git commit -m "feat: add scraping state to state management"
```

---

### Task 2.2: 创建刮削页逻辑模块

**Files:**
- Create: `static/js/scrape.js`

**Description:** 实现刮削页的核心逻辑:列表加载、筛选、单条刮削。

- [ ] **Step 1: 创建 scrape.js 模块**

```javascript
// static/js/scrape.js
/** 刮削页逻辑模块 (MVP) */

const ScrapeAPI = {
    async getList(page = 1, perPage = 50, filter = 'all', sort = 'code') {
        const params = new URLSearchParams({
            page: page.toString(),
            per_page: perPage.toString(),
            filter: filter,
            sort: sort
        });

        const response = await fetch(`/api/scrape?${params}`);
        return await response.json();
    },

    async scrapeSingle(fileId) {
        const response = await fetch(`/api/scrape/${fileId}`, {
            method: 'POST'
        });
        return await response.json();
    }
};

const ScrapePage = {
    currentPage: 1,
    perPage: 50,
    items: [],

    async loadList() {
        try {
            const result = await ScrapeAPI.getList(
                this.currentPage,
                this.perPage,
                state.scrapeFilter,
                state.scrapeSort
            );
            this.items = result.items || [];
            this.render();
        } catch (error) {
            console.error('加载刮削列表失败:', error);
            alert('加载失败: ' + error.message);
        }
    },

    async handleScrape(fileId, code) {
        if (!confirm(`确认刮削 ${code}?`)) {
            return;
        }

        const btn = document.querySelector(`[data-file-id="${fileId}"] .scrape-btn`);
        if (btn) {
            btn.disabled = true;
            btn.textContent = '刮削中...';
        }

        try {
            const result = await ScrapeAPI.scrapeSingle(fileId);

            if (result.success) {
                alert(`${code} 刮削成功!`);
                await this.loadList();  // 刷新列表
            } else {
                alert(`${code} 刮削失败: ${result.error}`);
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = '刮削';
                }
            }
        } catch (error) {
            console.error('刮削失败:', error);
            alert(`刮削失败: ${error.message}`);
            if (btn) {
                btn.disabled = false;
                btn.textContent = '刮削';
            }
        }
    },

    render() {
        const tbody = document.querySelector('#scrape-table tbody');
        if (!tbody) return;

        if (this.items.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center">暂无数据</td></tr>';
            return;
        }

        tbody.innerHTML = this.items.map(item => `
            <tr data-file-id="${item.file_id}">
                <td>${item.code}</td>
                <td>${this.renderStatus(item.scrape_status)}</td>
                <td>${item.last_scrape_at || '-'}</td>
                <td>
                    <button class="scrape-btn" data-action="scrape">刮削</button>
                </td>
            </tr>
        `).join('');

        // 绑定事件
        tbody.querySelectorAll('[data-action="scrape"]').forEach(btn => {
            btn.addEventListener('click', () => {
                const row = btn.closest('tr');
                const fileId = parseInt(row.dataset.fileId);
                const code = row.querySelector('td:first-child').textContent;
                this.handleScrape(fileId, code);
            });
        });
    },

    renderStatus(status) {
        const statusMap = {
            'pending': '<span class="status status-pending">待刮削</span>',
            'success': '<span class="status status-success">已刮削</span>',
            'failed': '<span class="status status-failed">刮削失败</span>'
        };
        return statusMap[status] || status;
    },

    init() {
        this.loadList();

        // 筛选器
        document.querySelector('#scrape-filter')?.addEventListener('change', (e) => {
            state.scrapeFilter = e.target.value;
            this.currentPage = 1;
            this.loadList();
        });

        // 排序器
        document.querySelector('#scrape-sort')?.addEventListener('change', (e) => {
            state.scrapeSort = e.target.value;
            this.loadList();
        });
    }
};
```

- [ ] **Step 2: 提交**

```bash
git add static/js/scrape.js
git commit -m "feat: add scraping page logic module"
```

---

### Task 2.3: 更新 HTML 结构

**Files:**
- Modify: `static/index.html`

**Description:** 添加"刮削" tab 的 HTML 结构。

- [ ] **Step 1: 在 tabs 区域添加刮削 tab**

找到 tabs 定义(通常在顶部导航),添加刮削 tab:

```html
<!-- static/index.html -->

<!-- 在现有 tabs 后添加 -->
<div class="tab" data-tab="scrape">
    <h2>刮削</h2>

    <!-- 统计卡 -->
    <div class="stats-cards">
        <div class="stat-card">
            <div class="stat-label">已整理总数</div>
            <div class="stat-value" id="stat-organized">-</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">待刮削</div>
            <div class="stat-value" id="stat-pending">-</div>
        </div>
        <div class="stat-card">
            <div class="stat-label">已刮削</div>
            <div class="stat-value" id="stat-scraped">-</div>
        </div>
    </div>

    <!-- 筛选和排序 -->
    <div class="toolbar">
        <select id="scrape-filter">
            <option value="all">全部</option>
            <option value="pending">待刮削</option>
            <option value="success">已刮削</option>
            <option value="failed">刮削失败</option>
        </select>

        <select id="scrape-sort">
            <option value="code">按番号</option>
            <option value="scrape_time">按刮削时间</option>
        </select>
    </div>

    <!-- 刮削列表表格 -->
    <table id="scrape-table">
        <thead>
            <tr>
                <th>番号</th>
                <th>刮削状态</th>
                <th>上次刮削时间</th>
                <th>操作</th>
            </tr>
        </thead>
        <tbody>
            <tr><td colspan="5" class="text-center">加载中...</td></tr>
        </tbody>
    </table>
</div>
```

- [ ] **Step 2: 在 app.js 中注册刮削模块初始化**

找到 `app.js` 中的 tab 切换逻辑,添加刮削页初始化:

```javascript
// static/js/app.js

// 在 tab 切换逻辑中添加
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        // ... 现有逻辑 ...

        if (tabName === 'scrape') {
            ScrapePage.init();
        }
    });
});
```

- [ ] **Step 3: 提交**

```bash
git add static/index.html static/js/app.js
git commit -m "feat: add scraping tab UI"
```

---

## Phase 3: 单源 Scraping (最小实现)

### Task 3.1: 实现爬虫基类

**Files:**
- Create: `app/scrapers/base.py`
- Test: `tests/test_scrapers/test_base.py`

**Description:** 实现爬虫抽象基类,包含 HTTP 请求封装和延迟控制。

- [ ] **Step 1: 创建爬虫基类**

```python
# app/scrapers/base.py
"""Base crawler class."""

import asyncio
from abc import ABC, abstractmethod
from typing import Optional
from curl_cffi import requests

from .metadata import ScrapingMetadata

class BaseCrawler(ABC):
    """爬虫基类 (MVP - 简化版)"""

    name: str  # 子类必须定义

    def __init__(self):
        self._session = None

    @abstractmethod
    async def crawl(self, code: str) -> Optional[ScrapingMetadata]:
        """爬取指定番号的元数据

        Args:
            code: 番号,如 "SSIS-123"

        Returns:
            ScrapingMetadata 对象,失败返回 None
        """
        pass

    async def _request(self, url: str) -> Optional[str]:
        """HTTP GET 请求封装 (MVP - 固定延迟,无代理/Cookie)

        Args:
            url: 目标 URL

        Returns:
            响应文本,失败返回 None
        """
        try:
            # 固定延迟 2 秒
            await asyncio.sleep(2)

            # 创建 session
            if self._session is None:
                self._session = requests.Session()

            # 执行请求
            response = self._session.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                },
                timeout=25,
                verify=False,
                impersonate="chrome",  # 模拟 Chrome 浏览器指纹
            )

            if response.status_code == 200:
                return response.text
            else:
                return None

        except Exception as e:
            print(f"{self.name} request error: {e}")
            return None
```

- [ ] **Step 2: 编写基础测试**

```python
# tests/test_scrapers/test_base.py
"""Tests for base crawler."""

import pytest
from app.scrapers.base import BaseCrawler

def test_base_crawler_is_abstract():
    """测试基类不能直接实例化"""
    with pytest.raises(TypeError):
        BaseCrawler()
```

- [ ] **Step 3: 运行测试**

```bash
pytest tests/test_scrapers/test_base.py -v
```

Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add app/scrapers/base.py tests/test_scrapers/test_base.py
git commit -m "feat: add base crawler class"
```

---

### Task 3.2: 实现 JavDB 爬虫

**Files:**
- Create: `app/scrapers/javdb.py`
- Test: `tests/test_scrapers/test_javdb.py`

**Description:** 实现 JavDB 爬虫,解析 HTML 提取元数据。

- [ ] **Step 1: 实现 JavDB 爬虫**

```python
# app/scrapers/javdb.py
"""JavDB crawler (MVP)."""

from typing import Optional
from bs4 import BeautifulSoup

from .base import BaseCrawler
from .metadata import ScrapingMetadata

class JavDBCrawler(BaseCrawler):
    """JavDB 爬虫"""

    name = "javdb"

    def _build_url(self, code: str) -> str:
        return f"https://javdb.com/v/{code}"

    async def crawl(self, code: str) -> Optional[ScrapingMetadata]:
        """爬取 JavDB 元数据"""
        url = self._build_url(code)
        html = await self._request(url)

        if not html:
            return None

        soup = BeautifulSoup(html, 'html.parser')

        # 提取标题
        title = self._extract_title(soup)
        if not title:
            return None  # 没有标题说明页面不存在或格式错误

        return ScrapingMetadata(
            code=code,
            title=title,
            plot=self._extract_plot(soup),
            actors=self._extract_actors(soup),
            studio=self._extract_studio(soup),
            release=self._extract_release(soup),
            poster_url=self._extract_poster(soup),
        )

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """提取标题"""
        # JavDB 标题通常在 h2.title 中
        title_elem = soup.select_one("h2.title")
        if title_elem:
            return title_elem.get_text(strip=True)
        return None

    def _extract_plot(self, soup: BeautifulSoup) -> str:
        """提取剧情简介"""
        # 通常在特定 div 中
        plot_elem = soup.select_one(".plot-text")
        if plot_elem:
            return plot_elem.get_text(strip=True)
        return ""

    def _extract_actors(self, soup: BeautifulSoup) -> list:
        """提取演员列表"""
        actors = []
        # 演员通常在链接中
        for actor_elem in soup.select(".actors a"):
            name = actor_elem.get_text(strip=True)
            if name:
                actors.append(name)
        return actors

    def _extract_studio(self, soup: BeautifulSoup) -> str:
        """提取制作商"""
        studio_elem = soup.select_one(".studio a")
        if studio_elem:
            return studio_elem.get_text(strip=True)
        return ""

    def _extract_release(self, soup: BeautifulSoup) -> str:
        """提取发布日期"""
        release_elem = soup.select_one(".release-date")
        if release_elem:
            return release_elem.get_text(strip=True)
        return ""

    def _extract_poster(self, soup: BeautifulSoup) -> str:
        """提取封面图 URL"""
        img_elem = soup.select_one(".poster img")
        if img_elem:
            return img_elem.get("src", "")
        return ""
```

**注意**: 以上选择器是示例,实际需要根据 JavDB 网站的当前 HTML 结构调整。

- [ ] **Step 2: 编写集成测试**

```python
# tests/test_scrapers/test_javdb.py
"""Tests for JavDB crawler."""

import pytest
from app.scrapers.javdb import JavDBCrawler

@pytest.mark.asyncio
async def test_javdb_crawl_success():
    """测试成功爬取 (使用真实番号)"""
    crawler = JavDBCrawler()
    result = await crawler.crawl("SSIS-123")

    # 注意: 这个测试依赖真实网站,可能不稳定
    # 在 CI/CD 中应该 mock
    if result:
        assert result.code == "SSIS-123"
        assert result.title is not None
        assert isinstance(result.actors, list)

@pytest.mark.asyncio
async def test_javdb_crawl_not_found():
    """测试爬取不存在的番号"""
    crawler = JavDBCrawler()
    result = await crawler.crawl("INVALID-CODE-999")

    assert result is None
```

- [ ] **Step 3: 本地测试爬虫**

创建测试脚本 `test_crawler.py`:

```python
import asyncio
from app.scrapers.javdb import JavDBCrawler

async def main():
    crawler = JavDBCrawler()
    result = await crawler.crawl("SSIS-123")

    if result:
        print(f"成功爬取: {result.title}")
        print(f"演员: {', '.join(result.actors)}")
        print(f"发布日期: {result.release}")
    else:
        print("爬取失败")

if __name__ == "__main__":
    asyncio.run(main())
```

运行测试:

```bash
python3 test_crawler.py
```

Expected: 能成功输出元数据,如果失败,检查 HTML 选择器是否需要调整。

- [ ] **Step 4: 运行单元测试**

```bash
pytest tests/test_scrapers/test_javdb.py -v
```

- [ ] **Step 5: 提交**

```bash
git add app/scrapers/javdb.py tests/test_scrapers/test_javdb.py test_crawler.py
git commit -m "feat: add JavDB crawler implementation"
```

---

## Phase 4: NFO + Poster 输出

### Task 4.1: 实现 NFO 生成器

**Files:**
- Create: `app/scrapers/writers/__init__.py`
- Create: `app/scrapers/writers/nfo.py`
- Test: `tests/test_scrapers/test_writers.py`

**Description:** 生成 Emby 兼容的简化版 NFO 文件。

- [ ] **Step 1: 创建 writers 包**

```python
# app/scrapers/writers/__init__.py
"""File writers for scraping output."""

from .nfo import write_nfo
from .image import download_poster

__all__ = ['write_nfo', 'download_poster']
```

- [ ] **Step 2: 实现 NFO 生成器**

```python
# app/scrapers/writers/nfo.py
"""NFO file generator (MVP - simplified Emby format)."""

from pathlib import Path
import xml.etree.ElementTree as ET

from ..metadata import ScrapingMetadata

def write_nfo(metadata: ScrapingMetadata, output_path: Path):
    """生成 Emby 兼容的 NFO 文件 (MVP - 简化版)

    Args:
        metadata: 元数据对象
        output_path: 输出文件路径
    """
    # 创建根元素
    movie = ET.Element("movie")

    # title
    title = ET.SubElement(movie, "title")
    title.text = metadata.title

    # plot
    plot = ET.SubElement(movie, "plot")
    if metadata.plot:
        plot.text = metadata.plot

    # actors
    for actor_name in metadata.actors:
        actor = ET.SubElement(movie, "actor")
        name = ET.SubElement(actor, "name")
        name.text = actor_name

    # premiered
    if metadata.release:
        premiered = ET.SubElement(movie, "premiered")
        premiered.text = metadata.release

    # studio
    if metadata.studio:
        studio = ET.SubElement(movie, "studio")
        studio.text = metadata.studio

    # poster
    if metadata.poster_url:
        poster = ET.SubElement(movie, "poster")
        poster.text = f"{metadata.code}-poster.jpg"

    # 写入文件
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tree = ET.ElementTree(movie)
    ET.indent(tree, space="  ")  # 美化格式
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
```

- [ ] **Step 3: 编写测试**

```python
# tests/test_scrapers/test_writers.py
"""Tests for file writers."""

import pytest
from pathlib import Path
import tempfile
from app.scrapers.metadata import ScrapingMetadata
from app.scrapers.writers.nfo import write_nfo

def test_write_nfo():
    """测试 NFO 生成"""
    metadata = ScrapingMetadata(
        code="SSIS-123",
        title="テストタイトル",
        plot="テストプロット",
        actors=["女優1", "女優2"],
        studio="S1 NO.1 STYLE",
        release="2023-06-27",
        poster_url="https://example.com/poster.jpg"
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "SSIS-123.nfo"
        write_nfo(metadata, output_path)

        # 验证文件存在
        assert output_path.exists()

        # 验证内容
        content = output_path.read_text(encoding="utf-8")
        assert "<?xml version='1.0' encoding='utf-8'?>" in content
        assert "<title>テストタイトル</title>" in content
        assert "<name>女優1</name>" in content
        assert "<premiered>2023-06-27</premiered>" in content
```

- [ ] **Step 4: 运行测试**

```bash
pytest tests/test_scrapers/test_writers.py::test_write_nfo -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/scrapers/writers/__init__.py app/scrapers/writers/nfo.py tests/test_scrapers/test_writers.py
git commit -m "feat: add NFO file generator (simplified Emby format)"
```

---

### Task 4.2: 实现图片下载器

**Files:**
- Create: `app/scrapers/writers/image.py`

**Description:** 下载 poster 图片到目标目录。

- [ ] **Step 1: 实现图片下载器**

```python
# app/scrapers/writers/image.py
"""Image downloader (MVP - poster only)."""

import asyncio
from pathlib import Path
import aiohttp
import aiofiles

async def download_poster(url: str, output_path: Path):
    """下载 poster 图片

    Args:
        url: 图片 URL
        output_path: 输出文件路径
    """
    if not url:
        return

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as response:
                if response.status == 200:
                    content = await response.read()
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    async with aiofiles.open(output_path, "wb") as f:
                        await f.write(content)
    except Exception as e:
        print(f"下载图片失败 {url}: {e}")
        # 图片下载失败不抛出异常,静默处理
```

- [ ] **Step 2: 测试图片下载**

```python
# 在 tests/test_scrapers/test_writers.py 中添加

@pytest.mark.asyncio
async def test_download_poster():
    """测试图片下载"""
    from app.scrapers.writers.image import download_poster

    # 使用一个可靠的测试图片 URL
    test_url = "https://via.placeholder.com/300"

    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "poster.jpg"
        await download_poster(test_url, output_path)

        # 验证文件存在且非空
        assert output_path.exists()
        assert output_path.stat().st_size > 0
```

- [ ] **Step 3: 运行测试**

```bash
pytest tests/test_scrapers/test_writers.py::test_download_poster -v
```

Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add app/scrapers/writers/image.py tests/test_scrapers/test_writers.py
git commit -m "feat: add poster image downloader"
```

---

### Task 4.3: 实现刮削调度器

**Files:**
- Create: `app/scraper.py`

**Description:** 实现刮削调度器,整合爬虫、NFO 生成和图片下载。

- [ ] **Step 1: 实现刮削调度器**

```python
# app/scraper.py
"""Scraping scheduler (MVP)."""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiosqlite

from .scrapers.javdb import JavDBCrawler
from .scrapers.metadata import ScrapingMetadata
from .scrapers.writers.nfo import write_nfo
from .scrapers.writers.image import download_poster

class ScraperScheduler:
    """刮削调度器 (MVP)"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.crawler = JavDBCrawler()

    async def scrape_single(self, file_id: int) -> dict:
        """刮削单个文件

        Args:
            file_id: 数据库文件 ID

        Returns:
            {"success": bool, "code": str, "error": str or None}
        """
        # 1. 从数据库获取文件信息
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT identified_code, target_path FROM files WHERE id = ?",
                (file_id,)
            )
            row = await cursor.fetchone()

            if not row:
                return {"success": False, "code": None, "error": "文件不存在"}

            code, target_path = row

        # 2. 爬取元数据
        metadata = await self.crawler.crawl(code)

        if not metadata:
            await self._update_status(file_id, "failed", "爬取失败")
            return {"success": False, "code": code, "error": "爬取失败"}

        # 3. 写入文件
        target_dir = Path(target_path).parent

        try:
            # 写入 NFO
            nfo_path = target_dir / f"{code}.nfo"
            write_nfo(metadata, nfo_path)

            # 下载 poster
            if metadata.poster_url:
                poster_path = target_dir / f"{code}-poster.jpg"
                await download_poster(metadata.poster_url, poster_path)

        except Exception as e:
            await self._update_status(file_id, "failed", f"文件写入失败: {str(e)}")
            return {"success": False, "code": code, "error": str(e)}

        # 4. 更新数据库
        await self._update_status(file_id, "success")

        return {"success": True, "code": code, "error": None}

    async def _update_status(
        self,
        file_id: int,
        status: str,
        error: Optional[str] = None
    ):
        """更新刮削状态"""
        async with aiosqlite.connect(self.db_path) as db:
            if error:
                await db.execute(
                    "UPDATE files SET scrape_status = ?, last_scrape_at = ? WHERE id = ?",
                    (status, datetime.now().isoformat(), file_id)
                )
            else:
                await db.execute(
                    "UPDATE files SET scrape_status = ?, last_scrape_at = ? WHERE id = ?",
                    (status, datetime.now().isoformat(), file_id)
                )
            await db.commit()
```

- [ ] **Step 2: 编写集成测试**

```python
# tests/test_scraper.py
"""Tests for scraper scheduler."""

import pytest
import tempfile
import shutil
from pathlib import Path
from app.scraper import ScraperScheduler

@pytest.mark.asyncio
async def test_scrape_single_success():
    """测试成功刮削"""
    # 使用临时目录
    with tempfile.TemporaryDirectory() as tmpdir:
        # 准备测试数据库
        test_db = Path(tmpdir) / "test.db"

        # 创建测试文件目录
        dist_dir = Path(tmpdir) / "dist"
        dist_dir.mkdir()
        target_dir = dist_dir / "SSIS-123"
        target_dir.mkdir()

        # 这里需要插入测试数据到数据库...
        # (省略数据库初始化代码)

        scheduler = ScraperScheduler(str(test_db))
        result = await scheduler.scrape_single(1)

        # 验证结果
        assert result["success"] is True
        assert result["code"] == "SSIS-123"

        # 验证文件生成
        assert (target_dir / "SSIS-123.nfo").exists()
        # poster 可能不存在(如果爬取失败)
```

- [ ] **Step 3: 提交**

```bash
git add app/scraper.py tests/test_scraper.py
git commit -m "feat: add scraping scheduler"
```

---

### Task 4.4: 实现刮削 API

**Files:**
- Modify: `app/main.py`

**Description:** 在 FastAPI 中添加刮削相关路由。

- [ ] **Step 1: 在 main.py 中添加刮削路由**

找到路由定义区域,添加:

```python
# app/main.py

from .scraper import ScraperScheduler
from .models import ScrapeListItem, ScrapeResponse

# 初始化调度器
scraper_scheduler = None

@app.on_event("startup")
async def startup_event():
    global scraper_scheduler
    scraper_scheduler = ScraperScheduler(DB_PATH)

# ===== 刮削 API (MVP) =====

@app.get("/api/scrape")
async def get_scrape_list(
    page: int = 1,
    per_page: int = 50,
    filter: str = "all",
    sort: str = "code"
):
    """获取刮削列表"""
    async with aiosqlite.connect(DB_PATH) as db:
        # 构建 WHERE 子句
        where_clauses = ["status = 'organized'"]
        if filter != "all":
            where_clauses.append(f"scrape_status = '{filter}'")

        where_sql = " AND ".join(where_clauses)

        # 构建排序
        sort_mapping = {
            "code": "identified_code ASC",
            "scrape_time": "last_scrape_at DESC",
        }
        order_sql = sort_mapping.get(sort, sort_mapping["code"])

        # 查询总数
        cursor = await db.execute(f"SELECT COUNT(*) FROM files WHERE {where_sql}")
        total = (await cursor.fetchone())[0]

        # 查询数据
        offset = (page - 1) * per_page
        cursor.execute(f"""
            SELECT id, identified_code, target_path, scrape_status, last_scrape_at
            FROM files
            WHERE {where_sql}
            ORDER BY {order_sql}
            LIMIT {per_page} OFFSET {offset}
        """)
        rows = await cursor.fetchall()

        items = [
            ScrapeListItem(
                file_id=row[0],
                code=row[1],
                target_path=row[2],
                scrape_status=row[3],
                last_scrape_at=row[4]
            )
            for row in rows
        ]

    return {"total": total, "page": page, "per_page": per_page, "items": items}

@app.post("/api/scrape/{file_id}")
async def scrape_single(file_id: int):
    """单条刮削"""
    result = await scraper_scheduler.scrape_single(file_id)

    return ScrapeResponse(
        success=result["success"],
        code=result.get("code"),
        error=result.get("error")
    )
```

- [ ] **Step 2: 测试 API**

启动服务后测试:

```bash
# 测试获取列表
curl http://localhost:4020/api/scrape?page=1&per_page=10

# 测试单条刮削 (替换 file_id)
curl -X POST http://localhost:4020/api/scrape/1
```

Expected: 返回正确的 JSON 数据

- [ ] **Step 3: 提交**

```bash
git add app/main.py
git commit -m "feat: add scraping API endpoints"
```

---

## Phase 5: 端到端测试

### Task 5.1: 完整流程测试

**Files:**
- Test: `tests/test_e2e/test_scraping_flow.py`

**Description:** 测试完整的刮削流程。

- [ ] **Step 1: 编写端到端测试**

```python
# tests/test_e2e/test_scraping_flow.py
"""End-to-end tests for scraping flow."""

import pytest
import tempfile
from pathlib import Path
from app.scraper import ScraperScheduler

@pytest.mark.asyncio
@pytest.mark.e2e  # 标记为端到端测试
async def test_full_scraping_flow():
    """测试完整刮削流程"""
    # 1. 准备测试环境
    with tempfile.TemporaryDirectory() as tmpdir:
        # ... 准备测试数据库和文件 ...

        # 2. 执行刮削
        scheduler = ScraperScheduler(test_db_path)
        result = await scheduler.scrape_single(test_file_id)

        # 3. 验证结果
        assert result["success"] is True

        # 4. 验证文件生成
        nfo_path = Path(target_dir) / "SSIS-123.nfo"
        assert nfo_path.exists()

        # 5. 验证 NFO 内容
        nfo_content = nfo_path.read_text(encoding="utf-8")
        assert "<title>" in nfo_content
        assert "<plot>" in nfo_content
```

- [ ] **Step 2: 运行端到端测试**

```bash
pytest tests/test_e2e/test_scraping_flow.py -v -m e2e
```

Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add tests/test_e2e/test_scraping_flow.py
git commit -m "test: add end-to-end scraping flow test"
```

---

## 验收标准

### 功能验收

- [ ] 用户能够看到"刮削" tab
- [ ] 刮削页显示已整理的文件列表
- [ ] 点击"刮削"按钮后,按钮变为"刮削中..."
- [ ] 10-30 秒后,状态变为"已刮削"
- [ ] 文件夹中生成 `{code}.nfo` 文件
- [ ] 文件夹中生成 `{code}-poster.jpg` 文件
- [ ] NFO 文件包含 title, plot, actors 等核心字段
- [ ] 在 Emby 中刷新后,能够看到元数据

### 性能验收

- [ ] 单个番号刮削耗时 < 30 秒
- [ ] 刮削失败率 < 10%(基于测试样本)

### 稳定性验收

- [ ] 爬虫失败不影响其他功能
- [ ] 网络错误能够正确处理
- [ ] 数据库操作失败能够回滚

---

## 附录

### 依赖安装

```bash
# 新增依赖
pip install curl-cffi beautifulsoup4 aiohttp aiofiles
```

### 测试命令

```bash
# 运行所有测试
pytest tests/ -v

# 只运行刮削相关测试
pytest tests/test_scrapers/ -v

# 运行端到端测试
pytest tests/test_e2e/ -v -m e2e
```

### 开发检查清单

- [ ] Task 1.1: 数据库迁移
- [ ] Task 1.2: 元数据模型
- [ ] Task 1.3: API 模型
- [ ] Task 2.1: 前端状态管理
- [ ] Task 2.2: 刮削页逻辑
- [ ] Task 2.3: HTML 结构
- [ ] Task 3.1: 爬虫基类
- [ ] Task 3.2: JavDB 爬虫
- [ ] Task 4.1: NFO 生成器
- [ ] Task 4.2: 图片下载器
- [ ] Task 4.3: 刮削调度器
- [ ] Task 4.4: 刮削 API
- [ ] Task 5.1: 端到端测试

---

**Total Estimated Time:** 3 weeks (1 developer)

**Risk Level:** Low (单源、单条、无复杂特性)

**Next Steps After MVP:**
1. 收集真实环境反馈
2. 评估是否需要多源支持
3. 考虑添加批量刮削功能
4. 优化 NFO 格式和图片下载
