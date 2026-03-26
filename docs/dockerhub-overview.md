# Noctra Docker Hub Repository Overview

## English

Noctra is a self-hosted JAV file organizer for local machines and NAS deployments. It scans a source directory, detects video codes, previews the target path, and only moves files after confirmation.

### What the container does

- Recursively scans `/source`
- Generates organized output under `/dist`
- Stores scan history and processing state in `/app/data/noctra.db`
- Exposes the web UI and API on port `8000` inside the container

### Runtime directories

| Path | Meaning |
| --- | --- |
| `/source` | Input directory. Put unsorted media files here. |
| `/dist` | Output directory. Organized files are written here. |
| `/app/data` | Persistent data directory. Stores SQLite and runtime state. |

### Repository directories

| Path | Meaning |
| --- | --- |
| `app/` | FastAPI backend: scan, organize, API routes, models. |
| `static/` | No-build frontend UI (`index.html`). |
| `scripts/` | Local startup, status, stop, and NAS deployment scripts. |
| `config/profiles/` | Example env profiles for local and NAS setups. |
| `tests/` | Smoke tests and parser/organizer coverage. |
| `test_data/` | Sample source/dist trees for local verification. |
| `docs/` | Local startup, deployment, and design notes. |

### Quick run

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

Open:

```text
http://127.0.0.1:4020
```

## 中文

Noctra 是一个适合本地电脑和 NAS 使用的 JAV 文件整理工具。它会扫描源目录、识别番号、预览目标路径，并在用户确认后执行整理。

### 容器的作用

- 递归扫描 `/source`
- 在 `/dist` 下生成整理后的目录结构
- 在 `/app/data/noctra.db` 中保存扫描历史和处理状态
- 容器内部通过 `8000` 端口提供 Web UI 和 API

### 运行时目录说明

| 路径 | 含义 |
| --- | --- |
| `/source` | 输入目录，存放待整理的原始文件 |
| `/dist` | 输出目录，整理后的文件写入这里 |
| `/app/data` | 持久化数据目录，保存 SQLite 和运行时状态 |

### 仓库目录说明

| 路径 | 含义 |
| --- | --- |
| `app/` | FastAPI 后端代码，包含扫描、整理、接口和模型 |
| `static/` | 无构建流程的前端页面（`index.html`） |
| `scripts/` | 本地启动、状态查看、停止、NAS 部署脚本 |
| `config/profiles/` | 本地和 NAS 的环境变量示例 |
| `tests/` | smoke test 和识别/整理逻辑测试 |
| `test_data/` | 本地验证用的示例 source/dist 树 |
| `docs/` | 本地运行、部署、设计等说明文档 |

### 快速运行

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

访问地址：

```text
http://127.0.0.1:4020
```
