#!/bin/bash

# ============================================================
# myTrader 部署脚本 (ECS 一键部署)
# 功能: git pull + pip install + 重启 API 和前端
# 用法: ./scripts/deploy.sh
# ============================================================

set -e

PROJECT_DIR="/opt/myTrader"
LOG_FILE="/var/log/mytrader/deploy.log"
ERROR_LOG="/var/log/mytrader/error.log"

# 确保日志目录存在
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

error() {
    echo "[ERROR] $1" | tee -a "$ERROR_LOG" >&2
}

log "========== Deploy Start =========="

# 1. 进入项目目录
cd "$PROJECT_DIR" || { error "项目目录不存在: $PROJECT_DIR"; exit 1; }

# 2. Git 更新代码
log "Pulling latest code..."
if ! git pull origin main >> "$LOG_FILE" 2>&1; then
    error "Git pull failed"
    exit 1
fi

# 3. 安装/更新依赖（仅安装新增的）
log "Installing Python dependencies..."
if ! pip install -q -r requirements.txt >> "$LOG_FILE" 2>&1; then
    error "pip install failed"
    exit 1
fi

# 4. 数据库迁移
log "Running database migrations..."
if ! alembic upgrade head >> "$LOG_FILE" 2>&1; then
    error "Database migration failed"
    exit 1
fi

# 5. 重启 API 服务 (使用 systemd)
log "Restarting API service..."
if ! sudo systemctl restart mytrader-api >> "$LOG_FILE" 2>&1; then
    error "Failed to restart API service"
    exit 1
fi

# 6. 重启前端 (如果使用 Next.js，使用 PM2 或 systemd)
log "Restarting frontend service..."
if ! sudo systemctl restart mytrader-web >> "$LOG_FILE" 2>&1; then
    error "Failed to restart frontend service"
    exit 1
fi

# 7. 健康检查
log "Waiting for services to be ready..."
sleep 3

log "Checking API health..."
if ! curl -sf http://localhost:8000/health > /dev/null; then
    error "API health check failed"
    exit 1
fi

log "========== Deploy Success =========="
