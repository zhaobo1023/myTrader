# -*- coding: utf-8 -*-
"""
Industry router: SW rotation + ETF log bias
"""
import logging

from fastapi import APIRouter, HTTPException, Query

from api.services import sw_rotation_service
from api.services import log_bias_service

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/industry', tags=['industry'])


@router.get('/sw-rotation/runs')
async def list_runs(limit: int = 5):
    """Return recent N rotation run summaries."""
    try:
        return {'data': sw_rotation_service.list_runs(limit)}
    except Exception as e:
        logger.error('[SW_ROTATION] list_runs failed: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.post('/sw-rotation/trigger')
async def trigger_run():
    """Trigger a new rotation analysis for the current week."""
    return sw_rotation_service.trigger_run()


@router.post('/sw-rotation/force-trigger')
async def force_trigger_run():
    """
    Force re-run even if already completed.

    WARNING: This will delete the existing result and re-calculate.
    Use with caution - typically only needed after code/logic fixes.
    """
    return sw_rotation_service.force_trigger_run()


@router.get('/sw-rotation/runs/{run_id}')
async def get_run_detail(run_id: int):
    """Get run detail including per-industry scores."""
    detail = sw_rotation_service.get_run_detail(run_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f'Run {run_id} not found')
    return detail


# ---------------------------------------------------------------------------
# ETF Log Bias endpoints
# ---------------------------------------------------------------------------

@router.get('/log-bias/latest')
async def get_log_bias_latest():
    """Return latest trade date log_bias snapshot for all tracked ETFs."""
    try:
        return {'data': log_bias_service.get_latest()}
    except Exception as e:
        logger.error('[LOG_BIAS] get_latest failed: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.get('/log-bias/run-status')
async def get_log_bias_run_status():
    """Return today's log bias run status."""
    try:
        status = log_bias_service.get_run_status()
        return status or {}
    except Exception as e:
        logger.error('[LOG_BIAS] get_run_status failed: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.post('/log-bias/trigger')
async def trigger_log_bias():
    """Trigger today's ETF log bias daily calculation."""
    return log_bias_service.trigger_run(force=False)


@router.post('/log-bias/force-trigger')
async def force_trigger_log_bias():
    """
    Force re-run even if already completed.

    WARNING: This will delete the existing result and re-calculate.
    Use with caution - typically only needed after code/logic fixes.
    """
    return log_bias_service.trigger_run(force=True)


@router.get('/log-bias/history/{ts_code}')
async def get_log_bias_history(ts_code: str, days: int = 120):
    """Return log_bias history for a single ETF (default last 120 days)."""
    try:
        return {'data': log_bias_service.get_history(ts_code, days)}
    except Exception as e:
        logger.error('[LOG_BIAS] get_history failed: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')
