# -*- coding: utf-8 -*-
"""
Subscription & Payment router
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import text

from api.dependencies import get_db
from api.middleware.auth import get_current_user
from api.models.user import User

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/subscription', tags=['subscription'])

PLANS = {
    'free': {'price': 0, 'daily_quota': 50, 'name': 'Free'},
    'pro': {'price': 99, 'daily_quota': 1000, 'name': 'Pro'},
}


@router.get('/plans')
async def list_plans():
    """List available subscription plans."""
    return {'plans': PLANS}


@router.get('/current')
async def get_current_subscription(
    current_user: User = Depends(get_current_user),
):
    """Get current user's subscription status."""
    db = get_db()
    try:
        sub = db.execute(
            text(
                "SELECT plan, start_date, end_date, stripe_subscription_id "
                "FROM subscriptions WHERE user_id = :uid ORDER BY id DESC LIMIT 1"
            ),
            {"uid": current_user.id},
        )
        row = sub.fetchone()
        if not row:
            return {
                'user_id': current_user.id,
                'tier': current_user.tier,
                'plan': None,
                'is_expired': False,
            }

        row_dict = row if isinstance(row, dict) else dict(zip(row._fields, row))
        is_expired = row_dict.get('end_date') and row_dict['end_date'] < str(__import__('datetime').date.today())

        return {
            'user_id': current_user.id,
            'tier': current_user.tier,
            'plan': row_dict.get('plan'),
            'start_date': str(row_dict.get('start_date', '')),
            'end_date': str(row_dict.get('end_date', '')),
            'is_expired': is_expired,
        }
    except Exception as e:
        logger.error('[SUB] Get subscription failed: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/upgrade')
async def upgrade_subscription(
    plan: str = Query(..., pattern='^(pro)$'),
    current_user: User = Depends(get_current_user),
):
    """Upgrade to Pro plan. In production, this would integrate with Stripe/WeChat Pay."""
    import datetime

    if plan not in PLANS:
        raise HTTPException(status_code=400, detail='Invalid plan')

    db = get_db()
    try:
        today = datetime.date.today()
        end_date = today + datetime.timedelta(days=30)

        # Upsert subscription
        existing = db.execute(
            text("SELECT id FROM subscriptions WHERE user_id = :uid ORDER BY id DESC LIMIT 1"),
            {"uid": current_user.id},
        )
        existing_row = existing.fetchone()

        if existing_row:
            sub_id = existing_row['id'] if isinstance(existing_row, dict) else existing_row[0]
            db.execute(
                text(
                    "UPDATE subscriptions SET plan = :plan, start_date = :start, end_date = :end "
                    "WHERE id = :sid"
                ),
                {"plan": plan, "start": str(today), "end": str(end_date), "sid": sub_id},
            )
        else:
            db.execute(
                text(
                    "INSERT INTO subscriptions (user_id, plan, start_date, end_date) "
                    "VALUES (:uid, :plan, :start, :end)"
                ),
                {"uid": current_user.id, "plan": plan, "start": str(today), "end": str(end_date)},
            )

        # Update user tier
        db.execute(
            text("UPDATE users SET tier = :tier WHERE id = :uid"),
            {"tier": plan, "uid": current_user.id},
        )
        db.commit()

        return {
            'message': f'Upgraded to {PLANS[plan]["name"]}',
            'plan': plan,
            'end_date': str(end_date),
        }
    except Exception as e:
        logger.error('[SUB] Upgrade failed: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/webhook')
async def payment_webhook():
    """
    Payment webhook endpoint (placeholder for Stripe/WeChat Pay).
    In production, verify webhook signature and process payment events.
    """
    return {'message': 'Webhook endpoint ready - integrate with payment provider'}
