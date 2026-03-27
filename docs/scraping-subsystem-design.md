# Noctra 刮削子系统详细设计

## 文档说明

- **版本**: v1.5
- **更新日期**: 2026-03-27
- **基于**: PRD v1.5
- **目的**: 为开发人员提供详细的技术实现指南

---

## 1. 系统架构

### 1.1 整体架构

```
┌─────────────────────────────────────────────────────────┐
│                     FastAPI 应用层                      │
│  ┌───────────────────────────────────────────────────┐  │
│  │              API 路由层 (app/main.py)            │  │
│  │  GET  /api/scrape                                 │  │
│  │  POST /api/scrape/batch                           │  │
│  └───────────────────────┬───────────────────────────┘  │
└──────────────────────────┼───────────────────────────────┘
                           │
                           ↓
┌─────────────────────────────────────────────────────────┐
│              刮削业务逻辑层 (app/scraper.py)            │
│  ┌───────────────────────────────────────────────────┐  │
│  │          刮削调度器 (ScraperScheduler)            │  │
│  │  - 批处理任务管理                                 │  │
│  │  - 速率控制                                       │  │
│  │  - 进度追踪                                       │  │
│  └───────────────────────┬───────────────────────────┘  │
└──────────────────────────┼───────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         ↓                 ↓                 ↓
┌─────────────────┐ ┌─────────────┐ ┌──────────────┐
│  爬虫管理器     │ │ 元数据合并器│ │  文件写入器  │
│ CrawlerManager  │ │ MetadataMerger│ │ FileWriter  │
└────────┬────────┘ └──────┬───────┘ └──────┬───────┘
         │                 │                 │
         ↓                 ↓                 ↓
┌─────────────────┐ ┌─────────────┐ ┌──────────────┐
│ 具体爬虫实现    │ │ 合并策略    │ │ NFO/图片     │
│ - javdb         │ │ - 优先级    │ │ - 生成NFO    │
│ - javbus        │ │ - fallback  │ │ - 下载图片   │
│ - dmm           │ │ - 来源追踪  │ │ - 备份管理   │
│ - javtrailers   │ │             │ │              │
└─────────────────┘ └─────────────┘ └──────────────┘
```

### 1.2 目录结构

```
app/
├── main.py                 # FastAPI 应用,API 路由
├── models.py              # Pydantic 模型(扩展)
├── scraper.py             # 刮削调度器和业务逻辑
└── scrapers/              # 刮削子系统
    ├── __init__.py
    ├── base.py            # 爬虫基类
    ├── metadata.py        # 元数据模型
    ├── merger.py          # 元数据合并器
    ├── javdb.py           # JavDB 爬虫
    ├── javbus.py          # JavBus 爬虫
    ├── dmm.py             # DMM 爬虫
    ├── javtrailers.py     # JavTrailers 爬虫
    └── writers/           # 文件写入器
        ├── __init__.py
        ├── nfo.py         # NFO 生成器
        └── image.py       # 图片下载器
```

---

## 2. 核心组件设计

### 2.1 元数据模型 (app/scrapers/metadata.py)

```python
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class ScrapeMetadata:
    """统一的元数据模型"""

    # 基础信息
    code: str                          # 番号 "SSIS-123"
    title: Optional[str] = None        # 标题
    plot: Optional[str] = None         # 剧情简介

    # 制作信息
    actors: List[str] = field(default_factory=list)     # 演员列表
    studio: Optional[str] = None        # 制作商
    series: Optional[str] = None         # 系列
    director: Optional[str] = None       # 导演
    release: Optional[str] = None        # 发布日期 YYYY-MM-DD
    runtime: Optional[int] = None        # 时长(分钟)

    # 分类信息
    tags: List[str] = field(default_factory=list)       # 标签/类别

    # 媒体资源
    poster_url: Optional[str] = None     # 封面图 URL
    fanart_url: Optional[str] = None     # 背景图 URL
    preview_urls: List[str] = field(default_factory=list)  # 预览图 URL
    trailer_url: Optional[str] = None    # 预告片 URL
    website: Optional[str] = None        # 来源网站 URL
    resolution: Optional[str] = None     # 分辨率 "1920x1080"

    # 来源追踪
    source: Optional[str] = None         # 主来源(按优先级最高的)
    raw_sources: List[str] = field(default_factory=list)  # 实际成功的来源列表

    def to_dict(self) -> dict:
        """转换为字典,用于 NFO 生成"""
        return {
            "code": self.code,
            "title": self.title,
            "plot": self.plot,
            "actors": self.actors,
            "studio": self.studio,
            "series": self.series,
            "director": self.director,
            "release": self.release,
            "runtime": self.runtime,
            "tags": self.tags,
            "website": self.website,
            "resolution": self.resolution,
            "poster": f"{self.code}-poster.jpg" if self.poster_url else None,
            "fanart": f"{self.code}-fanart.jpg" if self.fanart_url else None,
        }
```

