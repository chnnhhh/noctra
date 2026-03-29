# Noctra PRD v1.5 - 刮削能力升级

## 文档说明

- **版本**: v1.5
- **更新日期**: 2026-03-27
- **基于版本**: v1.0 (整理工具)
- **变更类型**: 功能新增 - 元数据刮削
- **作者**: 基于用户需求和 MrBanana 项目参考

---

## 1. 项目目标(更新)

### v1.0 目标(保持不变)

Noctra 是一个面向本地机器和 NAS 场景的 JAV 文件整理工作台,解决从混乱的下载目录中递归扫描、识别、预览、整理视频文件的问题。

### v1.5 新增目标

**在整理能力基础上,增加元数据刮削能力**,使 Noctra 从"整理工具"升级为"整理+刮削工具":

- 保持"先看后搬"的产品哲学,扩展到"先整理后刮削"
- 从番号自动获取元数据(标题、演员、标签、剧情简介等)
- 生成 Emby 兼容的 NFO 文件
- 下载封面、背景、预览图
- 提供与整理页一致的刮削交互体验

### 核心价值

1. **可见性**: 刮削前预览元数据,刮削后查看结果
2. **可控性**: 手动触发刮削,支持批量/单条操作
3. **可追踪**: 记录刮削历史,支持重新刮削
4. **稳定性**: 保守的反爬策略,预留扩展架构

---

## 2. 能力边界(更新)

### v1.5 新增能力

- ✅ 多源元数据爬取(JavDB, JavBus, DMM, JavTrailers)
- ✅ 元数据智能合并(字段级优先级)
- ✅ NFO 文件生成(Emby/Kodi 兼容格式)
- ✅ 图片下载(poster, fanart, preview)
- ✅ 刮削历史记录
- ✅ 批量刮削(最多50个/次,串行执行)
- ✅ 刮削失败重试
- ✅ 重新刮削(自动备份旧 NFO)

### 明确不在 v1.5 范围内

- ❌ 视频下载
- ❌ 字幕解析/生成/下载
- ❌ 自动刮削(整理后不自动触发)
- ❌ 多层目录分类策略
- ❌ 复杂规则引擎
- ❌ 多用户权限体系
- ❌ 后台监控目录并自动整理+刮削
- ❌ 代理池、Cookie 管理的产品化配置(代码架构预留,但不在 UI 暴露)
- ❌ 元数据缓存系统(架构预留,v2 考虑)

### 保持 v1.0 能力

所有 v1.0 的整理能力完全保持不变:
- 扫描、识别、预览、整理
- 批处理、历史记录
- 删除/忽略操作

---

## 3. 状态体系(完整定义)

### 3.1 主状态

| 内部状态 | 前端显示 | 含义 | 出现位置 | 可操作 |
|---------|---------|------|---------|--------|
| `to_organize` | 待整理 | 可进入整理流程的主候选 | 扫描页 | 可整理、可删除/忽略 |
| `duplicate` | 重复 | 同番号下的非主候选 | 扫描页 | 可单条整理、可删除/忽略 |
| `target_exists` | 已存在 | 目标已存在或历史已整理 | 扫描页 | 可删除/忽略 |
| `unidentifiable` | 未识别 | 未识别到可用番号 | 扫描页 | 可删除/忽略 |
| `organized` | 已整理 | 已整理完成,等待刮削 | 刮削页 | 可刮削、可删除/忽略 |
| `ignored` | 不展示 | 用户选择忽略 | 两页均不显示 | 不可操作 |

### 3.2 刮削子状态

仅在主状态为 `organized` 时有效:

| 内部状态 | 前端显示 | 含义 | 可操作 |
|---------|---------|------|--------|
| `pending` | 待刮削 | 从未刮削过 | 可刮削 |
| `success` | 已刮削 | 至少刮削成功过一次 | 可重新刮削 |
| `failed` | 刮削失败 | 最近一次刮削失败 | 可重试刮削 |

### 3.3 状态流转图

```
初始扫描
    ↓
[to_organize / duplicate / target_exists / unidentifiable]
    ↓
[执行整理]
    ↓
organized (scrape_status=pending)
    ↓
[手动触发刮削]
    ↓
    ├─→ success (scrape_status=success)
    │      ↓
    │   [可重新刮削]
    │
    └─→ failed (scrape_status=failed)
           ↓
        [可重试]
```

