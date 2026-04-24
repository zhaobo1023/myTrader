# -*- coding: utf-8 -*-
"""
Candidate Pool Router

Endpoints:
  GET    /api/candidate-pool/stocks             - list all stocks
  POST   /api/candidate-pool/stocks             - add stock
  PATCH  /api/candidate-pool/stocks/{code}      - update status/memo
  DELETE /api/candidate-pool/stocks/{code}      - remove stock
  GET    /api/candidate-pool/stocks/{code}/history  - monitor history
  POST   /api/candidate-pool/stocks/{code}/refresh  - refresh single stock

  GET    /api/candidate-pool/industries         - list all SW industries
  GET    /api/candidate-pool/industry-stocks    - screen stocks in an industry

  GET    /api/candidate-pool/tags               - list tags
  POST   /api/candidate-pool/tags               - create tag
  DELETE /api/candidate-pool/tags/{tag_id}      - delete tag
  POST   /api/candidate-pool/stocks/{stock_id}/tags     - tag a stock
  DELETE /api/candidate-pool/stocks/{stock_id}/tags/{tag_id}  - untag

  POST   /api/candidate-pool/monitor/trigger    - manual trigger daily monitor
  GET    /api/candidate-pool/monitor/latest     - latest monitor summary
  POST   /api/candidate-pool/monitor/push       - push Feishu report now
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel

from api.middleware.auth import get_current_user
from api.models.user import User
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


class CreateTagRequest(BaseModel):
    name: str
    color: Optional[str] = '#5e6ad2'


class TagStockRequest(BaseModel):
    tag_id: int


# ---------------------------------------------------------------------------
# Stock CRUD
# ---------------------------------------------------------------------------

@router.get('/stocks')
async def list_stocks(
    status: Optional[str] = Query(None, description='watching|focused|excluded'),
    source_type: Optional[str] = Query(None, description='industry|strategy|manual'),
    tag_id: Optional[int] = Query(None, description='filter by tag id'),
    current_user: User = Depends(get_current_user),
):
    """List all candidate pool stocks with latest monitor snapshot and tags."""
    try:
        data = svc.list_stocks_with_tags(
            current_user.id, tag_id=tag_id, status=status, source_type=source_type,
        )
        return {'count': len(data), 'data': data}
    except Exception as e:
        logger.error('[candidate_pool] list_stocks error: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.post('/stocks')
async def add_stock(
    body: AddStockRequest,
    current_user: User = Depends(get_current_user),
):
    """Add a stock to the candidate pool."""
    valid_sources = {'industry', 'strategy', 'manual'}
    if body.source_type not in valid_sources:
        raise HTTPException(status_code=400, detail=f'source_type must be one of {valid_sources}')
    try:
        result = svc.add_stock(
            user_id=current_user.id,
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
async def update_stock(
    stock_code: str,
    body: UpdateStockRequest,
    current_user: User = Depends(get_current_user),
):
    """Update stock status or memo."""
    valid_statuses = {'watching', 'focused', 'excluded', None}
    if body.status not in valid_statuses:
        raise HTTPException(status_code=400, detail='Invalid status value')
    try:
        ok = svc.update_stock(current_user.id, stock_code, status=body.status, memo=body.memo)
        return {'success': ok}
    except Exception as e:
        logger.error('[candidate_pool] update_stock error: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.delete('/stocks/{stock_code}')
async def remove_stock(
    stock_code: str,
    current_user: User = Depends(get_current_user),
):
    """Remove a stock from the candidate pool."""
    try:
        svc.remove_stock(current_user.id, stock_code)
        return {'success': True, 'stock_code': stock_code}
    except Exception as e:
        logger.error('[candidate_pool] remove_stock error: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.get('/stocks/{stock_code}/history')
async def get_stock_history(
    stock_code: str,
    days: int = Query(default=30, ge=1, le=120),
    current_user: User = Depends(get_current_user),
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
async def list_industries(
    current_user: User = Depends(get_current_user),
):
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
    current_user: User = Depends(get_current_user),
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
# Tags
# ---------------------------------------------------------------------------

@router.get('/tags')
async def list_tags(
    current_user: User = Depends(get_current_user),
):
    """List all tags for the current user."""
    try:
        data = svc.list_tags(current_user.id)
        return {'count': len(data), 'data': data}
    except Exception as e:
        logger.error('[candidate_pool] list_tags error: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.post('/tags')
async def create_tag(
    body: CreateTagRequest,
    current_user: User = Depends(get_current_user),
):
    """Create a new tag."""
    if not body.name.strip():
        raise HTTPException(status_code=400, detail='Tag name cannot be empty')
    try:
        result = svc.create_tag(current_user.id, body.name.strip(), body.color or '#5e6ad2')
        return result
    except Exception as e:
        logger.error('[candidate_pool] create_tag error: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.delete('/tags/{tag_id}')
async def delete_tag(
    tag_id: int,
    current_user: User = Depends(get_current_user),
):
    """Delete a tag and remove all associations."""
    try:
        svc.delete_tag(current_user.id, tag_id)
        return {'success': True}
    except Exception as e:
        logger.error('[candidate_pool] delete_tag error: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.post('/stocks/{stock_id}/tags')
async def tag_stock(
    stock_id: int,
    body: TagStockRequest,
    current_user: User = Depends(get_current_user),
):
    """Add a tag to a stock."""
    try:
        ok = svc.tag_stock(current_user.id, stock_id, body.tag_id)
        if not ok:
            raise HTTPException(status_code=403, detail='Tag or stock not found or not owned by user')
        return {'success': True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error('[candidate_pool] tag_stock error: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.delete('/stocks/{stock_id}/tags/{tag_id}')
async def untag_stock(
    stock_id: int,
    tag_id: int,
    current_user: User = Depends(get_current_user),
):
    """Remove a tag from a stock."""
    try:
        svc.untag_stock(current_user.id, stock_id, tag_id)
        return {'success': True}
    except Exception as e:
        logger.error('[candidate_pool] untag_stock error: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


# ---------------------------------------------------------------------------
# Single stock refresh
# ---------------------------------------------------------------------------

@router.post('/stocks/{stock_code}/refresh')
async def refresh_single_stock(
    stock_code: str,
    current_user: User = Depends(get_current_user),
):
    """Refresh monitor data for a single stock."""
    try:
        result = svc.refresh_single_stock(stock_code, current_user.id)
        return {'success': True, 'data': result}
    except Exception as e:
        logger.error('[candidate_pool] refresh_single_stock error: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------

@router.post('/monitor/trigger')
async def trigger_monitor(
    current_user: User = Depends(get_current_user),
):
    """Manually trigger daily monitor computation."""
    try:
        result = svc.run_daily_monitor()
        return result
    except Exception as e:
        logger.error('[candidate_pool] trigger_monitor error: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.get('/monitor/latest')
async def get_latest_monitor(
    current_user: User = Depends(get_current_user),
):
    """Return latest monitor snapshot summary."""
    try:
        stocks = svc.list_stocks(current_user.id)
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
async def push_feishu(
    current_user: User = Depends(get_current_user),
):
    """Push today's monitor report to Feishu."""
    try:
        ok = svc.push_feishu_daily_report()
        return {'success': ok}
    except Exception as e:
        logger.error('[candidate_pool] push_feishu error: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')