### 2.2 爬虫基类 (app/scrapers/base.py)

```python
from abc import ABC, abstractmethod
from typing import Optional, Dict
import asyncio
import time
import random
from curl_cffi import requests

from .metadata import ScrapeMetadata

class BaseCrawler(ABC):
    """爬虫基类,预留扩展能力"""

    name: str  # 爬虫名称,子类必须定义

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self._session = None

    @abstractmethod
    async def crawl(self, code: str) -> Optional[ScrapeMetadata]:
        """爬取指定番号的元数据

        Args:
            code: 番号,如 "SSIS-123"

        Returns:
            ScrapeMetadata 对象,失败返回 None
        """
        pass

    def _build_url(self, code: str) -> str:
        """构建目标 URL,子类可覆盖"""
        raise NotImplementedError

    async def _request(
        self,
        url: str,
        proxy: Optional[str] = None,
        cookies: Optional[Dict[str, str]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Optional[str]:
        """HTTP GET 请求封装

        Args:
            url: 目标 URL
            proxy: 代理 URL(预留,本期不使用)
            cookies: Cookie 字典(预留,本期不使用)
            headers: 自定义 headers(预留,本期不使用)

        Returns:
            响应文本,失败返回 None
        """
        try:
            # 延迟控制
            await self._apply_delay()

            # 构建 session
            if self._session is None:
                self._session = requests.Session()

            # 基础 headers
            default_headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            if headers:
                default_headers.update(headers)

            # 执行请求
            response = self._session.get(
                url,
                headers=default_headers,
                cookies=cookies,
                proxy=proxy,
                timeout=25,
                verify=False,
                impersonate="chrome",  # 模拟 Chrome 浏览器指纹
            )

            if response.status_code == 200:
                return response.text
            else:
                return None

        except Exception as e:
            # 记录错误但不抛出异常,返回 None 让调用方处理
            print(f"{self.name} request error: {e}")
            return None

    async def _request_json(self, url: str) -> Optional[dict]:
        """HTTP GET 请求,返回 JSON"""
        text = await self._request(url)
        if not text:
            return None

        try:
            import json
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    async def _apply_delay(self):
        """应用延迟策略,子类可覆盖"""
        # 默认延迟 0.5 秒(批处理调度器会额外控制)
        await asyncio.sleep(0.5)

    def _normalize_code(self, code: str) -> str:
        """标准化番号格式"""
        return code.upper().replace("-", "-").strip()
```

### 2.3 元数据合并器 (app/scrapers/merger.py)

```python
from typing import List, Optional
from .metadata import ScrapeMetadata

# 固定优先级配置
FIELD_SOURCE_PRIORITY = {
    "title": ["javtrailers", "javdb", "javbus", "dmm"],
    "plot": ["javtrailers", "dmm", "javdb", "javbus"],
    "actors": ["javtrailers", "javdb", "javbus", "dmm"],
    "studio": ["javtrailers", "javdb", "javbus", "dmm"],
    "series": ["javtrailers", "javdb", "javbus", "dmm"],
    "director": ["javtrailers", "javdb", "javbus", "dmm"],
    "release": ["javtrailers", "javdb", "javbus", "dmm"],
    "runtime": ["javtrailers", "javdb", "javbus", "dmm"],
    "tags": ["javtrailers", "javdb", "javbus", "dmm"],
    "poster_url": ["javtrailers", "javdb", "javbus", "dmm"],
    "fanart_url": ["javtrailers", "javdb", "javbus", "dmm"],
    "preview_urls": ["javtrailers", "javdb", "javbus", "dmm"],
    "trailer_url": ["javtrailers", "javdb", "javbus", "dmm"],
    "website": ["javtrailers", "javdb", "javbus", "dmm"],
    "resolution": ["javtrailers", "javdb", "javbus", "dmm"],
}

def merge_metadata(results: List[ScrapeMetadata], code: str) -> Optional[ScrapeMetadata]:
    """合并多个源的元数据

    Args:
        results: 多个爬虫返回的元数据列表
        code: 番号

    Returns:
        合并后的元数据,如果所有源都失败返回 None
    """
    if not results:
        return None

    # 过滤掉 None 结果
    valid_results = [r for r in results if r is not None]
    if not valid_results:
        return None

    merged = ScrapeMetadata(code=code)
    merged.raw_sources = [r.source for r in valid_results if r.source]

    # 按优先级合并每个字段
    for field, priority_list in FIELD_SOURCE_PRIORITY.items():
        for source_name in priority_list:
            for result in valid_results:
                if result.source == source_name:
                    value = getattr(result, field, None)
                    if value and value not in (None, "", [], {}):
                        setattr(merged, field, value)
                        break
            else:
                continue
            break

    # 确定主来源(以 title 的来源为主)
    for source_name in FIELD_SOURCE_PRIORITY["title"]:
        if any(r.source == source_name for r in valid_results):
            merged.source = source_name
            break

    return merged
```

