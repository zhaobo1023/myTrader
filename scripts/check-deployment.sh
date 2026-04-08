#!/bin/bash

# ============================================================
# myTrader 部署检查脚本
# 检查 API、前端、Nginx、Redis 是否正常运行
# 用法: ./scripts/check-deployment.sh
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_ok() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

echo "========== myTrader 部署检查 =========="
echo ""

# 1. 检查 systemd 服务
echo "1. 检查 systemd 服务状态..."

for service in mytrader-redis mytrader-api mytrader-web; do
    if systemctl is-active --quiet $service 2>/dev/null; then
        log_ok "$service is running"
    else
        log_error "$service is NOT running"
        echo "   启动命令: sudo systemctl start $service"
    fi
done
echo ""

# 2. 检查端口监听
echo "2. 检查端口监听..."

if lsof -i :6379 > /dev/null 2>&1; then
    log_ok "Redis is listening on port 6379"
else
    log_error "Redis is NOT listening on port 6379"
fi

if lsof -i :8000 > /dev/null 2>&1; then
    log_ok "API is listening on port 8000"
else
    log_error "API is NOT listening on port 8000"
fi

if lsof -i :3000 > /dev/null 2>&1; then
    log_ok "Frontend is listening on port 3000"
else
    log_warn "Frontend is NOT listening on port 3000 (might use different port)"
fi

if lsof -i :80 > /dev/null 2>&1; then
    log_ok "Nginx is listening on port 80"
else
    log_error "Nginx is NOT listening on port 80"
fi
echo ""

# 3. 检查 API 健康
echo "3. 检查 API 健康状态..."

if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    log_ok "API health check passed (direct)"
else
    log_error "API health check failed (direct)"
fi

if curl -sf http://localhost/health > /dev/null 2>&1; then
    log_ok "API health check passed (via Nginx)"
else
    log_error "API health check failed (via Nginx)"
fi
echo ""

# 4. 检查数据库连接
echo "4. 检查数据库连接..."

cd /opt/myTrader 2>/dev/null || cd .

if python3 -c "from config.db import get_connection; c = get_connection(); print('Connected')" 2>&1 | grep -q "Connected"; then
    log_ok "Database connection OK"
else
    log_warn "Database connection failed - check .env file"
fi
echo ""

# 5. 检查 Nginx 配置
echo "5. 检查 Nginx 配置..."

if sudo nginx -t > /dev/null 2>&1; then
    log_ok "Nginx configuration is valid"
else
    log_error "Nginx configuration has errors"
    sudo nginx -t
fi
echo ""

# 6. 检查磁盘空间
echo "6. 检查磁盘空间..."

disk_usage=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')

if [ "$disk_usage" -lt 80 ]; then
    log_ok "Disk usage: ${disk_usage}% (OK)"
else
    log_warn "Disk usage: ${disk_usage}% (HIGH)"
fi
echo ""

# 7. 检查进程内存
echo "7. 检查进程内存占用..."

api_mem=$(ps aux | grep uvicorn | grep -v grep | awk '{print $6}' | head -1)
if [ -n "$api_mem" ]; then
    log_ok "API memory usage: ${api_mem}KB"
else
    log_warn "Cannot determine API memory usage"
fi
echo ""

echo "========== 检查完成 =========="
echo ""
echo "访问应用:"
echo "  API docs:    http://localhost:8000/docs"
echo "  Frontend:    http://localhost/"
echo ""
echo "查看日志:"
echo "  API:         sudo journalctl -u mytrader-api -f"
echo "  Frontend:    sudo journalctl -u mytrader-web -f"
echo "  Nginx:       sudo tail -f /var/log/nginx/error.log"