---

## 4. 页面结构(更新)

### 4.1 页面概览

| Tab 名称 | 展示内容 | 主要操作 |
|---------|---------|---------|
| **扫描** | `to_organize`, `duplicate`, `target_exists`, `unidentifiable` | 执行整理、删除/忽略 |
| **刮削**(新) | `organized` 及其刮削子状态 | 执行刮削、重新刮削、删除/忽略 |

### 4.2 扫描页(保持不变)

- 顶部统计卡: 总文件数、已识别、未识别、待整理、已整理
- 筛选器: 全部、已识别、未识别、待整理、重复、已存在
- 操作: 扫描目录、执行整理
- **不展示刮削相关状态**

### 4.3 刮削页(新增)

#### 统计卡

```
┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
│已整理总数│ │待刮削   │ │已刮削   │ │刮削失败 │
│  150    │ │  120    │ │   25    │ │   5     │
└─────────┘ └─────────┘ └─────────┘ └─────────┘
```

- **已整理总数**: status='organized' 的记录数
- **待刮削**: scrape_status='pending'
- **已刮削**: scrape_status='success'
- **刮削失败**: scrape_status='failed'

#### 筛选器

- 全部
- 待刮削
- 已刮削
- 刮削失败

#### 排序项

- 按番号(默认)
- 按刮削时间
- 按整理时间

#### 表格列

| 列名 | 说明 |
|------|------|
| 勾选框 | 支持跨页勾选(最多50个) |
| 番号 | 识别出的番号 |
| 刮削状态 | 待刮削 / 已刮削 / 刮削失败 |
| 上次刮削时间 | 格式: YYYY-MM-DD HH:MM |
| 元数据来源 | 例如: javtrailers, javdb |
| 操作 | 刮削按钮(失败时显示"重试") |

#### 行级操作

| 状态 | 可批量勾选 | 行级刮削 | 删除/忽略 |
|-----|-----------|---------|----------|
| 待刮削 | 是 | 是 | 是 |
| 已刮削 | 是 | 是(重新刮削) | 是 |
| 刮削失败 | 是 | 是(重试) | 是 |

#### 批处理面板

```
┌─────────────────────────────────────────┐
│ 状态: 运行中                             │
│ 进度: 5/120 | 成功:4 跳过:0 失败:1      │
│ ████████░░░░░░░░░░░░░░░░░░░░░░          │
│ 当前: 正在刮削 ABP-456 (javdb)          │
│                                         │
│ 错误详情:                               │
│ • FC2-789: javdb 请求超时               │
│                                         │
│ [取消]                                  │
└─────────────────────────────────────────┘
```

- 实时显示当前刮削的番号和数据源
- 显示失败项的具体错误信息
- 支持取消批处理

---

## 5. 数据流(更新)

### 5.1 完整流程图

```
1. 扫描 SOURCE_DIR
   ↓
2. 识别番号
   ↓
3. 计算目标路径 /dist/{番号}/{番号}.ext
   ↓
4. 状态判定
   ↓
   ├─→ to_organize  → [用户整理] → organized
   ├─→ duplicate
   ├─→ target_exists
   └─→ unidentifiable

5. 在刮削页选择 organized 状态的记录
   ↓
6. 触发刮削(批量/单条)
   ↓
7. 多源爬取(串行,每源间隔 2-3 秒)
   ├─→ javdb
   ├─→ javbus
   ├─→ dmm
   └─→ javtrailers
   ↓
8. 元数据合并(固定优先级)
   ↓
9. 写入文件
   ├─→ /dist/{番号}/{番号}.nfo
   ├─→ /dist/{番号}/{番号}-poster.jpg
   ├─→ /dist/{番号}/{番号}-fanart.jpg
   └─→ /dist/{番号}/{番号}-preview-01.jpg ~ 10.jpg
   ↓
10. 更新 scrape_status
   ├─→ success
   └─→ failed (记录错误信息)
```

### 5.2 刮削数据流