### 2.4 刮削调度器 (app/scraper.py)

```python
import asyncio
import random
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

from .scrapers.base import BaseCrawler
from .scrapers.metadata import ScrapeMetadata
from .scrapers.merger import merge_metadata
from .scrapers.javdb import JavDBCrawler
from .scrapers.javbus import JavBusCrawler
from .scrapers.dmm import DMMCrawler
from .scrapers.javtrailers import JavTrailersCrawler
from .scrapers.writers.nfo import write_nfo
from .scrapers.writers.image import download_images

class ScrapeResult:
    """刮削结果"""
    def __init__(
        self,
        success: bool,
        code: str,
        metadata: Optional[ScrapeMetadata] = None,
        error: Optional[str] = None
    ):
        self.success = success
        self.code = code
        self.metadata = metadata
        self.error = error

class ScraperScheduler:
    """刮削调度器"""

    def __init__(self, db_conn):
        self.db_conn = db_conn
        self.crawlers = [
            JavDBCrawler(),
            JavBusCrawler(),
            DMMCrawler(),
            JavTrailersCrawler(),
        ]
        self._running_tasks: Dict[str, asyncio.Task] = {}

    async def scrape_single(self, file_id: int) -> ScrapeResult:
        """刮削单个文件

        Args:
            file_id: 数据库文件 ID

        Returns:
            ScrapeResult
        """
        # 1. 从数据库获取文件信息
        file_info = await self._get_file_info(file_id)
        if not file_info:
            return ScrapeResult(success=False, code="", error="文件不存在")

        code = file_info["identified_code"]
        target_dir = Path(file_info["target_path"]).parent

        # 2. 多源爬取(串行)
        results = []
        for crawler in self.crawlers:
            try:
                metadata = await crawler.crawl(code)
                if metadata:
                    results.append(metadata)
                # 每个源之间等待 2-3 秒
                await asyncio.sleep(random.uniform(2.0, 3.0))
            except Exception as e:
                print(f"{crawler.name} crawl failed: {e}")
                continue

        # 3. 合并元数据
        if not results:
            await self._update_scrape_status(
                file_id, "failed", error="所有数据源均失败"
            )
            return ScrapeResult(success=False, code=code, error="所有数据源均失败")

        merged = merge_metadata(results, code)
        if not merged:
            await self._update_scrape_status(
                file_id, "failed", error="元数据合并失败"
            )
            return ScrapeResult(success=False, code=code, error="元数据合并失败")

        # 4. 写入文件
        try:
            await self._write_metadata(merged, target_dir)
        except Exception as e:
            await self._update_scrape_status(
                file_id, "failed", error=f"文件写入失败: {str(e)}"
            )
            return ScrapeResult(success=False, code=code, error=str(e))

        # 5. 更新数据库
        await self._update_scrape_status(
            file_id,
            "success",
            source=merged.source,
            scrape_count=file_info.get("scrape_count", 0) + 1
        )

        return ScrapeResult(success=True, code=code, metadata=merged)

    async def scrape_batch(
        self,
        file_ids: List[int],
        progress_callback: Optional[callable] = None
    ) -> Dict:
        """批量刮削

        Args:
            file_ids: 文件 ID 列表
            progress_callback: 进度回调函数 callback(current, total, item)

        Returns:
            结果统计 {"success": int, "failed": int, "errors": List[str]}
        """
        if len(file_ids) > 50:
            raise ValueError("单次最多刮削50个文件")

        results = {"success": 0, "failed": 0, "errors": []}

        for i, file_id in enumerate(file_ids):
            try:
                result = await self.scrape_single(file_id)
                if result.success:
                    results["success"] += 1
                else:
                    results["failed"] += 1
                    results["errors"].append(f"{result.code}: {result.error}")

                # 进度回调
                if progress_callback:
                    file_info = await self._get_file_info(file_id)
                    progress_callback(i + 1, len(file_ids), file_info["identified_code"])

            except Exception as e:
                results["failed"] += 1
                results["errors"].append(f"{file_id}: {str(e)}")

            # 不是最后一个,等待 2-3 秒
            if i < len(file_ids) - 1:
                await asyncio.sleep(random.uniform(2.0, 3.0))

        return results

    async def _write_metadata(self, metadata: ScrapeMetadata, target_dir: Path):
        """写入元数据文件"""
        target_dir.mkdir(parents=True, exist_ok=True)

        # 1. 备份旧 NFO
        nfo_path = target_dir / f"{metadata.code}.nfo"
        if nfo_path.exists():
            backup_path = target_dir / f"{metadata.code}.nfo.bak"
            nfo_path.rename(backup_path)

        # 2. 写入 NFO
        write_nfo(metadata, nfo_path)

        # 3. 下载图片
        await download_images(metadata, target_dir)

    async def _get_file_info(self, file_id: int) -> Optional[dict]:
        """从数据库获取文件信息"""
        cursor = self.db_conn.cursor()
        cursor.execute(
            "SELECT * FROM files WHERE id = ?",
            (file_id,)
        )
        row = cursor.fetchone()
        if row:
            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))
        return None

    async def _update_scrape_status(
        self,
        file_id: int,
        status: str,
        source: Optional[str] = None,
        scrape_count: Optional[int] = None,
        error: Optional[str] = None
    ):
        """更新刮削状态"""
        cursor = self.db_conn.cursor()
        updates = {
            "scrape_status": status,
            "last_scrape_at": datetime.now().isoformat(),
        }
        if source:
            updates["scrape_source"] = source
        if scrape_count is not None:
            updates["scrape_count"] = scrape_count
        if error:
            updates["scrape_error"] = error

        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [file_id]

        cursor.execute(
            f"UPDATE files SET {set_clause} WHERE id = ?",
            values
        )
        self.db_conn.commit()
```

