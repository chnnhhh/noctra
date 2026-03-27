# Noctra 项目概览

## 1. 项目目标

Noctra 是一个面向本地机器和 NAS 场景的 JAV 文件整理工具，核心目标是把“混乱目录中的视频文件”整理成“可预览、可确认、可追踪”的标准结构。它不是全自动黑盒搬运器，而是一个强调可见性和可控性的整理工作台。

当前主要服务的流程是：

1. 扫描 `source` 目录中的视频文件
2. 识别番号并生成目标路径预览
3. 用户勾选确认
4. 批量执行整理
5. 在历史页回看结果

## 2. 一期能力边界

### 已包含

- 递归扫描 source 目录
- JAV 番号识别
- 目标路径预览
- 扫描页分页、排序、跨页勾选
- 扫描页统一 toolbar（筛选、已选状态、排序、每页、分页）
- 批量整理任务与稳定进度反馈
- 历史记录页
- 本地运行、Docker 运行、NAS 镜像部署

### 暂不包含

- 元数据刮削
- NFO / poster / fanart 生成
- 字幕文件单独处理
- 多层分类策略
- 复杂媒体库规则引擎

## 3. 当前技术栈与部署方式

### 后端

- Python 3
- FastAPI
- aiosqlite / SQLite

### 前端

- 页面壳：`/Users/liujiejian/git/noctra/static/index.html`
- 交互逻辑：`/Users/liujiejian/git/noctra/static/js/*.js`
- 样式：`/Users/liujiejian/git/noctra/static/css/index.css`
- Alpine.js 风格的数据驱动交互
- 无构建流程，直接服务静态资源

### 部署

- 本地开发：`./start.sh`
- Docker 镜像：`acyua/noctra:latest`
- NAS 部署：`docker-image` 模式 + Watchtower 自动更新
- 本地默认端口：`4020`

说明：历史文档里仍能看到 `8888` 或 `8000`，这些属于旧配置；当前本地开发默认端口是 `4020`。

## 4. source / dist 挂载语义

Noctra 当前围绕 3 个核心路径工作：

- `SOURCE_DIR`：待扫描的原始文件目录
- `DIST_DIR`：整理后的输出目录
- `DB_PATH`：SQLite 数据库路径

### 本地默认值

- `test_data/source`
- `test_data/dist`
- `data/noctra.db`

### Docker / NAS 典型挂载

- `/source` -> 原始文件目录
- `/dist` -> 整理结果目录
- `/app/data` -> 数据库和运行时数据

## 5. 扫描与整理规则

### 扫描规则

- 递归扫描 `SOURCE_DIR`
- 跳过 `DIST_DIR`，避免把输出再次扫回来
- 仅处理视频扩展名：`.mp4`、`.mkv`、`.avi`、`.wmv`、`.mov`

### 状态规则

后端内部状态和前端显示语义存在一层映射：

- `pending` -> 待处理
- `target_exists` -> 已存在
- `processed` -> 已处理
- `skipped` -> 未识别

`skipped` 是内部状态名，前端与产品文案统一显示为“未识别”。

### 整理输出规则

目录始终使用纯番号：

```text
/dist/{番号}/
```

文件名会被规范成：

```text
{番号}{规范化后缀}{扩展名}
```

例如：

```text
/source/北野未奈/MEYD-695 出轨xxx@北野未奈.mp4
-> /dist/MEYD-695/MEYD-695.mp4
```

## 6. JAV 番号识别与 suffix 规范化原则

当前实现分成两层：

### 识别层

`scanner.py` 负责识别“纯番号”：

- 去掉 `-C`、`C`、`-UC`、`UC`
- 去掉 `字幕版`、`字幕`
- 去掉 `[Uncensored]` 这类展示性标记
- 返回统一大写的纯番号

### 文件名生成层

`organizer.py` 负责保留“文件语义后缀”并清洗冗余文本：

- 字幕类统一规范成 `-C`
- 无修正 / 无码类统一规范成 `-UC`
- `CH` / `ch` 也会归一成 `-C`
- 去掉番号后的中文、日文、演员名、编码标记等冗余文本

示例：

```text
FPRE-123_字幕版.mp4 -> FPRE-123-C.mp4
HMN-439-C.H265.mp4 -> HMN-439-C.mp4
CEMD-721ch.mp4 -> CEMD-721-C.mp4
HMN-112-C マジxxx痴 北野未奈.mp4 -> HMN-112-C.mp4
```

## 7. 当前值得记住的约束

- 项目强调“先预览，再整理”，不是后台静默自动整理
- 批量整理已经改成批任务模型，不再是简单 loading
- 扫描页工具栏已经统一为单一布局系统，不再把分页拆成上下两套入口
- 历史页是记录页，不应继续沿用扫描页的大表格节奏
- 当前品牌命名在仓库和代码中使用 `Noctra`

### 待确认

- 用户口头偶尔会说 `Nocta`，但代码、仓库、镜像和页面标题当前都使用 `Noctra`。如果未来要统一品牌命名，需要一次性确认并批量收敛。
