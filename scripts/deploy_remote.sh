#!/bin/bash
# Remote deploy script -- executed on ECS via CI/CD
# Uses Gunicorn HUP reload for zero-downtime API deploys
set -e

cd /root/app

# ── 1. Pull latest code ──────────────────────────────────────
echo "[1/5] Pulling latest code..."
git fetch origin
git reset --hard origin/main

# ── 2. Graceful API reload (zero downtime) ───────────────────
echo "[2/5] Graceful API reload via SIGHUP..."
if docker exec mytrader-api kill -HUP 1 2>/dev/null; then
  # Wait for new workers to be ready
  for i in $(seq 1 10); do
    sleep 2
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
      echo "  API reloaded successfully after ${i}x2s"
      break
    fi
    if [ "$i" = "10" ]; then
      echo "[WARN] HUP reload may have failed, falling back to docker restart"
      docker restart mytrader-api
      for j in $(seq 1 20); do
        sleep 2
        STATUS=$(docker inspect --format="{{.State.Health.Status}}" mytrader-api 2>/dev/null || echo "none")
        if [ "$STATUS" = "healthy" ]; then
          echo "  API healthy after restart (${j}x2s)"
          break
        fi
        if [ "$j" = "20" ]; then
          echo "[ERROR] API did not become healthy"
          docker logs --tail 30 mytrader-api
          exit 1
        fi
      done
    fi
  done
else
  echo "[WARN] Cannot send HUP (container not running or not gunicorn), using docker restart"
  docker restart mytrader-api
  for i in $(seq 1 20); do
    sleep 2
    STATUS=$(docker inspect --format="{{.State.Health.Status}}" mytrader-api 2>/dev/null || echo "none")
    if [ "$STATUS" = "healthy" ]; then
      echo "  API healthy after ${i}x2s"
      break
    fi
    if [ "$i" = "20" ]; then
      echo "[ERROR] API did not become healthy in 40s"
      docker logs --tail 30 mytrader-api
      exit 1
    fi
  done
fi

# ── 3. Restart Celery workers ────────────────────────────────
echo "[3/5] Restarting Celery workers..."
docker restart app-celery-worker-1 app-celery-beat-1 || true

# ── 4. Web frontend (only when changed) ──────────────────────
echo "[4/5] Checking frontend changes (WEB_CHANGED=${WEB_CHANGED})..."
if [ "${WEB_CHANGED}" = "true" ]; then
  echo "  web/ changed -- rebuilding image..."
  docker build --no-cache \
    -t mytrader-web:latest ./web
  # Brief downtime during swap, maintenance page covers it
  docker stop mytrader-web && docker rm mytrader-web
  docker run -d \
    --name mytrader-web \
    --network app_mytrader-network \
    -p 127.0.0.1:3000:3000 \
    -e NEXT_PUBLIC_API_BASE_URL=http://123.56.3.1:8000 \
    --restart unless-stopped \
    mytrader-web:latest
  echo "  Web container restarted with new image."
else
  echo "  No web/ changes -- skipping frontend rebuild."
fi

# ── 5. Final health check ────────────────────────────────────
echo "[5/5] Final health check..."
curl -sf http://localhost:8000/health \
  || { echo "[ERROR] API health check failed"; exit 1; }
echo "[SUCCESS] Deploy completed."