---

## 3. 文件写入器实现

### 3.1 NFO 生成器 (app/scrapers/writers/nfo.py)

```python
from datetime import datetime
from pathlib import Path
from typing import Optional
import xml.etree.ElementTree as ET

from ..metadata import ScrapeMetadata

def write_nfo(metadata: ScrapeMetadata, output_path: Path):
    """生成 Emby 兼容的 NFO 文件

    Args:
        metadata: 元数据对象
        output_path: 输出文件路径
    """
    # 创建根元素
    movie = ET.Element("movie")

    # plot
    plot = ET.SubElement(movie, "plot")
    if metadata.plot:
        plot.text = metadata.plot
        plot.set("CDATA", "true")  # 标记为 CDATA

    # outline
    outline = ET.SubElement(movie, "outline")

    # lockdata
    lockdata = ET.SubElement(movie, "lockdata")
    lockdata.text = "false"

    # dateadded
    dateadded = ET.SubElement(movie, "dateadded")
    dateadded.text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # title
    title = ET.SubElement(movie, "title")
    title.text = metadata.title or metadata.code

    # originaltitle
    originaltitle = ET.SubElement(movie, "originaltitle")
    originaltitle.text = metadata.code

    # actors
    for actor_name in metadata.actors:
        actor = ET.SubElement(movie, "actor")
        name = ET.SubElement(actor, "name")
        name.text = actor_name
        type_elem = ET.SubElement(actor, "type")
        type_elem.text = "Actor"

    # year
    if metadata.release:
        year = ET.SubElement(movie, "year")
        year.text = metadata.release[:4]  # YYYY-MM-DD -> YYYY

    # sorttitle
    sorttitle = ET.SubElement(movie, "sorttitle")
    sorttitle.text = metadata.code

    # imdbid
    imdbid = ET.SubElement(movie, "imdbid")
    imdbid.text = metadata.code

    # premiered
    if metadata.release:
        premiered = ET.SubElement(movie, "premiered")
        premiered.text = metadata.release

    # releasedate
    if metadata.release:
        releasedate = ET.SubElement(movie, "releasedate")
        releasedate.text = metadata.release

    # genres (tags)
    for tag in metadata.tags:
        genre = ET.SubElement(movie, "genre")
        genre.text = tag

    # studio
    if metadata.studio:
        studio = ET.SubElement(movie, "studio")
        studio.text = metadata.studio

    # uniqueid
    uniqueid = ET.SubElement(movie, "uniqueid")
    uniqueid.set("type", "imdb")
    uniqueid.text = metadata.code

    # id
    id_elem = ET.SubElement(movie, "id")
    id_elem.text = metadata.code

    # fileinfo
    fileinfo = ET.SubElement(movie, "fileinfo")
    streamdetails = ET.SubElement(fileinfo, "streamdetails")

    # website
    if metadata.website:
        website = ET.SubElement(movie, "website")
        website.text = metadata.website

    # resolution
    if metadata.resolution:
        resolution = ET.SubElement(movie, "resolution")
        resolution.text = metadata.resolution

    # poster
    if metadata.poster_url:
        poster = ET.SubElement(movie, "poster")
        poster.text = f"{metadata.code}-poster.jpg"

    # cover
    if metadata.poster_url:
        cover = ET.SubElement(movie, "cover")
        cover.text = f"{metadata.code}-poster.jpg"

    # fanart
    if metadata.fanart_url:
        fanart = ET.SubElement(movie, "fanart")
        thumb = ET.SubElement(fanart, "thumb")
        thumb.text = f"{metadata.code}-fanart.jpg"

    # 写入文件
    tree = ET.ElementTree(movie)
    ET.indent(tree, space="  ")  # 美化格式
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
```

