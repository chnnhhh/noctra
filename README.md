# Noctra Phase 1 交付文档

## 已完成内容

## 运行与部署

统一的环境配置和脚本工作流见 `docs/runtime-workflow.md`。
本地启动说明见 `docs/local-startup.md`。
推荐优先使用：

```bash
./start.sh
NOCTRA_PROFILE=local ./scripts/start.sh
NOCTRA_PROFILE=local ./scripts/status.sh
NOCTRA_PROFILE=local ./scripts/stop.sh
./scripts/deploy.sh nas
```

### 核心功能
1. ✅ Web 服务（FastAPI + SQLite + 原生 HTML/Alpine.js）
2. ✅ Docker 部署支持
3. ✅ 目录扫描（递归遍历，跳过 dist）
4. ✅ JAV 番号识别（支持主流格式）
5. ✅ 整理结果预览
6. ✅ 用户确认后执行整理
7. ✅ 历史记录与幂等
8. ✅ Web 前端界面

### 文档与测试
1. ✅ 设计文档：`docs/phase1-design.md`
2. ✅ 测试报告：`docs/phase1-test.md`
3. ✅ 验证报告：`docs/phase1-validation.md`
4. ✅ 交付文档：本文档

---

## 主要文件清单

```
noctra/
├── app/
│   ├── __init__.py           # 包初始化
│   ├── main.py              # FastAPI 入口和路由
│   ├── models.py            # Pydantic 数据模型
│   ├── scanner.py           # 扫描和识别逻辑
│   └── organizer.py         # 整理逻辑
├── static/
│   └── index.html          # Web 前端页面
├── tests/
│   ├── __init__.py         # 测试包初始化
│   └── test_scanner.py     # 核心测试
├── docs/
│   ├── phase1-design.md     # 设计文档
│   ├── phase1-test.md      # 测试报告
│   ├── phase1-validation.md # 验证报告
│   └── phase1-delivery.md  # 本文档
├── test_data/
│   ├── source/             # 测试源目录
│   │   └── videos/
│   │       ├── SSIS-123.mp4
│   │       ├── ABP-456-C.mkv
│   │       ├── FC2-PPV-1234567.mp4
│   │       └── SSIS-456_字幕版.mp4
│   └── dist/              # 测试目标目录
├── Dockerfile             # Docker 镜像构建文件
├── docker-compose.yml     # Docker Compose 配置
├── requirements.txt       # Python 依赖
└── README.md             # 本文档
```

---

## 启动方式

### 方式一：本地开发启动

```bash
# 进入项目目录
cd /Users/liujiejian/workspace/repos/noctra

# 设置环境变量
export SOURCE_DIR=/path/to/source
export DIST_DIR=/path/to/dist
export DB_PATH=/path/to/noctra.db

# 安装依赖
pip3 install -r requirements.txt

# 启动服务
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8888
```

访问：`http://localhost:8888`

### 方式二：Docker 启动

**1. 构建镜像：**
```bash
cd /Users/liujiejian/workspace/repos/noctra
docker build -t noctra:latest .
```

**2. 创建 docker-compose.yml 或直接运行：**

使用 docker-compose：
```bash
# 复制 docker-compose.yml 到本地，修改挂载路径
cp docker-compose.yml ~/noctra-docker-compose.yml

# 启动
docker-compose -f ~/noctra-docker-compose.yml up -d
```

使用 docker run：
```bash
docker run -d \
  --name noctra \
  -p 8888:8888 \
  -v /path/to/source:/source \
  -v /path/to/dist:/dist \
  -v ~/noctra-data:/app/data \
  -e SOURCE_DIR=/source \
  -e DIST_DIR=/dist \
  -e DB_PATH=/app/data/noctra.db \
  noctra:latest
```

访问：`http://<容器主机IP>:8888`

---

## 测试方式

### 运行单元测试

```bash
cd /Users/liujiejian/workspace/repos/noctra
python3 -m pytest tests/test_scanner.py -v
```

### 测试 API

```bash
# 健康检查
curl http://localhost:8888/api/health

# 扫描文件
curl http://localhost:8888/api/scan

# 查看历史
curl http://localhost:8888/api/history

# 执行整理
curl -X POST http://localhost:8888/api/organize \
  -H "Content-Type: application/json" \
  -d '{"file_ids": [1, 2, 3]}'
```

---

## API 文档

服务启动后，访问 Swagger 文档：
```
http://localhost:8888/docs
```

访问 ReDoc 文档：
```
http://localhost:8888/redoc
```

---

## 当前限制

### 功能限制
1. **番号识别范围**：只支持字母/数字开头、连字符分隔的格式，不支持纯数字、无连字符等极端情况
2. **文件重命名**：一期不做复杂重命名，只保留原文件名，目录名使用标准番号
3. **撤销操作**：不支持撤销，已移动的文件需要手动恢复
4. **并发安全**：未做多进程并发保护，建议单用户使用
5. **大文件支持**：未做分片上传等优化，超大文件可能需要更长处理时间

### 技术限制
1. **数据库**：使用 SQLite，不支持高并发写入
2. **前端**：使用原生 JavaScript，无构建流程，大型项目可升级到 Vue/React
3. **部署**：当前配置为单容器部署，未做负载均衡和高可用

---

## 环境变量说明

| 变量名 | 默认值 | 说明 |
|-------|-------|------|
| `SOURCE_DIR` | `/source` | 源目录，存放待整理的视频文件 |
| `DIST_DIR` | `/dist` | 目标目录，整理后的文件存放位置 |
| `DB_PATH` | `/app/data/noctra.db` | SQLite 数据库文件路径 |

---

## 端口说明

- **Web 服务端口**：`8888`（可配置）
- **内部通信**：无

---

## 日志与调试

### Docker 日志
```bash
docker logs -f noctra
```

### 本地运行日志
本地运行时，日志直接输出到 stdout/stderr。

### 数据库查看
```bash
sqlite3 /path/to/noctra.db

# 查看所有文件
SELECT * FROM files ORDER BY id DESC;

# 查看已处理文件
SELECT * FROM files WHERE status = 'processed';
```

---

## 下一期建议

### Phase 2 功能规划

1. **刮削功能**
   - 集成第三方 API（如 JavDB、DMM）
   - 获取作品信息：封面、标题、演员、发布日期等
   - 生成 NFO 文件（Emby 格式）

2. **元数据管理**
   - 下载封面和 fanart
   - 支持手动编辑元数据
   - 元数据缓存策略

3. **字幕支持**
   - 字幕文件识别和关联
   - 字幕下载（集成字幕站）
   - 字幕重命名和整理

4. **UI/UX 改进**
   - 美化界面，使用 Vue3 + Element Plus
   - 添加图片预览（封面图）
   - 进度条显示
   - 批量操作优化

5. **高级功能**
   - 撤销操作（记录移动历史）
   - 文件重命名规则配置
   - 多级分类（按演员、工作室、发布日期等）
   - 搜索和筛选

6. **部署优化**
   - 多容器部署（Web + Worker）
   - 数据库迁移到 PostgreSQL/MySQL
   - Redis 缓存
   - 监控和告警

### 技术改进
- 从原生 JS 迁移到 Vue3
- 添加单元测试覆盖率报告
- 集成 CI/CD
- API 版本管理

---

## 联系与反馈

如有问题或建议，请通过以下方式反馈：

- **项目仓库**：`git@gitee-cora:celoj/noctra.git`
- **Issue**：在 Gitee 提交 Issue

---

## 许可证

待定

---

## 致谢

感谢使用 Noctra JAV 整理工具！
