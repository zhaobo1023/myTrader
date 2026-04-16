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

# ======================================================================
# Unified Celery Beat Schedule
#
# Timeline overview (weekdays, Asia/Shanghai):
#
# 00:05  订阅过期检查
# 01:00  数据完整性检查
# 02:00  技术面持仓扫描
# 03:00  ETF对数乖离率
# 08:00  数据完备性检查
# 08:30  晨报 -> 飞书
# 09:35  SimPool T+1 买入价填充
#
# --- 盘中 ---
# 每小时:15  宏观数据增量拉取 (Redis锁防重复)
# 08:00/12:00/18:30  恐慌指数 (3次/天)
#
# --- 收盘后数据处理链 ---
# 16:25  复盘数据预检
# 16:30  监控自选股
# 16:35  SimPool每日更新
# 17:00  复盘 -> 飞书
# 17:00  市场看板数据拉取 (无依赖,可并行)
# 17:30  个股新闻拉取 (无依赖)
#
# --- Gate -> 因子 -> 指标 -> 策略 链 ---
# 18:00  数据就绪Gate (轮询trade_stock_daily)
# 18:30  因子计算 (basic/extended/valuation/quality/technical)
#         恐慌指数 (第3次)
# 19:00  指标计算 (RPS/技术指标/SVD)
#         资金流向增量
# 19:10  概念板块同步
# 19:20  新闻情感分析
# 19:30  预设策略 (动量反转+微盘股)
#         融资融券增量
#         事件信号检测
# 19:45  Polymarket
# 20:00  主题池评分 + 北向持仓 + 候选池监控
# 20:30  看板信号计算 + 申万估值
# 21:00  数据健康日报 -> 飞书
# 23:00  精选观点日报 (Cubox文章 -> 飞书)
# ======================================================================

