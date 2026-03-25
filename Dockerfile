ARG PYTHON_BASE_IMAGE=python:3.11-slim
FROM ${PYTHON_BASE_IMAGE}

WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

ARG NOCTRA_PIP_INDEX_URL=
ARG NOCTRA_PIP_TRUSTED_HOST=

# 安装 Python 依赖
RUN if [ -n "$NOCTRA_PIP_INDEX_URL" ]; then \
      PIP_INDEX_URL="$NOCTRA_PIP_INDEX_URL" PIP_TRUSTED_HOST="$NOCTRA_PIP_TRUSTED_HOST" \
      pip install --no-cache-dir -r requirements.txt; \
    else \
      pip install --no-cache-dir -r requirements.txt; \
    fi

# 复制应用代码
COPY . .

# 创建数据目录
RUN mkdir -p /app/data

# 暴露端口
EXPOSE 8000

# 启动命令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
