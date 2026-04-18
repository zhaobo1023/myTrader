# -*- coding: utf-8 -*-
"""
Candidate Pool Router

Endpoints:
  GET    /api/candidate-pool/stocks             - list all stocks
  POST   /api/candidate-pool/stocks             - add stock
  PATCH  /api/candidate-pool/stocks/{code}      - update status/memo
  DELETE /api/candidate-pool/stocks/{code}      - remove stock
  GET    /api/candidate-pool/stocks/{code}/history  - monitor history

  GET    /api/candidate-pool/industries         - list all SW industries
  GET    /api/candidate-pool/industry-stocks    - screen stocks in an industry

  POST   /api/candidate-pool/monitor/trigger    - manual trigger daily monitor
  GET    /api/candidate-pool/monitor/latest     - latest monitor summary
  POST   /api/candidate-pool/monitor/push       - push Feishu report now
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.services import candidate_pool_service as svc

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/candidate-pool', tags=['candidate-pool'])


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class AddStockRequest(BaseModel):
    stock_code: str
    stock_name: str
    source_type: str           # 'industry' | 'strategy' | 'manual'
    source_detail: Optional[str] = None
    entry_snapshot: Optional[dict] = None
    memo: Optional[str] = None


class UpdateStockRequest(BaseModel):
    status: Optional[str] = None    # 'watching' | 'focused' | 'excluded'
    memo: Optional[str] = None


# ---------------------------------------------------------------------------
# Stock CRUD
# ---------------------------------------------------------------------------

@router.get('/stocks')
async def list_stocks(
    status: Optional[str] = Query(None, description='watching|focused|excluded'),
    source_type: Optional[str] = Query(None, description='industry|strategy|manual'),
):
    """List all candidate pool stocks with latest monitor snapshot."""
    try:
        data = svc.list_stocks(status=status, source_type=source_type)
        return {'count': len(data), 'data': data}
    except Exception as e:
        logger.error('[candidate_pool] list_stocks error: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.post('/stocks')
async def add_stock(body: AddStockRequest):
    """Add a stock to the candidate pool."""
    valid_sources = {'industry', 'strategy', 'manual'}
    if body.source_type not in valid_sources:
        raise HTTPException(status_code=400, detail=f'source_type must be one of {valid_sources}')
    try:
        result = svc.add_stock(
            stock_code=body.stock_code,
            stock_name=body.stock_name,
            source_type=body.source_type,
            source_detail=body.source_detail,
            entry_snapshot=body.entry_snapshot,
            memo=body.memo,
        )
        return result
    except Exception as e:
        logger.error('[candidate_pool] add_stock error: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.patch('/stocks/{stock_code}')
async def update_stock(stock_code: str, body: UpdateStockRequest):
    """Update stock status or memo."""
    valid_statuses = {'watching', 'focused', 'excluded', None}
    if body.status not in valid_statuses:
        raise HTTPException(status_code=400, detail='Invalid status value')
    try:
        ok = svc.update_stock(stock_code, status=body.status, memo=body.memo)
        return {'success': ok}
    except Exception as e:
        logger.error('[candidate_pool] update_stock error: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.delete('/stocks/{stock_code}')
async def remove_stock(stock_code: str):
    """Remove a stock from the candidate pool."""
    try:
        svc.remove_stock(stock_code)
        return {'success': True, 'stock_code': stock_code}
    except Exception as e:
        logger.error('[candidate_pool] remove_stock error: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.get('/stocks/{stock_code}/history')
async def get_stock_history(
    stock_code: str,
    days: int = Query(default=30, ge=1, le=120),
):
    """Return daily monitor history for a stock."""
    try:
        data = svc.get_stock_history(stock_code, days=days)
        return {'stock_code': stock_code, 'count': len(data), 'data': data}
    except Exception as e:
        logger.error('[candidate_pool] get_stock_history error: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


# ---------------------------------------------------------------------------
# Industry screening
# ---------------------------------------------------------------------------

@router.get('/industries')
async def list_industries():
    """List all available SW industry names (from AKShare)."""
    try:
        data = svc.list_industries()
        return {'count': len(data), 'data': data}
    except Exception as e:
        logger.error('[candidate_pool] list_industries error: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.get('/industry-stocks')
async def get_industry_stocks(
    industry_name: str = Query(..., description='e.g. 通信'),
    min_rps: float = Query(default=0, ge=0, le=100),
    sort_by: str = Query(default='rps_250', description='rps_250|rps_120|rps_20|rps_slope'),
    limit: int = Query(default=100, ge=1, le=500),
):
    """Screen stocks in a given industry with RPS + price data."""
    try:
        data = svc.get_industry_stocks(
            industry_name=industry_name,
            min_rps=min_rps,
            sort_by=sort_by,
            limit=limit,
        )
        return {
            'industry_name': industry_name,
            'count': len(data),
            'data': data,
        }
    except Exception as e:
        logger.error('[candidate_pool] get_industry_stocks error: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------

@router.post('/monitor/trigger')
async def trigger_monitor():
    """Manually trigger daily monitor computation."""
    try:
        result = svc.run_daily_monitor()
        return result
    except Exception as e:
        logger.error('[candidate_pool] trigger_monitor error: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.get('/monitor/latest')
async def get_latest_monitor():
    """Return latest monitor snapshot summary."""
    try:
        stocks = svc.list_stocks()
        from collections import Counter
        alert_counts = Counter(s.get('alert_level', 'info') for s in stocks if s.get('monitor_date'))
        return {
            'total': len(stocks),
            'alert_counts': dict(alert_counts),
            'stocks': stocks,
        }
    except Exception as e:
        logger.error('[candidate_pool] get_latest_monitor error: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.post('/monitor/push')
async def push_feishu():
    """Push today's monitor report to Feishu."""
    try:
        ok = svc.push_feishu_daily_report()
        return {'success': ok}
    except Exception as e:
        logger.error('[candidate_pool] push_feishu error: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')