```
番号 "SSIS-123"
    ↓
并发爬取(实际串行执行,带延迟)
    ↓
┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│   javdb     │ │   javbus    │ │    dmm      │ │javtrailers  │
│ title: ...  │ │ title: ...  │ │ title: ...  │ │ title: ...  │
│ plot: ...   │ │ plot: null  │ │ plot: ...   │ │ plot: ...   │
│ actors: [...]│ │ actors: [...]│ │ actors: null│ │ actors: [...]│
│ poster: ... │ │ poster: ... │ │ poster: ... │ │ poster: ... │
└─────────────┘ └─────────────┘ └─────────────┘ └─────────────┘
         ↓              ↓              ↓              ↓
         └──────────────┴──────────────┴──────────────┘
                            ↓
                    按优先级合并
                            ↓
              title: javtrailers (优先级最高)
              plot: javtrailers
              actors: javtrailers
              poster: javtrailers
              fanart: javdb (javtrailers 无时 fallback)
                            ↓
                    生成 NFO + 下载图片
```

---

## 6. 用户流程(更新)

### 6.1 新用户首次使用流程

```
1. 放入文件到 SOURCE_DIR
2. 打开 Noctra,点击"扫描目录"
3. 查看扫描结果(扫描页)
4. 筛选"待整理",勾选要整理的文件
5. 点击"执行整理",确认后开始整理
6. 等待整理完成
7. 切换到"刮削" tab
8. 查看已整理的文件,筛选"待刮削"
9. 勾选要刮削的文件(最多50个)
10. 点击"执行刮削",确认后开始刮削
11. 等待刮削完成,查看结果
12. 在 Emby 中刷新媒体库,查看元数据
```

### 6.2 日常使用流程

```
1. 新增文件到 SOURCE_DIR
2. 扫描 → 整理 → 刮削(三步走)
3. 或:定期批量处理(周末一次性整理+刮削本周新增)
```

### 6.3 重新刮削流程

```
1. 在刮削页筛选"已刮削"
2. 找到要重新刮削的条目
3. 点击"刮削"按钮
4. 系统自动备份旧 NFO: movie.nfo → movie.nfo.bak
5. 重新爬取最新元数据
6. 覆盖写入新 NFO 和图片
7. 更新刮削时间
```

---

## 7. 刮削子系统设计(核心)

### 7.1 架构图

```
┌─────────────────────────────────────────────┐
│         刮削调度器           │
│  - 批处理任务管理                            │
│  - 速率控制(2-3秒/个)                        │
│  - 进度追踪                                  │
└─────────────────┬───────────────────────────┘
                  │
                  ↓
┌─────────────────────────────────────────────┐
│      多源爬虫管理器                          │
│  - 爬�生命周期管理                          │
│  - 串行调度                                  │
│  - 错误处理与重试                            │
└─────────────────┬───────────────────────────┘
                  │
      ┌───────────┼───────────┬───────────┐
      ↓           ↓           ↓           ↓
   ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
   │ javdb  │ │ javbus │ │  dmm   │ │javtrail│
   │crawler │ │crawler │ │crawler │ │crawler │
   └────────┘ └────────┘ └────────┘ └────────┘
      │           │           │           │
      └───────────┴───────────┴───────────┘
                  │
                  ↓
┌─────────────────────────────────────────────┐
│       元数据合并器                           │
│  - 字段级优先级                              │
│  - 空值 fallback                            │
│  - 来源追踪                                  │
└─────────────────┬───────────────────────────┘
                  │
                  ↓
┌─────────────────────────────────────────────┐
│       文件写入器                             │
│  - NFO 生成(Emby 格式)                       │
│  - 图片下载                                  │
│  - 备份管理                                  │
└─────────────────────────────────────────────┘
```

### 7.2 数据模型

#### ScrapeMetadata(统一元数据)

