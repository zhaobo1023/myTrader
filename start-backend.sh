#!/bin/bash
# 后端启动脚本 - Docker 方式

cd "$(dirname "$0")"

# 检查 Docker 是否运行
if ! docker info > /dev/null 2>&1; then
    echo "错误: Docker 未运行"
    exit 1
fi

# 启动 Redis（如果未启动）
if ! docker ps | grep -q "mytrader-redis"; then
    echo "启动 Redis..."
    docker run -d \
        --name mytrader-redis \
        --restart unless-stopped \
        -p 0.0.0.0:6379:6379 \
        redis:alpine
fi

# 启动 API 服务
echo "启动 FastAPI 服务..."
docker compose up -d api

echo ""
echo "后端启动完成!"
echo "API 地址: http://$(hostname -I | awk '{print $1}'):8000"
echo "健康检查: http://$(hostname -I | awk '{print $1}'):8000/health"