### 3.2 图片下载器 (app/scrapers/writers/image.py)

```python
import asyncio
from pathlib import Path
from typing import List
import aiohttp
import aiofiles

from ..metadata import ScrapeMetadata

async def download_images(metadata: ScrapeMetadata, target_dir: Path):
    """下载所有图片

    Args:
        metadata: 元数据对象
        target_dir: 目标目录
    """
    tasks = []

    # poster
    if metadata.poster_url:
        tasks.append(_download_single(
            metadata.poster_url,
            target_dir / f"{metadata.code}-poster.jpg"
        ))

    # fanart
    if metadata.fanart_url:
        tasks.append(_download_single(
            metadata.fanart_url,
            target_dir / f"{metadata.code}-fanart.jpg"
        ))

    # previews (最多 10 张)
    for i, url in enumerate(metadata.preview_urls[:10]):
        tasks.append(_download_single(
            url,
            target_dir / f"{metadata.code}-preview-{i+1:02d}.jpg"
        ))

    # 并发下载(控制并发数)
    if tasks:
        await _run_with_concurrency_limit(tasks, max_concurrent=3)

async def _download_single(url: str, output_path: Path):
    """下载单个图片"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=30) as response:
                if response.status == 200:
                    content = await response.read()
                    async with aiofiles.open(output_path, "wb") as f:
                        await f.write(content)
    except Exception as e:
        print(f"下载图片失败 {url}: {e}")
        # 图片下载失败不抛出异常,静默处理

async def _run_with_concurrency_limit(tasks: List, max_concurrent: int):
    """限制并发数执行任务"""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def run_with_semaphore(task):
        async with semaphore:
            return await task

    await asyncio.gather(*[run_with_semaphore(task) for task in tasks])
```

---

## 4. API 实现

### 4.1 扩展 models.py

```python
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class ScrapeListItem(BaseModel):
    """刮削列表项"""
    file_id: int
    code: str
    target_path: str
    scrape_status: str  # pending, success, failed
    last_scrape_at: Optional[str]
    scrape_source: Optional[str]
    scrape_error: Optional[str]

class ScrapeBatchRequest(BaseModel):
    """批量刮削请求"""
    file_ids: List[int]

class ScrapeBatchResponse(BaseModel):
    """批处理响应"""
    batch_id: str
    status: str  # queued, running, completed, cancelled, failed
    total: int
    success: int
    failed: int
    current_item: Optional[str]
    errors: List[str]
```

