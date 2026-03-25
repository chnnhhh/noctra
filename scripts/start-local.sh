#!/bin/bash

# 启动 noctra 服务（本地 Mac 测试）

cd ~/workspace/repos/noctra

# 激活虚拟环境（如果存在）
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# 设置环境变量（本地测试）
export SOURCE_DIR=~/workspace/repos/noctra/test_data/source
export DIST_DIR=~/workspace/repos/noctra/test_data/dist
export DB_PATH=~/workspace/repos/noctra/noctra.db

# 创建日志目录
mkdir -p logs

# 杀掉旧进程
if [ -f "logs/server.pid" ]; then
    old_pid=$(cat logs/server.pid)
    if ps -p $old_pid > /dev/null 2>&1; then
        echo "Kill old process: $old_pid"
        kill $old_pid 2>/dev/null
        sleep 2
    fi
fi

# 启动服务
echo "================================"
echo "Noctra 正在启动..."
echo "源目录：$SOURCE_DIR"
echo "目标目录：$DIST_DIR"
echo "数据库：$DB_PATH"
echo "端口：8888"
echo "================================"

nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8888 > logs/server.log 2>&1 &
echo $! > logs/server.pid

# 等待服务启动
sleep 5

# 检查服务状态
if curl -s http://127.0.0.1:8888/api/health > /dev/null 2>&1; then
    echo "✓ Noctra 启动成功！"
    echo "访问地址：http://127.0.0.1:8888"
    echo "或：http://localhost:8888"
else
    echo "✗ Noctra 启动失败，请查看日志："
    echo "运行：tail -f logs/server.log"
fi

echo "================================"
echo "日志监控：tail -f logs/server.log"
echo "停止服务：./scripts/stop.sh"
echo "================================"
