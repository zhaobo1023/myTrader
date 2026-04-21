# -*- coding: utf-8 -*-
"""
Celery task: 每日全市场重大公告抓取。

17:10 执行，覆盖当日重大事项/持股变动/风险提示/资产重组，
写入 research_announcements 表供个股分析和晨报使用。
"""
import logging

from api.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

_LOCK_KEY = 'celery:lock:fetch_announcements_daily'
_LOCK_EXPIRE = 1800  # 30 分钟


@celery_app.task(bind=True, name='fetch_announcements_daily')
def fetch_announcements_daily(self):
    """
    全市场重大公告每日抓取。
    使用 Redis 锁防止重复执行。
    """
    logger.info('[ANN] Starting daily announcement fetch')

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
            logger.warning('[ANN] Another run is in progress, skipping')
            return {'status': 'skipped', 'reason': 'lock held'}
    except Exception as lock_err:
        logger.warning('[ANN] Could not acquire Redis lock (%s), proceeding anyway', lock_err)
        redis = None

    try:
        from data_analyst.fetchers.announcement_fetcher import fetch_announcements_for_date
        from datetime import date

        result = fetch_announcements_for_date(date.today())
        logger.info('[ANN] Done: fetched=%d new=%d errors=%d',
                    result.get('fetched', 0), result.get('new', 0), result.get('errors', 0))
        return {'status': 'ok', **result}

    except Exception as e:
        logger.exception('[ANN] fetch_announcements_daily failed: %s', e)
        raise
    finally:
        try:
            if redis is not None:
                redis.delete(_LOCK_KEY)
        except Exception:
            pass
