# -*- coding: utf-8 -*-
"""
Admin router - user management
"""
import logging

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis

from api.dependencies import get_db, get_redis
from api.middleware.auth import require_admin
from api.models.user import User
from api.models.invite_code import InviteCode
from api.schemas.invite_code import InviteCodeCreate, InviteCodeResponse

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
                "SELECT id, username, display_name, email, tier, role, is_active, created_at "
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
        raise HTTPException(status_code=500, detail='Internal server error')


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
        raise HTTPException(status_code=500, detail='Internal server error')


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
        raise HTTPException(status_code=500, detail='Internal server error')


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
        raise HTTPException(status_code=500, detail='Internal server error')


# ============================================================
# Invite code management
# ============================================================

@router.post('/invite-codes', response_model=list[InviteCodeResponse])
async def create_invite_codes(
    req: InviteCodeCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Generate invitation codes (admin only)."""
    import secrets
    from datetime import datetime, timedelta

    codes = []
    for _ in range(req.count):
        code = secrets.token_urlsafe(16)[:16].upper()
        invite = InviteCode(
            code=code,
            created_by=current_user.id,
            max_uses=req.max_uses,
            expires_at=(
                datetime.utcnow() + timedelta(days=req.expires_in_days)
                if req.expires_in_days else None
            ),
        )
        db.add(invite)
        codes.append(invite)

    await db.flush()
    for c in codes:
        await db.refresh(c)

    return [
        InviteCodeResponse(
            code=c.code,
            max_uses=c.max_uses,
            use_count=c.use_count,
            is_active=c.is_active,
            expires_at=c.expires_at.isoformat() if c.expires_at else None,
            created_at=c.created_at.isoformat(),
        )
        for c in codes
    ]


@router.get('/invite-codes', response_model=list[InviteCodeResponse])
async def list_invite_codes(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all invitation codes with usage info."""
    from sqlalchemy import select
    result = await db.execute(
        select(InviteCode).order_by(InviteCode.created_at.desc())
    )
    codes = result.scalars().all()
    return [
        InviteCodeResponse(
            code=c.code,
            max_uses=c.max_uses,
            use_count=c.use_count,
            is_active=c.is_active,
            expires_at=c.expires_at.isoformat() if c.expires_at else None,
            created_at=c.created_at.isoformat(),
        )
        for c in codes
    ]


@router.delete('/invite-codes/{code}')
async def deactivate_invite_code(
    code: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate an invitation code."""
    from sqlalchemy import select
    result = await db.execute(
        select(InviteCode).where(InviteCode.code == code)
    )
    invite = result.scalar_one_or_none()
    if not invite:
        raise HTTPException(status_code=404, detail='Invite code not found')
    invite.is_active = False
    return {'message': f'Invite code {code} deactivated'}


# ============================================================
# Data health check endpoint
# ============================================================

_DATA_HEALTH_CACHE_KEY = 'admin:data_health'
_DATA_HEALTH_CACHE_TTL = 3600  # 1 hour


@router.get('/data-health')
async def get_data_health(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Return latest update dates and record counts for key data dimensions.
    Results are cached in Redis for 1 hour.
    """
    import json
    from datetime import date as _date
    import asyncio

    cached = await redis.get(_DATA_HEALTH_CACHE_KEY)
    if cached:
        return json.loads(cached)

    today = _date.today().isoformat()

    checks = [
        # --- 行情数据 ---
        {
            'key': 'daily_price',
            'label': 'A股日线行情',
            'group': '行情',
            'sql_date': 'SELECT MAX(trade_date) as d FROM trade_stock_daily',
            'sql_count': 'SELECT COUNT(DISTINCT stock_code) as cnt FROM trade_stock_daily',
            'count_label': '股票数',
            'expected_count': 5300,
            'warn_days': 2,
        },
        {
            'key': 'daily_basic',
            'label': 'A股每日指标',
            'group': '行情',
            'sql_date': 'SELECT MAX(trade_date) as d FROM trade_stock_daily_basic',
            'sql_count': 'SELECT COUNT(DISTINCT stock_code) as cnt FROM trade_stock_daily_basic WHERE trade_date = (SELECT MAX(trade_date) FROM trade_stock_daily_basic)',
            'count_label': '股票数',
            'expected_count': 5300,
            'warn_days': 2,
        },
        {
            'key': 'etf_price',
            'label': 'ETF日线行情',
            'group': '行情',
            'sql_date': 'SELECT MAX(trade_date) as d FROM trade_etf_daily',
            'sql_count': 'SELECT COUNT(DISTINCT fund_code) as cnt FROM trade_etf_daily',
            'count_label': 'ETF数',
            'expected_count': 600,
            'warn_days': 2,
        },
        {
            'key': 'hk_daily',
            'label': '港股日线行情',
            'group': '行情',
            'sql_date': 'SELECT MAX(trade_date) as d FROM trade_hk_daily',
            'sql_count': 'SELECT COUNT(DISTINCT stock_code) as cnt FROM trade_hk_daily WHERE trade_date = (SELECT MAX(trade_date) FROM trade_hk_daily)',
            'count_label': '股票数',
            'expected_count': 2000,
            'warn_days': 3,
        },
        # --- 因子与指标 ---
        {
            'key': 'rps',
            'label': 'RPS相对强度',
            'group': '因子',
            'sql_date': 'SELECT MAX(trade_date) as d FROM trade_stock_rps',
            'sql_count': 'SELECT COUNT(DISTINCT stock_code) as cnt FROM trade_stock_rps WHERE trade_date = (SELECT MAX(trade_date) FROM trade_stock_rps)',
            'count_label': '股票数',
            'expected_count': 5300,
            'warn_days': 3,
        },
        {
            'key': 'basic_factor',
            'label': '基础量价因子',
            'group': '因子',
            'sql_date': 'SELECT MAX(calc_date) as d FROM trade_stock_basic_factor',
            'sql_count': 'SELECT COUNT(DISTINCT stock_code) as cnt FROM trade_stock_basic_factor WHERE calc_date = (SELECT MAX(calc_date) FROM trade_stock_basic_factor)',
            'count_label': '股票数',
            'expected_count': 5300,
            'warn_days': 3,
        },
        {
            'key': 'extended_factor',
            'label': '扩展因子',
            'group': '因子',
            'sql_date': 'SELECT MAX(calc_date) as d FROM trade_stock_extended_factor',
            'sql_count': 'SELECT COUNT(DISTINCT stock_code) as cnt FROM trade_stock_extended_factor WHERE calc_date = (SELECT MAX(calc_date) FROM trade_stock_extended_factor)',
            'count_label': '股票数',
            'expected_count': 5300,
            'warn_days': 3,
        },
        {
            'key': 'log_bias',
            'label': '对数偏差指标',
            'group': '因子',
            'sql_date': 'SELECT MAX(trade_date) as d FROM trade_log_bias_daily',
            'sql_count': 'SELECT COUNT(DISTINCT stock_code) as cnt FROM trade_log_bias_daily WHERE trade_date = (SELECT MAX(trade_date) FROM trade_log_bias_daily)',
            'count_label': '股票数',
            'expected_count': 5300,
            'warn_days': 3,
        },
        # --- 财务数据 ---
        {
            'key': 'financial',
            'label': '财务报表',
            'group': '财务',
            'sql_date': 'SELECT MAX(report_date) as d FROM trade_stock_financial',
            'sql_count': 'SELECT COUNT(DISTINCT stock_code) as cnt FROM trade_stock_financial',
            'count_label': '股票数',
            'expected_count': 5300,
            'warn_days': 90,
        },
        # --- 资金与情绪 ---
        {
            'key': 'margin_trade',
            'label': '融资融券明细',
            'group': '资金',
            'sql_date': 'SELECT MAX(trade_date) as d FROM trade_margin_trade',
            'sql_count': 'SELECT COUNT(DISTINCT stock_code) as cnt FROM trade_margin_trade WHERE trade_date = (SELECT MAX(trade_date) FROM trade_margin_trade)',
            'count_label': '股票数',
            'expected_count': 1600,
            'warn_days': 3,
        },
        {
            'key': 'north_holding',
            'label': '北向个股持仓',
            'group': '资金',
            'sql_date': 'SELECT MAX(hold_date) as d FROM trade_north_holding',
            'sql_count': 'SELECT COUNT(DISTINCT stock_code) as cnt FROM trade_north_holding WHERE hold_date = (SELECT MAX(hold_date) FROM trade_north_holding)',
            'count_label': '股票数',
            'expected_count': 1200,
            'warn_days': 3,
        },
        {
            'key': 'north_flow',
            'label': '北向资金流向',
            'group': '资金',
            'sql_date': "SELECT MAX(date) as d FROM macro_data WHERE indicator = 'north_flow'",
            'sql_count': "SELECT COUNT(*) as cnt FROM macro_data WHERE indicator = 'north_flow'",
            'count_label': '数据条数',
            'warn_days': 3,
        },
        {
            'key': 'margin_balance',
            'label': '融资余额',
            'group': '资金',
            'sql_date': "SELECT MAX(date) as d FROM macro_data WHERE indicator = 'margin_balance'",
            'sql_count': "SELECT COUNT(*) as cnt FROM macro_data WHERE indicator = 'margin_balance'",
            'count_label': '数据条数',
            'warn_days': 7,
        },
        {
            'key': 'concept_map',
            'label': '概念板块映射',
            'group': '资金',
            'sql_date': 'SELECT MAX(updated_at) as d FROM stock_concept_map',
            'sql_count': 'SELECT COUNT(DISTINCT concept_name) as cnt FROM stock_concept_map',
            'count_label': '概念数',
            'expected_count': 300,
            'warn_days': 14,
        },
        {
            'key': 'fear_index',
            'label': '恐慌指数',
            'group': '情绪',
            'sql_date': 'SELECT MAX(trade_date) as d FROM trade_fear_index',
            'sql_count': 'SELECT COUNT(*) as cnt FROM trade_fear_index',
            'count_label': '记录数',
            'warn_days': 3,
        },
        # --- 宏观与全球资产 ---
        {
            'key': 'macro_data',
            'label': '宏观数据(macro_data)',
            'group': '宏观',
            'sql_date': 'SELECT MAX(date) as d FROM macro_data',
            'sql_count': 'SELECT COUNT(DISTINCT indicator) as cnt FROM macro_data',
            'count_label': '指标数',
            'warn_days': 2,
        },
        {
            'key': 'global_us_equity',
            'label': '美股ETF(SPY/QQQ/DIA)',
            'group': '全球资产',
            'sql_date': "SELECT MAX(date) as d FROM macro_data WHERE indicator = 'spy'",
            'sql_count': "SELECT COUNT(*) as cnt FROM macro_data WHERE indicator IN ('spy','qqq','dia') AND date = (SELECT MAX(date) FROM macro_data WHERE indicator = 'spy')",
            'count_label': '品种数',
            'expected_count': 3,
            'warn_days': 3,
        },
        {
            'key': 'global_commodity',
            'label': '商品(黄金/原油/BTC)',
            'group': '全球资产',
            'sql_date': "SELECT MAX(date) as d FROM macro_data WHERE indicator = 'gold'",
            'sql_count': "SELECT COUNT(*) as cnt FROM macro_data WHERE indicator IN ('gold','wti_oil','btc') AND date = (SELECT MAX(date) FROM macro_data WHERE indicator = 'gold')",
            'count_label': '品种数',
            'expected_count': 3,
            'warn_days': 3,
        },
        {
            'key': 'global_rates',
            'label': '美债收益率',
            'group': '全球资产',
            'sql_date': "SELECT MAX(date) as d FROM macro_data WHERE indicator = 'us_10y_bond'",
            'sql_count': "SELECT COUNT(*) as cnt FROM macro_data WHERE indicator IN ('us_2y_bond','us_10y_bond','us_30y_bond') AND date = (SELECT MAX(date) FROM macro_data WHERE indicator = 'us_10y_bond')",
            'count_label': '品种数',
            'expected_count': 3,
            'warn_days': 3,
        },
        # --- 个股分析 ---
        {
            'key': 'tech_report',
            'label': '技术面报告',
            'group': '个股',
            'sql_date': 'SELECT MAX(trade_date) as d FROM trade_tech_report',
            'sql_count': 'SELECT COUNT(DISTINCT stock_code) as cnt FROM trade_tech_report',
            'count_label': '股票数',
            'warn_days': 3,
        },
        {
            'key': 'stock_news',
            'label': '个股新闻',
            'group': '个股',
            'sql_date': 'SELECT MAX(publish_time) as d FROM stock_news',
            'sql_count': 'SELECT COUNT(*) as cnt FROM stock_news',
            'count_label': '新闻数',
            'warn_days': 3,
        },
        # --- 策略产出 ---
        {
            'key': 'theme_score',
            'label': '主题池评分',
            'group': '策略',
            'sql_date': 'SELECT MAX(score_date) as d FROM theme_pool_scores',
            'sql_count': 'SELECT COUNT(*) as cnt FROM theme_pool_scores WHERE score_date = (SELECT MAX(score_date) FROM theme_pool_scores)',
            'count_label': '评分数',
            'warn_days': 2,
        },
        {
            'key': 'sw_rotation',
            'label': '申万行业轮动',
            'group': '策略',
            'sql_date': 'SELECT MAX(run_date) as d FROM trade_sw_rotation_run',
            'sql_count': 'SELECT COUNT(*) as cnt FROM trade_sw_rotation_run',
            'count_label': '运行次数',
            'warn_days': 7,
        },
    ]

    from datetime import datetime as _dt
    from api.dependencies import AsyncSessionLocal

    async def _run_check(c: dict) -> dict:
        item = {
            'key': c['key'],
            'label': c['label'],
            'group': c.get('group', ''),
            'count_label': c['count_label'],
            'expected_count': c.get('expected_count'),
            'latest_date': None,
            'count': None,
            'completeness': None,
            'days_behind': None,
            'status': 'unknown',
        }
        # Each check gets its own session for true parallel execution
        async with AsyncSessionLocal() as conn:
            try:
                r = await conn.execute(text(c['sql_date']))
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
                r2 = await conn.execute(text(c['sql_count']))
                row2 = r2.mappings().first()
                if row2:
                    item['count'] = int(list(row2.values())[0] or 0)
                    if c.get('expected_count') and item['count'] is not None:
                        item['completeness'] = min(100, round(item['count'] / c['expected_count'] * 100))
            except Exception:
                pass

        return item

    result = await asyncio.gather(*[_run_check(c) for c in checks])

    ok_count = sum(1 for r in result if r['status'] == 'ok')
    warn_count = sum(1 for r in result if r['status'] == 'warn')
    error_count = sum(1 for r in result if r['status'] == 'error')

    payload = {
        'checked_at': today,
        'summary': {
            'ok': ok_count,
            'warn': warn_count,
            'error': error_count,
            'total': len(result),
        },
        'items': result,
    }
    await redis.set(_DATA_HEALTH_CACHE_KEY, json.dumps(payload), ex=_DATA_HEALTH_CACHE_TTL)
    return payload


# ============================================================
# Task run log endpoint
# ============================================================

# Friendly labels for task_name values
_TASK_LABELS = {
    'fetch_daily_price': 'A股日线拉取',
    'fetch_etf_daily': 'ETF日线拉取',
    'fetch_macro_data': '宏观指标拉取',
    'fetch_global_assets': '全球资产拉取',
    'fetch_dashboard': '市场看板指标',
    'calc_basic_factor': '基础量价因子',
    'calc_extended_factor': '扩展因子',
    'calc_rps': 'RPS相对强度',
    'calc_technical': '技术指标',
    'calc_log_bias': '对数偏差',
    'calc_svd_monitor': 'SVD市场状态',
    'run_universe_scan': '全市场扫描',
    'run_theme_score': '主题池评分',
    'monitor_candidate': '候选池监控',
    'briefing_morning': '早报',
    'briefing_evening': '晚报',
    'calc_dashboard_signal': '看板信号计算',
    'calc_fear_index': '恐慌指数',
}


@router.get('/task-runs')
async def get_task_runs(
    run_date: str = Query(default=None, description='YYYY-MM-DD, default today'),
    task_group: str = Query(default=None, description='filter by group'),
    days: int = Query(default=7, ge=1, le=30, description='recent N days'),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Return task run logs for a date-range, grouped by task_name."""
    from datetime import date as _date, timedelta as _td

    end_date = _date.today()
    if run_date:
        try:
            from datetime import datetime as _dt
            end_date = _dt.strptime(run_date, '%Y-%m-%d').date()
        except ValueError:
            raise HTTPException(status_code=400, detail='run_date must be YYYY-MM-DD')

    start_date = end_date - _td(days=days - 1)

    # Build date list
    dates = []
    d = end_date
    while d >= start_date:
        dates.append(d.isoformat())
        d -= _td(days=1)

    # Query logs
    where_clauses = ["run_date >= :start_date AND run_date <= :end_date"]
    params = {"start_date": start_date.isoformat(), "end_date": end_date.isoformat()}
    if task_group:
        where_clauses.append("task_group = :task_group")
        params["task_group"] = task_group

    where_sql = " AND ".join(where_clauses)
    sql = text(
        f"SELECT run_date, task_name, task_group, status, "
        f"duration_ms, record_count, error_msg "
        f"FROM trade_task_run_log WHERE {where_sql} "
        f"ORDER BY task_group, task_name, run_date DESC"
    )

    try:
        result = await db.execute(sql, params)
        rows = [dict(r) for r in result.mappings()]
    except Exception as e:
        logger.error('[ADMIN] task-runs query failed: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')

    # Group by task_name
    task_map = {}  # task_name -> {task_group, runs: {date: row}}
    for row in rows:
        tn = row['task_name']
        rd = row['run_date']
        rd_str = rd.isoformat() if hasattr(rd, 'isoformat') else str(rd)[:10]
        if tn not in task_map:
            task_map[tn] = {
                'task_name': tn,
                'task_group': row['task_group'],
                'label': _TASK_LABELS.get(tn, tn),
                'runs': {},
            }
        task_map[tn]['runs'][rd_str] = {
            'status': row['status'],
            'duration_ms': row['duration_ms'],
            'record_count': row['record_count'],
            'error_msg': row.get('error_msg'),
        }

    # Build summary per date
    summary = {}
    for dt in dates:
        counts = {'success': 0, 'failed': 0, 'running': 0, 'skipped': 0, 'total': 0}
        for t in task_map.values():
            run = t['runs'].get(dt)
            if run:
                s = run['status']
                counts[s] = counts.get(s, 0) + 1
                counts['total'] += 1
        summary[dt] = counts

    return {
        'dates': dates,
        'tasks': list(task_map.values()),
        'summary': summary,
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


# ============================================================
# Scheduler management
# ============================================================

@router.get('/scheduler/tasks')
async def list_scheduler_tasks(
    current_user: User = Depends(require_admin),
):
    """
    Return all scheduler tasks with schedule config, today's run status,
    last run info, and whether dependencies are satisfied.
    """
    import asyncio
    from datetime import datetime

    def _build():
        from scheduler.loader import load_tasks
        from config.db import execute_query

        tasks = load_tasks()

        # Today's runs
        today_map: dict = {}
        try:
            rows = execute_query(
                """
                SELECT task_id, status
                FROM task_runs
                WHERE DATE(started_at) = CURDATE()
                ORDER BY started_at ASC
                """,
                env='local',
            )
            priority = {'running': 4, 'success': 3, 'failed': 2, 'skipped': 1}
            for r in rows:
                tid, st = r['task_id'], r['status']
                if priority.get(st, 0) > priority.get(today_map.get(tid, ''), 0):
                    today_map[tid] = st
        except Exception as e:
            logger.warning('[SCHEDULER] today_runs query failed: %s', e)

        # Latest run per task (any day)
        latest_map: dict = {}
        try:
            rows = execute_query(
                """
                SELECT r.task_id, r.status, r.started_at, r.finished_at,
                       r.duration_s, r.error_msg, r.triggered_by
                FROM task_runs r
                INNER JOIN (
                    SELECT task_id, MAX(started_at) AS max_st
                    FROM task_runs
                    GROUP BY task_id
                ) mx ON r.task_id = mx.task_id AND r.started_at = mx.max_st
                """,
                env='local',
            )
            for row in rows:
                latest_map[row['task_id']] = {
                    'status': row['status'],
                    'started_at': str(row['started_at']) if row['started_at'] else None,
                    'finished_at': str(row['finished_at']) if row['finished_at'] else None,
                    'duration_s': float(row['duration_s'] or 0),
                    'error_msg': row['error_msg'],
                    'triggered_by': row['triggered_by'],
                }
        except Exception as e:
            logger.warning('[SCHEDULER] latest run query failed: %s', e)

        # Build all-task id set for dep checks
        all_task_ids = {t['id'] for t in tasks}
        result = []
        for task in tasks:
            tid = task['id']
            deps = task.get('depends_on', [])
            deps_ok = all(today_map.get(d) in ('success',) for d in deps)
            deps_detail = [
                {'id': d, 'status': today_map.get(d, 'not_run')}
                for d in deps
            ]
            today_status = today_map.get(tid)
            result.append({
                'id': tid,
                'name': task.get('name', tid),
                'group': task.get('tags', [''])[0] if task.get('tags') else '',
                'schedule': task.get('schedule', ''),
                'enabled': task.get('enabled', True),
                'tags': task.get('tags', []),
                'depends_on': deps,
                'deps_detail': deps_detail,
                'deps_ok': deps_ok or len(deps) == 0,
                'today_status': today_status,
                'latest_run': latest_map.get(tid),
                'alert_on_failure': task.get('alert_on_failure', False),
            })
        return result

    loop = asyncio.get_running_loop()
    try:
        tasks = await loop.run_in_executor(None, _build)
    except Exception as e:
        logger.error('[SCHEDULER] list tasks failed: %s', e, exc_info=True)
        raise HTTPException(status_code=500, detail=f'Scheduler tasks error: {e}')
    return {'tasks': tasks, 'as_of': __import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}


@router.post('/scheduler/trigger')
async def trigger_task(
    payload: dict,
    current_user: User = Depends(require_admin),
):
    """
    Manually trigger a task by ID.

    Body: { "task_id": "fetch_stock_daily", "force": false }
    force=true ignores dep checks and runs even if deps haven't run today.
    """
    import asyncio

    task_id = payload.get('task_id', '').strip()
    force = bool(payload.get('force', False))
    if not task_id:
        raise HTTPException(status_code=400, detail='task_id is required')

    def _run():
        import os
        from scheduler.loader import load_tasks
        from scheduler.executor import execute_task
        from scheduler.state import ensure_table

        env = os.getenv('DB_ENV', 'local')

        tasks = load_tasks()
        task = next((t for t in tasks if t['id'] == task_id), None)
        if task is None:
            raise ValueError(f'Task not found: {task_id}')

        # Ensure task_runs table exists before querying it
        ensure_table(env=env)

        if force:
            # Pretend all deps succeeded
            completed = {d: 'success' for d in task.get('depends_on', [])}
        else:
            from scheduler.watchdog import _today_runs
            try:
                today_map = _today_runs(env=env)
                completed = dict(today_map)
            except Exception as e:
                logger.warning('[SCHEDULER] _today_runs failed, forcing: %s', e)
                completed = {d: 'success' for d in task.get('depends_on', [])}

        result = execute_task(
            task,
            completed=completed,
            dry_run=False,
            env=env,
            triggered_by=f'admin:{current_user.username}',
        )
        return result

    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _run)
        return {'task_id': task_id, 'result': result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error('[SCHEDULER] trigger failed for %s: %s', task_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/scheduler/watchdog')
async def run_watchdog(
    current_user: User = Depends(require_admin),
):
    """Run the missed-run watchdog check and return detected issues."""
    import asyncio

    def _check():
        import os
        from scheduler.state import ensure_table
        from scheduler.watchdog import check_missed_runs
        env = os.getenv('DB_ENV', 'local')
        ensure_table(env=env)
        missed = check_missed_runs(env=env, dry_run=False)
        return [
            {
                'id': t['id'],
                'name': t.get('name', t['id']),
                'schedule': t.get('schedule', ''),
                'missed_by_minutes': t.get('missed_by_minutes', 0),
                'last_status_today': t.get('last_status_today'),
            }
            for t in missed
        ]

    loop = asyncio.get_running_loop()
    missed = await loop.run_in_executor(None, _check)
    return {'missed_count': len(missed), 'missed': missed}
