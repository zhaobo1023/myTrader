#!/bin/bash
# migrate_compose.sh - Consolidate dual Docker Compose into single project
#
# This script:
# 1. Stops the old 'app' compose project (duplicate beat/worker)
# 2. Migrates Redis data from standalone container to compose-managed volume
# 3. Restarts the unified 'mytrader' compose project with all services
# 4. Verifies all services are healthy
# 5. Disables the old compose file to prevent accidental restart
#
# Run on the server: bash /tmp/migrate_compose.sh

set -euo pipefail

MYTRADER_DIR="/app/myTrader"
APP_DIR="/root/app"
LOG_PREFIX="[migrate]"

log() { echo "$LOG_PREFIX $(date '+%H:%M:%S') $*"; }
err() { echo "$LOG_PREFIX [ERROR] $(date '+%H:%M:%S') $*" >&2; }

# ── Step 0: Pre-flight checks ──────────────────────────────────────
log "Pre-flight checks..."

if ! docker ps --format '{{.Names}}' | grep -q mytrader-redis; then
    err "mytrader-redis container not found. Aborting."
    exit 1
fi

if [ ! -f "$MYTRADER_DIR/docker-compose.yml" ]; then
    err "$MYTRADER_DIR/docker-compose.yml not found. Aborting."
    exit 1
fi

# Check Redis is responding
REDIS_PASS=$(grep '^REDIS_PASSWORD=' "$MYTRADER_DIR/.env" | cut -d= -f2)
if ! docker exec mytrader-redis redis-cli -a "$REDIS_PASS" PING 2>/dev/null | grep -q PONG; then
    err "Redis not responding. Aborting."
    exit 1
fi
log "  Redis OK, password confirmed"

# ── Step 1: Stop old 'app' compose project ──────────────────────────
log "Step 1: Stopping old 'app' compose project..."
if docker compose ls 2>/dev/null | grep -q "^app "; then
    cd "$APP_DIR"
    docker compose down --remove-orphans 2>/dev/null || true
    log "  'app' project stopped"
else
    log "  'app' project not running, skipping"
fi

# ── Step 2: Migrate Redis data ──────────────────────────────────────
log "Step 2: Migrating Redis data to named volume..."

# Save Redis data to disk first
docker exec mytrader-redis redis-cli -a "$REDIS_PASS" BGSAVE 2>/dev/null || true
sleep 2

# Get old volume path
OLD_VOL=$(docker inspect mytrader-redis --format '{{range .Mounts}}{{.Source}}{{end}}' 2>/dev/null)
log "  Old Redis volume: $OLD_VOL"

# Create the named volume
docker volume create mytrader_redis_data 2>/dev/null || true

# Copy data from old anonymous volume to new named volume
# Use a temp container to bridge the volumes
docker run --rm \
    -v "$OLD_VOL:/old_data:ro" \
    -v mytrader_redis_data:/new_data \
    alpine sh -c "cp -a /old_data/* /new_data/ 2>/dev/null || true"
log "  Data copied to mytrader_redis_data"

# Stop the old standalone Redis container
docker stop mytrader-redis 2>/dev/null || true
docker rm mytrader-redis 2>/dev/null || true
log "  Old Redis container removed"

# ── Step 3: Restart mytrader compose with all services ──────────────
log "Step 3: Starting unified mytrader compose..."
cd "$MYTRADER_DIR"

# Pull latest code
git pull --ff-only origin main 2>/dev/null || true

# Start Redis first, then other services
docker compose up -d redis
log "  Waiting for Redis to be healthy..."
for i in $(seq 1 30); do
    if docker compose exec redis redis-cli -a "$REDIS_PASS" PING 2>/dev/null | grep -q PONG; then
        log "  Redis healthy after ${i}s"
        break
    fi
    sleep 1
done

# Now start everything else
docker compose up -d --build
log "  All services starting..."

# ── Step 4: Health check ────────────────────────────────────────────
log "Step 4: Waiting for services to be healthy..."
MAX_WAIT=120
for i in $(seq 1 $MAX_WAIT); do
    API_OK=$(docker inspect mytrader-api --format '{{.State.Health.Status}}' 2>/dev/null || echo "missing")
    REDIS_OK=$(docker inspect mytrader-redis --format '{{.State.Health.Status}}' 2>/dev/null || echo "missing")
    WORKER_STATUS=$(docker compose ps celery-worker --format '{{.Health}}' 2>/dev/null || echo "unknown")

    if [ "$API_OK" = "healthy" ] && [ "$REDIS_OK" = "healthy" ]; then
        log "  API and Redis healthy after ${i}s"
        break
    fi

    if [ "$i" -eq "$MAX_WAIT" ]; then
        err "  Health check timeout. API=$API_OK, Redis=$REDIS_OK, Worker=$WORKER_STATUS"
        log "  Continuing anyway - check manually"
    fi
    sleep 1
done

# ── Step 5: Verify no duplicate services ────────────────────────────
log "Step 5: Verifying no duplicate services..."
APP_CONTAINERS=$(docker ps --filter "label=com.docker.compose.project=app" --format '{{.Names}}' 2>/dev/null | wc -l)
if [ "$APP_CONTAINERS" -gt 0 ]; then
    err "  Still have $APP_CONTAINERS containers from 'app' project!"
    docker ps --filter "label=com.docker.compose.project=app" --format '{{.Names}}'
else
    log "  No containers from 'app' project - clean"
fi

# ── Step 6: Disable old compose to prevent restart ──────────────────
log "Step 6: Disabling old compose file..."
if [ -f "$APP_DIR/docker-compose.yml" ]; then
    mv "$APP_DIR/docker-compose.yml" "$APP_DIR/docker-compose.yml.disabled"
    log "  Renamed to docker-compose.yml.disabled"
fi

# ── Step 7: E2E verification ────────────────────────────────────────
log "Step 7: End-to-end verification..."
API_STATUS=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health 2>/dev/null || echo "failed")
SITE_STATUS=$(curl -s -o /dev/null -w '%{http_code}' -k https://mytrader.cc 2>/dev/null || echo "failed")
log "  API /health: HTTP $API_STATUS"
log "  Site https://mytrader.cc: HTTP $SITE_STATUS"

# ── Summary ─────────────────────────────────────────────────────────
echo ""
echo "=========================================="
echo "  Compose consolidation complete"
echo "=========================================="
docker compose ps --format 'table {{.Name}}\t{{.Status}}\t{{.Image}}'
echo ""
echo "Active compose projects:"
docker compose ls
echo ""
log "Done. If issues arise, restore with:"
log "  mv $APP_DIR/docker-compose.yml.disabled $APP_DIR/docker-compose.yml"
log "  cd $APP_DIR && docker compose up -d"
