# -*- coding: utf-8 -*-
"""
Celery task for daily stock news fetching.

Fetches news for all stocks that have tech reports (analyzed stocks).
Runs daily at 18:30 after market close.
"""
import logging

from api.tasks.celery_app import celery_app
from config.db import execute_query

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name='fetch_stock_news_daily')
def fetch_stock_news_daily(self):
    """
    Fetch news for all analyzed stocks and store to database.
    """
    logger.info('[STOCK_NEWS] Starting daily stock news fetch')

    # Get all stocks that have tech reports
    rows = list(execute_query(
        "SELECT DISTINCT stock_code FROM trade_tech_report",
    ))
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