### 4.2 API 路由 (app/main.py 扩展)

```python
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Optional

scraper_router = APIRouter(prefix="/api/scrape", tags=["scraping"])

# 全局批处理任务存储
scrape_tasks: Dict[str, Dict] = {}

@scraper_router.get("/")
async def get_scrape_list(
    page: int = 1,
    per_page: int = 50,
    filter: Optional[str] = None,  # pending, success, failed
    sort: str = "code"
):
    """获取刮削列表"""
    db_conn = get_db_connection()

    # 构建 WHERE 子句
    where_clauses = ["status = 'organized'"]
    if filter:
        where_clauses.append(f"scrape_status = '{filter}'")

    where_sql = " AND ".join(where_clauses)

    # 构建排序
    sort_mapping = {
        "code": "identified_code ASC",
        "scrape_time": "last_scrape_at DESC",
        "organize_time": "updated_at DESC",
    }
    order_sql = sort_mapping.get(sort, sort_mapping["code"])

    # 查询总数
    cursor = db_conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM files WHERE {where_sql}")
    total = cursor.fetchone()[0]

    # 查询数据
    offset = (page - 1) * per_page
    cursor.execute(f"""
        SELECT * FROM files
        WHERE {where_sql}
        ORDER BY {order_sql}
        LIMIT {per_page} OFFSET {offset}
    """)
    rows = cursor.fetchall()
    columns = [desc[0] for desc in cursor.description]
    items = [dict(zip(columns, row)) for row in rows]

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "items": items,
    }

@scraper_router.post("/{file_id}")
async def scrape_single(file_id: int):
    """单条刮削"""
    db_conn = get_db_connection()
    scheduler = ScraperScheduler(db_conn)

    # 检查文件状态
    cursor = db_conn.cursor()
    cursor.execute("SELECT status FROM files WHERE id = ?", (file_id,))
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="文件不存在")
    if row[0] != "organized":
        raise HTTPException(status_code=400, detail="只能刮削已整理的文件")

    # 执行刮削
    result = await scheduler.scrape_single(file_id)

    if result.success:
        return {"success": True, "code": result.code}
    else:
        return {"success": False, "error": result.error}

@scraper_router.post("/batch")
async def create_scrape_batch(request: ScrapeBatchRequest, background_tasks: BackgroundTasks):
    """创建批量刮削任务"""
    import uuid
    batch_id = str(uuid.uuid4())

    # 初始化任务状态
    scrape_tasks[batch_id] = {
        "status": "queued",
        "total": len(request.file_ids),
        "success": 0,
        "failed": 0,
        "current_item": None,
        "errors": [],
    }

    # 后台执行
    async def run_batch():
        db_conn = get_db_connection()
        scheduler = ScraperScheduler(db_conn)

        scrape_tasks[batch_id]["status"] = "running"

        def progress_callback(current, total, code):
            scrape_tasks[batch_id]["current_item"] = code

        results = await scheduler.scrape_batch(
            request.file_ids,
            progress_callback=progress_callback
        )

        scrape_tasks[batch_id].update(results)
        scrape_tasks[batch_id]["status"] = "completed"
        scrape_tasks[batch_id]["current_item"] = None

    background_tasks.add_task(run_batch)

    return {"batch_id": batch_id, "total": len(request.file_ids)}

@scraper_router.get("/batch/{batch_id}")
async def get_scrape_batch(batch_id: str):
    """查询批处理进度"""
    if batch_id not in scrape_tasks:
        raise HTTPException(status_code=404, detail="批处理任务不存在")

    return scrape_tasks[batch_id]

@scraper_router.post("/batch/{batch_id}/cancel")
async def cancel_scrape_batch(batch_id: str):
    """取消批处理"""
    if batch_id not in scrape_tasks:
        raise HTTPException(status_code=404, detail="批处理任务不存在")

    task = scrape_tasks[batch_id]
    if task["status"] not in ["queued", "running"]:
        raise HTTPException(status_code=400, detail="任务已完成或已取消")

    task["status"] = "cancelled"
    return {"success": True}
```

---

## 5. 数据库迁移

### 5.1 升级脚本 (migrations/add_scraping.sql)

