#!/bin/bash
# deploy_remote.sh — 在 ECS 服务器上执行的部署脚本
# 由 CI/CD (.github/workflows/deploy.yml) 通过 scp + ssh 调用
#
# 环境变量（由 CI/CD 传入）：
#   WEB_CHANGED=true|false   是否有前端文件变更
#
# 前端使用蓝绿部署：新槽验证通过后才切换 Nginx，无停机
# API 使用 Gunicorn USR2 优雅热重载：真正零停机
set -euo pipefail

APP_DIR="/app/myTrader"
UPSTREAM_FILE="$APP_DIR/nginx_upstream_web.conf"
SLOT_FILE="$APP_DIR/.deploy_slot"

# ── 自动检测 Docker 网络 ─────────────────────────────────────
NETWORK=$(docker inspect mytrader-nginx --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}' 2>/dev/null | head -1)
if [ -z "$NETWORK" ]; then
  echo "[ERROR] Cannot detect Docker network"
  exit 1
fi
echo "[INFO] Docker network: $NETWORK"

cd "$APP_DIR"

# ── 1. 拉取最新代码 ──────────────────────────────────────────
echo "[1/5] Pulling latest code..."
git fetch origin
git reset --hard origin/main
echo "  HEAD: $(git log --oneline -1)"

# ── 2. API 热重载（USR2 无停机）─────────────────────────────
# USR2 流程：master fork 新 master -> 新 master 启动新 worker（加载新代码）
#            -> 旧 worker 处理完当前请求后退出 -> 全程 socket 持续监听，无请求丢失
# 热重载前先清 .pyc 缓存，防止新路由/新文件加载失败（历史踩坑：HUP 后新路由 404）
echo "[2/5] API hot reload (USR2, zero-downtime)..."

# 清 .pyc 缓存
docker exec mytrader-api find /app -name '*.pyc' -delete 2>/dev/null || true
echo "  .pyc cache cleared"

# 获取 gunicorn master pid（取最小 pid，即最老的 master）
GUNICORN_PID=$(docker exec mytrader-api pgrep -f "gunicorn" 2>/dev/null | sort -n | head -1)
if [ -z "$GUNICORN_PID" ]; then
  echo "  [WARN] gunicorn master not found, falling back to docker restart"
  docker restart mytrader-api
else
  echo "  Sending USR2 to gunicorn master (pid=$GUNICORN_PID)..."
  docker exec mytrader-api kill -USR2 "$GUNICORN_PID"
fi

# 健康检查（最多 40s）
HEALTHY=false
for i in $(seq 1 20); do
  sleep 2
  if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "  API healthy after USR2 (${i}x2s)"
    HEALTHY=true
    break
  fi
done
if [ "$HEALTHY" = "false" ]; then
  echo "[WARN] API did not recover after USR2 in 40s, attempting docker restart fallback..."
  docker restart mytrader-api
  for i in $(seq 1 10); do
    sleep 2
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
      echo "  API healthy after fallback restart (${i}x2s)"
      HEALTHY=true
      break
    fi
  done
  if [ "$HEALTHY" = "false" ]; then
    echo "[ERROR] API did not become healthy after fallback restart"
    docker logs --tail 30 mytrader-api
    exit 1
  fi
fi

# ── 3. Celery 重启 ───────────────────────────────────────────
echo "[3/5] Restarting Celery workers..."
docker restart mytrader-celery-worker-1 mytrader-celery-beat-1 2>/dev/null \
  || docker restart app-celery-worker-1 app-celery-beat-1 2>/dev/null \
  || echo "  [WARN] Celery containers not found, skipping"

