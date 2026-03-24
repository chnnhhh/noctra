# Noctra Phase 1 交付文档

## 已完成内容

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
5. ✅ 交付文档副本：`README.md`

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
├── logs/                  # 日志目录（运行时生成）
├── Dockerfile             # Docker 镜像构建文件
├── docker-compose.yml     # Docker Compose 配置
├── requirements.txt       # Python 依赖
├── start.sh             # 快速启动脚本
└── README.md            # 项目说明（交付文档副本）
```

---

## 启动方式

### 方式一：使用启动脚本（推荐）

```bash
# 进入项目目录
cd /Users/liujiejian/workspace/repos/noctra

# 运行启动脚本
./start.sh
```

脚本会自动设置环境变量并启动服务，默认配置：
- 源目录：`/Users/liujiejian/workspace/repos/noctra/test_data/source`
- 目标目录：`/Users/liujiejian/workspace/repos/noctra/test_data/dist`
- 数据库：`/Users/liujiejian/workspace/repos/noctra/test_data/noctra.db`
- 端口：`8888`

访问：`http://localhost:8888`

### 方式二：手动启动

```bash
# 进入项目目录
cd /Users/liujiejian/workspace/repos/noctra

# 设置环境变量
export SOURCE_DIR=/path/to/source
export DIST_DIR=/path/to/dist
export DB_PATH=/path/to/noctra.db

# 安装依赖（首次运行）
pip3 install -r requirements.txt

# 启动服务
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8888
```

访问：`http://localhost:8888`

### 方式三：Docker 启动

**1. 构建镜像：**
```bash
cd /Users/liujiejian/workspace/repos/noctra
docker build -t noctra:latest .
```

**2. 使用 docker-compose：**

```bash
# 修改 docker-compose.yml 中的挂载路径
# 然后启动
docker-compose up -d
```

**3. 使用 docker run：**

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

## 网络访问

服务已绑定到 `0.0.0.0:8888`，可以在局域网内访问。

**访问方式：**
```
http://<本机IP>:8888
```

查看本机 IP：
```bash
# macOS
ifconfig | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}'

# 或使用系统设置查看网络配置
```

---

## 使用流程

1. **启动服务**
   ```bash
   ./start.sh
   ```

2. **访问 Web 界面**
   ```
   http://localhost:8888
   ```

3. **扫描目录**
   - 点击"📂 扫描目录"按钮
   - 系统会扫描 `/source` 目录下的所有视频文件
   - 显示识别结果（番号、原路径、目标路径、状态）

4. **选择要整理的文件**
   - 勾选要处理的文件（默认可全选所有已识别项）
   - 未识别文件默认不处理

5. **执行整理**
   - 点击"🚀 执行整理"按钮
   - 确认操作
   - 系统会将文件移动到 `/dist/番号/原文件名` 路径

6. **查看历史记录**
   - 点击右上角"历史记录"链接
   - 查看所有已处理的文件

---

## 测试方式

### 运行单元测试

```bash
cd /Users/liujiejian/workspace/repos/noctra
python3 -m pytest tests/test_scanner.py -v
```

### 测试番号识别

```bash
cd /Users/liujiejian/workspace/repos/noctra
python3 -c "from app.scanner import test_identify; test_identify()"
```

### 测试 API

```bash
# 健康检查
curl http://localhost:8888/api/health

# 扫描文件
curl http://localhost:8888/api/scan | python3 -m json.tool

# 查看历史
curl http://localhost:8888/api/history | python3 -m json.tool

# 执行整理（替换 file_ids）
curl -X POST http://localhost:8888/api/organize \
  -H "Content-Type: application/json" \
  -d '{"file_ids": [1, 2, 3]}' | python3 -m json.tool
```

### 访问 API 文档

启动服务后，访问以下地址：
- Swagger UI：`http://localhost:8888/docs`
- ReDoc：`http://localhost:8888/redoc`

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
2. **前端**：使用原生 JavaScript + Alpine.js，适合一期快速验证，后续可升级到 Vue/React
3. **部署**：当前配置为单容器部署，未做负载均衡和高可用

---

## 环境变量说明

| 变量名 | 默认值 | 说明 |
|-------|-------|------|
| `SOURCE_DIR` | `/source` | 源目录，存放待整理的视频文件 |
| `DIST_DIR` | `/dist` | 目标目录，整理后的文件存放位置 |
| `DB_PATH` | `/app/data/noctra.db` | SQLite 数据库文件路径 |

---

## 支持的番号格式

### 支持的格式（一期）
- `SSIS-123.mp4` → `SSIS-123`
- `ABP-456-C.mkv` → `ABP-456-C`
- `FC2-PPV-1234567.mp4` → `FC2-PPV-1234567`
- `ABC-123_字幕版.mp4` → `ABC-123`
- `ABC-123 [Uncensored].mp4` → `ABC-123`
- `SSIS-123字幕版.mp4` → `SSIS-123`

### 规则
1. 第一段必须包含字母（不能纯数字开头）
2. 支持多段字母数字组合（FC2-PPV）
3. 连字符 `-` 分隔各段
4. 最后一段必须是数字
5. 可选后缀：`-C`、`-UC`、`_字幕版` 等
6. 识别后统一转大写

### 不支持（二期考虑）
- 纯数字编号
- 无连字符格式
- 日文/中文命名
- 复杂的多段编号

---

## 支持的视频格式

- `.mp4`
- `.mkv`
- `.avi`
- `.wmv`
- `.mov`

其他文件格式会被自动跳过。

---

## 日志与调试

### 本地运行日志
```bash
# 查看实时日志（使用 start.sh）
tail -f logs/server.log

# 直接输出到控制台（手动启动）
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8888
```

### Docker 日志
```bash
docker logs -f noctra
```

### 数据库查看
```bash
sqlite3 /path/to/noctra.db

# 查看所有文件
SELECT * FROM files ORDER BY id DESC;

# 查看已处理文件
SELECT * FROM files WHERE status = 'processed';

# 查看未识别文件
SELECT * FROM files WHERE identified_code IS NULL;
```

---

## 故障排查

### 服务无法启动
1. 检查 Python 版本（需要 3.9+）
2. 确认依赖已安装：`pip3 install -r requirements.txt`
3. 检查端口是否被占用：`lsof -i :8888`
4. 查看日志：`cat logs/server.log`

### 扫描不到文件
1. 检查 `SOURCE_DIR` 环境变量是否正确
2. 确认目录挂载权限（Docker 环境）
3. 检查视频文件扩展名是否在白名单中

### 整理失败
1. 检查 `DIST_DIR` 是否有写权限
2. 确认磁盘空间充足
3. 查看服务日志获取详细错误信息

### 无法访问 Web 界面
1. 检查服务是否启动：`curl http://localhost:8888/api/health`
2. 检查防火墙设置
3. 确认服务绑定到 `0.0.0.0` 而不是 `127.0.0.1`

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
- 集成 CI/CD（GitHub Actions / Gitee Actions）
- API 版本管理

---

## 项目状态

### Phase 1
- ✅ 设计完成
- ✅ 实现完成
- ✅ 测试通过（19/19）
- ✅ 验证通过（8/8）
- ✅ 文档完成
- ✅ 服务已启动并可通过 Web 访问

### 当前服务信息
- **状态**：运行中
- **端口**：8888
- **访问地址**：`http://0.0.0.0:8888`
- **进程 ID**：83942
- **数据库**：`/Users/liujiejian/workspace/repos/noctra/test_data/noctra.db`

---

## 致谢

感谢使用 Noctra JAV 整理工具！

如有问题或建议，欢迎反馈。