```python
@dataclass
class ScrapeMetadata:
    """统一的元数据模型"""
    code: str                          # 番号 "SSIS-123"
    title: str | None = None           # 标题
    plot: str | None = None            # 剧情简介
    actors: list[str] = field(default_factory=list)   # 演员列表
    studio: str | None = None          # 制作商
    series: str | None = None          # 系列
    director: str | None = None        # 导演
    release: str | None = None         # 发布日期 YYYY-MM-DD
    runtime: int | None = None         # 时长(分钟)
    tags: list[str] = field(default_factory=list)     # 标签
    poster_url: str | None = None      # 封面图 URL
    fanart_url: str | None = None      # 背景图 URL
    preview_urls: list[str] = field(default_factory=list)  # 预览图 URL(最多10张)
    trailer_url: str | None = None     # 预告片 URL
    website: str | None = None         # 来源网站 URL
    resolution: str | None = None      # 分辨率 "1920x1080"

    # 来源追踪
    source: str | None = None          # 主来源(按优先级最高的)
    raw_sources: list[str] = field(default_factory=list)  # 实际成功的来源列表
```

### 7.3 爬虫接口设计

#### BaseCrawler(抽象基类)

```python
class BaseCrawler(ABC):
    """爬虫基类,预留扩展能力"""

    name: str  # 爬虫名称

    @abstractmethod
    async def crawl(self, code: str) -> ScrapeMetadata | None:
        """爬取指定番号的元数据"""
        pass

    def _request(
        self,
        url: str,
        proxy: str | None = None,      # 预留代理扩展
        cookies: dict | None = None,   # 预留 Cookie 扩展
        headers: dict | None = None    # 预留自定义 headers
    ) -> str | None:
        """HTTP 请求封装,使用 curl_cffi 模拟 Chrome"""
        pass

    def _build_url(self, code: str) -> str:
        """构建目标 URL"""
        pass
```

#### 具体爬虫示例

```python
class JavDBCrawler(BaseCrawler):
    """JavDB 爬虫 - HTML 爬取"""
    name = "javdb"

    def _build_url(self, code: str) -> str:
        return f"https://javdb.com/v/{code}"

    async def crawl(self, code: str) -> ScrapeMetadata | None:
        url = self._build_url(code)
        html = await self._request(url)
        if not html:
            return None

        # 使用 BeautifulSoup 解析 HTML
        soup = BeautifulSoup(html, 'html.parser')

        return ScrapeMetadata(
            code=code,
            title=self._extract_title(soup),
            plot=self._extract_plot(soup),
            actors=self._extract_actors(soup),
            # ... 其他字段
            source=self.name
        )

class DMMCrawler(BaseCrawler):
    """DMM 爬虫 - API 调用"""
    name = "dmm"

    def _build_url(self, code: str) -> str:
        # DMM 可能需要转换番号格式
        dmm_cid = self._convert_to_dmm_cid(code)
        return f"https://api.dmm.co.jp/.../cid={dmm_cid}"

    async def crawl(self, code: str) -> ScrapeMetadata | None:
        url = self._build_url(code)
        json_data = await self._request_json(url)  # 返回 dict
        if not json_data:
            return None

        # 解析 JSON
        return ScrapeMetadata(
            code=code,
            title=json_data.get("title"),
            # ...
            source=self.name
        )
```

### 7.4 元数据合并策略

#### 固定优先级配置

```python
FIELD_SOURCE_PRIORITY = {
    "title": ["javtrailers", "javdb", "javbus", "dmm"],
    "plot": ["javtrailers", "dmm", "javdb", "javbus"],
    "actors": ["javtrailers", "javdb", "javbus", "dmm"],
    "studio": ["javtrailers", "javdb", "javbus", "dmm"],
    "poster_url": ["javtrailers", "javdb", "javbus", "dmm"],
    "fanart_url": ["javtrailers", "javdb", "javbus", "dmm"],
    "preview_urls": ["javtrailers", "javdb", "javbus", "dmm"],
    "tags": ["javtrailers", "javdb", "javbus", "dmm"],
    "release": ["javtrailers", "javdb", "javbus", "dmm"],
    "runtime": ["javtrailers", "javdb", "javbus", "dmm"],
}
```

#### 合并逻辑