# ── 4. 前端蓝绿切换（仅 WEB_CHANGED=true）──────────────────
echo "[4/5] Frontend deploy (WEB_CHANGED=${WEB_CHANGED:-false})..."
if [ "${WEB_CHANGED:-false}" = "true" ]; then

  # 确认初始化已完成
  if [ ! -f "$SLOT_FILE" ] || [ ! -f "$UPSTREAM_FILE" ]; then
    echo "[ERROR] Blue-green not initialized. Run scripts/init_blue_green.sh first."
    exit 1
  fi

  ACTIVE=$(cat "$SLOT_FILE")
  if [ "$ACTIVE" = "blue" ]; then
    NEW_SLOT="green"
    NEW_PORT="3001"
    OLD_PORT="3000"
  else
    NEW_SLOT="blue"
    NEW_PORT="3000"
    OLD_PORT="3001"
  fi
  echo "  Active slot: $ACTIVE -> deploying to: $NEW_SLOT (:$NEW_PORT)"

  # 停止旧的新槽容器（如果存在）
  if docker inspect "mytrader-web-$NEW_SLOT" > /dev/null 2>&1; then
    echo "  Stopping old mytrader-web-$NEW_SLOT..."
    docker stop "mytrader-web-$NEW_SLOT" && docker rm "mytrader-web-$NEW_SLOT"
  fi

  # 构建新镜像
  echo "  Building mytrader-web:$NEW_SLOT..."
  docker build -t "mytrader-web:$NEW_SLOT" ./web
  echo "  Build complete."

  # 启动新槽容器（宿主机端口用于直连健康检查）
  docker run -d \
    --name "mytrader-web-$NEW_SLOT" \
    --network "$NETWORK" \
    -p "127.0.0.1:${NEW_PORT}:3000" \
    --restart unless-stopped \
    "mytrader-web:$NEW_SLOT"
  echo "  mytrader-web-$NEW_SLOT started (host port :$NEW_PORT for health check)"

  # 等待新槽健康（直连宿主机端口验证）
  echo "  Waiting for mytrader-web-$NEW_SLOT to be healthy..."
  HEALTHY=false
  for i in $(seq 1 20); do
    HTTP=$(curl -sf -o /dev/null -w '%{http_code}' "http://127.0.0.1:${NEW_PORT}" 2>/dev/null || echo "000")
    if [ "$HTTP" != "000" ]; then
      echo "  $NEW_SLOT healthy: HTTP $HTTP (${i}x3s)"
      HEALTHY=true
      break
    fi
    sleep 3
  done

  if [ "$HEALTHY" = "false" ]; then
    echo "[ERROR] mytrader-web-$NEW_SLOT did not respond in 60s"
    docker logs --tail 20 "mytrader-web-$NEW_SLOT"
    docker stop "mytrader-web-$NEW_SLOT" && docker rm "mytrader-web-$NEW_SLOT"
    exit 1
  fi

  # 备份当前 upstream 文件（用于回滚）
  cp "$UPSTREAM_FILE" "${UPSTREAM_FILE}.bak"

  # 切换 Nginx upstream 指向新槽（用容器名，Nginx 容器内可解析）
  echo "  Switching Nginx upstream to mytrader-web-$NEW_SLOT..."
  cat > "$UPSTREAM_FILE" << EOF
upstream nextjs_frontend {
    server mytrader-web-${NEW_SLOT}:3000;
    keepalive 16;
}
EOF
  docker exec mytrader-nginx nginx -s reload
  sleep 2

  # 端到端验证（经 Nginx）
  E2E_HTTP=$(curl -sf -o /dev/null -w '%{http_code}' -L --max-redirs 3 https://mytrader.cc 2>/dev/null || echo "000")
  if [ "$E2E_HTTP" = "000" ] || [ "$E2E_HTTP" = "502" ] || [ "$E2E_HTTP" = "503" ]; then
    echo "[ERROR] End-to-end check failed: HTTP $E2E_HTTP — rolling back..."
    cp "${UPSTREAM_FILE}.bak" "$UPSTREAM_FILE"
    docker exec mytrader-nginx nginx -s reload
    docker stop "mytrader-web-$NEW_SLOT" && docker rm "mytrader-web-$NEW_SLOT"
    echo "[ROLLBACK] Restored upstream to mytrader-web-$ACTIVE"
    exit 1
  fi
  echo "  End-to-end OK: HTTP $E2E_HTTP"

  # 切换成功：停止旧槽，记录新活跃槽
  echo "  Stopping old slot: mytrader-web-$ACTIVE..."
  docker stop "mytrader-web-$ACTIVE" && docker rm "mytrader-web-$ACTIVE" || true
  echo "$NEW_SLOT" > "$SLOT_FILE"
  echo "  .deploy_slot = $NEW_SLOT"
  rm -f "${UPSTREAM_FILE}.bak"
  echo "  Frontend blue-green switch complete: $ACTIVE -> $NEW_SLOT"

else
  echo "  No web/ changes — skipping frontend rebuild."
fi

# ── 5. 最终健康检查 ──────────────────────────────────────────
echo "[5/5] Final health check..."
API_HEALTH=$(curl -sf http://localhost:8000/health 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status','?'))" 2>/dev/null || echo "failed")
E2E=$(curl -sf -o /dev/null -w '%{http_code}' -L --max-redirs 3 https://mytrader.cc 2>/dev/null || echo "000")
echo "  API health : $API_HEALTH"
echo "  Site (e2e) : HTTP $E2E"

if [ "$API_HEALTH" = "failed" ]; then
  echo "[ERROR] API health check failed"
  exit 1
fi

ACTIVE_SLOT=$(cat "$SLOT_FILE" 2>/dev/null || echo "unknown")
echo ""
echo "[SUCCESS] Deploy complete."
echo "  Commit     : $(git log --oneline -1)"
echo "  Active slot: $ACTIVE_SLOT"
echo "  API status : $API_HEALTH"
echo "  Site e2e   : HTTP $E2E"
