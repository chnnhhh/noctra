# Scraping v1 MVP (最小可实现范围)

## 文档说明

- **版本**: v1 MVP
- **更新日期**: 2026-03-27
- **基于**: PRD v1.5
- **目标**: 在最短时间内跑通核心流程,避免过度设计

---

## 1. 核心原则

### MVP 哲学

1. **先跑通,再优化**: 确保"能刮削",而不是"刮削完美"
2. **单源优先**: 不做多源合并,先验证单源可用性
3. **核心字段优先**: 只保留 Emby 识别必需的字段
4. **延后所有"可以以后再加"的功能**

### 成功标准

```
用户能够:
1. 扫描 → 整理 → 看到"已刮削"状态
2. 点击"刮削"按钮
3. 等待 10-20 秒
4. 看到 NFO 文件和封面图已生成
5. 在 Emby 中刷新后看到元数据
```

---

## 2. Scraping v1 最小功能清单

### ✅ 必须实现 (MVP)

#### 2.1 数据源(仅 1 个)

**选择: JavDB**

理由:
- 数据质量高,字段完整
- HTML 结构相对稳定
- 不需要登录
- 反爬相对宽松

**❌ 本期不实现**:
- JavBus
- DMM
- JavTrailers

#### 2.2 核心元数据字段(仅 7 个)

```python
@dataclass
class ScrapingMetadata:
    code: str              # 番号
    title: str             # 标题 ⭐ 必需
    plot: str              # 剧情简介 ⭐ 必需
    actors: list[str]      # 演员列表 ⭐ 必需
    release: str           # 发布日期 ⭐ 必需
    studio: str            # 制作商
    poster_url: str        # 封面图 URL ⭐ 必需
```

**字段说明**:
- ⭐ 标记为 Emby 识别必需字段
- 不包含: director, series, runtime, tags, trailer, fanart, preview

#### 2.3 图片类型(仅 1 种)

**仅下载 poster**

- ✅ 下载封面图 `{code}-poster.jpg`
- ❌ 不下载 fanart
- ❌ 不下载 preview 图片

**理由**:
- Emby 显示海报是刚需
- 其他图片属于"锦上添花"

#### 2.4 NFO 格式(简化版)

```xml
<?xml version="1.0" encoding="utf-8" standalone="yes"?>
<movie>
  <title>SSIS-123 タイトル</title>
  <plot><![CDATA[剧情简介...]]></plot>
  <actor><name>演员名</name></actor>
  <actor><name>演员名</name></actor>
  <premiered>2023-06-27</premiered>
  <studio>制作商</studio>
  <poster>SSIS-123-poster.jpg</poster>
</movie>
```

**包含字段**:
- ✅ title, plot, actor, premiered, studio, poster
- ❌ 不包含: uniqueid, website, resolution, fanart, tags, director 等

#### 2.5 刮削流程(极简)

```
1. 用户点击"刮削"按钮
2. 从数据库获取已整理的文件信息(code, target_path)
3. 调用 JavDB 爬虫
4. 解析 HTML,提取元数据
5. 写入 NFO 文件
6. 下载 poster 图片
7. 更新数据库: scrape_status = 'success'
8. 返回成功/失败
```

**特性**:
- ✅ 单条刮削
- ❌ 不支持批量刮削
- ❌ 不支持批处理面板
- ❌ 不支持进度条

#### 2.6 状态管理(最小化)

**主状态**:
- `to_organize` (待整理)
- `organized` (已整理)
- `scraped` (已刮削)
- `scrape_failed` (刮削失败)

**刮削子状态**(简化):
- `pending` → `success` / `failed`
- 不记录: scrape_source, scrape_count, scrape_error

#### 2.7 错误处理(简单)

```python
# 爬取失败
if not metadata:
    # 更新数据库: scrape_status = 'failed'
    # 返回错误信息: "JavDB 未找到该番号"
    return

# 写入失败
if not write_nfo:
    # 更新数据库: scrape_status = 'failed'
    # 返回错误信息: "NFO 写入失败"
    return
```

