# -*- coding: utf-8 -*-
"""SimPool REST API router."""

import logging
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from api.services.sim_pool_service import SimPoolService

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/sim-pool', tags=['sim-pool'])

_svc = SimPoolService()


# ------------------------------------------------------------------
# Request / Response models
# ------------------------------------------------------------------

class CreatePoolRequest(BaseModel):
    strategy_type: str = Field(..., description="momentum | industry | micro_cap")
    signal_date: str = Field(..., description="YYYY-MM-DD, the screening date")
    config: dict = Field(default_factory=dict,
                         description="SimPoolConfig overrides + strategy_params")


class CreatePoolResponse(BaseModel):
    task_id: str
    message: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    result: Optional[dict] = None


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.get('', summary="List all sim pools")
def list_pools(
    strategy_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    """List simulation pools, optionally filtered by strategy_type or status."""
    pools = _svc.list_pools(strategy_type=strategy_type, status=status)
    return {'pools': pools, 'total': len(pools)}


@router.post('', response_model=CreatePoolResponse, summary="Create a new sim pool")
def create_pool(body: CreatePoolRequest):
    """
    Trigger async pool creation:
    1. Dispatch Celery task to run strategy screening + create pool
    2. Return task_id for polling
    """
    valid_types = {'momentum', 'industry', 'micro_cap'}
    if body.strategy_type not in valid_types:
        raise HTTPException(400, detail=f"strategy_type must be one of {valid_types}")

    try:
        task_id = _svc.trigger_create_pool(
            strategy_type=body.strategy_type,
            signal_date=body.signal_date,
            config_dict=body.config,
            user_id=0,  # TODO: inject from JWT when auth added
        )
    except Exception as e:
        logger.exception('[SimPool] create_pool failed: %s', e)
        raise HTTPException(500, detail=str(e))

    return CreatePoolResponse(
        task_id=task_id,
        message='Pool creation task dispatched. Poll /api/sim-pool/tasks/{task_id} for status.',
    )


@router.get('/tasks/{task_id}', response_model=TaskStatusResponse,
            summary="Poll Celery task status")
def get_task_status(task_id: str):
    result = _svc.get_task_result(task_id)
    return result


@router.get('/{pool_id}', summary="Get pool detail")
def get_pool(pool_id: int):
    pool = _svc.get_pool(pool_id)
    if not pool:
        raise HTTPException(404, detail=f'Pool {pool_id} not found')
    return pool


@router.get('/{pool_id}/positions', summary="Get pool positions")
def get_positions(
    pool_id: int,
    status: Optional[str] = Query(None, description="open | exited | all"),
):
    pool = _svc.get_pool(pool_id)
    if not pool:
        raise HTTPException(404, detail=f'Pool {pool_id} not found')
    positions = _svc.get_positions(pool_id, status=status if status != 'all' else None)
    return {'pool_id': pool_id, 'positions': positions, 'total': len(positions)}


@router.get('/{pool_id}/nav', summary="Get daily NAV series")
def get_nav(
    pool_id: int,
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
):
    pool = _svc.get_pool(pool_id)
    if not pool:
        raise HTTPException(404, detail=f'Pool {pool_id} not found')

    start = date.fromisoformat(start_date) if start_date else None
    end = date.fromisoformat(end_date) if end_date else None

    nav_series = _svc.get_nav_series(pool_id, start_date=start, end_date=end)
    benchmark_series = _svc.get_benchmark_nav_series(pool_id)
    return {
        'pool_id': pool_id,
        'nav': nav_series,
        'benchmark': benchmark_series,
    }


@router.get('/{pool_id}/reports', summary="List performance reports")
def list_reports(
    pool_id: int,
    report_type: Optional[str] = Query(None, description="daily | weekly | final"),
):
    pool = _svc.get_pool(pool_id)
    if not pool:
        raise HTTPException(404, detail=f'Pool {pool_id} not found')
    reports = _svc.list_reports(pool_id, report_type=report_type)
    return {'pool_id': pool_id, 'reports': reports, 'total': len(reports)}


@router.get('/{pool_id}/reports/{report_date}/{report_type}',
            summary="Get specific report")
def get_report(pool_id: int, report_date: str, report_type: str):
    pool = _svc.get_pool(pool_id)
    if not pool:
        raise HTTPException(404, detail=f'Pool {pool_id} not found')
    try:
        rd = date.fromisoformat(report_date)
    except ValueError:
        raise HTTPException(400, detail='report_date must be YYYY-MM-DD')
    report = _svc.get_report(pool_id, rd, report_type)
    if not report:
        raise HTTPException(404, detail='Report not found')
    return report


@router.get('/{pool_id}/trades', summary="Get trade log")
def get_trades(pool_id: int):
    pool = _svc.get_pool(pool_id)
    if not pool:
        raise HTTPException(404, detail=f'Pool {pool_id} not found')
    trades = _svc.get_trade_log(pool_id)
    return {'pool_id': pool_id, 'trades': trades, 'total': len(trades)}


@router.post('/{pool_id}/close', summary="Force close pool")
def close_pool(pool_id: int):
    pool = _svc.get_pool(pool_id)
    if not pool:
        raise HTTPException(404, detail=f'Pool {pool_id} not found')
    if pool.get('status') == 'closed':
        raise HTTPException(400, detail='Pool is already closed')
    try:
        _svc.force_close_pool(pool_id)
    except Exception as e:
        logger.exception('[SimPool] force close pool %d failed: %s', pool_id, e)
        raise HTTPException(500, detail=str(e))
    return {'pool_id': pool_id, 'status': 'closed', 'message': 'Pool force-closed successfully'}
