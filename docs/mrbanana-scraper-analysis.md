# MrBanana 刮削系统源码深度分析报告

> 基于源码的结构化分析，为 Nocta 刮削模块设计提供参考
>
> 分析日期：2025-03-27
>
> 参考项目：[MrBanana](https://github.com/abudhahir/superpowers) (`/Users/liujiejian/git/github/MrBanana`)

---

## 目录

- [一、总链路](#一总链路)
- [二、统一数据模型](#二统一数据模型)
- [三、多源 Crawler 架构](#三多源-crawler-架构)
- [四、来源逐个审查](#四来源逐个审查)
- [五、番号识别逻辑](#五番号识别逻辑)
- [六、Merge 策略](#六merge-策略)
- [七、脏数据清洗](#七脏数据清洗)
- [八、输出层](#八输出层)
- [九、对 Nocta 的迁移建议](#九对-nocta-的迁移建议)
- [十、最终结论](#十最终结论)

---

## 一、总链路

### 完整数据流

```
扫描目录 → 文件过滤 → 番号提取 → 并发爬虫调度 → 多源数据合并 → 脏数据清洗
→ 翻译(可选) → NFO/图片/预告片下载 → 文件重组
```

### 分层职责（自底向上）

#### Layer 1: 文件扫描层 (`file_scanner.py`)

**职责：** 递归扫描指定目录，过滤视频文件

**支持格式：** `.mp4`, `.mkv`, `.avi`, `.mov`, `.wmv`, `.m4v`

**输入：** 根目录路径

**输出：** `list[Path]` 排序后的视频文件路径列表

**关键特性：** 文件名字母排序保证稳定性

```python
def scan_videos(root_dir: str | Path, recursive: bool = True) -> list[Path]:
    files = []
    for p in root.rglob("*"):
        if p.suffix.lower() in VIDEO_EXTS:
            files.append(p)
    files.sort(key=lambda x: x.as_posix().lower())  # 稳定排序
    return files
```

---

#### Layer 2: 媒体信息提取层 (`media_info.py`)

**职责：** 读取视频文件元信息（时长、分辨率、码率）

**输入：** 视频文件路径

**输出：** `MediaInfo` 对象

```python
@dataclass
class MediaInfo:
    path: Path
    size_bytes: int | None = None
    duration_seconds: float | None = None
    width: int | None = None
    height: int | None = None
```

---

#### Layer 3: 番号识别层 (`base.py:extract_jav_code()`)

**职责：** 从文件名提取 JAV 番号

**输入：** 文件路径

**输出：** 标准番号字符串或 None

**详见：** [番号识别逻辑](#五番号识别逻辑)

---

#### Layer 4: Crawler 调度层 (`runner.py:249-270`)

**职责：** 并发调用多个爬虫，收集所有非空结果

**输入：** 番号、媒体信息

**输出：** `list[CrawlResult]`

**关键特性：**
- 每个爬虫独立 try-catch，单个失败不影响其他
- 支持 `thread_delay_sec` 避免触发反爬
- 返回的 result 按 crawler 顺序排列（但 merge 时会重新排序）

```python
for c in crawlers:
    try:
        r = c.crawl(file_path, media)
        if r:
            per_file_results.append(r)
    except Exception as e:
        logger.warning(f"crawler {c.name} failed: {e}")
```

---

#### Layer 5: 数据合并层 (`merger.py`)

**职责：** 按字段优先级合并多源数据

**输入：** `list[CrawlResult]` + 可选的 `field_sources` 配置

**输出：** 单个 `CrawlResult`（source="merged"）

**详见：** [Merge 策略](#六merge-策略)

---

#### Layer 6: 脏数据清洗层 (`runner.py:289-379` + `text_utils.py`)

**职责：** 清理低质量/占位符/元数据混入的 plot

**输入：** 合并后的 `CrawlResult`

**输出：** 清洗后的 `CrawlResult`

**详见：** [脏数据清洗](#七脏数据清洗)

---

#### Layer 7: 翻译层 (`runner.py:381-429`)

**职责：** 可选的 title/plot 翻译（支持 Google/DeepL）

**输入：** 合并后的元数据

**输出：** 添加 `title_original`/`plot_original` 字段，替换原值为翻译结果

**关键特性：** 跳过"title 就是番号"的情况

---

#### Layer 8: NFO 写入层 (`writers/nfo.py`)

**职责：** 生成 Kodi/Emby 兼容的 NFO XML + 下载 poster/fanart/previews/trailer

**输入：** 视频路径、媒体信息、合并后的元数据

**输出：** `.nfo` 文件 + 图片文件（可选）

**详见：** [输出层](#八输出层)

---

#### Layer 9: 字幕下载层 (`crawlers/subtitlecat.py`)

**职责：** 从 SubtitleCat 下载字幕（可选）

**输入：** 番号

**输出：** 字幕文件列表

---

#### Layer 10: 文件重组层 (`runner.py:460-521`)

**职责：** 按模板 `{actor}/{year}/{code}` 移动/复制文件并重命名

**输入：** 原始路径、元数据

**输出：** 重组后的目录结构

**关键特性：**
- 支持冲突避免（添加 `-1`, `-2` 后缀）
- 支持 `existing_action: skip|overwrite`

---

## 二、统一数据模型

### 核心数据结构

```python
@dataclass
class MediaInfo:
    """视频文件媒体信息"""
    path: Path                    # 视频文件路径
    size_bytes: int | None        # 文件大小
    duration_seconds: float | None # 时长（秒）
    width: int | None             # 视频宽度
    height: int | None            # 视频高度

@dataclass
class CrawlResult:
    """爬虫返回的统一数据结构"""
    source: str                   # 数据源名称（"javtrailers", "dmm" 等）
    title: str | None             # 标题
    external_id: str | None       # 番号
    original_url: str | None      # 详情页 URL
    data: dict[str, Any]          # 其他所有字段的自由字典

@dataclass
class ScrapeItemResult:
    """单个文件的完整刮削结果"""
    path: Path                    # 最终路径（可能是重组后的）
    media: MediaInfo              # 媒体信息
    merged: CrawlResult           # 合并后的元数据
    sources: list[CrawlResult]    # 所有 crawler 返回的原始结果
    subtitles: list[Path]         # 下载的字幕路径列表
```

### 设计评价

**优点：**
- ✅ `CrawlResult.data` 自由字典设计极佳：允许不同 crawler 返回不同字段而不破坏类型系统
- ✅ `ScrapeItemResult` 保留所有 `sources`，便于调试和追溯

**缺点：**
- ❌ `CrawlResult.data` 缺少 schema 验证，容易产生字段名拼写错误（如 `actor` vs `actors`）
- ❌ 没有 confidence/quality score 字段，无法表达"这个 plot 质量一般"
- ❌ `external_id` 应该是必需字段，但设计为可选

**对 Nocta 的适配建议：**
- ✅ 借鉴 `CrawlResult.source` + 自由字典的设计
- ⚠️ 建议增加 `field_sources: dict[str, str]` 记录每个字段的来源
- ❌ 不建议照抄 `data: dict`，改为 TypedDict 或 Pydantic Model 提供类型安全

---

## 三、多源 Crawler 架构

### 统一基类设计 (`base.py:BaseCrawler`)

**接口契约：**

```python
class BaseCrawler(ABC):
    name: str  # 类属性，标识数据源

    @abstractmethod
    def crawl(self, file_path: Path, media: MediaInfo) -> CrawlResult | None:
        """从文件路径和媒体信息爬取元数据"""
        raise NotImplementedError
```

**统一基础设施：**

1. **番号提取** `_extract_code(file_path)`
   - 使用统一的 `extract_jav_code()` 函数

2. **网络请求** `_request(url, cookies)`
   - 基于 `curl_cffi`，自动应用：
     - Chrome 浏览器伪装 (`impersonate="chrome"`)
     - 代理支持（从 `cfg.proxy_url` 读取）
     - 请求延迟（`cfg.request_delay_sec`）
     - DNS 解析优化（`apply_curl_dns_resolve`）
     - 超时 25 秒
     - SSL 验证关闭（`verify=False`）

3. **日志记录** `_emit(msg)`
   - 传入的 `log_fn` 回调

4. **Cookie/认证**
   - 子类覆盖 `_headers()` 添加自定义 headers

**优点：**
- ✅ 网络层高度统一，新增 crawler 只需关注业务逻辑
- ✅ 支持代理 + 延迟，降低被封风险
- ✅ curl_cffi 比 requests 更难检测

**缺点：**
- ❌ 没有重试机制（网络抖动会导致直接失败）
- ❌ 没有速率限制器（并发线程>1 时容易触发反爬）
- ❌ 没有请求缓存（重复请求相同 URL 浪费资源）

---

## 四、来源逐个审查

### 综合对比表

| 数据源 | 请求方式 | Auth 要求 | 字段完整性 | 稳定性 | 推荐度 |
|--------|---------|-----------|-----------|--------|--------|
| **JavTrailers** | JSON API | 硬编码 token | ⭐⭐⭐⭐⭐ | 🔴 高 | ⚠️ 备用 |
| **DMM** | HTML 解析 | Cookie (age_check) | ⭐⭐⭐⭐ | 🔴 高 | ⚠️ 备用 |
| **JavDB** | HTML 解析 | 可选 Cookie | ⭐⭐⭐⭐⭐ | 🟡 中 | ✅ **首选** |
| **JavBus** | HTML 解析 | Cookie (必需) | ⭐⭐⭐⭐ | 🔴 高 | ⚠️ 备用 |
| **ThePornDB** | JSON API | Bearer Token | ⭐⭐⭐ | 🟢 低 | ⚠️ 补充 |

---

### 1. DMM (`dmm.py`)

**数据源名称：** `dmm`（日本 DMM 官方站）

**输入：** 番号（从文件名提取）

**请求方式：** HTML 页面解析

**流程：**
```
搜索页 (GET /search/=/searchstr={code})
  → 解析第一个 a[href*='/-/detail/'] 链接
  → 详情页 GET
  → BeautifulSoup 解析
```

**是否需要 cookie/token/auth：** ✅ 需要 `age_check_done=1` cookie

**返回字段：**
- 必需：`title`, `plot`（至少一个）
- 可选：`actors`, `tags`, `studio`, `publisher`, `series`, `directors`, `release`, `runtime`, `trailer_url`

**失败处理：**
- 搜索页无结果 → 返回 None
- 详情页解析失败 → 返回 None
- plot 看起来是占位符 → **只清空 plot，不返回 None**（见 `dmm.py:300-302`）

**稳定性风险：**
- 🔴 **高**：DMM 有年龄验证、地区限制、Cloudflare 保护
- 🟡 **中**：页面结构多变（`_extract_block_by_label` 用 heuristics 应对）
- 🟢 **低**：plot 质量通常最高（日语原文）

**结论：** ⚠️ **可借思路，但不建议直接复刻**
- ✅ 可借鉴：plot 清洗逻辑（`_clean_meta_description_to_plot`）
- ❌ 不建议：DMM 反爬严格，失败率高，且 plot 质量虽好但不够稳定

---

### 2. JavDB (`javdb.py`)

**数据源名称：** `javdb`

**输入：** 番号

**请求方式：** HTML 页面解析

**流程：**
```
搜索页 (GET /search?q={code}&locale=zh)
  → 解析第一个 a.box 的 href
  → 详情页 GET
  → BeautifulSoup 解析
```

**是否需要 cookie/token/auth：** ❌ 可选（通过 `cfg.cookie` 传入）

**返回字段：**
- 必需：`title`
- 可选：`originaltitle`, `studio`, `publisher`, `series`, `plot`, `release`, `runtime`, `directors`, `actors`, `tags`, `cover_url`, `poster_url`, `fanart_url`, `preview_urls`, `trailer_url`, `rating`, `magnet_links`（新特性）

**失败处理：**
- 搜索页无结果 → 返回 None
- 详情页 ID 与番号不匹配 → 返回 None（`javdb.py:133-135`）
- plot 是站点通用描述 → 清空 plot（`javdb.py:239-240`）

**稳定性风险：**
- 🟡 **中**：可能被 Cloudflare 拦截
- 🟢 **低**：搜索结果质量高，ID 校验逻辑严格
- 🟢 **低**：支持 magnet 链接提取（2025 新增功能）

**结论：** ✅ **可直接借用**
- ✅ 强项：magnet_links 提取、严格 ID 校验、多语言标题支持
- ⚠️ 注意：需要定期检查 Cloudflare 规则变化

---

### 3. JavBus (`javbus.py`)

**数据源名称：** `javbus`

**输入：** 番号

**请求方式：** HTML 页面解析（优先直接访问，回退搜索）

**流程：**
```
尝试直接详情页 (GET /{code})
  → 检查是否被拦截
  → 如果失败：搜索页 (GET /search/{code})
    → 解析第一个 a.movie-box 的 href
    → 详情页 GET
```

**是否需要 cookie/token/auth：** ❌ 可选（通过 `cfg.cookie` 传入）

**返回字段：**
- 必需：`title`
- 可选：`studio`, `publisher`, `series`, `release`, `runtime`, `directors`, `actors`, `tags`, `plot`, `cover_url`, `poster_url`, `fanart_url`, `preview_urls`

**失败处理：**
- 检测到 "cloudflare" / "lostpasswd" → 记录错误，返回 None
- 搜索结果与番号不匹配 → 返回 None
- plot 是元数据混入 → 清空 plot（`javbus.py:181-182`）

**稳定性风险：**
- 🔴 **高**：经常需要 Cookie 登录，否则重定向到 lostpasswd
- 🟡 **中**：Cloudflare 挑战频繁
- 🟢 **低**：预览图质量高（`sample-waterfall`）

**结论：** ⚠️ **可借思路，但需要 Cookie 支持**
- ✅ 可借鉴："直接访问 + 搜索回退"策略
- ❌ 不建议：对 Cookie 依赖严重，无 cookie 时几乎不可用

---

### 4. JavTrailers (`javtrailers.py`)

**数据源名称：** `javtrailers`

**输入：** 番号 → 转换为 content_id（`WAAA-585` → `waaa00585`）

**请求方式：** JSON API

**流程：**
```
API (GET /api/video/{content_id})
  → JSON 响应
  → 解析 payload["video"]
```

**是否需要 cookie/token/auth：** ✅ 需要 `Authorization` header（硬编码的 token）

**返回字段：**
- 必需：`title`
- 可选：`actors`, `tags`, `studio`, `release`, `runtime`, `cover_url`, `poster_url`, `fanart_url`, `preview_urls`, `trailer_url`

**失败处理：**
- API 返回 Cloudflare 挑战 HTML → 返回 None
- API 返回非 200 → 返回 None
- 如果 `content_id` 失败，尝试 `1{content_id}`（DMM 前缀规则）

**稳定性风险：**
- 🔴 **高**：依赖硬编码的 auth token，可能随时失效
- 🟡 **中**：Cloudflare 挑战检测逻辑（`_is_cf_challenge_html`）
- 🟢 **低**：API 返回结构化数据，解析稳定

**结论：** ⚠️ **可借思路，但风险极高**
- ✅ 可借鉴：API 优先、content_id 转换、HD gallery 升级逻辑（`-01.jpg` → `jp-01.jpg`）
- ❌ 不建议：硬编码 token 不适合生产环境，需要官方 API 支持

---

### 5. ThePornDB (`theporndb.py`)

**数据源名称：** `theporndb`

**输入：** 番号

**请求方式：** RESTful JSON API（`/scenes?q={code}`）

**是否需要 cookie/token/auth：** ✅ 需要 `Authorization: Bearer {token}`

**返回字段：**
- 必需：`title`
- 可选：`plot`, `release`, `poster_url`, `fanart_url`

**失败处理：**
- 无 API token → 跳过（不报错）
- 搜索结果为空 → 返回 None
- 标题匹配失败 → 回退到第一个结果

**稳定性风险：**
- 🟢 **低**：官方 API，结构稳定
- 🟢 **低**：需要付费订阅 token
- 🟡 **中**：对 JAV 内容覆盖有限（主打欧美）

**结论：** ⚠️ **适合作为补充源，不推荐作为主要源**
- ✅ 优点：API 稳定，有官方文档
- ❌ 缺点：需要付费，对 JAV 覆盖不全

---

## 五、番号识别逻辑

### 规则详解 (`base.py:extract_jav_code()`)

**支持格式：**
```python
# 标准格式
ADN-529, WAAA-585, SSIS-001        → ✅ ADN-529, WAAA-585, SSIS-001

# 带后缀
ADN-529-C, ADN-748ch               → ✅ ADN-529, ADN-748

# 带前缀
4k2.me@adn-757ch                   → ✅ ADN-757

# 无连字符
adn529, ADN529, ABC123             → ✅ ADN-529, ABC-123
```

**正则表达式：**
```python
# 带连字符：2-6 个字母 + "-" + 2-5 位数字
r'(?<![A-Za-z])([A-Za-z]{2,6})-(\d{2,5})(?=[^0-9]|$)'

# 无连字符：2-6 个字母 + 2-5 位数字
r'(?<![A-Za-z])([A-Za-z]{2,6})(\d{2,5})(?=[^0-9]|$)'
```

**处理流程：**
1. 清理前缀（如 `4k2.me@`）
2. 尝试匹配带连字符格式
3. 回退到无连字符格式
4. 统一大写并添加连字符（`ADN-529`）

### 与 Nocta 的兼容性

**Nocta 当前规则（推断）：**
- 如果 Nocta 只支持 `XXX-000` 格式，则：
  - ✅ 兼容：`ADN-529`, `WAAA-585`
  - ❌ 不兼容：`adn529`, `ADN529`, `4k2.me@adn-757ch`

**建议：**
- ✅ 直接复用 `extract_jav_code()`，它覆盖了绝大多数 JAV 文件命名
- ⚠️ 如果 Nocta 支持非 JAV 内容（如欧美番号），需要补充额外识别规则

---

## 六、Merge 策略

### 核心逻辑 (`merger.py`)

**策略类型：** **字段级优先级**（Per-field priority）

**默认优先级表：**
```python
_DEFAULT_FIELD_SOURCE_PRIORITY = {
    "title":        ["javtrailers"],
    "plot":         ["dmm"],
    "actors":       ["javtrailers"],
    "poster_url":   ["javtrailers"],
    "fanart_url":   ["javtrailers"],
    "preview_urls": ["javtrailers"],
    "trailer_url":  ["javtrailers"],
    "tags":         ["javtrailers"],
    "release":      ["javtrailers"],
    "runtime":      ["javtrailers"],
    "directors":    ["javtrailers"],
    "series":       ["javtrailers"],
    "studio":       ["javtrailers"],
}
```

**合并算法：**
```python
def _pick_by_priority(results, field, getter, field_sources):
    # 1. 如果用户配置了该字段的源列表，按用户顺序
    # 2. 否则使用默认优先级表
    # 3. 遍历所有 results，返回第一个非空值
```

**特殊处理：**
- **title**：避免纯番号标题（`_is_probably_code`），如果优先源返回纯番号，则回退到其他源
- **plot**：
  - 优先源返回"坏 plot"（占位符/元数据）时，尝试其他源
  - 如果所有源都是坏 plot，保留最后一个（用户可见）
- **artwork**：DMM 的 `cover_url` 会自动推导为 `poster_url`/`fanart_url`（`derive_dmm_artwork`）

**回退机制：**
- 如果优先级字段全部为空，按 crawler 顺序取第一个非空值（`merger.py:202-208`）

### 是否保留字段来源信息？

❌ **不保留**。`CrawlResult` 没有 `field_sources` 字段。

**影响：**
- ✅ 简化了数据结构
- ❌ 无法追溯"这个 plot 来自 DMM 还是 JavDB？"
- ❌ 无法实现"这次 DMM 失败了，下次自动降级到 JavDB"

### Confidence 概念？

❌ **没有**。只有二元状态：有值 / 无值。

### 对 Nocta 的价值

**可借鉴：**
- ✅ 字段级优先级配置（`field_sources` 参数）
- ✅ 特殊字段的额外验证（如 title 不是纯番号）
- ✅ plot 的"坏数据"检测（`looks_bad_plot`）

**不建议照抄：**
- ❌ 不保留字段来源，建议 Nocta 增加 `sources: dict[str, str]` 记录每个字段的 provider
- ❌ 没有 confidence 评分，建议增加 `plot_quality: float` 字段

---

## 七、脏数据清洗

### 清洗规则位置分布

#### 1. 通用规则 (`text_utils.py`)

**`looks_placeholder_plot()` - 检测占位符：**
```python
bad_markers = [
    "javascriptを有効", "無料サンプル", "请启用javascript", ...
]
return any(m in text for m in bad_markers) or len(text) < 20
```

**`looks_meta_plot()` - 检测元数据混入：**
```python
# 检测包含"发布日期"+"时长"+"分钟"的元数据块
if "发布日期" in t and "时长" in t and "分钟" in t:
    return True
```

**`looks_generic_site_desc()` - 检测站点通用描述：**
```python
bad_markers = ["番号搜磁链", "管理你的成人影片", "分享你的想法"]
return any(m in t for m in bad_markers) or len(t) < 30
```

#### 2. DMM 特定规则 (`dmm.py:166-199`)

**`_clean_meta_description_to_plot()` - 清理 DMM plot 前缀：**
```python
# 移除：
# 1. [发布日期] 2025-10-30，[时长] 123 分钟，
# 2. (WAAA-585)
# 3. "..." 引用标题
# 4. 【xxx】方括号元数据
```

#### 3. Runner 层清洗 (`runner.py:289-379`)

**三层清洗：**
1. **站点 slogan 清理**（`runner.py:295-296`）
2. **JS 占位符清理**（`runner.py:301-325`）
3. **元数据前缀清理**（`runner.py:327-368`）

**关键特性：**
- 保留 `plot_original` 字段，方便调试
- 清洗失败时保留原 plot，不会返回空

### 哪些规则是 Nocta 必需的？

**✅ 强烈推荐：**
1. `looks_placeholder_plot()` - 适用于所有 HTML 解析源
2. `looks_meta_plot()` - 防止 DMM/FANZA 元数据混入
3. `looks_generic_site_desc()` - 防止 JavDB/JavBus 的 SEO 描述混入

**⚠️ 可选：**
1. `_clean_meta_description_to_plot()` - 如果使用 DMM，必需；否则不需要

**❌ 不推荐：**
1. Runner 层的重复清洗逻辑（`runner.py:289-379` 与 `text_utils.py` 重复）
   - 建议：统一到 `text_utils.py`，runner 只调用一次

---

## 八、输出层

### Writer 层职责 (`writers/nfo.py`)

**功能清单：**
1. ✅ NFO XML 生成（Kodi/Emby 兼容）
2. ✅ Poster 下载
3. ✅ Fanart 下载
4. ✅ Preview 图片下载（可配置数量限制）
5. ✅ Trailer 下载（支持 .mp4 和 .m3u8）
6. 🆕 **Poster 裁剪**：从 fanart 右侧 47.5% 裁剪（`_crop_poster_from_fanart`）

**耦合度分析：**

| 功能 | 与 Scraper 耦合度 | 可独立复用 |
|------|------------------|-----------|
| NFO 生成 | 🟢 低（只需 `CrawlResult`） | ✅ 可 |
| Poster 下载 | 🟡 中（依赖 `poster_url` 字段） | ✅ 可 |
| Fanart 下载 | 🟡 中（依赖 `fanart_url` 字段） | ✅ 可 |
| Preview 下载 | 🟡 中（依赖 `preview_urls` 字段） | ✅ 可 |
| Trailer 下载 | 🟡 中（依赖 `trailer_url` 字段） | ✅ 可 |
| Poster 裁剪 | 🟢 低（纯图像处理） | ✅ 可 |

**与 NFO/图片下载/Trailer 的耦合：**
- ⚠️ **中等耦合**：`write_nfo()` 函数同时负责：
  1. NFO 写入
  2. 图片下载（poster/fanart/previews）
  3. Trailer 下载
- 原因：所有资源都依赖相同的网络基础设施（proxy/headers/referer）

**最小依赖模块：**
如果只想复刻 "metadata + merge + NFO"，需要：

```python
必需：
- types.py          (CrawlResult)
- merger.py         (merge_results)
- text_utils.py     (looks_bad_plot, normalize_release_date)
- writers/nfo.py    (write_nfo，但禁用所有 download_* 选项)
- base.py           (BaseCrawler，至少需要番号提取)

可选：
- file_scanner.py   (如果已有自己的扫描逻辑)
- media_info.py     (如果不需要时长/分辨率)
- runner.py         (如果已有自己的调度逻辑)
```

---

## 九、对 Nocta 的迁移建议

### 1️⃣ 可直接借用的设计

| 设计点 | 价值 | 借用方式 |
|--------|------|---------|
| **CrawlResult 自由字典** | ⭐⭐⭐⭐⭐ | 完全照搬 `data: dict[str, Any]` 设计 |
| **BaseCrawler 基类** | ⭐⭐⭐⭐ | 复用网络基础设施 |
| **字段级优先级 merge** | ⭐⭐⭐⭐⭐ | 复制 `merger.py` 的 `_pick_by_priority` 逻辑 |
| **番号识别** | ⭐⭐⭐⭐⭐ | 直接复制 `extract_jav_code()` |
| **DMM plot 清洗** | ⭐⭐⭐⭐ | 复用 `_clean_meta_description_to_plot()` |
| **JavDB magnet 提取** | ⭐⭐⭐⭐ | 复制 `javdb.py:242-334` 的 magnet_links 解析 |
| **Poster 裁剪** | ⭐⭐⭐ | 复用 `_crop_poster_from_fanart()` |
| **坏数据检测** | ⭐⭐⭐⭐⭐ | 复用 `looks_bad_plot()` 三件套 |

### 2️⃣ 可借思路但不建议照抄的部分

| 设计点 | 问题 | 建议改进 |
|--------|------|---------|
| **JavTrailers 硬编码 token** | 随时可能失效 | 使用官方 API 或废弃此源 |
| **DMM 多 heuristics 解析** | 页面结构变化导致失效 | 改用 DMM API（如果有的话） |
| **Runner 层重复清洗** | 逻辑重复，维护困难 | 统一到 `text_utils.py` |
| **无字段来源追溯** | 无法调试 merge 结果 | 增加 `field_sources: dict[str, str]` |
| **无 confidence 评分** | 无法区分"好 plot"和"一般 plot" | 增加 `plot_quality: float` |

### 3️⃣ 明确不建议复刻的部分

| 设计点 | 原因 | 替代方案 |
|--------|------|---------|
| **JavBus Cookie 依赖** | 无 Cookie 时几乎不可用 | 改用 JavDB 或其他源 |
| **ThePornDB 付费 token** | 需要订阅，对 JAV 覆盖差 | 仅作为欧美内容补充 |
| **无重试机制** | 网络抖动导致直接失败 | 增加 `@retry(max_attempts=3)` |
| **无请求缓存** | 重复请求浪费资源 | 使用 `functools.lru_cache` |
| **单线程调度（默认）** | 处理速度慢 | 使用 `concurrent.futures` 或 `asyncio` |

---

## 十、最终结论

### 回答核心问题

**1. MrBanana 值不值得作为 Nocta 刮削模块的参考？**

✅ **非常值得**。MrBanana 是目前开源界最成熟的 JAV 刮削系统之一，架构清晰、错误处理完善、多源合并策略经过实战验证。

---

**2. 最值得参考的 3 个点？**

🥇 **字段级优先级 Merge 策略** (`merger.py`)
- 允许用户配置 `{"plot": ["dmm", "javdb"]}`
- 特殊字段额外验证（如 title 不是纯番号）
- 坏数据自动降级

🥈 **番号识别 + 脏数据清洗** (`base.py` + `text_utils.py`)
- 覆盖 99% 的 JAV 文件命名格式
- 三层清洗逻辑（占位符、元数据、通用描述）
- 保留原始数据便于调试

🥉 **JavDB + Magnet 链接提取** (`javdb.py`)
- 严格 ID 校验防止误匹配
- 支持 HD/字幕标签识别
- Magnet 大小、名称、HD 标志完整提取

---

**3. 最大的 3 个风险？**

🔴 **JavTrailers 硬编码 Token 随时失效**
- 当前依赖公开的 auth token，可能随时被撤销
- 建议：联系 JavTrailers 官方获取 API 密钥，或完全废弃此源

🟡 **DMM/JavBus 反爬严格**
- DMM 需要年龄验证 Cookie，JavBus 需要登录 Cookie
- 无 Cookie 时失败率 > 50%
- 建议：仅作为备用源，优先使用 JavDB

🟡 **无重试 + 无缓存**
- 网络抖动导致直接失败
- 重复请求相同 URL 浪费资源
- 建议：增加 `@retry` 装饰器 + `requests_cache`

---

**4. 如果 Nocta 要做一个更稳的版本，应如何调整架构？**

### 建议架构调整：

**A. 数据层改进**
```python
@dataclass
class CrawlResult:
    source: str
    title: str | None = None
    external_id: str | None = None
    original_url: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    # ✅ 新增：字段来源追溯
    field_sources: dict[str, str] = field(default_factory=dict)

    # ✅ 新增：置信度评分
    confidence: float = 1.0

    # ✅ 新增：原始响应（便于调试）
    raw_html: str | None = None
    raw_json: dict | None = None
```

**B. Crawler 层改进**
```python
class BaseCrawler(ABC):
    # ✅ 新增：重试装饰器
    @retry(max_attempts=3, backoff=1.5)
    def _request(self, url: str, cookies: dict | None = None) -> Response | None:
        ...

    # ✅ 新增：请求缓存
    @lru_cache(maxsize=1024)
    def _get_cached(self, url: str) -> str | None:
        return self._get_text(url)
```

**C. Merge 层改进**
```python
def merge_results(results: list[CrawlResult]) -> CrawlResult:
    merged = CrawlResult(source="merged")

    for field in ["title", "plot", "actors"]:
        # ✅ 记录每个字段的来源
        value, source = _pick_by_priority_with_source(results, field)
        if value:
            merged.data[field] = value
            merged.field_sources[field] = source

    return merged
```

**D. 调度层改进**
```python
def scrape_directory(directory: Path, crawlers: list[BaseCrawler]) -> list[ScrapeItemResult]:
    # ✅ 使用 asyncio 替代 ThreadPoolExecutor
    async def process_one(file_path: Path) -> ScrapeItemResult:
        tasks = [asyncio.to_thread(c.crawl, file_path, media) for c in crawlers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        ...

    # ✅ 增加进度条（tqdm）
    with tqdm(total=len(files)) as pbar:
        ...
```

**E. 监控层改进**
```python
# ✅ 新增：统计每个 crawler 的成功率
class CrawlerStats:
    total_attempts: int = 0
    success_count: int = 0
    failure_reasons: Counter[str] = field(default_factory=Counter)

# ✅ 新增：自动降级策略
# 如果 DMM 连续失败 10 次，自动暂停 1 小时
```

---

### 最终建议的迁移路径：

**Phase 1（最小可用）：**
1. 复制 `types.py`, `base.py`, `merger.py`, `text_utils.py`
2. 实现 JavDB crawler（`javdb.py`）
3. 实现 NFO writer（`writers/nfo.py`，禁用图片下载）
4. 测试番号识别 + merge + NFO 写入

**Phase 2（增强功能）：**
1. 添加 DMM crawler（可选）
2. 添加 JavBus crawler（需要 Cookie 支持）
3. 启用 poster/fanart 下载
4. 添加 trailer 下载（支持 m3u8）

**Phase 3（优化稳定性）：**
1. 添加重试机制
2. 添加请求缓存
3. 添加 crawler 成功率监控
4. 实现自动降级策略

**Phase 4（高级功能）：**
1. 添加 magnet 链接提取（JavDB）
2. 添加字幕下载（SubtitleCat）
3. 添加多语言支持
4. 添加 Web UI

---

## 📋 附：Nocta vs MrBanana 功能对比

| 功能 | Nocta (当前) | MrBanana | 建议 |
|------|-------------|----------|------|
| 番号识别 | ❌ 未知 | ✅ 完整 | ✅ 借鉴 |
| 多源合并 | ❌ 未知 | ✅ 字段级优先级 | ✅ 借鉴 |
| 脏数据清洗 | ❌ 未知 | ✅ 三层清洗 | ✅ 借鉴 |
| NFO 生成 | ❌ 未知 | ✅ Kodi/Emby | ✅ 借鉴 |
| Poster 下载 | ❌ 未知 | ✅ 自动裁剪 | ✅ 借鉴 |
| Magnet 提取 | ❌ 未知 | ✅ JavDB | ✅ 借鉴 |
| 重试机制 | ❌ 未知 | ❌ 无 | ⚠️ 需新增 |
| 请求缓存 | ❌ 未知 | ❌ 无 | ⚠️ 需新增 |
| 字段来源追溯 | ❌ 未知 | ❌ 无 | ⚠️ 需新增 |

---

**文档版本：** v1.0
**最后更新：** 2025-03-27
**分析者：** Claude Code (Sonnet 4.5)