```python
def merge_metadata(results: list[ScrapeMetadata]) -> ScrapeMetadata:
    """合并多个源的元数据

    策略:
    - 每个字段按优先级从高到低选择第一个非空值
    - 如果所有源都为空,字段留空
    - 记录主来源(按 title 优先级)
    """
    if not results:
        return None

    merged = ScrapeMetadata(code=results[0].code)
    merged.raw_sources = [r.source for r in results if r.source]

    # 按优先级合并每个字段
    for field, priority_list in FIELD_SOURCE_PRIORITY.items():
        for source_name in priority_list:
            for result in results:
                if result.source == source_name:
                    value = getattr(result, field, None)
                    if value and value not in (None, "", [], {}):
                        setattr(merged, field, value)
                        break
            else:
                continue
            break

    # 确定 source (以 title 的来源为主来源)
    for source_name in FIELD_SOURCE_PRIORITY["title"]:
        if any(r.source == source_name for r in results):
            merged.source = source_name
            break

    return merged
```

### 7.5 文件输出规范

#### 目录结构

```
/dist/{番号}/
├── {番号}.mp4                  # 视频文件
├── {番号}.nfo                  # 元数据
├── {番号}-poster.jpg           # 封面
├── {番号}-fanart.jpg           # 背景
├── {番号}-preview-01.jpg       # 预览 1
├── {番号}-preview-02.jpg       # 预览 2
└── ... (最多10张预览图)
```

#### NFO 文件格式(Emby 兼容)

```xml
<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<movie>
  <plot><![CDATA[剧情简介...]]></plot>
  <outline />
  <lockdata>false</lockdata>
  <dateadded>2026-03-27 12:00:00</dateadded>
  <title>SSIS-123</title>
  <originaltitle>SSIS-123</originaltitle>
  <actor>
    <name>演员名</name>
    <type>Actor</type>
  </actor>
  <year>2023</year>
  <sorttitle>SSIS-123</sorttitle>
  <imdbid>SSIS-123</imdbid>
  <premiered>2023-06-27</premiered>
  <releasedate>2023-06-27</releasedate>
  <genre>标签1</genre>
  <genre>标签2</genre>
  <genre>标签3</genre>
  <studio>制作商</studio>
  <uniqueid type="imdb">SSIS-123</uniqueid>
  <id>SSIS-123</id>
  <fileinfo>
    <streamdetails />
  </fileinfo>
  <website>https://www.dmm.co.jp/...</website>
  <resolution>1920x1080</resolution>
  <poster>SSIS-123-poster.jpg</poster>
  <cover>SSIS-123-poster.jpg</cover>
  <fanart>
    <thumb>SSIS-123-fanart.jpg</thumb>
  </fanart>
</movie>
```

### 7.6 批处理控制

#### 速率控制

```python
async def scrape_batch(file_ids: list[int]):
    """批量刮削,串行执行,固定间隔"""

    # 前端限制最多 50 个
    if len(file_ids) > 50:
        raise ValueError("单次最多刮削50个文件")

    results = {"success": 0, "failed": 0, "errors": []}

    for i, file_id in enumerate(file_ids):
        try:
            await scrape_single(file_id)
            results["success"] += 1
        except Exception as e:
            results["failed"] += 1
            results["errors"].append(f"{file_id}: {str(e)}")

        # 不是最后一个,等待 2-3 秒
        if i < len(file_ids) - 1:
            delay = random.uniform(2.0, 3.0)
            await asyncio.sleep(delay)

    return results
```

#### 时间估算

- 单个刮削平均耗时: 8-12 秒(4个源 × 2秒请求 + 网络延迟)
- 间隔时间: 2-3 秒
- **总计**: 约 10-15 秒/个
- **50个批量**: 约 8-12 分钟

---

## 8. 数据库 Schema(更新)

### 8.1 新增字段

```sql
-- 刮削相关字段
ALTER TABLE files ADD COLUMN scrape_status TEXT DEFAULT 'pending';
ALTER TABLE files ADD COLUMN scrape_source TEXT;
ALTER TABLE files ADD COLUMN last_scrape_at TEXT;
ALTER TABLE files ADD COLUMN scrape_count INTEGER DEFAULT 0;
ALTER TABLE files ADD COLUMN scrape_error TEXT;

-- 索引优化
CREATE INDEX idx_files_scrape_status ON files(scrape_status);
CREATE INDEX idx_files_status_scrape ON files(status, scrape_status);
```

### 8.2 完整 Schema

