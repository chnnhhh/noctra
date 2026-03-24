#!/bin/bash

# 停止 noctra 服务（飞牛 NAS）

cd ~/noctra

# 检查 PID 文件
if [ -f logs/server.pid ]; then
    PID=$(cat logs/server.pid)
    echo "================================"
    echo "停止 Noctra 服务..."
    echo "PID: $PID"
    echo "================================"
    
    # 终止进程
    kill $PID 2>/dev/null
    
    # 等待进程退出
    sleep 2
    
    # 确认进程已停止
    if ps -p $PID > /dev/null 2>&1; then
        echo "强制终止..."
        kill -9 $PID 2>/dev/null
    fi
    
    echo "✓ Noctra 已停止"
else
    echo "未找到 PID 文件，尝试查找进程..."
    PIDS=$(ps aux | grep 'uvicorn app.main:app' | grep -v grep | awk '{print $2}')
    if [ -n \"$PIDS\" ]; then
        echo "找到进程: $PIDS"
        kill $PIDS 2>/dev/null
        sleep 2
        echo "✓ Noctra 已停止"
    else
        echo "✗ 未找到运行中的 Noctra 进程"
    fi
fi