```sql
-- 添加刮削相关字段
ALTER TABLE files ADD COLUMN scrape_status TEXT DEFAULT 'pending';
ALTER TABLE files ADD COLUMN scrape_source TEXT;
ALTER TABLE files ADD COLUMN last_scrape_at TEXT;
ALTER TABLE files ADD COLUMN scrape_count INTEGER DEFAULT 0;
ALTER TABLE files ADD COLUMN scrape_error TEXT;

-- 更新现有数据状态
UPDATE files SET status = 'organized' WHERE status = 'processed';

-- 创建索引
CREATE INDEX IF NOT EXISTS idx_files_scrape_status ON files(scrape_status);
CREATE INDEX IF NOT EXISTS idx_files_status_scrape ON files(status, scrape_status);

-- 验证
SELECT 'Migration completed' as status;
```

---

## 6. 测试策略

### 6.1 单元测试

```python
# tests/test_merger.py
import pytest
from app.scrapers.metadata import ScrapeMetadata
from app.scrapers.merger import merge_metadata

def test_merge_metadata():
    # 准备测试数据
    javdb_meta = ScrapeMetadata(
        code="SSIS-123",
        title="Title from JavDB",
        plot="Plot from JavDB",
        source="javdb"
    )

    javbus_meta = ScrapeMetadata(
        code="SSIS-123",
        title="Title from JavBus",
        actors=["Actor1", "Actor2"],
        source="javbus"
    )

    # 执行合并
    merged = merge_metadata([javdb_meta, javbus_meta], "SSIS-123")

    # 验证结果
    assert merged.code == "SSIS-123"
    assert merged.source == "javtrailers"  # 优先级最高,但这里没有,所以是第一个
    assert merged.title == "Title from JavDB"  # javdb 优先级高于 javbus
    assert merged.actors == ["Actor1", "Actor2"]  # javdb 没有演员,fallback 到 javbus

def test_merge_empty_results():
    merged = merge_metadata([], "SSIS-123")
    assert merged is None
```

### 6.2 集成测试

```python
# tests/test_scraper_integration.py
import pytest
from pathlib import Path
from app.scraper import ScraperScheduler

@pytest.mark.asyncio
async def test_scrape_single(test_db, test_file_path):
    scheduler = ScraperScheduler(test_db)

    # 创建测试文件
    # ...

    result = await scheduler.scrape_single(file_id=1)

    assert result.success is True
    assert result.metadata is not None

    # 验证文件生成
    nfo_path = test_file_path / "SSIS-123.nfo"
    assert nfo_path.exists()

    poster_path = test_file_path / "SSIS-123-poster.jpg"
    assert poster_path.exists()
```

---

## 7. 部署注意事项

### 7.1 依赖安装

```bash
# 新增依赖
pip install curl-cffi aiohttp aiofiles beautifulsoup4 lxml
```

### 7.2 环境变量(可选扩展)

```bash
# 本期不使用,预留
# SCRAPE_PROXY_URL=http://proxy:8080
# SCRAPE_REQUEST_DELAY=2.0
```

### 7.3 Docker 更新

```dockerfile
# 安装依赖
RUN pip install curl-cffi aiohttp aiofiles beautifulsoup4 lxml
```

---

## 8. 开发检查清单

### Phase 1: 基础架构
- [ ] 数据库 schema 升级
- [ ] 爬虫基类实现
- [ ] 元数据模型定义
- [ ] 合并器实现和测试

### Phase 2: 爬虫实现
- [ ] JavDB 爬虫(HTML 解析)
- [ ] JavBus 爬虫(HTML 解析)
- [ ] DMM 爬虫(API 或 HTML)
- [ ] JavTrailers 爬虫(HTML 解析)
- [ ] 每个爬虫单独测试

### Phase 3: 文件写入
- [ ] NFO 生成器(Emby 格式)
- [ ] 图片下载器(并发控制)
- [ ] 备份管理

### Phase 4: API 和批处理
- [ ] 刮削 API 实现
- [ ] 批处理调度器
- [ ] 速率控制(2-3秒间隔)

### Phase 5: 前端
- [ ] 刮削页 UI
- [ ] 批处理面板
- [ ] 进度展示
- [ ] 错误提示

### Phase 6: 测试和优化
- [ ] 单元测试覆盖率 > 80%
- [ ] 集成测试
- [ ] 性能测试
- [ ] 文档完善

---

这份技术设计文档与 PRD v1.5 配合使用,为开发团队提供完整的实现指南。
