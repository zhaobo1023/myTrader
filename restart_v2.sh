#!/bin/bash
# myTrader 服务重启脚本 v2.0 (使用卷挂载 + 依赖缓存)
#
# 部署目录说明:
# - 宿主机代码: /root/app
# - 容器内挂载: /app (通过卷挂载映射)
# - 输出目录: /root/app/output
# - 依赖缓存: /root/app/.pip_cache

set -e

echo "========================================="
echo "myTrader 服务重启脚本 v2.0"
echo "========================================="

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

success() { echo -e "${GREEN}✓ $1${NC}"; }
warning() { echo -e "${YELLOW}⚠ $1${NC}"; }
error() { echo -e "${RED}✗ $1${NC}"; }

# 创建持久化依赖目录
mkdir -p /root/app/.pip_cache
mkdir -p /root/app/output
mkdir -p /root/app/nginx_logs

# 停止容器
echo ""
echo "1. 停止旧容器..."
docker stop mytrader-api mytrader-web mytrader-nginx-new 2>/dev/null || true
docker rm mytrader-api mytrader-web mytrader-nginx-new 2>/dev/null || true
success "旧容器已停止"

# 启动 API (使用卷挂载)
echo ""
echo "2. 启动 API 容器 (卷挂载模式)..."
docker run -d \
  --name mytrader-api \
  --network app_mytrader-network \
  -p 127.0.0.1:8000:8000 \
  -v /root/app:/app \
  -v /root/app/output:/app/output \
  -v /root/app/.pip_cache:/root/.local \
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

# 首次运行时安装依赖 (使用阿里云镜像)
echo "   检查/安装 Python 依赖..."
sleep 3
docker exec mytrader-api pip install -i https://mirrors.aliyun.com/pypi/simple/ --user -q \
  pyarrow yfinance akshare 2>/dev/null || true

# 等待 API 启动
echo "   等待 API 启动..."
for i in {1..30}; do
  if docker exec mytrader-api python -c "import fastapi; import uvicorn" 2>/dev/null; then
    success "API 容器已启动"
    break
  fi
  if [ $i -eq 30 ]; then
    error "API 启动超时"
    exit 1
  fi
  sleep 1
done

# 启动 Web
echo ""
echo "3. 启动 Web 容器..."
docker run -d \
  --name mytrader-web \
  --network app_mytrader-network \
  -p 127.0.0.1:3000:3000 \
  -e NEXT_PUBLIC_API_BASE_URL=http://123.56.3.1 \
  --restart unless-stopped \
  mytrader-web:latest

# 等待 Web 启动
echo "   等待 Web 启动..."
sleep 5
if docker exec mytrader-web test -f /app/.next/standalone 2>/dev/null || \
   docker exec mytrader-web test -d /app/.next 2>/dev/null; then
  success "Web 容器已启动"
else
  warning "Web 容器启动状态未知"
fi

# 启动 Nginx
echo ""
echo "4. 启动 Nginx 容器..."
if [ -f /root/app/nginx.conf ]; then
  docker run -d \
    --name mytrader-nginx-new \
    --network app_mytrader-network \
    -p 0.0.0.0:80:80 \
    -v /root/app/nginx.conf:/etc/nginx/conf.d/default.conf:ro \
    -v /root/app/nginx_logs:/var/log/nginx \
    --restart unless-stopped \
    nginx:alpine
  success "Nginx 容器已启动"
else
  warning "nginx.conf 不存在，跳过 Nginx 启动"
fi

# 等待服务启动
echo ""
echo "5. 等待服务就绪..."
sleep 10

# 检查状态
echo ""
echo "6. 检查服务状态..."
echo ""
echo "容器状态："
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "NAMES|mytrader" || echo "  警告：未找到运行的容器"

echo ""
echo "服务测试："

# 测试 API
API_HEALTH=$(curl -s http://localhost:8000/health 2>/dev/null || echo '{"status":"error"}')
if echo "$API_HEALTH" | grep -q '"status":"ok"'; then
  success "API 服务正常 (http://localhost:8000)"
else
  error "API 服务异常: $API_HEALTH"
  echo "   检查日志: docker logs mytrader-api | tail -50"
fi

# 测试前端
if curl -s http://localhost/ > /dev/null 2>&1; then
  success "前端服务正常 (http://localhost/)"
else
  error "前端服务无法访问 (http://localhost/)"
fi

echo ""
echo "========================================="
echo "部署信息:"
echo "  代码目录: /root/app"
echo "  输出目录: /root/app/output"
echo "  日志目录: /root/app/nginx_logs"
echo ""
echo "服务访问地址："
echo "  前端: http://123.56.3.1/"
echo "  API:  http://123.56.3.1/api/"
echo "  文档: http://123.56.3.1/docs"
echo ""
echo "常用命令："
echo "  查看日志: docker logs -f mytrader-api"
echo "  进入容器: docker exec -it mytrader-api bash"
echo "  重启服务: bash /root/app/restart_v2.sh"
echo "========================================="
