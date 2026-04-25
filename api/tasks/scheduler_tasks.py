# -*- coding: utf-8 -*-
"""
Celery task wrappers for scheduler adapter functions.

These tasks bridge Celery Beat scheduling and the scheduler/adapters.py
functions. Named to match the beat_schedule task names.
"""
import logging

from api.tasks.celery_app import celery_app

logger = logging.getLogger('myTrader.tasks')


@celery_app.task(name='scheduler.adapters.run_data_gate', bind=True, max_retries=0)
def run_data_gate(self):
    from scheduler.adapters import run_data_gate as _fn
    logger.info('[CELERY] run_data_gate start')
    return _fn()


@celery_app.task(name='scheduler.adapters.run_factor_calculation', bind=True, max_retries=0)
def run_factor_calculation(self):
    from scheduler.adapters import run_factor_calculation as _fn
    logger.info('[CELERY] run_factor_calculation start')
    return _fn()


@celery_app.task(name='scheduler.adapters.run_indicator_calculation', bind=True, max_retries=0)
def run_indicator_calculation(self):
    from scheduler.adapters import run_indicator_calculation as _fn
    logger.info('[CELERY] run_indicator_calculation start')
    return _fn()


@celery_app.task(name='scheduler.adapters.run_theme_pool_score', bind=True, max_retries=0)
def run_theme_pool_score(self):
    from api.tasks.theme_pool_score import run_theme_pool_score as _fn
    logger.info('[CELERY] run_theme_pool_score start')
    return _fn()


@celery_app.task(name='scheduler.adapters.run_data_integrity_check', bind=True, max_retries=0)
def run_data_integrity_check(self):
    from scheduler.adapters import run_data_integrity_check as _fn
    logger.info('[CELERY] run_data_integrity_check start')
    return _fn()


@celery_app.task(name='scheduler.adapters.run_tech_scan', bind=True, max_retries=0)
def run_tech_scan(self):
    from scheduler.adapters import run_tech_scan as _fn
    logger.info('[CELERY] run_tech_scan start')
    return _fn()


@celery_app.task(name='scheduler.adapters.run_log_bias_strategy', bind=True, max_retries=0)
def run_log_bias_strategy(self):
    from scheduler.adapters import run_log_bias as _fn
    logger.info('[CELERY] run_log_bias_strategy start')
    return _fn()


@celery_app.task(name='scheduler.adapters.run_stock_info_incremental', bind=True, max_retries=1)
def run_stock_info_incremental(self):
    from scheduler.adapters import run_stock_info_incremental as _fn
    logger.info('[CELERY] run_stock_info_incremental start')
    return _fn()


@celery_app.task(name='scheduler.adapters.run_positions_daily_report', bind=True, max_retries=1)
def run_positions_daily_report(self):
    from scheduler.adapters import run_positions_daily_report as _fn
    logger.info('[CELERY] run_positions_daily_report start')
    return _fn()


@celery_app.task(name='scheduler.adapters.fetch_stock_daily_incremental', bind=True, max_retries=0,
                 soft_time_limit=10800, time_limit=12000)  # 3h soft / 3.3h hard, no retry
def fetch_stock_daily_incremental(self):
    from celery.exceptions import SoftTimeLimitExceeded
    from scheduler.adapters import fetch_stock_daily_incremental as _fn
    logger.info('[CELERY] fetch_stock_daily_incremental start')
    try:
        return _fn()
    except SoftTimeLimitExceeded:
        logger.error('[CELERY] fetch_stock_daily_incremental: soft time limit (3h) exceeded, aborting')
        raise


@celery_app.task(name='fetch_daily_basic_incremental', bind=True, max_retries=0,
                 soft_time_limit=7200, time_limit=8400)
def fetch_daily_basic_incremental(self):
    """Fetch daily basic data (total_mv, pe_ttm, pb, etc.).

    Tries Tushare daily_basic API first (fast, bulk per-date).
    Falls back to AKShare stock_value_em (slower, per-stock) if Tushare unavailable.
    """
    from datetime import date, timedelta
    logger.info('[CELERY] fetch_daily_basic_incremental start')

    today = date.today()
    end_str = today.strftime('%Y%m%d')
    start_str = (today - timedelta(days=7)).strftime('%Y%m%d')

    # Try Tushare first (fast path: ~1 API call per date)
    try:
        from data_analyst.fetchers.daily_basic_fetcher import (
            _fetch_daily_basic_bulk,
            _daily_basic_available,
        )
        if _daily_basic_available():
            logger.info('[CELERY] fetch_daily_basic_incremental: using Tushare, range %s ~ %s', start_str, end_str)
            total = _fetch_daily_basic_bulk(start_str, end_str)
            logger.info('[CELERY] fetch_daily_basic_incremental done (Tushare): %d rows', total)
            return {'status': 'ok', 'source': 'tushare', 'rows': total}
        else:
            logger.info('[CELERY] fetch_daily_basic_incremental: Tushare daily_basic API not available, trying AKShare')
    except Exception as e:
        logger.warning('[CELERY] fetch_daily_basic_incremental: Tushare failed (%s), trying AKShare', e)

    # Fallback to AKShare (slower: 1 API call per stock)
    try:
        from data_analyst.financial_fetcher.daily_basic_history_fetcher import run as akshare_run
        start_iso = (today - timedelta(days=7)).isoformat()
        end_iso = today.isoformat()
        logger.info('[CELERY] fetch_daily_basic_incremental: using AKShare, range %s ~ %s', start_iso, end_iso)
        akshare_run(start_date=start_iso, end_date=end_iso, force=False, test=False)
        logger.info('[CELERY] fetch_daily_basic_incremental done (AKShare)')
        return {'status': 'ok', 'source': 'akshare'}
    except Exception as e:
        logger.error('[CELERY] fetch_daily_basic_incremental: AKShare also failed: %s', e)
        raise
