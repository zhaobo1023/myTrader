# -*- coding: utf-8 -*-
"""
Celery task for fetching and storing fear index data
"""
import logging
from datetime import date

from api.tasks.celery_app import celery_app
from data_analyst.sentiment.fear_index import FearIndexService
from data_analyst.sentiment.storage import SentimentStorage

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name='fetch_fear_index')
def fetch_fear_index(self):
    """
    Fetch fear index data from Yahoo Finance and store to database.
    Scheduled to run every hour via Celery Beat.
    """
    logger.info('[FEAR_INDEX] Starting fear index fetch task')

    try:
        # Fetch fear index data
        service = FearIndexService()
        result = service.get_fear_index()

        # Store to database
        storage = SentimentStorage(env='online')
        success = storage.save_fear_index(result)

        if success:
            logger.info(
                f'[FEAR_INDEX] Successfully saved fear index: '
                f'VIX={result.vix}, OVX={result.ovx}, GVZ={result.gvz}, US10Y={result.us10y}, '
                f'Score={result.fear_greed_score}, Regime={result.market_regime}'
            )
            return {
                'status': 'success',
                'vix': result.vix,
                'ovx': result.ovx,
                'gvz': result.gvz,
                'us10y': result.us10y,
                'fear_greed_score': result.fear_greed_score,
                'market_regime': result.market_regime,
            }
        else:
            logger.error('[FEAR_INDEX] Failed to save fear index to database')
            return {'status': 'error', 'message': 'Failed to save to database'}

    except Exception as e:
        logger.exception(f'[FEAR_INDEX] Task failed: {e}')
        raise
