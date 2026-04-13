#!/bin/bash
# Start Celery worker for preset strategies

cd /app

echo "Starting Celery worker for preset strategies..."
celery -A api.tasks.celery_app worker \
    --loglevel=info \
    --concurrency=2 \
    --max-tasks-per-child=10 \
    --time-limit=3600 \
    --soft-time-limit=3000 \
    --queues=preset_strategies,default \
    --hostname=celery@%h \
    --logfile=/var/log/celery/worker.log
