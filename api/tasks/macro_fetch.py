# -*- coding: utf-8 -*-
"""
Celery task for macro data fetching (global assets + A-share indicators).

Runs hourly to keep macro_data table fresh for the dashboard and global assets page.
"""
import logging

from api.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


_LOCK_KEY = 'celery:lock:fetch_macro_data_hourly'
_LOCK_EXPIRE = 3300  # 55 min — slightly less than the 1-hour schedule


@celery_app.task(bind=True, name='fetch_macro_data_hourly')
def fetch_macro_data_hourly(self):
    """
    Incremental fetch of all macro indicators (AKShare + yfinance fallback).
    Safe to run frequently — only fetches data newer than what's already in DB.
    Uses a Redis lock to prevent overlap if a run takes longer than 1 hour.
    """
    logger.info('[MACRO] Starting hourly macro data fetch')

    # Acquire Redis lock (sync client for Celery context)
    redis = None
    try:
        import redis as sync_redis
        from api.config import get_settings
        _s = get_settings()
        redis = sync_redis.Redis(
            host=_s.redis_host, port=_s.redis_port,
            password=_s.redis_password or None, db=_s.redis_db,
            socket_connect_timeout=2,
        )
        acquired = redis.set(_LOCK_KEY, '1', nx=True, ex=_LOCK_EXPIRE)
        if not acquired:
            logger.warning('[MACRO] Previous run still in progress, skipping')
            return {'status': 'skipped', 'reason': 'lock held'}
    except Exception as lock_err:
        logger.warning('[MACRO] Could not acquire Redis lock (%s), proceeding anyway', lock_err)
        redis = None

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

    finally:
        try:
            if redis is not None:
                redis.delete(_LOCK_KEY)
        except Exception:
            pass
