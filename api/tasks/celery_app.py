# -*- coding: utf-8 -*-
"""
Celery application configuration
"""
import os
from celery import Celery

from api.config import settings

# Clear Celery environment variables to avoid password authentication issues
# Celery prioritizes env vars over constructor parameters
if 'CELERY_BROKER_URL' in os.environ:
    del os.environ['CELERY_BROKER_URL']
if 'CELERY_RESULT_BACKEND' in os.environ:
    del os.environ['CELERY_RESULT_BACKEND']

# Build Redis URLs directly from settings (without password)
broker_url = f'redis://{settings.redis_host}:{settings.redis_port}/1'
backend_url = f'redis://{settings.redis_host}:{settings.redis_port}/2'

celery_app = Celery(
    'mytrader',
    broker=broker_url,
    backend=backend_url,
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
    # ============================================================
    # 每日收盘后任务 (交易日 15:00-16:00 收盘)
    # ============================================================

    # 16:30 - 监控自选股
    'daily-watchlist-scan': {
        'task': 'watchlist_scan.scan_all_users',
        'schedule': crontab(hour=16, minute=30, day_of_week='1-5'),
    },

    # 每小时 :15 - 宏观数据 + 全球资产增量拉取
    'hourly-macro-fetch': {
        'task': 'fetch_macro_data_hourly',
        'schedule': crontab(minute=15),
    },

    # 18:00 - 等待数据就绪
    'daily-data-gate': {
        'task': 'scheduler.adapters.run_data_gate',
        'schedule': crontab(hour=18, minute=0, day_of_week='1-5'),
    },

    # 18:30 - 因子计算
    'daily-factor-calc': {
        'task': 'scheduler.adapters.run_factor_calculation',
        'schedule': crontab(hour=18, minute=30, day_of_week='1-5'),
    },

    # 19:00 - 技术指标 & RPS
    'daily-indicator-calc': {
        'task': 'scheduler.adapters.run_indicator_calculation',
        'schedule': crontab(hour=19, minute=0, day_of_week='1-5'),
    },

    # 19:30 - 预设策略执行 (动量反转 + 微盘股)
    'daily-preset-strategies': {
        'task': 'run_preset_strategies_daily',
        'schedule': crontab(hour=19, minute=30, day_of_week='1-5'),
    },

    # 20:00 - 主题池评分
    'daily-theme-pool-score': {
        'task': 'scheduler.adapters.run_theme_pool_score',
        'schedule': crontab(hour=20, minute=0, day_of_week='1-5'),
    },

    # 18:30 - 个股新闻拉取 (已分析股票)
    'daily-stock-news-fetch': {
        'task': 'fetch_stock_news_daily',
        'schedule': crontab(hour=18, minute=30, day_of_week='1-5'),
    },

    # ============================================================
    # 舆情监控任务 (每小时)
    # ============================================================
    'hourly-fear-index-fetch': {
        'task': 'fetch_fear_index',
        'schedule': crontab(minute=0),  # Every hour
    },

    # ============================================================
    # 凌晨维护任务
    # ============================================================

    # 00:05 - 订阅过期检查
    'daily-expire-subscriptions': {
        'task': 'expire_subscriptions',
        'schedule': crontab(hour=0, minute=5),
    },

    # 01:00 - 数据完整性检查
    'daily-data-integrity-check': {
        'task': 'scheduler.adapters.run_data_integrity_check',
        'schedule': crontab(hour=1, minute=0, day_of_week='1-5'),
    },

    # 02:00 - 技术面持仓扫描
    'daily-tech-scan': {
        'task': 'scheduler.adapters.run_tech_scan',
        'schedule': crontab(hour=2, minute=0, day_of_week='1-5'),
    },

    # 03:00 - 行业ETF对数乖离率
    'daily-log-bias': {
        'task': 'scheduler.adapters.run_log_bias_strategy',
        'schedule': crontab(hour=3, minute=0, day_of_week='1-5'),
    },

    # ============================================================
    # SimPool 模拟池任务
    # ============================================================

    # 09:35 - T+1 买入价格填充
    'sim-pool-fill-entry-prices': {
        'task': 'tasks.fill_entry_prices',
        'schedule': crontab(hour=9, minute=35, day_of_week='1-5'),
    },

    # 16:30 - 每日更新（价格/止盈止损/NAV/报告）
    'sim-pool-daily-update': {
        'task': 'tasks.daily_sim_pool_update',
        'schedule': crontab(hour=16, minute=30, day_of_week='1-5'),
    },
}
celery_app.conf.timezone = 'Asia/Shanghai'
