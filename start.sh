#!/bin/bash

# Noctra 启动脚本

# 设置默认环境变量
export SOURCE_DIR=${SOURCE_DIR:-/Users/liujiejian/workspace/repos/noctra/test_data/source}
export DIST_DIR=${DIST_DIR:-/Users/liujiejian/workspace/repos/noctra/test_data/dist}
export DB_PATH=${DB_PATH:-/Users/liujiejian/workspace/repos/noctra/test_data/noctra.db}

# 设置端口
PORT=${PORT:-8888}

# 进入项目目录
cd "$(dirname "$0")"

# 创建日志目录
mkdir -p logs

# 启动服务
echo "Starting Noctra JAV Organizer..."
echo "Source: $SOURCE_DIR"
echo "Dist: $DIST_DIR"
echo "DB: $DB_PATH"
echo "Port: $PORT"
echo "Web: http://localhost:$PORT"
echo ""

python3 -m uvicorn app.main:app --host 0.0.0.0 --port $PORT 2>&1 | tee logs/server.log
