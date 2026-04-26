# -*- coding: utf-8 -*-
"""
Celery tasks for sector strength and morning picks calculation.

Schedule:
- 20:30 (Mon-Fri): Compute SW level-2 sector strength -> trade_sector_strength_daily
- 20:35 (Mon-Fri): Compute multi-factor morning picks -> trade_morning_picks
"""
import logging

from api.tasks.celery_app import celery_app

logger = logging.getLogger('myTrader.sector_strength_tasks')


@celery_app.task(bind=True, name='calc_sector_strength_daily')
def calc_sector_strength_daily(self):
    """
    Compute SW level-2 sector strength indicators for today and write to DB.

    Depends on: daily stock data (16:15), factor calc (18:30), indicator calc (19:30)
    """
    from scheduler.adapters import run_sector_strength_daily

    logger.info('[SECTOR_STRENGTH] Starting daily sector strength calculation')
    try:
        result = run_sector_strength_daily(env='online')
        logger.info('[SECTOR_STRENGTH] Done: %s', result)
        return {'status': 'ok', 'result': str(result)}
    except Exception as e:
        logger.exception('[SECTOR_STRENGTH] Failed: %s', e)
        raise


@celery_app.task(bind=True, name='calc_morning_picks_daily')
def calc_morning_picks_daily(self):
    """
    Compute multi-factor morning picks based on top sectors and write to DB.

    Depends on: calc_sector_strength_daily (20:30)
    """
    from scheduler.adapters import run_morning_picks_daily

    logger.info('[MORNING_PICKS] Starting daily morning picks calculation')
    try:
        result = run_morning_picks_daily(env='online')
        logger.info('[MORNING_PICKS] Done: %s', result)
        return {'status': 'ok', 'result': str(result)}
    except Exception as e:
        logger.exception('[MORNING_PICKS] Failed: %s', e)
        raise
