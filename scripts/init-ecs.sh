#!/bin/bash

# ============================================================
# myTrader ECS 初始化脚本（一键部署）
# 该脚本在 ECS 上执行一次，完成所有初始化
# 用法: curl -fsSL https://raw.githubusercontent.com/zhaobo03/myTrader/main/scripts/init-ecs.sh | bash
# 或者: ./scripts/init-ecs.sh
# ============================================================

set -e

echo "========== myTrader ECS 初始化 =========="

# 检查是否为 root
if [ "$EUID" -eq 0 ]; then
    echo "[ERROR] 请不要以 root 身份运行此脚本，使用普通用户（如 ubuntu）"
    exit 1
fi

# 1. 更新系统包
echo "[1/8] 更新系统包..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    git curl wget \
    python3.11 python3.11-venv python3-pip \
    nodejs npm \
    nginx redis-server \
    build-essential

# 2. 创建项目目录
echo "[2/8] 创建项目目录..."
if [ ! -d /opt/myTrader ]; then
    echo "目录不存在，执行 git clone..."
    sudo mkdir -p /opt/myTrader
    sudo chown $(whoami) /opt/myTrader
    cd /opt
    git clone https://github.com/zhaobo03/myTrader.git
else
    echo "目录已存在，执行 git pull..."
    cd /opt/myTrader
    git pull origin main || true
fi

cd /opt/myTrader

# 3. 创建环境配置
echo "[3/8] 创建环境配置文件..."
if [ ! -f .env ]; then
    cp .env.example .env || {
        echo "[WARN] .env.example 不存在，创建最小配置..."
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
    echo "[WARN] 请编辑 /opt/myTrader/.env 文件，填写数据库配置"
fi

# 4. 安装 Python 依赖
echo "[4/8] 安装 Python 依赖..."
pip install -q -r requirements.txt || {
    echo "[WARN] pip install 失败，尝试升级 pip..."
    pip install --upgrade pip setuptools wheel -q
    pip install -q -r requirements.txt
}

# 5. 构建前端
echo "[5/8] 构建前端..."
cd /opt/myTrader/web
npm ci -q || npm install -q
npm run build

cd /opt/myTrader

# 6. 安装 systemd 服务
echo "[6/8] 安装 systemd 服务..."
sudo cp scripts/mytrader-api.service /etc/systemd/system/
sudo cp scripts/mytrader-web.service /etc/systemd/system/
sudo cp scripts/mytrader-redis.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable mytrader-redis mytrader-api mytrader-web

# 7. 配置 Nginx
echo "[7/8] 配置 Nginx..."
sudo cp nginx.conf /etc/nginx/conf.d/mytrader.conf
sudo rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
sudo nginx -t
sudo systemctl enable nginx
sudo systemctl restart nginx

# 8. 创建日志目录
echo "[8/8] 创建日志目录..."
sudo mkdir -p /var/log/mytrader
sudo chown -R ubuntu:ubuntu /var/log/mytrader

echo ""
echo "========== 初始化完成 =========="
echo ""
echo "后续步骤:"
echo ""
echo "1. 编辑环境配置文件:"
echo "   vi /opt/myTrader/.env"
echo ""
echo "2. 运行数据库迁移:"
echo "   cd /opt/myTrader"
echo "   alembic upgrade head"
echo ""
echo "3. 启动服务:"
echo "   sudo systemctl start mytrader-redis"
echo "   sudo systemctl start mytrader-api"
echo "   sudo systemctl start mytrader-web"
echo ""
echo "4. 检查部署状态:"
echo "   sudo systemctl status mytrader-api"
echo "   curl http://localhost:8000/health"
echo ""
echo "5. 查看日志:"
echo "   sudo journalctl -u mytrader-api -f"
echo ""
