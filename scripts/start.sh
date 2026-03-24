#!/bin/bash

# 启动 noctra 服务（飞牛 NAS）

cd ~/noctra

# 激活虚拟环境
source venv/bin/activate

# 设置环境变量
export SOURCE_DIR=/vol2/1000/porn/ChaosJAV
export DIST_DIR=/vol2/1000/porn/OrderedJAV
export DB_PATH=~/noctra/noctra.db

# 启动服务
nohup uvicorn app.main:app --host 0.0.0.0 --port 8888 > logs/server.log 2>&1 &
echo $! > logs/server.pid

echo "================================"
echo "Noctra 正在启动..."
echo "访问地址：http://192.168.7.8:8888"
echo "日志：tail -f ~/noctra/logs/server.log"
echo "================================"

# 等待服务启动
sleep 5

# 检查服务状态
if curl -s http://127.0.0.1:8888/api/health > /dev/null 2>&1; then
    echo "✓ Noctra 启动成功！"
else
    echo "✗ Noctra 启动失败，请查看日志："
    cat logs/server.log | tail -20
fi
