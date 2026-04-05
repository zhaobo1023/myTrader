# -*- coding: utf-8 -*-
"""
Admin router - user management
"""
import logging

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import text

from api.dependencies import get_db
from api.middleware.auth import require_admin
from api.models.user import User

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/admin', tags=['admin'])


@router.get('/users')
async def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(require_admin),
):
    """List all users with pagination."""
    db = get_db()
    try:
        offset = (page - 1) * page_size
        users = db.execute(
            text(
                "SELECT id, email, tier, role, is_active, created_at "
                "FROM users ORDER BY id LIMIT :limit OFFSET :offset"
            ),
            {"limit": page_size, "offset": offset},
        )
        users = list(users)

        total = db.execute(text("SELECT COUNT(*) as cnt FROM users"))
        total_row = list(total)[0]
        total_count = total_row['cnt'] if isinstance(total_row, dict) else total_row[0]

        return {
            'total': total_count,
            'page': page,
            'page_size': page_size,
            'data': users,
        }
    except Exception as e:
        logger.error('[ADMIN] List users failed: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/users/{user_id}/usage')
async def get_user_usage(
    user_id: int,
    current_user: User = Depends(require_admin),
):
    """Get usage statistics for a specific user."""
    db = get_db()
    try:
        usage = db.execute(
            text(
                "SELECT api_endpoint, date, count "
                "FROM usage_logs WHERE user_id = :uid "
                "ORDER BY date DESC LIMIT 100"
            ),
            {"uid": user_id},
        )
        usage = list(usage)

        summary = db.execute(
            text(
                "SELECT api_endpoint, SUM(count) as total_count "
                "FROM usage_logs WHERE user_id = :uid "
                "GROUP BY api_endpoint ORDER BY total_count DESC"
            ),
            {"uid": user_id},
        )
        summary = list(summary)

        return {'usage': usage, 'summary': summary}
    except Exception as e:
        logger.error('[ADMIN] Get usage failed: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put('/users/{user_id}/tier')
async def update_user_tier(
    user_id: int,
    tier: str = Query(..., pattern='^(free|pro)$'),
    current_user: User = Depends(require_admin),
):
    """Update user tier (free/pro)."""
    db = get_db()
    try:
        db.execute(
            text("UPDATE users SET tier = :tier WHERE id = :uid"),
            {"tier": tier, "uid": user_id},
        )
        db.commit()
        return {'message': f'User {user_id} tier updated to {tier}'}
    except Exception as e:
        logger.error('[ADMIN] Update tier failed: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put('/users/{user_id}/active')
async def toggle_user_active(
    user_id: int,
    is_active: bool = Query(...),
    current_user: User = Depends(require_admin),
):
    """Enable or disable user account."""
    db = get_db()
    try:
        db.execute(
            text("UPDATE users SET is_active = :active WHERE id = :uid"),
            {"active": is_active, "uid": user_id},
        )
        db.commit()
        return {'message': f'User {user_id} {"enabled" if is_active else "disabled"}'}
    except Exception as e:
        logger.error('[ADMIN] Toggle active failed: %s', e)
        raise HTTPException(status_code=500, detail=str(e))
