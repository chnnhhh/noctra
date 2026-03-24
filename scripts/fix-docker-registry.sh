#!/bin/bash

# 修复 Docker 镜像源配置
# 在 NAS 上执行此脚本（需要 sudo）

echo "================================"
echo "修复 Docker 镜像源配置"
echo "================================"
echo ""

# 备份原配置
sudo cp /etc/docker/daemon.json /etc/docker/daemon.json.backup

# 创建新配置
sudo tee /etc/docker/daemon.json << 'EOF'
{
  "data-root": "/vol1/docker",
  "insecure-registries": ["127.0.0.1:19827"],
  "live-restore": true,
  "proxies": {},
  "registry-mirrors": ["https://registry.hub.docker.com"]
}
EOF

echo ""
echo "Docker 配置已更新！"
echo "================================"
echo ""

echo "重启 Docker 服务使配置生效："
echo "sudo systemctl restart docker"
echo ""

echo "================================"
echo "重启完成后，告诉我 'Docker 已重启'"
echo "我会继续部署 noctra"
echo "================================"
