# -*- coding: utf-8 -*-
"""
Celery application configuration
"""
import os
from celery import Celery

from api.config import settings

# Build Redis URLs from settings (single source of truth for host/port/password).
# Also write back to os.environ so Celery CLI (which reads env vars before
# importing the app module) uses the same values.
if settings.redis_password:
    broker_url = f'redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}/1'
    backend_url = f'redis://:{settings.redis_password}@{settings.redis_host}:{settings.redis_port}/2'
else:
    broker_url = f'redis://{settings.redis_host}:{settings.redis_port}/1'
    backend_url = f'redis://{settings.redis_host}:{settings.redis_port}/2'

os.environ['CELERY_BROKER_URL'] = broker_url
os.environ['CELERY_RESULT_BACKEND'] = backend_url

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
    # Redis connection resilience
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=10,
    broker_connection_retry=True,
    broker_transport_options={
        'socket_keepalive': True,
        'socket_keepalive_options': {},
        'retry_on_timeout': True,
    },
    # Global task timeout (prevent worker stuck)
    task_soft_time_limit=1800,   # 30min soft -> SoftTimeLimitExceeded
    task_time_limit=2400,        # 40min hard kill
)

# Auto-discover tasks
celery_app.autodiscover_tasks(['api.tasks'])

from celery.schedules import crontab

celery_app.conf.beat_schedule = {
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
    # 早间任务
    # ============================================================

    # 08:30 - 晨报生成并发布到飞书
    'daily-morning-briefing': {
        'task': 'publish_morning_briefing',
        'schedule': crontab(hour=8, minute=30, day_of_week='1-5'),
    },

    # 08:00 - 恐慌指数(盘前)
    'fear-index-morning': {
        'task': 'fetch_fear_index',
        'schedule': crontab(hour=8, minute=0, day_of_week='1-5'),
    },

    # 09:35 - SimPool T+1买入价格填充
    'sim-pool-fill-entry-prices': {
        'task': 'tasks.fill_entry_prices',
        'schedule': crontab(hour=9, minute=35, day_of_week='1-5'),
    },

    # ============================================================
    # 盘中任务
    # ============================================================

    # 每小时 :15 - 宏观数据 + 全球资产增量拉取
    'hourly-macro-fetch': {
        'task': 'fetch_macro_data_hourly',
        'schedule': crontab(minute=15),
    },

    # 12:00 - 恐慌指数(午间)
    'fear-index-noon': {
        'task': 'fetch_fear_index',
        'schedule': crontab(hour=12, minute=0, day_of_week='1-5'),
    },

    # ============================================================
    # 收盘后 -- 独立任务 (无依赖, 错开执行)
    # ============================================================

    # 16:20 - Dashboard 数据拉取 (涨跌家数/成交额/涨跌停/两融/新高低)
    'daily-dashboard-fetch': {
        'task': 'fetch_dashboard_data',
        'schedule': crontab(hour=16, minute=20, day_of_week='1-5'),
    },

    # 16:25 - 复盘数据预检（检查今日数据是否就绪）
    'daily-evening-precheck': {
        'task': 'precheck_evening_data',
        'schedule': crontab(hour=16, minute=25, day_of_week='1-5'),
    },

    # 16:30 - 监控自选股
    'daily-watchlist-scan': {
        'task': 'watchlist_scan.scan_all_users',
        'schedule': crontab(hour=16, minute=30, day_of_week='1-5'),
    },

    # 16:35 - SimPool每日更新（价格/止盈止损/NAV/报告）
    'sim-pool-daily-update': {
        'task': 'tasks.daily_sim_pool_update',
        'schedule': crontab(hour=16, minute=35, day_of_week='1-5'),
    },

    # 16:40 - 资金流向拉取
    'daily-moneyflow-fetch': {
        'task': 'fetch_moneyflow_daily',
        'schedule': crontab(hour=16, minute=40, day_of_week='1-5'),
    },

    # 16:45 - 融资融券拉取
    'daily-margin-fetch': {
        'task': 'fetch_margin_daily',
        'schedule': crontab(hour=16, minute=45, day_of_week='1-5'),
    },

    # 16:50 - 北向持仓拉取
    'daily-north-holding-fetch': {
        'task': 'fetch_north_holding_daily',
        'schedule': crontab(hour=16, minute=50, day_of_week='1-5'),
    },

    # 17:00 - 复盘生成并发布到飞书
    'daily-evening-briefing': {
        'task': 'publish_evening_briefing',
        'schedule': crontab(hour=17, minute=0, day_of_week='1-5'),
    },

    # 17:30 - 个股新闻拉取 (已分析股票)
    'daily-stock-news-fetch': {
        'task': 'fetch_stock_news_daily',
        'schedule': crontab(hour=17, minute=30, day_of_week='1-5'),
    },

    # ============================================================
    # 收盘后 -- 数据处理链 (时间间隔保证顺序, 避免OOM)
    # ============================================================

    # 18:00 - 数据就绪Gate (轮询等待日线数据写入完成)
    'daily-data-gate': {
        'task': 'scheduler.adapters.run_data_gate',
        'schedule': crontab(hour=18, minute=0, day_of_week='1-5'),
    },

    # 18:30 - 因子计算 (basic + extended + valuation + quality)
    'daily-factor-calc': {
        'task': 'scheduler.adapters.run_factor_calculation',
        'schedule': crontab(hour=18, minute=30, day_of_week='1-5'),
    },

    # 18:30 - 恐慌指数(盘后)
    'fear-index-evening': {
        'task': 'fetch_fear_index',
        'schedule': crontab(hour=18, minute=30, day_of_week='1-5'),
    },

    # 19:30 - 技术指标 & RPS (因子计算完成后, 间隔60min)
    'daily-indicator-calc': {
        'task': 'scheduler.adapters.run_indicator_calculation',
        'schedule': crontab(hour=19, minute=30, day_of_week='1-5'),
    },

    # 20:10 - 预设策略执行 (指标计算完成后, 间隔40min)
    'daily-preset-strategies': {
        'task': 'run_preset_strategies_daily',
        'schedule': crontab(hour=20, minute=10, day_of_week='1-5'),
    },

    # 20:40 - 主题池评分
    'daily-theme-pool-score': {
        'task': 'scheduler.adapters.run_theme_pool_score',
        'schedule': crontab(hour=20, minute=40, day_of_week='1-5'),
    },

    # ============================================================
    # 晚间收尾
    # ============================================================

    # 21:30 - 数据健康日报推送到飞书
    'daily-health-report': {
        'task': 'push_daily_health_report',
        'schedule': crontab(hour=21, minute=30, day_of_week='1-5'),
    },

    # 22:00 - 公众号文章导出 + LLM摘要 + 飞书推送
    'nightly-article-digest': {
        'task': 'run_nightly_digest',
        'schedule': crontab(hour=22, minute=0),
    },
}
celery_app.conf.timezone = 'Asia/Shanghai'
