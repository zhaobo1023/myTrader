#!/bin/bash
# myTrader 服务重启脚本

set -e

echo "========================================="
echo "myTrader 服务重启脚本"
echo "========================================="

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# 函数：打印成功信息
success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# 函数：打印警告信息
warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# 函数：打印错误信息
error() {
    echo -e "${RED}✗ $1${NC}"
}

# 停止容器
echo ""
echo "1. 停止旧容器..."
docker stop mytrader-api mytrader-web mytrader-nginx-new 2>/dev/null || true
docker rm mytrader-api mytrader-web mytrader-nginx-new 2>/dev/null || true
success "旧容器已停止"

# 启动 API
echo ""
echo "2. 启动 API 容器..."
docker run -d \
  --name mytrader-api \
  --network app_mytrader-network \
  -p 127.0.0.1:8000:8000 \
  -e DB_ENV=online \
  -e ONLINE_DB_HOST=host.docker.internal \
  -e ONLINE_DB_PORT=3306 \
  -e ONLINE_DB_USER=root \
  -e ONLINE_DB_PASSWORD='Hao1023@zb' \
  -e ONLINE_DB_NAME=trade \
  -e LOCAL_DB_HOST=host.docker.internal \
  -e LOCAL_DB_PASSWORD='Hao1023@zb' \
  -e REDIS_HOST=host.docker.internal \
  -e REDIS_PORT=6379 \
  -e REDIS_PASSWORD= \
  -e REDIS_DB=0 \
  --add-host=host.docker.internal:host-gateway \
  --restart unless-stopped \
  app-api:latest

# 安装依赖
echo "   安装 Python 依赖..."
docker exec mytrader-api pip install yfinance akshare -q 2>/dev/null || true
success "API 容器已启动"

# 启动 Web
echo ""
echo "3. 启动 Web 容器..."
docker run -d \
  --name mytrader-web \
  --network app_mytrader-network \
  -p 127.0.0.1:3000:3000 \
  -e NEXT_PUBLIC_API_URL=http://123.56.3.1 \
  --restart unless-stopped \
  mytrader-web:latest
success "Web 容器已启动"

# 启动 Nginx
echo ""
echo "4. 启动 Nginx 容器..."
docker run -d \
  --name mytrader-nginx-new \
  --network app_mytrader-network \
  -p 0.0.0.0:80:80 \
  -v /root/app/nginx.conf:/etc/nginx/conf.d/default.conf:ro \
  -v /root/app/nginx_logs:/var/log/nginx \
  --restart unless-stopped \
  nginx:alpine
success "Nginx 容器已启动"

# 等待服务启动
echo ""
echo "5. 等待服务启动..."
sleep 15

# 检查状态
echo ""
echo "6. 检查服务状态..."
echo ""

# 容器状态
echo "容器状态："
docker ps | grep mytrader --color=never || echo "  警告：未找到运行的容器"

echo ""
echo "服务测试："

# 测试 API
if curl -s http://localhost/health > /dev/null 2>&1; then
    API_STATUS=$(curl -s http://localhost/health | python3 -c "import sys,json; print(json.load(sys.stdin).get('status', 'unknown'))" 2>/dev/null)
    if [ "$API_STATUS" = "ok" ]; then
        success "API 服务正常 (http://123.56.3.1/health)"
    else
        warning "API 服务响应: $API_STATUS"
    fi
else
    error "API 服务无法访问"
fi

# 测试前端
if curl -s http://localhost/ > /dev/null 2>&1; then
    success "前端服务正常 (http://123.56.3.1/)"
else
    error "前端服务无法访问"
fi

echo ""
echo "========================================="
echo "服务访问地址："
echo "  前端: http://123.56.3.1/"
echo "  API:  http://123.56.3.1/api/"
echo "  文档: http://123.56.3.1/docs"
echo "========================================="
