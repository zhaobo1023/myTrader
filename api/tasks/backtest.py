# -*- coding: utf-8 -*-
"""
Celery async backtest task

Wraps strategist/ modules for async execution.
Worker runs the backtest, writes results to MySQL, updates job status.
"""
import logging
import traceback
from datetime import datetime

from api.tasks.celery_app import celery_app
from api.config import settings

logger = logging.getLogger('myTrader.tasks')


@celery_app.task(bind=True)
def run_backtest(self, job_id: int, params: dict):
    """
    Execute a backtest job.

    Args:
        job_id: BacktestJob primary key
        params: Backtest parameters dict
            - strategy_type: str (e.g. 'xgboost', 'doctor_tao')
            - stock_pool: list of stock codes
            - start_date: str YYYY-MM-DD
            - end_date: str YYYY-MM-DD
            - initial_cash: float
            - commission: float
            - position_pct: float
    """
    from config.db import execute_update, execute_query
    import os
    import sys

    # Ensure project root is in path
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)

    def update_job(status: str, **kwargs):
        sets = [f"status='{status}'", "updated_at=NOW()"]
        for k, v in kwargs.items():
            if isinstance(v, str):
                sets.append(f"{k}='{v}'")
            elif isinstance(v, float):
                sets.append(f"{k}={v}")
            elif v is None:
                sets.append(f"{k}=NULL")
            else:
                sets.append(f"{k}={v}")
        sql = f"UPDATE backtest_jobs SET {', '.join(sets)} WHERE id=%s"
        execute_update(sql, (job_id,))

    try:
        # Mark as running
        update_job('running')
        self.update_state(state='RUNNING', meta={'job_id': job_id, 'progress': 0})

        strategy_type = params.get('strategy_type', 'xgboost')
        start_date = params.get('start_date')
        end_date = params.get('end_date')
        stock_pool = params.get('stock_pool', [])
        initial_cash = params.get('initial_cash', 1000000)
        commission = params.get('commission', 0.0002)

        logger.info('[BACKTEST] Job %d started: type=%s, period=%s ~ %s',
                     job_id, strategy_type, start_date, end_date)

        # ---- Phase 1: Load data (20%) ----
        self.update_state(state='RUNNING', meta={'job_id': job_id, 'progress': 20,
                                                  'stage': 'loading_data'})
        from config.db import execute_query as eq

        # ---- Phase 2: Run strategy (50%) ----
        self.update_state(state='RUNNING', meta={'job_id': job_id, 'progress': 50,
                                                  'stage': 'running_strategy'})

        # Placeholder: integrate with actual strategist modules
        # For now, generate a simulated result to validate the pipeline
        result = _run_placeholder_backtest(params)

        # ---- Phase 3: Save results (80%) ----
        self.update_state(state='RUNNING', meta={'job_id': job_id, 'progress': 80,
                                                  'stage': 'saving_results'})

        update_job(
            'done',
            finished_at='NOW()',
            total_return=result.get('total_return', 0),
            annual_return=result.get('annual_return', 0),
            max_drawdown=result.get('max_drawdown', 0),
            sharpe_ratio=result.get('sharpe_ratio', 0),
            ic=result.get('ic'),
            icir=result.get('icir'),
            result_file=result.get('result_file'),
        )

        # ---- Phase 4: Complete (100%) ----
        logger.info('[BACKTEST] Job %d completed: return=%.2f%%',
                     job_id, result.get('total_return', 0) * 100)

        return {
            'job_id': job_id,
            'status': 'done',
            'total_return': result.get('total_return', 0),
            'annual_return': result.get('annual_return', 0),
            'max_drawdown': result.get('max_drawdown', 0),
            'sharpe_ratio': result.get('sharpe_ratio', 0),
        }

    except Exception as e:
        logger.error('[BACKTEST] Job %d failed: %s\n%s', job_id, str(e), traceback.format_exc())
        error_msg = str(e)[:500]
        update_job('failed', error_msg=error_msg, finished_at='NOW()')
        return {'job_id': job_id, 'status': 'failed', 'error': error_msg}


def _run_placeholder_backtest(params: dict) -> dict:
    """
    Placeholder backtest logic.
    TODO: Replace with actual strategist module calls.
    """
    import random
    random.seed(42)

    # Simulate a realistic backtest result
    total_days = 252
    daily_returns = [random.gauss(0.0005, 0.015) for _ in range(total_days)]

    cumulative = 1.0
    for r in daily_returns:
        cumulative *= (1 + r)

    total_return = cumulative - 1
    annual_return = total_return
    max_dd = 0
    peak = 1.0
    for r in daily_returns:
        peak *= (1 + r)
        dd = (peak - cumulative) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)

    sharpe = (annual_return / 0.015) if annual_return > 0 else -1

    return {
        'total_return': round(total_return, 4),
        'annual_return': round(annual_return, 4),
        'max_drawdown': round(max_dd, 4),
        'sharpe_ratio': round(sharpe, 2),
        'ic': None,
        'icir': None,
        'result_file': None,
    }
