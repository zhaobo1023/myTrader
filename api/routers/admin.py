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
# Data health check endpoint
# ============================================================

@router.get('/data-health')
async def get_data_health(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Return latest update dates and record counts for key data dimensions.
    No table names exposed - uses friendly descriptions.
    """
    from datetime import date as _date
    import asyncio

    today = _date.today().isoformat()

    checks = [
        {
            'key': 'daily_price',
            'label': 'A股日线行情',
            'desc': '全市场股票每日开高低收量额数据',
            'sql_date': 'SELECT MAX(trade_date) as d FROM trade_stock_daily',
            'sql_count': 'SELECT COUNT(DISTINCT stock_code) as cnt FROM trade_stock_daily',
            'count_label': '股票数',
            'warn_days': 2,
        },
        {
            'key': 'etf_price',
            'label': 'ETF日线行情',
            'desc': 'ETF基金每日行情数据',
            'sql_date': 'SELECT MAX(trade_date) as d FROM trade_etf_daily',
            'sql_count': 'SELECT COUNT(DISTINCT fund_code) as cnt FROM trade_etf_daily',
            'count_label': 'ETF数',
            'warn_days': 2,
        },
        {
            'key': 'rps',
            'label': 'RPS相对强度',
            'desc': '全市场股票RPS排名及斜率指标',
            'sql_date': 'SELECT MAX(trade_date) as d FROM trade_stock_rps',
            'sql_count': 'SELECT COUNT(DISTINCT stock_code) as cnt FROM trade_stock_rps WHERE trade_date = (SELECT MAX(trade_date) FROM trade_stock_rps)',
            'count_label': '覆盖股票数',
            'warn_days': 3,
        },
        {
            'key': 'theme_score',
            'label': '主题池评分',
            'desc': '主题选股池的技术面评分和动量指标',
            'sql_date': 'SELECT MAX(score_date) as d FROM theme_pool_scores',
            'sql_count': 'SELECT COUNT(*) as cnt FROM theme_pool_scores WHERE score_date = (SELECT MAX(score_date) FROM theme_pool_scores)',
            'count_label': '评分记录数',
            'warn_days': 2,
        },
        {
            'key': 'basic_factor',
            'label': '基础量价因子',
            'desc': '动量、波动率、换手率等基础因子',
            'sql_date': 'SELECT MAX(calc_date) as d FROM trade_stock_basic_factor',
            'sql_count': 'SELECT COUNT(DISTINCT stock_code) as cnt FROM trade_stock_basic_factor WHERE calc_date = (SELECT MAX(calc_date) FROM trade_stock_basic_factor)',
            'count_label': '覆盖股票数',
            'warn_days': 3,
        },
        {
            'key': 'fear_index',
            'label': '恐慌指数',
            'desc': 'VIX等恐慌指标及市场情绪数据',
            'sql_date': 'SELECT MAX(trade_date) as d FROM trade_fear_index',
            'sql_count': 'SELECT COUNT(*) as cnt FROM trade_fear_index WHERE trade_date = (SELECT MAX(trade_date) FROM trade_fear_index)',
            'count_label': '指标数',
            'warn_days': 3,
        },
        {
            'key': 'macro',
            'label': '宏观经济数据',
            'desc': '利率、汇率、大宗商品等宏观指标',
            'sql_date': 'SELECT MAX(trade_date) as d FROM trade_macro_indicator',
            'sql_count': 'SELECT COUNT(DISTINCT indicator_code) as cnt FROM trade_macro_indicator',
            'count_label': '指标数',
            'warn_days': 7,
        },
        {
            'key': 'north_holding',
            'label': '北向资金持仓',
            'desc': '陆股通北向资金持股数据',
            'sql_date': 'SELECT MAX(trade_date) as d FROM trade_north_holding',
            'sql_count': 'SELECT COUNT(DISTINCT stock_code) as cnt FROM trade_north_holding WHERE trade_date = (SELECT MAX(trade_date) FROM trade_north_holding)',
            'count_label': '覆盖股票数',
            'warn_days': 3,
        },
        {
            'key': 'moneyflow',
            'label': '资金流向',
            'desc': '主力资金净流入流出数据',
            'sql_date': 'SELECT MAX(trade_date) as d FROM trade_stock_moneyflow',
            'sql_count': 'SELECT COUNT(DISTINCT stock_code) as cnt FROM trade_stock_moneyflow WHERE trade_date = (SELECT MAX(trade_date) FROM trade_stock_moneyflow)',
            'count_label': '覆盖股票数',
            'warn_days': 3,
        },
    ]

    from datetime import datetime as _dt

    result = []
    for c in checks:
        item = {
            'key': c['key'],
            'label': c['label'],
            'desc': c['desc'],
            'count_label': c['count_label'],
            'latest_date': None,
            'count': None,
            'days_behind': None,
            'status': 'unknown',
        }
        try:
            r = await db.execute(text(c['sql_date']))
            row = r.mappings().first()
            if row and row['d']:
                d = row['d']
                latest_str = d.isoformat() if hasattr(d, 'isoformat') else str(d)[:10]
                item['latest_date'] = latest_str
                try:
                    delta = (_dt.strptime(today, '%Y-%m-%d') - _dt.strptime(latest_str, '%Y-%m-%d')).days
                    item['days_behind'] = delta
                    if delta <= c['warn_days']:
                        item['status'] = 'ok'
                    elif delta <= c['warn_days'] * 2:
                        item['status'] = 'warn'
                    else:
                        item['status'] = 'error'
                except Exception:
                    item['status'] = 'unknown'
        except Exception as e:
            item['status'] = 'error'
            item['error'] = str(e)

        try:
            r2 = await db.execute(text(c['sql_count']))
            row2 = r2.mappings().first()
            if row2:
                item['count'] = int(list(row2.values())[0] or 0)
        except Exception:
            pass

        result.append(item)

    ok_count = sum(1 for r in result if r['status'] == 'ok')
    warn_count = sum(1 for r in result if r['status'] == 'warn')
    error_count = sum(1 for r in result if r['status'] == 'error')

    return {
        'checked_at': today,
        'summary': {
            'ok': ok_count,
            'warn': warn_count,
            'error': error_count,
            'total': len(result),
        },
        'items': result,
    }


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