```sql
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_path TEXT UNIQUE NOT NULL,
    identified_code TEXT,
    target_path TEXT,
    status TEXT NOT NULL DEFAULT 'to_organize',
    file_size INTEGER NOT NULL,
    file_mtime REAL NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    -- 刮削相关
    scrape_status TEXT DEFAULT 'pending',
    scrape_source TEXT,
    last_scrape_at TEXT,
    scrape_count INTEGER DEFAULT 0,
    scrape_error TEXT
);
```

---

## 9. API 设计(新增)

### 9.1 刮削相关接口

```python
# 获取刮削列表
GET /api/scrape?page=1&per_page=50&filter=pending&sort=code

# 单条刮削
POST /api/scrape/{file_id}

# 批量刮削
POST /api/scrape/batch
Body: {"file_ids": [1, 2, 3, ...]}

# 查询批处理进度
GET /api/scrape/batch/{batch_id}

# 取消批处理
POST /api/scrape/batch/{batch_id}/cancel

# 查看刮削历史
GET /api/scrape/{file_id}/history
```

### 9.2 响应模型

```python
class ScrapeListItem(BaseModel):
    file_id: int
    code: str
    target_path: str
    scrape_status: str  # pending, success, failed
    last_scrape_at: str | None
    scrape_source: str | None
    scrape_error: str | None

class ScrapeBatchResponse(BaseModel):
    batch_id: str
    status: str  # queued, running, completed, failed, cancelled
    total: int
    success: int
    failed: int
    current_item: str | None
    errors: list[str]
```

---

## 10. 风险与应对策略

### 10.1 数据源不稳定风险

**风险描述**:
- 某些网站可能随时关闭、改版、限制访问
- HTML 结构变化导致解析失败

**应对策略**:
- ✅ 多源备份,不依赖单一网站
- ✅ 每个爬虫独立失败处理,一个挂了不影响其他
- ✅ 爬虫代码模块化,易于更新和替换
- ✅ 解析失败时返回 None,记录详细日志
- ✅ 预留配置项支持快速禁用某个源

### 10.2 反爬风险

**风险描述**:
- 网站检测到爬虫行为,封禁 IP 或要求验证码
- 高频请求导致 IP 被临时封禁

**v1.5 保守应对策略**:
- ✅ 使用 `curl_cffi` 模拟真实浏览器指纹
- ✅ 固定延迟 2-3 秒,避免高频请求
- ✅ 串行执行,不并发请求
- ✅ 不登录、不使用 Cookie,只爬公开页面
- ✅ 单次批量限制 50 个,避免长时间连续请求
- ✅ 随机化延迟时间(2.0-3.0 秒),更接近真人行为

**架构预留扩展能力**(v2 可启用):
- 🔧 代理池支持( `_request` 方法预留 `proxy` 参数)
- 🔧 Cookie 注入(预留 `cookies` 参数)
- 🔧 自定义 headers(预留 `headers` 参数)
- 🔧 每源独立延迟策略(子类可覆盖 `_apply_delay`)

### 10.3 多源冲突风险

**风险描述**:
- 不同网站返回的元数据不一致(演员名单、发布日期等)
- 可能导致用户困惑

**应对策略**:
- ✅ 字段级优先级,明确信任顺序
- ✅ 记录每个字段的实际来源,NFO 中保留 `source` 标识
- ✅ plot 字段过滤:避免使用纯占位符或元描述
- ✅ title 字段验证:避免使用纯番号作为标题

### 10.4 性能风险

**风险描述**:
- 用户一次选择 50 个文件刮削,耗时过长(8-12 分钟)
- 占用网络带宽

**应对策略**:
- ✅ 前端限制单次最多 50 个
- ✅ 显示预计完成时间(按 12 秒/个估算)
- ✅ 支持取消批处理
- ✅ 刮削进度持久化,服务重启可恢复(v2 考虑)
- ✅ 实时进度反馈,不会让用户感觉卡死
- ✅ 限制预览图下载数量(最多 10 张)

### 10.5 存储风险

**风险描述**:
- 图片下载失败或损坏
- NFO 文件写入错误
- 磁盘空间不足

