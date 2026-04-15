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
]
