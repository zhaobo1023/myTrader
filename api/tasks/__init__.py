# -*- coding: utf-8 -*-
"""
Celery tasks package

Explicitly import all task modules for Celery auto-discovery.
"""

from api.tasks import preset_strategies
from api.tasks import backtest
from api.tasks import expire_subscriptions
from api.tasks import watchlist_scan
from api.tasks import theme_pool_score
from api.tasks import fear_index
from api.tasks import daily_strategies
from api.tasks import report_tasks
from api.tasks import ingest_tasks
from api.tasks import sim_pool_tasks
from api.tasks import document_tasks
from api.tasks import scheduler_tasks
from api.tasks import briefing_tasks
from api.tasks import data_pipeline_tasks
from api.tasks import macro_fetch
from api.tasks import financial_fetch
from api.tasks import stock_news
from api.tasks import sector_strength_tasks
from api.tasks import announcement_tasks
from api.tasks import ai_wechat_sync

__all__ = [
    'preset_strategies',
    'backtest',
    'expire_subscriptions',
    'watchlist_scan',
    'theme_pool_score',
    'fear_index',
    'daily_strategies',
    'report_tasks',
    'ingest_tasks',
    'sim_pool_tasks',
    'document_tasks',
    'scheduler_tasks',
    'briefing_tasks',
    'data_pipeline_tasks',
    'macro_fetch',
    'financial_fetch',
    'stock_news',
    'sector_strength_tasks',
    'announcement_tasks',
    'ai_wechat_sync',
]
