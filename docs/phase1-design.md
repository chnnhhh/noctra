# Noctra Phase 1 Design Document

## 产品目标

构建一个 JAV 资源整理工具的一期版本，实现"识别、预览、确认、整理"的核心闭环。

## 范围

### 包含
- Web 服务（FastAPI + 简单前端）
- Docker 部署
- 扫描 /source 目录，识别 JAV 番号
- 预览整理结果
- 用户确认后执行移动
- 历史记录与幂等支持

### 不包含
- 第三方 API 刮削
- NFO/封面/fanart 生成
- 字幕处理
- 复杂分类分层

## 核心流程

1. 用户启动容器，挂载 /source 和 /dist
2. 服务扫描 /source（跳过 /dist）
3. 识别视频文件中的 JAV 番号
4. 前端展示识别结果和预计处理路径
5. 用户选择要处理的文件
6. 执行移动操作
7. 更新历史记录

## 技术选型

### 后端
- **FastAPI**：快速、类型安全、自动文档
- **SQLite**：轻量、零配置、Docker 友好
- **Python 3.11+**：主流版本，稳定

### 前端
- **HTML + Alpine.js**：单文件、零构建、直接 CDN 引入
- **不使用框架**：一期避免过度工程化

### 部署
- **Docker + docker-compose**：标准化部署、易于扩展

## 目录结构

```
noctra/
├── app/
│   ├── main.py           # FastAPI 入口
│   ├── scanner.py        # 扫描和识别逻辑
│   ├── organizer.py      # 整理逻辑
│   └── models.py        # 数据模型
├── static/
│   └── index.html       # 前端页面
├── tests/
│   └── test_scanner.py  # 核心测试
├── docs/
│   ├── phase1-design.md
│   ├── phase1-validation.md
│   └── phase1-delivery.md
├── data/
│   └── noctra.db        # SQLite 数据库（运行时生成）
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## 数据模型

### files 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PRIMARY KEY | 自增 ID |
| original_path | TEXT UNIQUE | 原始路径 |
| identified_code | TEXT | 识别的番号（大写） |
| target_path | TEXT | 目标路径 |
| status | TEXT | 状态：pending/processed/skipped |
| file_size | INTEGER | 文件大小（用于幂等判断） |
| file_mtime | REAL | 文件修改时间（用于幂等判断） |
| created_at | TEXT | 创建时间 |
| updated_at | TEXT | 更新时间 |

## API 设计

### GET /api/scan
扫描 /source 目录，返回识别结果。

**请求参数：**
- `force_rescan`: bool（默认 false，强制重新扫描）

**返回：**
```json
{
  "total_files": 100,
  "identified": 80,
  "unidentified": 20,
  "pending": 70,
  "processed": 10,
  "files": [
    {
      "original_path": "/source/videos/SSIS-123.mp4",
      "identified_code": "SSIS-123",
      "target_path": "/dist/SSIS-123/SSIS-123.mp4",
      "status": "pending"
    }
  ]
}
```

### POST /api/organize
执行整理操作。

**请求：**
```json
{
  "file_ids": [1, 2, 3]
}
```

**返回：**
```json
{
  "success_count": 3,
  "failed_count": 0,
  "results": [
    {
      "file_id": 1,
      "original_path": "/source/videos/SSIS-123.mp4",
      "target_path": "/dist/SSIS-123/SSIS-123.mp4",
      "status": "moved"
    }
  ]
}
```

### GET /api/history
获取历史记录。

**返回：**
```json
{
  "total": 10,
  "processed": 8,
  "skipped": 2,
  "files": [...]
}
```

## 风险与边界

### 已知风险
1. **dist 在 source 内部**：扫描时必须跳过 /dist，避免死循环
2. **番号识别误判**：一期只支持主流格式，不做复杂规则
3. **文件移动失败**：磁盘满、权限不足等场景需要处理
4. **幂等判断**：依赖文件大小和 mtime，极端情况可能误判

### 边界条件
1. 视频文件扩展名白名单：`.mp4`, `.mkv`, `.avi`, `.wmv`, `.mov`
2. 番号识别只支持：`XXX-123` 格式（数字和字母组合）
3. 目标路径格式：`/dist/{番号}/{原文件名}`
4. 未识别文件默认跳过，不移动

## JAV 番号识别规则

### 支持格式（一期）
- `SSIS-123.mp4`
- `ABP-456-C.mp4`
- `FC2-PPV-1234567.mp4`
- `ABC-123_字幕版.mp4`
- `ABC-123 [Uncensored].mp4`

### 规则
1. 匹配字母开头，中间连字符 `-`，后接数字
2. 数字后可能接 `-C`、`-UC` 等后缀
3. 可能有空格、括号等修饰词
4. 识别后统一转大写

### 不支持（二期考虑）
- 纯数字编号
- 无连字符格式
- 日文/中文命名

## 幂等策略

1. 原路径 + 文件大小 + mtime 唯一标识文件
2. 如果数据库中已存在相同记录，且目标文件存在，标记为 `processed`
3. 历史记录不删除，允许重新扫描时复用

## Docker 部署设计

### 目录挂载
```yaml
volumes:
  - /path/to/source:/source
  - /path/to/dist:/dist
  - ./data:/app/data
```

### 端口
- `8000`: Web 服务端口

### 环境变量
- `SOURCE_DIR=/source`
- `DIST_DIR=/dist`
- `DB_PATH=/app/data/noctra.db`
