#!/bin/bash

# myTrader Deployment Check Script
# Check if API, frontend, Nginx, and Redis are running correctly
# Usage: ./scripts/check-deployment.sh

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

echo "========== myTrader Deployment Check =========="
echo ""

# Step 1: Check systemd services
echo "1. Checking systemd service status..."

for service in mytrader-redis mytrader-api mytrader-web; do
    if systemctl is-active --quiet $service 2>/dev/null; then
        log_ok "$service is running"
    else
        log_error "$service is NOT running"
        echo "   Start with: sudo systemctl start $service"
    fi
done
echo ""

# Step 2: Check port listening
echo "2. Checking port listening..."

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

# Step 3: Check API health
echo "3. Checking API health..."

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

# Step 4: Check database connection
echo "4. Checking database connection..."

cd /opt/myTrader 2>/dev/null || cd .

if python3 -c "from config.db import get_connection; c = get_connection(); print('Connected')" 2>&1 | grep -q "Connected"; then
    log_ok "Database connection OK"
else
    log_warn "Database connection failed - check .env file"
fi
echo ""

# Step 5: Check Nginx configuration
echo "5. Checking Nginx configuration..."

if sudo nginx -t > /dev/null 2>&1; then
    log_ok "Nginx configuration is valid"
else
    log_error "Nginx configuration has errors"
    sudo nginx -t
fi
echo ""

# Step 6: Check disk space
echo "6. Checking disk space..."

disk_usage=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')

if [ "$disk_usage" -lt 80 ]; then
    log_ok "Disk usage: ${disk_usage}% (OK)"
else
    log_warn "Disk usage: ${disk_usage}% (HIGH)"
fi
echo ""

# Step 7: Check process memory
echo "7. Checking process memory usage..."

api_mem=$(ps aux | grep uvicorn | grep -v grep | awk '{print $6}' | head -1)
if [ -n "$api_mem" ]; then
    log_ok "API memory usage: ${api_mem}KB"
else
    log_warn "Cannot determine API memory usage"
fi
echo ""

echo "========== Check Complete =========="
echo ""
echo "Access application:"
echo "  API docs:    http://localhost:8000/docs"
echo "  Frontend:    http://localhost/"
echo ""
echo "View logs:"
echo "  API:         sudo journalctl -u mytrader-api -f"
echo "  Frontend:    sudo journalctl -u mytrader-web -f"
echo "  Nginx:       sudo tail -f /var/log/nginx/error.log"
