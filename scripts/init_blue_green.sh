#!/bin/bash
# init_blue_green.sh
# 首次在服务器上执行，建立蓝绿部署初始状态。
# 执行后：blue 容器运行在 :3000，Nginx 指向 blue，.deploy_slot=blue
#
# 使用方式：
#   scp scripts/init_blue_green.sh aliyun-ecs:/tmp/init_blue_green.sh
#   ssh aliyun-ecs "bash /tmp/init_blue_green.sh"

set -euo pipefail

APP_DIR="/app/myTrader"
NGINX_UPSTREAM_FILE="$APP_DIR/nginx_upstream_web.conf"
SLOT_FILE="$APP_DIR/.deploy_slot"

# 自动检测 Docker 网络名
NETWORK=$(docker inspect mytrader-nginx --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}' 2>/dev/null | head -1)
if [ -z "$NETWORK" ]; then
  echo "[ERROR] Cannot detect Docker network from mytrader-nginx container"
  exit 1
fi
echo "[INFO] Detected Docker network: $NETWORK"

cd "$APP_DIR"

# ── 1. 确定当前 web 容器状态 ─────────────────────────────────
echo "[1/6] Checking current web container..."
if docker inspect mytrader-web-blue > /dev/null 2>&1; then
  echo "  mytrader-web-blue already exists, skipping rename"
elif docker inspect mytrader-web > /dev/null 2>&1; then
  echo "  Renaming mytrader-web -> mytrader-web-blue..."
  # Docker 不支持 rename 并保持运行，需要停止重建
  OLD_IMAGE=$(docker inspect mytrader-web --format '{{.Config.Image}}')
  docker stop mytrader-web
  docker rm mytrader-web
  docker run -d \
    --name mytrader-web-blue \
    --network "$NETWORK" \
    -p 127.0.0.1:3000:3000 \
    --restart unless-stopped \
    "$OLD_IMAGE"
  echo "  mytrader-web-blue started on :3000"
else
  echo "  No existing web container found, will build blue from scratch..."
  docker build -t mytrader-web:blue ./web
  docker run -d \
    --name mytrader-web-blue \
    --network "$NETWORK" \
    -p 127.0.0.1:3000:3000 \
    --restart unless-stopped \
    mytrader-web:blue
  echo "  mytrader-web-blue built and started on :3000"
fi

# ── 2. 等待 blue 健康 ────────────────────────────────────────
echo "[2/6] Waiting for mytrader-web-blue to be healthy..."
for i in $(seq 1 20); do
  if curl -sf http://127.0.0.1:3000 -o /dev/null 2>/dev/null; then
    echo "  blue healthy after ${i}x3s"
    break
  fi
  if [ "$i" = "20" ]; then
    echo "[ERROR] mytrader-web-blue did not respond in 60s"
    docker logs --tail 20 mytrader-web-blue
    exit 1
  fi
  sleep 3
done

# ── 3. 生成初始 upstream_web.conf ───────────────────────────
echo "[3/6] Writing initial nginx_upstream_web.conf (blue -> mytrader-web-blue:3000)..."
cat > "$NGINX_UPSTREAM_FILE" << 'EOF'
upstream nextjs_frontend {
    server mytrader-web-blue:3000;
    keepalive 16;
}
EOF
echo "  Written: $NGINX_UPSTREAM_FILE"

# ── 4. 写 .deploy_slot ──────────────────────────────────────
echo "[4/6] Writing .deploy_slot = blue..."
echo "blue" > "$SLOT_FILE"

# ── 5. 挂载 upstream_web.conf 到 Nginx 并重载 ───────────────
echo "[5/6] Reloading Nginx to pick up new upstream config..."
# 检查 nginx 容器是否已挂载该文件
MOUNTED=$(docker inspect mytrader-nginx --format '{{range .Mounts}}{{.Source}}:{{.Destination}} {{end}}' | grep -c "nginx_upstream_web.conf" || true)
if [ "$MOUNTED" = "0" ]; then
  echo "  nginx_upstream_web.conf not mounted in mytrader-nginx, need to recreate nginx container..."
  echo "  Stopping nginx..."
  docker stop mytrader-nginx
  docker rm mytrader-nginx
  docker run -d \
    --name mytrader-nginx \
    --network "$NETWORK" \
    -p 80:80 \
    -p 443:443 \
    -v "$APP_DIR/nginx.conf:/etc/nginx/conf.d/default.conf:ro" \
    -v "$APP_DIR/nginx_upstream_web.conf:/etc/nginx/conf.d/upstream_web.conf:ro" \
    -v "$APP_DIR/nginx_logs:/var/log/nginx" \
    -v /etc/letsencrypt:/etc/letsencrypt:ro \
    -v "$APP_DIR/maintenance.html:/usr/share/nginx/html/50x.html:ro" \
    --restart unless-stopped \
    nginx:alpine
  echo "  Nginx recreated with upstream_web.conf mounted"
  sleep 3
else
  echo "  nginx_upstream_web.conf already mounted, doing reload..."
  docker exec mytrader-nginx nginx -s reload
fi

# ── 6. 验证 ─────────────────────────────────────────────────
echo "[6/6] Verifying..."
sleep 2
HTTP=$(curl -sf -o /dev/null -w '%{http_code}' http://localhost:3000 2>/dev/null || echo "000")
echo "  blue direct (:3000): HTTP $HTTP"

if [ "$HTTP" = "000" ]; then
  echo "[ERROR] blue not responding"
  exit 1
fi

echo ""
echo "[SUCCESS] Blue-green init complete."
echo "  Active slot : blue"
echo "  Blue port   : 3000"
echo "  Green port  : 3001 (unused until next web deploy)"
echo "  Slot file   : $SLOT_FILE"
echo "  Upstream cfg: $NGINX_UPSTREAM_FILE"
echo ""
echo "  Next web deploy will:"
echo "    build -> mytrader-web-green (:3001)"
echo "    verify green -> switch nginx -> stop blue"
