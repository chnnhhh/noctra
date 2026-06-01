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
  acyua/noctra:latest
```

If you keep the standard mount points above, you do not need to pass
`SOURCE_DIR`, `DIST_DIR`, or `DB_PATH` explicitly. The container defaults to:

- `SOURCE_DIR=/source`
- `DIST_DIR=/dist`
- `DB_PATH=/app/data/noctra.db`

### Proxy support for scraping

If your network can only reach metadata sources through a proxy, pass proxy
environment variables into the container:

```bash
-e HTTP_PROXY=http://192.168.7.2:7890 \
-e HTTPS_PROXY=http://192.168.7.2:7890 \
-e ALL_PROXY=http://192.168.7.2:7890 \
-e NO_PROXY=127.0.0.1,localhost
```

Notes:

- Include the URL scheme when possible, for example `http://192.168.7.2:7890`
- Proxy settings are used by official/DMM metadata requests, optional LLM requests, and artwork downloads
- If one exit node is unstable for DMM or maker sites, try Hong Kong or Taiwan nodes

Open:

```text
http://127.0.0.1:4020
```

### Storage diagnostics

Noctra always tries atomic `rename` first and falls back to `copy_delete` when
the current deployment layout cannot support it. You can inspect the effective
mode with:

```bash
curl http://127.0.0.1:4020/api/health
```

Look for `storage_diagnostic.mode`:

- `rename`: atomic rename is available
- `copy_delete`: the current deployment will copy then delete
- `unknown`: the probe could not complete

### Advanced same-filesystem optimization

If your input and output directories are on the same filesystem and you want
Docker to preserve atomic rename, mount their common parent once and point
`SOURCE_DIR` / `DIST_DIR` at subdirectories under that parent.

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
| `static/` | 无构建流程的前端静态资源（`index.html` + `css/js`） |
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
  acyua/noctra:latest
```

如果你沿用上面的标准挂载路径，其实不需要再额外传：

- `SOURCE_DIR`
- `DIST_DIR`
- `DB_PATH`

因为容器默认就是：

- `SOURCE_DIR=/source`
- `DIST_DIR=/dist`
- `DB_PATH=/app/data/noctra.db`

### 刮削代理支持

如果你的网络访问元数据源必须走代理，可以把代理环境变量一起传进容器：

```bash
-e HTTP_PROXY=http://192.168.7.2:7890 \
-e HTTPS_PROXY=http://192.168.7.2:7890 \
-e ALL_PROXY=http://192.168.7.2:7890 \
-e NO_PROXY=127.0.0.1,localhost
```

注意：

- 建议代理地址带上协议头，例如 `http://192.168.7.2:7890`
- 这些代理变量会同时用于官方/DMM 元数据请求、可选 LLM 请求和图片下载
- 如果某个出口节点访问 DMM 或厂商站不稳定，可以切换到香港或台湾节点重试

### 可选 LLM 抽取

刮削默认会按固定 URL 抓取官方/DMM 页面并本地解析。需要让模型辅助结构化抽取时，可额外传入：

```bash
-e NOCTRA_LLM_ENABLED=1 \
-e NOCTRA_LLM_BASE_URL=http://example.com:18082 \
-e NOCTRA_LLM_WIRE_API=responses \
-e NOCTRA_LLM_MODEL=gpt-5.4-mini \
-e NOCTRA_LLM_API_KEY=...
```

访问地址：

```text
http://127.0.0.1:4020
```

### 存储诊断

Noctra 会优先尝试原子 `rename`，如果当前部署方式不允许，就自动退化成 `copy_delete`。
你可以通过下面的接口查看当前容器实际探测到的模式：

```bash
curl http://127.0.0.1:4020/api/health
```

重点看返回里的 `storage_diagnostic.mode`：

- `rename`：当前部署支持原子重命名
- `copy_delete`：当前部署会走复制后删除
- `unknown`：本次探测没有成功完成

### 同盘优化（高级可选）

如果你明确知道输入目录和输出目录在同一个文件系统，并且想让 Docker 场景尽量命中原子 `rename`，可以把它们的共同父目录只挂载一次，再用 `SOURCE_DIR` / `DIST_DIR` 指向其中的子目录。
