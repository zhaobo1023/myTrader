# -*- coding: utf-8 -*-
"""
Admin router - user management
"""
import logging

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
    db: AsyncSession = Depends(get_db),
):
    """List all users with pagination."""
    try:
        offset = (page - 1) * page_size
        users_result = await db.execute(
            text(
                "SELECT id, email, tier, role, is_active, created_at "
                "FROM users ORDER BY id LIMIT :limit OFFSET :offset"
            ),
            {"limit": page_size, "offset": offset},
        )
        users = [dict(row) for row in users_result.mappings()]

        total_result = await db.execute(text("SELECT COUNT(*) FROM users"))
        total_count = total_result.scalar()

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
    db: AsyncSession = Depends(get_db),
):
    """Get usage statistics for a specific user."""
    try:
        usage_result = await db.execute(
            text(
                "SELECT api_endpoint, date, count "
                "FROM usage_logs WHERE user_id = :uid "
                "ORDER BY date DESC LIMIT 100"
            ),
            {"uid": user_id},
        )
        usage = [dict(row) for row in usage_result.mappings()]

        summary_result = await db.execute(
            text(
                "SELECT api_endpoint, SUM(count) as total_count "
                "FROM usage_logs WHERE user_id = :uid "
                "GROUP BY api_endpoint ORDER BY total_count DESC"
            ),
            {"uid": user_id},
        )
        summary = [dict(row) for row in summary_result.mappings()]

        return {'usage': usage, 'summary': summary}
    except Exception as e:
        logger.error('[ADMIN] Get usage failed: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put('/users/{user_id}/tier')
async def update_user_tier(
    user_id: int,
    tier: str = Query(..., pattern='^(free|pro)$'),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update user tier (free/pro)."""
    try:
        await db.execute(
            text("UPDATE users SET tier = :tier WHERE id = :uid"),
            {"tier": tier, "uid": user_id},
        )
        await db.commit()
        return {'message': f'User {user_id} tier updated to {tier}'}
    except Exception as e:
        logger.error('[ADMIN] Update tier failed: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put('/users/{user_id}/active')
async def toggle_user_active(
    user_id: int,
    is_active: bool = Query(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Enable or disable user account."""
    try:
        await db.execute(
            text("UPDATE users SET is_active = :active WHERE id = :uid"),
            {"active": is_active, "uid": user_id},
        )
        await db.commit()
        return {'message': f'User {user_id} {"enabled" if is_active else "disabled"}'}
    except Exception as e:
        logger.error('[ADMIN] Toggle active failed: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# Log tail endpoints
# ============================================================
import os as _os
from pathlib import Path as _Path

_LOG_DIR = _Path('logs')
_ALLOWED_FILES = {'app', 'error', 'access'}


def _tail(filepath: str, lines: int) -> list:
    """Read last N lines from a file efficiently."""
    try:
        with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
            all_lines = f.readlines()
        return [line.rstrip('\n') for line in all_lines[-lines:]]
    except FileNotFoundError:
        return []
    except Exception as e:
        return [f'[ERROR reading log] {e}']


@router.get('/logs')
async def tail_log(
    file: str = 'app',
    lines: int = 100,
    current_user: User = Depends(require_admin),
):
    """
    Tail a server log file (admin only).

    Query params:
        file  : app | error | access  (default: app)
        lines : number of lines to return (max 2000)
    """
    if file not in _ALLOWED_FILES:
        raise HTTPException(status_code=400, detail=f'file must be one of {sorted(_ALLOWED_FILES)}')
    lines = min(max(1, lines), 2000)
    filepath = _LOG_DIR / f'{file}.log'
    content = _tail(str(filepath), lines)
    return {
        'file': file,
        'lines_returned': len(content),
        'content': content,
    }


@router.get('/logs/list')
async def list_log_files(current_user: User = Depends(require_admin)):
    """List available log files with sizes."""
    result = []
    for name in sorted(_ALLOWED_FILES):
        path = _LOG_DIR / f'{name}.log'
        if path.exists():
            stat = path.stat()
            result.append({
                'file': name,
                'size_bytes': stat.st_size,
                'size_kb': round(stat.st_size / 1024, 1),
            })
        else:
            result.append({'file': name, 'size_bytes': 0, 'size_kb': 0})
    return {'logs': result}