**特性**:
- ✅ 记录失败状态
- ✅ 显示错误信息
- ❌ 不重试
- ❌ 不 fallback

#### 2.8 反爬策略(最保守)

```python
# 固定延迟
async def _request(self, url):
    await asyncio.sleep(2)  # 每次请求前等待 2 秒
    response = self._session.get(url, impersonate="chrome")
    return response.text if response.status_code == 200 else None
```

**特性**:
- ✅ 使用 curl_cffi 模拟 Chrome
- ✅ 固定延迟 2 秒
- ❌ 不使用代理
- ❌ 不使用 Cookie
- ❌ 不随机化延迟

#### 2.9 API(最小化)

```python
# 单条刮削
POST /api/scrape/{file_id}
Response: {"success": true/false, "error": "..."}

# 获取刮削列表
GET /api/scrape?page=1&per_page=50
Response: {"total": 100, "items": [...]}
```

**不包含**:
- ❌ 批量刮削 API
- ❌ 批处理进度查询
- ❌ 批处理取消

#### 2.10 前端 UI(最小化)

**刮削页**:
- ✅ 展示已整理文件列表
- ✅ 显示刮削状态(待刮削/已刮削/失败)
- ✅ 每行有"刮削"按钮
- ❌ 不支持勾选
- ❌ 不支持批量操作
- ❌ 没有批处理面板

**统计卡**:
- ✅ 已整理总数
- ✅ 待刮削数量
- ✅ 已刮削数量
- ❌ 刮削失败数量(简化,不显示)

---

## 3. 明确不在本期实现的功能清单

### ❌ v1.5 / v2 再考虑

#### 3.1 多源相关
- ❌ 多源爬取(JavBus, DMM, JavTrailers)
- ❌ 元数据合并器
- ❌ 字段级优先级配置
- ❌ 来源追踪和记录

#### 3.2 批处理相关
- ❌ 批量刮削(勾选多个文件)
- ❌ 批处理调度器
- ❌ 批处理进度面板
- ❌ 实时进度反馈
- ❌ 批处理取消

#### 3.3 图片相关
- ❌ fanart 背景图
- ❌ preview 预览图
- ❌ 并发下载
- ❌ 图片重试机制

#### 3.4 高级特性
- ❌ 重试机制(失败后自动重试)
- ❌ 缓存系统
- ❌ 代理支持
- ❌ Cookie 管理
- ❌ 自定义 headers

#### 3.5 元数据字段
- ❌ director(导演)
- ❌ series(系列)
- ❌ runtime(时长)
- ❌ tags(标签)
- ❌ trailer_url(预告片)
- ❌ website(来源网址)
- ❌ resolution(分辨率)
- ❌ uniqueid(外部 ID)
- ❌ sorttitle(排序标题)

#### 3.6 NFO 高级字段
- ❌ outline
- ❌ lockdata
- ❌ dateadded
- ❌ originaltitle
- ❌ year
- ❌ sorttitle
- ❌ imdbid
- ❌ releasedate
- ❌ genre(用 tags 替代)
- ❌ uniqueid
- ❌ id
- ❌ fileinfo
- ❌ website
- ❌ resolution
- ❌ cover
- ❌ fanart

#### 3.7 用户体验
- ❌ 刮削历史记录
- ❌ 刮削时间统计
- ❌ 错误详情展示
- ❌ 重新刮削确认
- ❌ NFO 备份

---

## 4. 推荐的开发顺序(Phase 1)

### Week 1: 数据库 + 基础架构

#### Day 1-2: 数据库升级
```sql
-- 最小化 schema 变更
ALTER TABLE files ADD COLUMN scrape_status TEXT DEFAULT 'pending';
ALTER TABLE files ADD COLUMN last_scrape_at TEXT;

-- 索引
CREATE INDEX idx_files_scrape_status ON files(scrape_status);

-- 状态迁移
UPDATE files SET status = 'organized' WHERE status = 'processed';
```

#### Day 3-4: 爬虫基类 + JavDB 爬虫

