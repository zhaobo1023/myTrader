# -*- coding: utf-8 -*-
"""
Market router - K-line, technical indicators, factors, RPS
"""
import logging

from fastapi import APIRouter, HTTPException, Query, Depends

from api.schemas.market import (
    KlineResponse,
    IndicatorResponse,
    FactorResponse,
    RPSResponse,
    StockSearchResponse,
)
from api.services import market_service
from api.middleware.auth import get_current_user
from api.models.user import User

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/market', tags=['market'])


@router.get('/kline', response_model=KlineResponse)
async def get_kline(
    code: str = Query(..., description="Stock code, e.g. 600519"),
    start_date: str = Query(None, description="Start date YYYY-MM-DD"),
    end_date: str = Query(None, description="End date YYYY-MM-DD"),
    limit: int = Query(default=120, ge=1, le=1000),
):
    """Get K-line (candlestick) data for a stock."""
    result = await market_service.get_kline(code, start_date, end_date, limit)
    if result['count'] == 0:
        raise HTTPException(status_code=404, detail=f'No data found for stock {code}')
    return result


@router.get('/indicators', response_model=IndicatorResponse)
async def get_indicators(
    code: str = Query(..., description="Stock code"),
    start_date: str = Query(None, description="Start date YYYY-MM-DD"),
    end_date: str = Query(None, description="End date YYYY-MM-DD"),
    indicators: str = Query(None, description="Comma-separated indicator names"),
):
    """Get technical indicators for a stock."""
    indicator_list = indicators.split(',') if indicators else None
    result = await market_service.get_indicators(code, start_date, end_date, indicator_list)
    if result['count'] == 0:
        raise HTTPException(status_code=404, detail=f'No indicator data for stock {code}')
    return result


@router.get('/factors', response_model=FactorResponse)
async def get_factors(
    date: str = Query(..., description="Calculation date YYYY-MM-DD"),
    codes: str = Query(None, description="Comma-separated stock codes"),
    current_user: User = Depends(get_current_user),
):
    """Get pre-computed factors for a date. Requires authentication."""
    stock_codes = codes.split(',') if codes else None
    result = await market_service.get_factors(date, stock_codes)
    return result


@router.get('/rps', response_model=RPSResponse)
async def get_rps(
    trade_date: str = Query(None, description="Trade date YYYY-MM-DD (default: latest)"),
    window: int = Query(default=250, ge=20, le=500, description="RPS window"),
    top_n: int = Query(default=50, ge=1, le=500),
    min_rps: float = Query(None, description="Minimum RPS filter"),
):
    """Get RPS (Relative Price Strength) rankings."""
    result = await market_service.get_rps(trade_date, window, top_n, min_rps)
    return result


@router.get('/search', response_model=StockSearchResponse)
async def search_stocks(
    keyword: str = Query(..., min_length=1, description="Stock code or name"),
    limit: int = Query(default=20, ge=1, le=100),
):
    """Search stocks by code or name."""
    result = await market_service.search_stocks(keyword, limit)
    return result


@router.get('/latest-date')
async def get_latest_date():
    """Get the latest trading date in the database."""
    date = await market_service.get_latest_trade_date()
    return {'latest_date': date or ''}


@router.get('/global-assets')
async def get_global_assets(
    days: int = Query(default=30, ge=1, le=365, description="Trend data lookback days"),
):
    """Get global macro asset overview: latest values, changes, and trend sparklines."""
    return await market_service.get_global_assets(days)


@router.get('/global-briefing')
async def get_global_briefing(
    session: str = Query(default='morning', description="'morning' (08:30) or 'evening' (18:00)"),
    force: bool = Query(default=False, description="Force regenerate even if cached"),
):
    """Get LLM-generated global asset briefing for today."""
    from api.services.global_asset_briefing import get_latest_briefing
    return await get_latest_briefing(session, force=force)


# In-memory dedup for running briefing tasks: session -> task_id
_briefing_running_tasks: dict[str, str] = {}


