# -*- coding: utf-8 -*-
"""
Daily scheduled tasks for preset strategies (动量反转 + 微盘股)

每日收盘后自动执行策略筛选
"""
import logging
from datetime import datetime

from api.tasks.celery_app import celery_app
from api.services.preset_strategy_service import trigger_strategy_run

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name='run_preset_strategies_daily')
def run_preset_strategies_daily(self):
    """
    每日自动执行预设策略

    执行时间建议：收盘后 18:30（确保行情数据已更新）
    """
    logger.info('=' * 60)
    logger.info('[SCHEDULE] Starting daily preset strategies execution')
    logger.info('=' * 60)

    strategies = ['momentum_reversal', 'microcap_pure_mv']
    results = {}

    for strategy_key in strategies:
        try:
            logger.info(f'[SCHEDULE] Triggering strategy: {strategy_key}')
            result = trigger_strategy_run(strategy_key, force=False)
            results[strategy_key] = result
            logger.info(f'[SCHEDULE] Strategy {strategy_key} triggered: run_id={result.get("run_id")}')
        except Exception as e:
            logger.error(f'[SCHEDULE] Failed to trigger {strategy_key}: {e}')
            results[strategy_key] = {'error': str(e)}

    logger.info('=' * 60)
    logger.info('[SCHEDULE] Daily preset strategies execution completed')
    logger.info(f'Results: {results}')
    logger.info('=' * 60)

    return results