```python
# app/scrapers/base.py
class BaseCrawler:
    async def crawl(self, code: str) -> Optional[ScrapingMetadata]:
        pass

# app/scrapers/javdb.py
class JavDBCrawler(BaseCrawler):
    async def crawl(self, code: str):
        url = f"https://javdb.com/v/{code}"
        html = await self._request(url)
        return self._parse(html)
```

**任务**:
- [ ] 实现 BaseCrawler
- [ ] 实现 JavDBCrawler
- [ ] 单元测试:爬取单个番号

### Week 2: 文件写入 + API

#### Day 5-6: NFO 生成器

```python
# app/scrapers/writers/nfo.py
def write_nfo(metadata: ScrapingMetadata, output_path: Path):
    # 生成简化版 NFO
    movie = ET.Element("movie")
    # 只包含核心字段
```

**任务**:
- [ ] 实现 write_nfo
- [ ] 单元测试:生成 NFO 文件

#### Day 7: 图片下载器

```python
# app/scrapers/writers/image.py
async def download_poster(url: str, output_path: Path):
    # 下载单个 poster
```

**任务**:
- [ ] 实现图片下载
- [ ] 单元测试:下载图片

#### Day 8-10: 刮削调度器 + API

```python
# app/scraper.py
class ScraperScheduler:
    async def scrape_single(self, file_id: int):
        # 1. 获取文件信息
        # 2. 调用 JavDB 爬虫
        # 3. 写入 NFO + poster
        # 4. 更新数据库

# app/main.py
@router.post("/api/scrape/{file_id}")
async def scrape_single(file_id: int):
    result = await scheduler.scrape_single(file_id)
    return result
```

**任务**:
- [ ] 实现 ScraperScheduler
- [ ] 实现刮削 API
- [ ] 集成测试:完整刮削流程

### Week 3: 前端 UI

#### Day 11-13: 刮削页 UI

```javascript
// static/js/scrape-page.js
async function renderScrapeList() {
    // 获取已整理文件列表
    // 显示刮削状态
    // 渲染"刮削"按钮
}

async function handleScrape(fileId) {
    // 调用刮削 API
    // 显示成功/失败提示
    // 刷新列表
}
```

**任务**:
- [ ] 刮削页 HTML
- [ ] 刮削列表展示
- [ ] 刮削按钮交互
- [ ] 状态更新逻辑

#### Day 14-15: 测试 + 修复

**任务**:
- [ ] 端到端测试
- [ ] Bug 修复
- [ ] 性能测试

---

## 5. 代码简化示例

### 5.1 元数据模型(MVP)

```python
@dataclass
class ScrapingMetadata:
    """最小化元数据模型"""
    code: str
    title: str
    plot: str
    actors: List[str]
    release: str
    studio: str
    poster_url: str
```

### 5.2 爬虫实现(MVP)

```python
class JavDBCrawler(BaseCrawler):
    async def crawl(self, code: str) -> Optional[ScrapingMetadata]:
        url = f"https://javdb.com/v/{code}"
        html = await self._request(url)

        if not html:
            return None

        soup = BeautifulSoup(html, 'html.parser')

        return ScrapingMetadata(
            code=code,
            title=self._extract_title(soup),
            plot=self._extract_plot(soup),
            actors=self._extract_actors(soup),
            release=self._extract_release(soup),
            studio=self._extract_studio(soup),
            poster_url=self._extract_poster(soup),
        )
```

### 5.3 刮削流程(MVP)

```python
async def scrape_single(file_id: int):
    # 1. 获取文件信息
    file_info = db.query("SELECT * FROM files WHERE id = ?", file_id)
    code = file_info["identified_code"]
    target_dir = Path(file_info["target_path"]).parent

    # 2. 爬取
    crawler = JavDBCrawler()
    metadata = await crawler.crawl(code)

    if not metadata:
        db.execute("UPDATE files SET scrape_status = 'failed' WHERE id = ?", file_id)
        return {"success": False, "error": "爬取失败"}

    # 3. 写入 NFO
    nfo_path = target_dir / f"{code}.nfo"
    write_nfo(metadata, nfo_path)

    # 4. 下载 poster
    poster_path = target_dir / f"{code}-poster.jpg"
    await download_poster(metadata.poster_url, poster_path)

    # 5. 更新数据库
    db.execute(
        "UPDATE files SET scrape_status = 'success', last_scrape_at = ? WHERE id = ?",
        (datetime.now().isoformat(), file_id)
    )

    return {"success": True}
```

