# Noctra NAS 部署

## 推荐方式

优先使用 Docker Hub 预构建镜像部署，而不是在 NAS 本机 `build`。这样发布更快，也能避免 NAS 上 Python 依赖和镜像构建链路不稳定。

当前仓库已经支持两种 Docker 模式：

- `docker`: 在 NAS 上 `docker compose up -d --build`
- `docker-image`: 在 NAS 上 `docker compose pull && docker compose up -d`

NAS 推荐使用 `docker-image`。

## 本地 profile

复制 [config/profiles/nas.env.example](/Users/liujiejian/git/noctra/config/profiles/nas.env.example) 为 `config/profiles/nas.env`，至少确认这些变量：

```bash
NOCTRA_SOURCE_DIR=/vol2/1000/porn/ChaosJAV
NOCTRA_DIST_DIR=/vol2/1000/porn/OrderedJAV
NOCTRA_DATA_DIR=/vol1/1000/docker/noctra/data
NOCTRA_REMOTE_HOST=nas-jieliu
NOCTRA_REMOTE_PATH=/home/jieliu/noctra
NOCTRA_REMOTE_DEPLOY_MODE=docker-image
NOCTRA_REMOTE_COMPOSE_FILE=docker-compose.nas-image.yml
NOCTRA_DOCKER_IMAGE=acyua/noctra:latest
NOCTRA_HTTP_PROXY=
NOCTRA_HTTPS_PROXY=
```

## 部署命令

在本机执行：

```bash
./scripts/deploy.sh nas
```

部署脚本会同步代码、同步 `nas.env`，然后在 NAS 上拉取镜像并启动容器。

`docker-compose.nas-image.yml` 默认会同时启动：

- `noctra`: 主服务
- `noctra-watchtower`: 轮询 Docker Hub 并在镜像变化时自动更新 `noctra`

默认会通过 `NOCTRA_WATCHTOWER_SCHEDULE` 在每天凌晨 1 点检查一次新镜像。
如果需要改时间，使用 Watchtower 的 6 段 cron 表达式，例如：

```bash
NOCTRA_WATCHTOWER_SCHEDULE="0 0 1 * * *"
```

如果 NAS 上的 Noctra 容器本身也需要代理访问外网，请设置：

- `NOCTRA_HTTP_PROXY`
- `NOCTRA_HTTPS_PROXY`

如果 Watchtower 也需要代理访问 Docker Hub，再额外设置：

- `NOCTRA_WATCHTOWER_HTTP_PROXY`
- `NOCTRA_WATCHTOWER_HTTPS_PROXY`
- `NOCTRA_WATCHTOWER_NO_PROXY`

## Docker Hub 代理

`docker pull` 走的是 NAS 上的 Docker daemon，不是当前 shell。所以仅在命令前加 `HTTP_PROXY` 不够，必须给 Docker daemon 配代理。

你的代理可用地址：

```bash
http://192.168.7.2:7890
```

当前实测结果：

- 通过代理访问 `https://registry-1.docker.io/v2/` 正常
- 不走代理会超时
- `docker pull` 目前还不会自动使用这个代理

需要在 NAS 的 Docker 配置里加入：

```json
{
  "proxies": {
    "http-proxy": "http://192.168.7.2:7890",
    "https-proxy": "http://192.168.7.2:7890",
    "no-proxy": "127.0.0.1,localhost,192.168.7.0/24"
  }
}
```

如果 NAS 提供 Docker 图形界面，优先在图形界面里配置；否则修改 `/etc/docker/daemon.json` 后重启 Docker 服务。

## 验证

代理配置生效后，在 NAS 上检查：

```bash
docker info | sed -n '/HTTP Proxy/,+4p'
docker pull acyua/noctra:latest
curl http://127.0.0.1:8888/api/health
docker logs --tail 20 noctra-watchtower
```

健康检查返回 `status=ok` 即表示部署正常。