@router.post('/global-briefing/submit')
async def submit_briefing(
    session: str = Query(default='morning', description="'morning' or 'evening'"),
):
    """
    Submit async briefing generation task.

    Returns:
      {status: "cached", session, date, content, ...}  — today's cache exists
      {status: "running", task_id}                      — task already in progress
      {status: "submitted", task_id}                    — new task dispatched
    """
    import uuid
    from datetime import date as _date
    from api.services.global_asset_briefing import get_latest_briefing

    # 1. Check today's cache (non-force)
    cached = await get_latest_briefing(session, force=False)
    if cached and cached.get('content') and cached.get('cached'):
        return {**cached, 'status': 'cached'}

    # 2. Check if a task is already running for this session
    existing_task_id = _briefing_running_tasks.get(session)
    if existing_task_id:
        from api.tasks.celery_app import celery_app as _celery
        result = _celery.AsyncResult(existing_task_id)
        if result.state in ('PENDING', 'STARTED', 'RETRY'):
            return {'status': 'running', 'task_id': existing_task_id, 'session': session}
        # Previous task finished or failed — allow new submission
        _briefing_running_tasks.pop(session, None)

    # 3. Dispatch new Celery task
    from api.tasks.briefing_tasks import generate_briefing_async

    task_id = str(uuid.uuid4())
    generate_briefing_async.apply_async(
        args=[task_id, session],
        task_id=task_id,
    )
    _briefing_running_tasks[session] = task_id

    logger.info('[briefing/submit] dispatched task_id=%s session=%s', task_id, session)
    return {'status': 'submitted', 'task_id': task_id, 'session': session}


@router.get('/global-briefing/status')
async def get_briefing_status(
    task_id: str = Query(..., description='Celery task UUID'),
):
    """
    Poll briefing task status.

    Returns:
      {task_id, status: "pending"|"running"|"done"|"failed", briefing?: {...}}
    """
    from api.tasks.celery_app import celery_app as _celery

    result = _celery.AsyncResult(task_id)

    state_map = {
        'PENDING': 'pending',
        'STARTED': 'running',
        'RETRY': 'running',
        'SUCCESS': 'done',
        'FAILURE': 'failed',
        'REVOKED': 'failed',
    }
    status = state_map.get(result.state, 'pending')

    resp: dict = {'task_id': task_id, 'status': status}

    if status == 'done':
        # Task finished — read fresh briefing from DB
        task_result = result.result or {}
        session = task_result.get('session', 'morning')
        from api.services.global_asset_briefing import get_latest_briefing
        briefing = await get_latest_briefing(session, force=False)
        resp['briefing'] = briefing
        # Clean up dedup map
        _briefing_running_tasks.pop(session, None)
    elif status == 'failed':
        resp['error'] = str(result.result)[:500] if result.result else 'Unknown error'
        # Clean up dedup map
        for s, tid in list(_briefing_running_tasks.items()):
            if tid == task_id:
                _briefing_running_tasks.pop(s, None)

    return resp


@router.post('/digest-articles')
async def digest_articles(
    directory: str = Query(
        default='/root/cubox',
        description="Directory containing Cubox-exported Markdown files",
    ),
):
    """Scan Cubox article directory, extract structured digests via LLM."""
    from api.services.article_digest_service import digest_directory
    results = await digest_directory(directory)
    return {'processed': len(results), 'articles': results}


@router.post('/publish-briefing')
async def publish_briefing(
    session: str = Query(default='morning', description="'morning' or 'evening'"),
    force: bool = Query(default=False, description="Force regenerate briefing"),
    current_user: User = Depends(get_current_user),
):
    """Publish briefing to Feishu document and return shareable link."""
    from api.services.feishu_doc_publisher import publish_latest_briefing
    result = await publish_latest_briefing(session, force=force)
    return result


@router.get('/data-health')
async def get_data_health(
    date: str = Query(None, description="Target date YYYY-MM-DD (default: today)"),
    current_user: User = Depends(get_current_user),
):
    """Get data health report for a given date."""
    from api.services.daily_health_report import build_health_report
    from datetime import date as _date, datetime as _dt
    target = _dt.strptime(date, '%Y-%m-%d').date() if date else _date.today()
    return build_health_report(target)


@router.post('/data-health/push')
async def push_data_health(
    date: str = Query(None, description="Target date YYYY-MM-DD (default: today)"),
    current_user: User = Depends(get_current_user),
):
    """Build data health report and push to Feishu bot."""
    from api.services.daily_health_report import push_health_report
    from datetime import date as _date, datetime as _dt
    target = _dt.strptime(date, '%Y-%m-%d').date() if date else _date.today()
    return push_health_report(target)
