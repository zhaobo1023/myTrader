#!/bin/bash

# myTrader ECS initialization script (one-click deployment)
# Run once on ECS to complete all initialization
# Usage: curl -fsSL https://raw.githubusercontent.com/zhaobo03/myTrader/main/scripts/init-ecs.sh | bash
# Or: ./scripts/init-ecs.sh

set -e

echo "========== myTrader ECS Initialization =========="

# Check if running as root
if [ "$EUID" -eq 0 ]; then
    echo "[ERROR] Do not run this script as root, use a regular user (e.g., ubuntu)"
    exit 1
fi

# Step 1: Update system packages
echo "[1/8] Updating system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    git curl wget \
    python3.11 python3.11-venv python3-pip \
    nodejs npm \
    nginx redis-server \
    build-essential

# Step 2: Create project directory
echo "[2/8] Creating project directory..."
if [ ! -d /opt/myTrader ]; then
    echo "Directory does not exist, cloning..."
    sudo mkdir -p /opt/myTrader
    sudo chown $(whoami) /opt/myTrader
    cd /opt
    git clone https://github.com/zhaobo03/myTrader.git
else
    echo "Directory exists, pulling..."
    cd /opt/myTrader
    git pull origin main || true
fi

cd /opt/myTrader

# Step 3: Create environment configuration
echo "[3/8] Creating environment configuration..."
if [ ! -f .env ]; then
    cp .env.example .env || {
        echo "[WARN] .env.example not found, creating minimal config..."
        cat > .env << 'EOF'
DB_ENV=online
ONLINE_DB_HOST=your-mysql-host
ONLINE_DB_PORT=3306
ONLINE_DB_USER=root
ONLINE_DB_PASSWORD=your-password
ONLINE_DB_NAME=trade

REDIS_HOST=127.0.0.1
REDIS_PORT=6379

JWT_SECRET_KEY=your-secret-key-min-32-chars
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=30
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

LOG_LEVEL=INFO
APP_VERSION=0.1.0
EOF
    }
    echo "[WARN] Please edit /opt/myTrader/.env to configure database"
fi

# Step 4: Install Python dependencies
echo "[4/8] Installing Python dependencies..."
pip install -q -r requirements.txt || {
    echo "[WARN] pip install failed, trying to upgrade pip..."
    pip install --upgrade pip setuptools wheel -q
    pip install -q -r requirements.txt
}

# Step 5: Build frontend
echo "[5/8] Building frontend..."
cd /opt/myTrader/web
npm ci -q || npm install -q
npm run build

cd /opt/myTrader

# Step 6: Install systemd services
echo "[6/8] Installing systemd services..."
sudo cp scripts/mytrader-api.service /etc/systemd/system/
sudo cp scripts/mytrader-web.service /etc/systemd/system/
sudo cp scripts/mytrader-redis.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable mytrader-redis mytrader-api mytrader-web

# Step 7: Configure Nginx
echo "[7/8] Configuring Nginx..."
sudo cp nginx.conf /etc/nginx/conf.d/mytrader.conf
sudo rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl restart nginx

# Step 8: Create log directory
echo "[8/8] Creating log directory..."
sudo mkdir -p /var/log/mytrader
sudo chown -R ubuntu:ubuntu /var/log/mytrader

echo ""
echo "========== Initialization Complete =========="
echo ""
echo "Next steps:"
echo ""
echo "1. Edit environment configuration:"
echo "   vi /opt/myTrader/.env"
echo ""
echo "2. Run database migration:"
echo "   cd /opt/myTrader"
echo "   alembic upgrade head"
echo ""
echo "3. Start services:"
echo "   sudo systemctl start mytrader-redis"
echo "   sudo systemctl start mytrader-api"
echo "   sudo systemctl start mytrader-web"
echo ""
echo "4. Check deployment status:"
echo "   sudo systemctl status mytrader-api"
echo "   curl http://localhost:8000/health"
echo ""
echo "5. View logs:"
echo "   sudo journalctl -u mytrader-api -f"
echo ""
