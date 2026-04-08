#!/bin/bash

# myTrader Deployment Script for ECS
# Functions: git pull + pip install + restart API and frontend
# Usage: ./scripts/deploy.sh

set -e

PROJECT_DIR="/opt/myTrader"
LOG_FILE="/var/log/mytrader/deploy.log"
ERROR_LOG="/var/log/mytrader/error.log"

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

error() {
    echo "[ERROR] $1" | tee -a "$ERROR_LOG" >&2
}

log "========== Deploy Start =========="

# Step 1: Enter project directory
cd "$PROJECT_DIR" || { error "Project directory does not exist: $PROJECT_DIR"; exit 1; }

# Step 2: Git update code
log "Pulling latest code..."
if ! git pull origin main >> "$LOG_FILE" 2>&1; then
    error "Git pull failed"
    exit 1
fi

# Step 3: Install/update dependencies
log "Installing Python dependencies..."
if ! pip install -q -r requirements.txt >> "$LOG_FILE" 2>&1; then
    error "pip install failed"
    exit 1
fi

# Step 4: Database migration
log "Running database migrations..."
if ! alembic upgrade head >> "$LOG_FILE" 2>&1; then
    error "Database migration failed"
    exit 1
fi

# Step 5: Restart API service (using systemd)
log "Restarting API service..."
if ! sudo systemctl restart mytrader-api >> "$LOG_FILE" 2>&1; then
    error "Failed to restart API service"
    exit 1
fi

# Step 6: Restart frontend (using systemd)
log "Restarting frontend service..."
if ! sudo systemctl restart mytrader-web >> "$LOG_FILE" 2>&1; then
    error "Failed to restart frontend service"
    exit 1
fi

# Step 7: Health check
log "Waiting for services to be ready..."
sleep 3

log "Checking API health..."
if ! curl -sf http://localhost:8000/health > /dev/null; then
    error "API health check failed"
    exit 1
fi

log "========== Deploy Success =========="
