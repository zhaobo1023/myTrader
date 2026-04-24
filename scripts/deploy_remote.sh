#!/bin/bash
# Remote deploy script — executed on ECS via CI/CD
set -e

cd /root/app

echo "[1/4] Pulling latest code..."
git fetch origin
git reset --hard origin/main

echo "[2/4] Restarting API, Celery & Nginx containers..."
docker restart mytrader-nginx mytrader-api app-celery-worker-1 app-celery-beat-1
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

echo "[3/4] Checking frontend changes (WEB_CHANGED=${WEB_CHANGED})..."
if [ "${WEB_CHANGED}" = "true" ]; then
  echo "  web/ changed -- rebuilding image..."
  docker build --no-cache \
    --build-arg NEXT_PUBLIC_POSTHOG_KEY="${POSTHOG_KEY}" \
    --build-arg NEXT_PUBLIC_POSTHOG_HOST="${POSTHOG_HOST}" \
    -t mytrader-web:latest ./web
  docker stop mytrader-web && docker rm mytrader-web
  docker run -d \
    --name mytrader-web \
    --network app_mytrader-network \
    -p 127.0.0.1:3000:3000 \
    -e NEXT_PUBLIC_API_BASE_URL=http://123.56.3.1:8000 \
    -e NEXT_PUBLIC_POSTHOG_KEY="${POSTHOG_KEY}" \
    -e NEXT_PUBLIC_POSTHOG_HOST="${POSTHOG_HOST}" \
    --restart unless-stopped \
    mytrader-web:latest
  echo "  Web container restarted with new image."
else
  echo "  No web/ changes -- skipping frontend rebuild."
fi

echo "[4/4] Final health check..."
curl -sf http://localhost:8000/health \
  || { echo "[ERROR] API health check failed"; exit 1; }
echo "[SUCCESS] Deploy completed."
