# Noctra NAS 部署配置

## 部署方案

### 方案一：使用 docker compose（推荐）

适用于支持 SSH 的 NAS（Synology、QNAP 等）

#### 步骤：

1. **SSH 登录 NAS**
   ```bash
   ssh user@nas-ip
   ```

2. **创建部署目录**
   ```bash
   mkdir -p ~/noctra
   cd ~/noctra
   ```

3. **准备代码和 profile**
   
   方式 A：从 GitHub 克隆
   ```bash
   git clone https://github.com/chnnhhh/noctra.git
   cd noctra
   ```

   方式 B：从本地部署脚本同步
   ```bash
   # 在本地执行
   ./scripts/deploy.sh nas
   ```

4. **配置 NAS profile**

   复制 `config/profiles/nas.env.example` 为 `config/profiles/nas.env`，至少确认以下变量：
   ```bash
   NOCTRA_SOURCE_DIR=/vol2/1000/porn/ChaosJAV
   NOCTRA_DIST_DIR=/vol2/1000/porn/OrderedJAV
   NOCTRA_DATA_DIR=/vol2/1000/appdata/noctra/data
   NOCTRA_REMOTE_HOST=nas-jieliu
   NOCTRA_REMOTE_PATH=/home/jieliu/noctra
   NOCTRA_REMOTE_DEPLOY_MODE=docker
   ```

5. **启动容器**
   ```bash
   set -a
   source config/profiles/nas.env
   set +a
   docker compose -f docker-compose.nas.yml up -d --build
   ```

6. **验证部署**
   ```bash
   # 查看容器状态
   docker compose ps
   
   # 查看日志
   docker compose logs -f
   ```

7. **访问 Web 界面**
   ```
   http://nas-ip:8000
   ```

---

### 方案二：使用 NAS Docker Web UI

适用于不熟悉命令行的用户

#### Synology (群晖 DSM)

1. 打开 **套件中心** → **Docker**
2. 点击 **注册表** → 搜索 `python:3.11-slim`
3. 或使用镜像构建（需要高级设置）
4. 点击 **映像** → 启动容器
5. 配置：
   - **端口**：8000 → 8000
   - **卷**：
     - `/volume1/videos` → `/source`
     - `/volume1/jav` → `/dist`
     - `/volume1/docker/noctra/data` → `/app/data`
   - **环境变量**：
     - `SOURCE_DIR=/source`
     - `DIST_DIR=/dist`
     - `DB_PATH=/app/data/noctra.db`

#### QNAP (威联通 QTS)

1. 打开 **Container Station**
2. 点击 **创建容器**
3. 配置：
   - **镜像**：`python:3.11-slim`
   - **挂载卷**：同上
   - **端口映射**：8000 → 8000

---

### 方案三：使用 GitHub Actions 自动部署

高级方案，代码推送到 GitHub 后自动部署到 NAS

#### 步骤：

1. 在 NAS 上创建 SSH 接收脚本
2. 配置 GitHub Actions workflow
3. 推送代码时自动部署

（需要额外配置，暂不推荐首次部署使用）

---

## NAS 配置示例

### Synology 群晖

```yaml
volumes:
  - /volume1/Downloads/videos:/source
  - /volume1/Media/JAV:/dist
     - /volume1/docker/noctra/data:/app/data
ports:
  - "8888:8000"  # 使用 8888 端口访问
```

### QNAP 威联通

```yaml
volumes:
  - /share/Multimedia/videos:/source
  - /share/Multimedia/jav:/dist
  - /share/Container/noctra/data:/app/data
ports:
  - "8888:8000"
```

### 通用 Linux NAS

```yaml
volumes:
  - /mnt/storage/videos:/source
  - /mnt/storage/jav:/dist
  - /opt/noctra/data:/app/data
ports:
  - "8888:8000"
```

---

## 目录权限

确保 NAS 上的目录有正确的读写权限：

```bash
# Synology
chmod -R 777 /volume1/videos
chmod -R 777 /volume1/Media/JAV

# QNAP
chmod -R 777 /share/Multimedia/videos
chmod -R 777 /share/Multimedia/jav
```

---

## 常见问题

### 1. 容器无法启动

**检查：**
```bash
docker-compose logs noctra
```

**可能原因：**
- 挂载路径不存在
- 权限不足
- 端口被占用

### 2. 无法访问 Web 界面

**检查：**
- 防火墙是否开放 8888 端口
- NAS IP 是否正确
- 容器是否正常运行

### 3. 扫描不到文件

**检查：**
- 挂载路径是否正确
- 目录下是否有文件
- 权限是否足够

---

## 优化配置

### 使用 NAS 的 CPU 架构优化镜像

如果 NAS 是 ARM 架构（如群晖），可以优化镜像：

```dockerfile
FROM python:3.11-slim

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建数据目录
RUN mkdir -p /app/data

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
```

---

## 快速启动脚本

创建 `start-noctra.sh`：

```bash
#!/bin/bash

# 快速启动 noctra

# 检查 docker-compose.yml
if [ ! -f docker-compose.yml ]; then
    echo "docker-compose.yml not found"
    exit 1
fi

# 启动容器
docker-compose up -d

# 等待服务启动
sleep 5

# 检查容器状态
docker-compose ps

echo ""
echo "Noctra started!"
echo "Access: http://$(hostname -I | awk '{print $1}'):8888"
```

使用：
```bash
chmod +x start-noctra.sh
./start-noctra.sh
```

---

## 备份与恢复

### 备份数据

```bash
# 备份数据库
cp ~/noctra/data/noctra.db ~/noctra/backup/noctra.db.$(date +%Y%m%d)
```

### 恢复数据

```bash
# 恢复数据库
cp ~/noctra/backup/noctra.db.20260324 ~/noctra/data/noctra.db

# 重启容器
docker-compose restart
```
