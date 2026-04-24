#!/bin/bash
# docker_cleanup.sh - Safe Docker cleanup that preserves build cache and service images
# Scheduled: daily at 03:00 via crontab
# Crontab entry: 0 3 * * * /root/app/scripts/docker_cleanup.sh >> /var/log/docker_cleanup.log 2>&1

set -e

LOG_PREFIX="[docker_cleanup] $(date '+%Y-%m-%d %H:%M:%S')"

echo "${LOG_PREFIX} start"

# 1. Remove stopped containers (but never touch running ones)
STOPPED=$(docker ps -aq --filter status=exited --filter status=created 2>/dev/null)
if [ -n "${STOPPED}" ]; then
    echo "${LOG_PREFIX} removing stopped containers: $(echo ${STOPPED} | wc -w)"
    docker rm ${STOPPED} 2>/dev/null || true
else
    echo "${LOG_PREFIX} no stopped containers"
fi

# 2. Remove dangling images only (<none>:<none>, safe to remove)
DANGLING=$(docker images -q --filter dangling=true 2>/dev/null)
if [ -n "${DANGLING}" ]; then
    echo "${LOG_PREFIX} removing dangling images: $(echo ${DANGLING} | wc -w)"
    docker rmi ${DANGLING} 2>/dev/null || true
else
    echo "${LOG_PREFIX} no dangling images"
fi

# 3. Prune build cache older than 14 days (keeps recent layers for fast rebuild)
echo "${LOG_PREFIX} pruning build cache older than 14 days..."
docker builder prune -f --filter "until=336h" 2>/dev/null || true

# 4. Remove dangling volumes (not named volumes)
VOLUMES=$(docker volume ls -q --filter dangling=true 2>/dev/null)
if [ -n "${VOLUMES}" ]; then
    echo "${LOG_PREFIX} removing dangling volumes: $(echo ${VOLUMES} | wc -w)"
    docker volume rm ${VOLUMES} 2>/dev/null || true
else
    echo "${LOG_PREFIX} no dangling volumes"
fi

# 5. Clean old app backups (keep last 3)
BACKUP_DIR="/root"
BACKUPS=$(ls -dt ${BACKUP_DIR}/app_backup_* 2>/dev/null | tail -n +4)
if [ -n "${BACKUPS}" ]; then
    echo "${LOG_PREFIX} removing old backups (keeping last 3):"
    echo "${BACKUPS}" | while read b; do
        echo "  removing: ${b}"
        rm -rf "${b}"
    done
else
    echo "${LOG_PREFIX} no old backups to remove"
fi

echo "${LOG_PREFIX} done"
echo "${LOG_PREFIX} disk usage:"
df -h /dev/vda1 /data 2>/dev/null || df -h / 2>/dev/null
echo "${LOG_PREFIX} docker disk:"
docker system df 2>/dev/null || true