---

## 6. 验收标准

### 功能验收

- [ ] 用户能够看到"刮削" tab
- [ ] 刮削页显示已整理的文件列表
- [ ] 点击"刮削"按钮后,状态变为"刮削中..."
- [ ] 10-20 秒后,状态变为"已刮削"
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

## 7. v1.5 / v2 扩展路线图

### v1.5(第二批功能)

1. **多源支持**:
   - 新增 JavBus 爬虫
   - 新增 DMM 爬虫
   - 实现简单的元数据合并(按优先级)

2. **图片完善**:
   - 新增 fanart 下载
   - 新增 preview 图片(5张)

3. **NFO 完善**:
   - 添加 tags 字段
   - 添加 director 字段
   - 完整 Emby 兼容格式

4. **用户体验**:
   - 批量刮削(最多10个)
   - 简单的批处理面板
   - 错误提示优化

### v2(完整功能)

1. **完整多源**:
   - 新增 JavTrailers 爬虫
   - 智能元数据合并
   - 来源追踪

2. **高级特性**:
   - 重试机制
   - 缓存系统
   - 代理支持

3. **批处理增强**:
   - 支持最多 50 个批量
   - 实时进度反馈
   - 取消批处理

4. **元数据完善**:
   - 所有字段支持
   - 预览图最多 10 张
   - 完整 NFO 格式

---

## 8. 总结

### MVP 对比完整功能

| 功能 | 完整版 v1.5 | MVP v1 | 说明 |
|------|------------|--------|------|
| 数据源 | 4 个 | 1 个(JavDB) | 验证可行性 |
| 元数据字段 | 15+ 个 | 7 个 | Emby 识别必需 |
| 图片类型 | poster + fanart + preview | 仅 poster | 核心需求 |
| NFO 格式 | 完整 Emby 兼容 | 简化版 | 功能够用 |
| 批处理 | 支持 50 个 | 不支持 | 单条为主 |
| 进度反馈 | 实时进度面板 | 简单状态 | 延后优化 |
| 重试机制 | 支持 | 不支持 | 延后 |
| 多源合并 | 支持 | 不支持 | 延后 |

### 开发时间估算

- **MVP v1**: 3 周(单人)
- **完整版 v1.5**: 9 周(单人)

### 风险控制

**MVP 优势**:
- ✅ 快速验证核心流程
- ✅ 降低开发风险
- ✅ 尽早获得用户反馈
- ✅ 迭代式开发,压力小

**MVP 劣势**:
- ❌ 功能不完整
- ❌ 需要后续迭代

**建议**:
1. 先完成 MVP,确保核心流程跑通
2. 在真实环境中测试(至少刮削 100 个番号)
3. 收集反馈,评估是否需要多源
4. 再决定是否投入 v1.5 开发

---

## 9. 立即开始的检查清单

### 准备工作
- [ ] 确认 JavDB 网站可访问
- [ ] 确认 curl_cffi 库可用
- [ ] 准备测试用番号(至少 10 个)
- [ ] 准备 Emby 测试环境

### 开发环境
- [ ] Python 3.10+
- [ ] 安装依赖: curl-cffi, beautifulsoup4, aiohttp
- [ ] 数据库升级脚本测试
- [ ] 单元测试框架搭建

### 第一个任务
- [ ] 实现 JavDBCrawler.crawl("SSIS-123")
- [ ] 打印结果,验证能正确解析
- [ ] 进入下一步:文件写入

---

这份 MVP 定义将帮助你 **在最短时间内(3 周)跑通核心刮削流程**,而不是一次做完所有功能。建议先按 MVP 开发,验证可行性后再考虑扩展功能。
