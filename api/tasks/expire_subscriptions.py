# -*- coding: utf-8 -*-
"""
Celery task: expire subscriptions that have passed their end_date.
Run daily via Celery beat.
"""
import datetime
import logging

from api.tasks.celery_app import celery_app

logger = logging.getLogger('myTrader.api')


@celery_app.task(name='expire_subscriptions')
def expire_subscriptions():
    """Check and expire outdated subscriptions, downgrade user tier to free."""
    from config.db import execute_query

    today = str(datetime.date.today())

    try:
        # Find expired active subscriptions
        expired = execute_query(
            "SELECT user_id FROM subscriptions "
            "WHERE end_date < :today AND end_date IS NOT NULL",
            params={'today': today},
        )
        expired = list(expired)

        if not expired:
            logger.info('[SUB_EXPIRE] No expired subscriptions found')
            return {'expired_count': 0}

        expired_ids = [row['user_id'] if isinstance(row, dict) else row[0] for row in expired]

        # Downgrade to free tier
        if expired_ids:
            placeholders = ','.join(['%s'] * len(expired_ids))
            execute_query(
                f"UPDATE users SET tier = 'free' WHERE id IN ({placeholders})",
                params=expired_ids,
            )

        logger.info('[SUB_EXPIRE] Expired %d subscriptions', len(expired_ids))
        return {'expired_count': len(expired_ids), 'user_ids': expired_ids}
    except Exception as e:
        logger.error('[SUB_EXPIRE] Task failed: %s', e)
        return {'error': str(e)}
