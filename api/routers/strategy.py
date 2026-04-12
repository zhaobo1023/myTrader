# -*- coding: utf-8 -*-
"""
Strategy & Backtest router
"""
import logging

from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.middleware.auth import get_current_user
from api.models.user import User
from api.schemas.strategy import (
    BacktestSubmitRequest,
    BacktestSubmitResponse,
    BacktestStatusResponse,
    StrategyResponse,
    StrategyCreateRequest,
    PresetStrategyCard,
    PresetRunDetail,
)
from api.services import backtest_service
from api.services import preset_strategy_service

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/strategy', tags=['strategy'])


@router.post('/backtest', response_model=BacktestSubmitResponse)
async def submit_backtest(
    req: BacktestSubmitRequest,
    current_user: User = Depends(get_current_user),
):
    """Submit a backtest job. Returns job_id for status tracking."""
    params = req.model_dump()
    try:
        result = backtest_service.submit_backtest(current_user.id, params)
        return result
    except Exception as e:
        logger.error('[BACKTEST] Submit failed: %s', e)
        raise HTTPException(status_code=500, detail=f'Backtest submit failed: {str(e)}')


@router.get('/backtest/{job_id}', response_model=BacktestStatusResponse)
async def get_backtest_status(
    job_id: int,
    current_user: User = Depends(get_current_user),
):
    """Get backtest job status and results."""
    status = backtest_service.get_backtest_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail=f'Backtest job {job_id} not found')
    return status


@router.get('/backtest/{job_id}/sse')
async def backtest_sse(
    job_id: int,
    current_user: User = Depends(get_current_user),
):
    """SSE endpoint for real-time backtest progress updates."""
    import asyncio
    import json
    from fastapi.responses import StreamingResponse

    async def event_generator():
        max_polls = 120  # 2 minutes timeout at 1s interval
        for _ in range(max_polls):
            status = backtest_service.get_backtest_status(job_id)
            if not status:
                yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                break

            yield f"data: {json.dumps(status, default=str)}\n\n"

            if status['status'] in ('done', 'failed'):
                break

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )


@router.get('/backtests')
async def list_backtests(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """List recent backtest jobs for current user."""
    jobs = backtest_service.get_user_backtests(current_user.id, limit)
    return {'count': len(jobs), 'data': jobs}


@router.get('/strategies', response_model=list[StrategyResponse])
async def list_strategies(
    current_user: User = Depends(get_current_user),
):
    """List all strategies for current user."""
    strategies = backtest_service.get_user_strategies(current_user.id)
    return strategies


@router.post('/strategies')
async def create_strategy(
    req: StrategyCreateRequest,
    current_user: User = Depends(get_current_user),
):
    """Create a new strategy."""
    strategy_id = backtest_service.create_strategy(
        user_id=current_user.id,
        name=req.name,
        description=req.description,
        params=req.params,
    )
    return {'id': strategy_id, 'message': 'Strategy created'}


# ---------------------------------------------------------------------------
# Preset strategy endpoints
# ---------------------------------------------------------------------------

@router.get('/preset', response_model=list[PresetStrategyCard])
async def list_preset_strategies():
    """List all preset strategies with today's run and recent runs."""
    try:
        return preset_strategy_service.list_preset_strategies()
    except Exception as e:
        logger.error('[PRESET] list failed: %s', e)
        raise HTTPException(status_code=500, detail=f'Failed to list preset strategies: {str(e)}')


@router.post('/preset/{key}/trigger')
async def trigger_preset_strategy(key: str):
    """Trigger today's run for a preset strategy."""
    return preset_strategy_service.trigger_strategy_run(key)


@router.get('/preset/{key}/runs/{run_id}', response_model=PresetRunDetail)
async def get_preset_run_detail(key: str, run_id: int):
    """Get full run detail including signals list."""
    detail = preset_strategy_service.get_run_detail(run_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f'Run {run_id} not found')
    return detail
