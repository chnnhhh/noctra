# Noctra

Noctra 是一个用于本地/NAS 场景的 JAV 文件整理工具。它会扫描源目录、识别番号、预览目标路径，并在你确认后把文件整理到标准目录结构中。项目后端使用 FastAPI + SQLite，前端是无构建流程的静态页面壳 + Alpine.js/原生 JavaScript 资源，适合直接部署在个人机器或家用 NAS 上。

## 功能概览

- 递归扫描源目录，自动跳过目标目录和已排除项
- 识别常见 JAV 番号，并清洗文件名中的冗余文本
- 预览整理后的目标路径，避免直接盲搬
- 区分 `待处理`、`未识别`、`已存在`、`已处理`
- 扫描页工具栏统一承载筛选、已选状态、排序、每页和分页
- 支持单条或批量执行整理
- 批量整理面板会在任务创建后立即显示，完成后保留结果直到手动收起
- 记录历史状态，避免重复处理
- 支持本地运行、Docker 运行和 NAS 镜像部署
- 支持 Watchtower 自动拉取 Docker Hub 新镜像更新

## 整理规则

扫描后，Noctra 会按番号生成目标目录，例如：

```text
/source/北野未奈/MEYD-695 出轨xxx@北野未奈.mp4
-> /dist/MEYD-695/MEYD-695.mp4
```

规则上尽量保持简单：

- 识别出番号：进入整理流程
- 未识别：保留原文件，不自动处理
- 目标已存在：不重复覆盖
- 已处理：进入历史记录，可追踪结果

## 快速开始

### 1. 本地运行

推荐使用仓库自带脚本：

```bash
cd /Users/liujiejian/git/noctra
python3 -m pip install -r requirements.txt
./start.sh
```

默认会使用：

- `SOURCE_DIR=/Users/liujiejian/git/noctra/test_data/source`
- `DIST_DIR=/Users/liujiejian/git/noctra/test_data/dist`
- `DB_PATH=/Users/liujiejian/git/noctra/data/noctra.db`
- 访问地址：`http://127.0.0.1:4020`

如果你希望后台运行：

```bash
NOCTRA_PROFILE=local ./scripts/start.sh
NOCTRA_PROFILE=local ./scripts/status.sh
NOCTRA_PROFILE=local ./scripts/stop.sh
```

### 2. 自定义本地目录

复制 profile 示例：

```bash
cp config/profiles/local.env.example config/profiles/local.env
```

常改的变量有：

```bash
NOCTRA_SOURCE_DIR=/path/to/source
NOCTRA_DIST_DIR=/path/to/dist
NOCTRA_DATA_DIR=/path/to/data
NOCTRA_DB_PATH=/path/to/data/noctra.db
NOCTRA_PORT=4020
```

### 3. Docker 运行

直接运行镜像：

```bash
docker run -d \
  --name noctra \
  -p 4020:8000 \
  -v /path/to/source:/source \
  -v /path/to/dist:/dist \
  -v /path/to/data:/app/data \
  -e SOURCE_DIR=/source \
  -e DIST_DIR=/dist \
  -e DB_PATH=/app/data/noctra.db \
  acyua/noctra:latest
```

或者使用 Compose：

```bash
export NOCTRA_SOURCE_DIR=/path/to/source
export NOCTRA_DIST_DIR=/path/to/dist
export NOCTRA_DATA_DIR=/path/to/data
docker compose up --build
```

### 4. NAS 部署

NAS 推荐使用 Docker Hub 预构建镜像：

```bash
cp config/profiles/nas.env.example config/profiles/nas.env
./scripts/deploy.sh nas
```

默认会走 `docker-image` 模式，在 NAS 上执行：

- `docker compose pull`
- `docker compose up -d`

如果启用了 Watchtower，镜像更新后也可以自动拉取。

## 使用方式

典型流程如下：

1. 启动服务并打开 `http://127.0.0.1:4020`
2. 点击“扫描目录”
3. 检查扫描结果和目标路径预览
4. 对 `待处理` 文件执行整理
5. 在“历史”页查看已处理记录

状态说明：

- `待处理`：识别成功，等待执行整理
- `未识别`：未识别到番号，不自动处理
- `已存在`：目标文件已存在，不重复落盘
- `已处理`：文件已成功整理

## 目录结构

```text
app/                    FastAPI 后端代码
  main.py               API 路由、扫描/整理入口
  scanner.py            番号识别逻辑
  organizer.py          目标路径生成与文件移动
  models.py             Pydantic 模型
  statuses.py           状态判定与展示语义

static/                 无构建流程的前端静态资源
  index.html            页面骨架与 Alpine 挂载点
  css/index.css         页面样式
  js/*.js               状态、渲染与交互逻辑
tests/                  本地 smoke test 与解析测试
test_data/              示例 source/dist 数据
scripts/                启动、停止、部署脚本
config/profiles/        本地/NAS profile 示例
docs/                   本地运行、部署、设计说明
data/                   本地 SQLite 数据目录
```

## 运行时挂载目录

无论是本地 Docker 还是 NAS 镜像部署，核心目录语义都一致：

| 容器路径 | 说明 |
| --- | --- |
| `/source` | 待扫描的原始文件目录 |
| `/dist` | 整理后的输出目录 |
| `/app/data` | SQLite 数据库和运行时数据 |

## 常用命令

安装依赖：

```bash
python3 -m pip install -r requirements.txt
```

本地健康检查：

```bash
curl http://127.0.0.1:4020/api/health
```

本地 smoke test：

```bash
python3 tests/test_local.py
```

更细的测试：

```bash
python3 tests/test_integration.py
python3 -m pytest tests/test_scanner.py -v
```

## API 入口

- Swagger: `http://127.0.0.1:4020/docs`
- ReDoc: `http://127.0.0.1:4020/redoc`

## 相关文档

- [本地启动说明](/Users/liujiejian/git/noctra/docs/local-startup.md)
- [运行时工作流](/Users/liujiejian/git/noctra/docs/runtime-workflow.md)
- [NAS 部署说明](/Users/liujiejian/git/noctra/docs/nas-deployment.md)
- [Docker Hub Overview（中英双语）](/Users/liujiejian/git/noctra/docs/dockerhub-overview.md)

## Docker Hub

镜像仓库：

- `acyua/noctra:latest`

如果你要把仓库说明同步到 Docker Hub，可以直接使用：

- [docs/dockerhub-overview.md](/Users/liujiejian/git/noctra/docs/dockerhub-overview.md)
