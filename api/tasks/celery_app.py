# -*- coding: utf-8 -*-
"""
Celery application configuration
"""
from celery import Celery

from api.config import settings

celery_app = Celery(
    'mytrader',
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Shanghai',
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=86400,  # Results expire after 24h
)

# Auto-discover tasks
celery_app.autodiscover_tasks(['api.tasks'])

from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    'daily-watchlist-scan': {
        'task': 'watchlist_scan.scan_all_users',
        'schedule': crontab(hour=16, minute=30, day_of_week='1-5'),
    },
    'daily-expire-subscriptions': {
        'task': 'expire_subscriptions',
        'schedule': crontab(hour=0, minute=5),
    },
}
celery_app.conf.timezone = 'Asia/Shanghai'
