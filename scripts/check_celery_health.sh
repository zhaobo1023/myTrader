#!/bin/bash
# ============================================================
# Celery & Redis health monitor (runs on HOST via crontab)
#
# Checks Docker container health status and Redis connectivity.
# Sends alert to Feishu webhook when any service is unhealthy.
#
# Install:
#   chmod +x /root/app/scripts/check_celery_health.sh
#   crontab -e
#   */5 * * * * /root/app/scripts/check_celery_health.sh >> /var/log/celery_health.log 2>&1
# ============================================================

set -euo pipefail

# Load webhook URL from .env
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../.env"
WEBHOOK_URL=""
if [ -f "$ENV_FILE" ]; then
    WEBHOOK_URL=$(grep -E '^ALERT_WEBHOOK_URL=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' || true)
    if [ -z "$WEBHOOK_URL" ]; then
        WEBHOOK_URL=$(grep -E '^FEISHU_WEBHOOK_URL=' "$ENV_FILE" | cut -d= -f2- | tr -d '"' || true)
    fi
fi

# Cooldown: avoid alert flood (max 1 alert per 10 minutes per service)
COOLDOWN_DIR="/tmp/celery_health_cooldown"
mkdir -p "$COOLDOWN_DIR"

send_alert() {
    local title="$1"
    local content="$2"
    local cooldown_key="$3"
    local cooldown_file="${COOLDOWN_DIR}/${cooldown_key}"

    # Check cooldown (10 min = 600 seconds)
    if [ -f "$cooldown_file" ]; then
        local last=$(cat "$cooldown_file")
        local now=$(date +%s)
        local diff=$((now - last))
        if [ "$diff" -lt 600 ]; then
            return 0
        fi
    fi

    if [ -n "$WEBHOOK_URL" ]; then
        curl -s -X POST "$WEBHOOK_URL" \
            -H 'Content-Type: application/json' \
            -d "{\"msg_type\":\"text\",\"content\":{\"text\":\"${title}\n\n${content}\"}}" \
            >/dev/null 2>&1 || true
        date +%s > "$cooldown_file"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ALERT sent: ${title}"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ALERT (no webhook): ${title}"
    fi
}

# ============================================================
# Check containers
# ============================================================
CONTAINERS="app-celery-beat-1 app-celery-worker-1 mytrader-api mytrader-redis"
ALL_OK=true

for svc in $CONTAINERS; do
    # Check if container exists and is running
    state=$(docker inspect --format='{{.State.Status}}' "$svc" 2>/dev/null || echo "missing")
    if [ "$state" != "running" ]; then
        send_alert \
            "[RED] Container DOWN: ${svc}" \
            "Status: ${state}\nTime: $(date '+%Y-%m-%d %H:%M:%S')\nAction: docker compose up -d" \
            "container_${svc}"
        ALL_OK=false
        continue
    fi

    # Check health status (if healthcheck is configured)
    health=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}no-healthcheck{{end}}' "$svc" 2>/dev/null || echo "unknown")
    if [ "$health" = "unhealthy" ]; then
        # Get last health check log
        last_log=$(docker inspect --format='{{with (index .State.Health.Log (len .State.Health.Log | add -1))}}{{.Output}}{{end}}' "$svc" 2>/dev/null | head -c 200 || echo "N/A")
        send_alert \
            "[RED] Container UNHEALTHY: ${svc}" \
            "Health: ${health}\nLast check: ${last_log}\nTime: $(date '+%Y-%m-%d %H:%M:%S')" \
            "health_${svc}"
        ALL_OK=false
    fi
done

# ============================================================
# Check Redis connectivity from host
# ============================================================
REDIS_PASSWORD=$(grep -E '^REDIS_PASSWORD=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d '"' || true)
REDIS_PING=$(docker exec mytrader-redis redis-cli -a "$REDIS_PASSWORD" --no-auth-warning ping 2>/dev/null || echo "FAIL")
if [ "$REDIS_PING" != "PONG" ]; then
    send_alert \
        "[RED] Redis unreachable" \
        "PING result: ${REDIS_PING}\nTime: $(date '+%Y-%m-%d %H:%M:%S')" \
        "redis_ping"
    ALL_OK=false
fi

if [ "$ALL_OK" = true ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] All services healthy"
fi