**应对策略**:
- ✅ 图片下载失败不影响 NFO 生成
- ✅ NFO 写入前做 XML 格式校验
- ✅ 重新刮削时自动备份旧 NFO(`.bak`)
- ✅ 写入失败时记录详细错误日志
- ✅ 预留磁盘空间检查(v2 考虑)

---

## 11. 与 MrBanana 的对比总结

| 设计维度 | MrBanana | Noctra v1.5 | 选择理由 |
|---------|----------|-------------|---------|
| **核心定位** | 下载+刮削工具 | 整理+刮削工具 | 聚焦不同场景 |
| **语言/框架** | Python + FastAPI | Python + FastAPI | 保持一致 |
| **HTTP 库** | curl_cffi | curl_cffi | 反爬能力 |
| **并发模型** | ThreadPoolExecutor | asyncio | 更轻量 |
| **配置化** | 用户可配置优先级 | 固定优先级 | v1 简化 |
| **反爬策略** | 支持代理/Cookie | 预留扩展点 | v1 保守 |
| **缓存机制** | 无缓存 | 预留接口 | 后续优化 |
| **重试策略** | 无 | 简单重试1次 | 提高成功率 |
| **图片策略** | 全量下载 | 限制预览10张 | 控制开销 |
| **NFO 格式** | Kodi 兼容 | Emby 兼容 | 参考 SSIS-743.nfo |
| **目录结构** | previews/ 子目录 | 扁平化 {code}-preview-*.jpg | Emby 兼容性 |
| **批处理限制** | 无明确限制 | 最多50个/次 | 控制风险 |
| **请求延迟** | 可配置 | 固定2-3秒 | 保守策略 |
| **错误反馈** | 静默失败 | 详细错误日志 | 便于调试 |
| **状态独立** | 无状态 | 整理/刮削状态独立 | 产品哲学一致 |

---

## 12. 开发里程碑建议

### Phase 1: 基础架构(Week 1-2)
- [ ] 数据库 schema 升级
- [ ] 爬虫基类和接口定义
- [ ] 元数据模型定义
- [ ] 合并器实现

### Phase 2: 爬虫实现(Week 3-4)
- [ ] JavDB 爬虫
- [ ] JavBus 爬虫
- [ ] DMM 爬虫
- [ ] JavTrailers 爬虫

### Phase 3: 文件写入(Week 5)
- [ ] NFO 生成器(Emby 格式)
- [ ] 图片下载器
- [ ] 备份管理

### Phase 4: API 和批处理(Week 6)
- [ ] 刮削 API 实现
- [ ] 批处理调度器
- [ ] 速率控制

### Phase 5: 前端(Week 7-8)
- [ ] 刮削页 UI
- [ ] 批处理面板
- [ ] 进度展示

### Phase 6: 测试和优化(Week 9)
- [ ] 单元测试
- [ ] 集成测试
- [ ] 性能优化
- [ ] 文档完善

---

## 13. 与 v1.0 的关键变更

### 13.1 状态重命名

| v1.0 | v1.5 | 原因 |
|------|------|------|
| `pending` | `to_organize` | 更准确的语义 |
| `processed` | `organized` | 与刮削状态区分 |
| `skipped` | `unidentifiable` | 更明确的含义 |

### 13.2 新增概念

- **刮削子状态**: `pending`, `success`, `failed`
- **刮削页**: 独立的刮削管理界面
- **刮削历史**: 记录每次刮削的时间和结果

### 13.3 页面变更

| v1.0 | v1.5 |
|------|------|
| 扫描页 | 扫描页(保持) |
| 历史页 | 刮削页(新增) |

---

## 14. 总结

Noctra v1.5 在保持 v1.0 整理能力的基础上,新增了完整的元数据刮削子系统:

1. **产品哲学延续**: 从"先看后搬"到"先整理后刮削"
2. **状态独立**: 整理和刮削完全解耦,用户可自由控制
3. **保守策略**: v1.5 采用保守的反爬策略,预留扩展架构
4. **Emby 兼容**: NFO 格式和目录结构完全兼容 Emby
5. **模块化设计**: 爬虫、合并器、写入器独立,易于维护和扩展

这份 PRD 可作为下一步开发的唯一依据。
