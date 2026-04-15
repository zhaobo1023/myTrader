# -*- coding: utf-8 -*-
"""
Celery task for macro data fetching (global assets + A-share indicators).

Runs hourly to keep macro_data table fresh for the dashboard and global assets page.
"""
import logging

from api.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name='fetch_macro_data_hourly')
def fetch_macro_data_hourly(self):
    """
    Incremental fetch of all macro indicators (AKShare + yfinance fallback).
    Safe to run frequently — only fetches data newer than what's already in DB.
    """
    logger.info('[MACRO] Starting hourly macro data fetch')

    try:
        from data_analyst.fetchers.macro_fetcher import fetch_all_indicators, ensure_table_exists
        ensure_table_exists()
        results = fetch_all_indicators()

        total = 0
        errors = 0
        for key, res in results.items():
            if res.get('success'):
                total += res.get('count', 0)
            else:
                errors += 1
                logger.warning('[MACRO] %s failed: %s', key, res.get('error', ''))

        logger.info('[MACRO] Done: %d indicators, %d new rows, %d errors',
                    len(results), total, errors)

        return {
            'status': 'ok',
            'indicators': len(results),
            'new_rows': total,
            'errors': errors,
        }

    except Exception as e:
        logger.exception('[MACRO] Task failed: %s', e)
        raise
