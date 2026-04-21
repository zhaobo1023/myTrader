# -*- coding: utf-8 -*-
"""
Celery task for daily stock news fetching.

Fetches news for stocks in user positions + watchlist (not full market).
Runs daily at 17:30 after market close.
"""
import logging

from api.tasks.celery_app import celery_app
from config.db import execute_query

logger = logging.getLogger(__name__)

_LOCK_KEY = 'celery:lock:fetch_stock_news_daily'
_LOCK_EXPIRE = 3600  # 1 hour — long enough to cover any realistic run


def _get_target_stocks() -> list:
    """
    获取需要拉取新闻的股票列表：用户持仓 + 关注列表。
    比全量扫描成本低，覆盖用户最关心的股票。
    """
    codes = set()

    # 用户持仓
    try:
        rows = execute_query("SELECT DISTINCT stock_code FROM user_positions", env='online')
        for r in rows:
            if r.get('stock_code'):
                codes.add(r['stock_code'])
    except Exception as e:
        logger.warning('[STOCK_NEWS] Failed to query user_positions: %s', e)

    # 用户关注列表
    try:
        rows = execute_query(
            "SELECT DISTINCT stock_code FROM user_watchlist", env='online'
        )
        for r in rows:
            if r.get('stock_code'):
                codes.add(r['stock_code'])
    except Exception as e:
        # 兼容 watchlist 表名变体
        try:
            rows = execute_query(
                "SELECT DISTINCT code as stock_code FROM watchlist", env='online'
            )
            for r in rows:
                if r.get('stock_code'):
                    codes.add(r['stock_code'])
        except Exception:
            logger.warning('[STOCK_NEWS] Failed to query watchlist: %s', e)

    # 候选池（sim_pool）
    try:
        rows = execute_query(
            "SELECT DISTINCT stock_code FROM sim_pool WHERE status='active'", env='online'
        )
        for r in rows:
            if r.get('stock_code'):
                codes.add(r['stock_code'])
    except Exception as e:
        logger.debug('[STOCK_NEWS] sim_pool query skipped: %s', e)

    # 兜底: 原有 trade_tech_report 已分析股票
    if not codes:
        try:
            rows = execute_query("SELECT DISTINCT stock_code FROM trade_tech_report")
            for r in rows:
                if r.get('stock_code'):
                    codes.add(r['stock_code'])
        except Exception as e:
            logger.warning('[STOCK_NEWS] Fallback trade_tech_report query failed: %s', e)

    return [{'stock_code': c} for c in sorted(codes)]


@celery_app.task(bind=True, name='fetch_stock_news_daily')
def fetch_stock_news_daily(self):
    """
    Fetch news for user positions + watchlist stocks and store to database.

    Uses a Redis lock to prevent concurrent runs when the beat schedule
    fires while a previous run is still in progress.
    """
    logger.info('[STOCK_NEWS] Starting daily stock news fetch')

    # Acquire a Redis lock to prevent overlapping runs (sync client for Celery context)
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
            logger.warning('[STOCK_NEWS] Another run is in progress, skipping')
            return {'status': 'skipped', 'reason': 'lock held'}
    except Exception as lock_err:
        logger.warning('[STOCK_NEWS] Could not acquire Redis lock (%s), proceeding anyway', lock_err)
        redis = None

    try:
        rows = _get_target_stocks()
        if not rows:
            logger.info('[STOCK_NEWS] No analyzed stocks found')
            return {'status': 'ok', 'stocks': 0, 'total_new': 0}

        from api.services.stock_news_service import fetch_and_store_news

        total_new = 0
        total_events = 0
        errors = 0

        for r in rows:
            code = r['stock_code']
            try:
                result = fetch_and_store_news(code, days=3)
                total_new += result.get('new', 0)
                total_events += result.get('events', 0)
                logger.info('[STOCK_NEWS] %s: fetched=%d new=%d events=%d',
                            code, result.get('fetched', 0), result.get('new', 0), result.get('events', 0))
            except Exception as e:
                logger.error('[STOCK_NEWS] Failed for %s: %s', code, e)
                errors += 1

        logger.info('[STOCK_NEWS] Done: %d stocks, %d new articles, %d events, %d errors',
                    len(rows), total_new, total_events, errors)

        return {
            'status': 'ok',
            'stocks': len(rows),
            'total_new': total_new,
            'total_events': total_events,
            'errors': errors,
        }
    finally:
        # Always release the lock, even if an exception occurred
        try:
            if redis is not None:
                redis.delete(_LOCK_KEY)
        except Exception:
            pass
