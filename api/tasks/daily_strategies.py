# -*- coding: utf-8 -*-
"""
Daily scheduled tasks for preset strategies (动量反转 + 微盘股)

每日收盘后自动执行策略筛选。

NOTE: Beat 调度时直接同步执行策略（不通过 apply_async 二次投递），
避免 Docker 网络隔离导致 Celery 任务投递失败。
"""
import logging
from datetime import datetime

from api.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name='run_preset_strategies_daily',
                 soft_time_limit=3600, time_limit=3900)
def run_preset_strategies_daily(self):
    """
    每日自动执行预设策略 (由 Celery Beat 20:10 调度)

    直接在 Worker 进程内同步运行，不通过 apply_async 二次投递。
    """
    from config.db import execute_query, execute_update
    from api.tasks.preset_strategies import _run_momentum_reversal, _run_microcap_pure_mv

    logger.info('=' * 60)
    logger.info('[SCHEDULE] Starting daily preset strategies execution')
    logger.info('=' * 60)

    # Get latest trade date
    td_rows = execute_query(
        "SELECT MAX(trade_date) AS max_date FROM trade_stock_daily",
        env='online',
    )
    if not td_rows or not td_rows[0].get('max_date'):
        logger.error('[SCHEDULE] Cannot get latest trade date from trade_stock_daily')
        return {'error': 'no trade date'}
    trade_date_str = str(td_rows[0]['max_date'])
    logger.info('[SCHEDULE] Using trade_date=%s', trade_date_str)

    strategies = {
        'momentum_reversal': _run_momentum_reversal,
        'microcap_pure_mv': _run_microcap_pure_mv,
    }
    results = {}

    for strategy_key, run_fn in strategies.items():
        try:
            # Check if already done for this date
            existing = execute_query(
                "SELECT id, status FROM trade_preset_strategy_run "
                "WHERE strategy_key = %s AND run_date = %s ORDER BY id DESC LIMIT 1",
                (strategy_key, trade_date_str),
                env='online',
            )
            if existing and existing[0]['status'] == 'done':
                logger.info('[SCHEDULE] %s already done for %s, skipping', strategy_key, trade_date_str)
                results[strategy_key] = {'status': 'skipped', 'reason': 'already done'}
                continue

            # Clean up any stale pending/running/failed records
            if existing:
                execute_update(
                    "DELETE FROM trade_preset_strategy_run WHERE id = %s",
                    (existing[0]['id'],),
                    env='online',
                )

            # Insert new record
            execute_update(
                """INSERT INTO trade_preset_strategy_run
                    (strategy_key, run_date, status, triggered_at,
                     signal_count, momentum_count, reversal_count,
                     market_status, market_message)
                VALUES (%s, %s, 'running', NOW(), 0, 0, 0, '', '')""",
                (strategy_key, trade_date_str),
                env='online',
            )

            # Get the new run_id
            id_rows = execute_query(
                "SELECT id FROM trade_preset_strategy_run "
                "WHERE strategy_key = %s AND run_date = %s ORDER BY id DESC LIMIT 1",
                (strategy_key, trade_date_str),
                env='online',
            )
            run_id = id_rows[0]['id']
            logger.info('[SCHEDULE] Running %s: run_id=%d, trade_date=%s', strategy_key, run_id, trade_date_str)

            # Execute synchronously (no apply_async)
            result = run_fn(run_id, 'online')
            results[strategy_key] = result
            logger.info('[SCHEDULE] %s completed: %s', strategy_key, result)

        except Exception as e:
            logger.error('[SCHEDULE] %s failed: %s', strategy_key, e, exc_info=True)
            results[strategy_key] = {'error': str(e)[:500]}

    logger.info('=' * 60)
    logger.info('[SCHEDULE] Daily preset strategies completed: %s', results)
    logger.info('=' * 60)

    return results