celery_app.conf.beat_schedule = {

    # ============================================================
    # 凌晨维护任务
    # ============================================================

    'daily-expire-subscriptions': {
        'task': 'expire_subscriptions',
        'schedule': crontab(hour=0, minute=5),
    },
    'daily-data-integrity-check': {
        'task': 'scheduler.adapters.run_data_integrity_check',
        'schedule': crontab(hour=1, minute=0, day_of_week='1-5'),
    },
    'daily-tech-scan': {
        'task': 'scheduler.adapters.run_tech_scan',
        'schedule': crontab(hour=2, minute=0, day_of_week='1-5'),
    },
    'daily-log-bias': {
        'task': 'scheduler.adapters.run_log_bias_strategy',
        'schedule': crontab(hour=3, minute=0, day_of_week='1-5'),
    },

    # ============================================================
    # 早间任务
    # ============================================================

    'daily-data-completeness': {
        'task': 'check_data_completeness',
        'schedule': crontab(hour=8, minute=0, day_of_week='1-5'),
    },
    'daily-morning-briefing': {
        'task': 'publish_morning_briefing',
        'schedule': crontab(hour=8, minute=30, day_of_week='1-5'),
    },
    'sim-pool-fill-entry-prices': {
        'task': 'tasks.fill_entry_prices',
        'schedule': crontab(hour=9, minute=35, day_of_week='1-5'),
    },

    # ============================================================
    # 盘中周期任务
    # ============================================================

    # 宏观数据: 每小时增量拉取 (Redis锁防重叠)
    'hourly-macro-fetch': {
        'task': 'fetch_macro_data_hourly',
        'schedule': crontab(minute=15),
    },
    # 恐慌指数: 3次/天 (08:00盘前 + 12:00午间 + 18:30盘后)
    'fear-index-morning': {
        'task': 'fetch_fear_index',
        'schedule': crontab(hour=8, minute=0, day_of_week='1-5'),
    },
    'fear-index-midday': {
        'task': 'fetch_fear_index',
        'schedule': crontab(hour=12, minute=0, day_of_week='1-5'),
    },
    'fear-index-evening': {
        'task': 'fetch_fear_index',
        'schedule': crontab(hour=18, minute=30, day_of_week='1-5'),
    },

    # ============================================================
    # 收盘后 - 独立任务 (无依赖, 可并行)
    # ============================================================

    'daily-evening-precheck': {
        'task': 'precheck_evening_data',
        'schedule': crontab(hour=16, minute=25, day_of_week='1-5'),
    },
    'daily-watchlist-scan': {
        'task': 'watchlist_scan.scan_all_users',
        'schedule': crontab(hour=16, minute=30, day_of_week='1-5'),
    },
    'sim-pool-daily-update': {
        'task': 'tasks.daily_sim_pool_update',
        'schedule': crontab(hour=16, minute=35, day_of_week='1-5'),
    },
    'daily-evening-briefing': {
        'task': 'publish_evening_briefing',
        'schedule': crontab(hour=17, minute=0, day_of_week='1-5'),
    },
    'daily-dashboard-fetch': {
        'task': 'fetch_dashboard_data',
        'schedule': crontab(hour=17, minute=0, day_of_week='1-5'),
    },
    'daily-stock-news-fetch': {
        'task': 'fetch_stock_news_daily',
        'schedule': crontab(hour=17, minute=30, day_of_week='1-5'),
    },

    # ============================================================
    # 收盘后 - 数据处理链 (有依赖, 按时间顺序)
    #
    # 依赖链:
    #   data_gate -> factor_calc -> indicator_calc -> strategies
    #                                              -> theme_pool_score
    #                                              -> candidate_monitor
    # ============================================================

    # 18:00 - Gate: 轮询 trade_stock_daily 直到今日数据就绪
    'daily-data-gate': {
        'task': 'scheduler.adapters.run_data_gate',
        'schedule': crontab(hour=18, minute=0, day_of_week='1-5'),
    },
    # 18:30 - 因子计算 (依赖: gate通过, 实际耗时 15-20min)
    'daily-factor-calc': {
        'task': 'scheduler.adapters.run_factor_calculation',
        'schedule': crontab(hour=18, minute=30, day_of_week='1-5'),
    },
    # 18:30 - 恐慌指数(盘后) (轻量, 与因子并行无压力)
    'daily-fear-index-evening': {
        'task': 'fetch_fear_index',
        'schedule': crontab(hour=18, minute=30, day_of_week='1-5'),
    },
    # 19:30 - 指标计算: RPS + 技术指标 + SVD (依赖: 因子, 间隔 60min 留足余量)
    'daily-indicator-calc': {
        'task': 'scheduler.adapters.run_indicator_calculation',
        'schedule': crontab(hour=19, minute=30, day_of_week='1-5'),
    },
    # 19:35 - 资金流向增量 (独立, 轻量)
    'daily-moneyflow-fetch': {
        'task': 'fetch_moneyflow_daily',
        'schedule': crontab(hour=19, minute=35, day_of_week='1-5'),
    },
    # 19:40 - 概念板块同步 (独立)
    'daily-concept-board-sync': {
        'task': 'sync_concept_board',
        'schedule': crontab(hour=19, minute=40, day_of_week='1-5'),
    },
    # 19:50 - 新闻情感分析 (独立)
    'daily-news-sentiment': {
        'task': 'fetch_news_sentiment',
        'schedule': crontab(hour=19, minute=50, day_of_week='1-5'),
    },
    # 20:10 - 预设策略 (依赖: 指标计算, 间隔 40min)
    'daily-preset-strategies': {
        'task': 'run_preset_strategies_daily',
        'schedule': crontab(hour=20, minute=10, day_of_week='1-5'),
    },
    # 20:15 - 融资融券增量 (独立)
    'daily-margin-fetch': {
        'task': 'fetch_margin_daily',
        'schedule': crontab(hour=20, minute=15, day_of_week='1-5'),
    },
    # 20:20 - 事件信号检测 (依赖: 新闻)
    'daily-event-signals': {
        'task': 'fetch_event_signals',
        'schedule': crontab(hour=20, minute=20, day_of_week='1-5'),
    },
    # 20:30 - Polymarket (独立)
    'daily-polymarket': {
        'task': 'fetch_polymarket',
        'schedule': crontab(hour=20, minute=30, day_of_week='1-5'),
    },
    # 20:40 - 主题池评分 (依赖: 概念板块 + 指标)
    'daily-theme-pool-score': {
        'task': 'scheduler.adapters.run_theme_pool_score',
        'schedule': crontab(hour=20, minute=40, day_of_week='1-5'),
    },
    # 20:45 - 北向持仓增量 (独立)
    'daily-north-holding-fetch': {
        'task': 'fetch_north_holding_daily',
        'schedule': crontab(hour=20, minute=45, day_of_week='1-5'),
    },
    # 20:50 - 候选池监控 (依赖: 指标)
    'daily-candidate-monitor': {
        'task': 'monitor_candidate_pool',
        'schedule': crontab(hour=20, minute=50, day_of_week='1-5'),
    },
    # 21:00 - 看板信号计算 (依赖: 因子 + 指标)
    'daily-dashboard-compute': {
        'task': 'compute_dashboard',
        'schedule': crontab(hour=21, minute=0, day_of_week='1-5'),
    },
    # 21:05 - 申万行业估值 (独立)
    'daily-sw-valuation': {
        'task': 'calc_sw_valuation',
        'schedule': crontab(hour=21, minute=5, day_of_week='1-5'),
    },

    # ============================================================
    # 晚间收尾
    # ============================================================

    'daily-health-report': {
        'task': 'push_daily_health_report',
        'schedule': crontab(hour=21, minute=30, day_of_week='1-5'),
    },

    # 21:30 - 精选观点日报 (wechat2rss文章摘要 -> 交叉验证报告 -> 飞书)
    'nightly-curated-digest': {
        'task': 'run_nightly_digest',
        'schedule': crontab(hour=21, minute=30, day_of_week='1-5'),
    },
}
