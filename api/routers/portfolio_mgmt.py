# -*- coding: utf-8 -*-
"""
Portfolio Management router
GET/POST/PUT/DELETE /api/portfolio-mgmt/*
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.schemas.portfolio_mgmt import (
    PortfolioStockIn,
    PortfolioStockRow,
    TriggerPriceRow,
    OptimizerResult,
    PortfolioOverview,
)
from api.services import portfolio_mgmt_service as svc
from api.models.user import User
from api.middleware.auth import get_current_user

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/portfolio-mgmt', tags=['portfolio-mgmt'])


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

@router.get('/overview', response_model=PortfolioOverview)
async def get_overview(current_user: User = Depends(get_current_user)):
    """Portfolio overview: metrics, industry breakdown, bubble chart data."""
    try:
        data = svc.get_portfolio_overview(current_user.id)
        return data
    except Exception as e:
        logger.error('[PORTFOLIO_MGMT] overview failed: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


# ---------------------------------------------------------------------------
# Stock CRUD
# ---------------------------------------------------------------------------

@router.get('/stocks')
async def list_stocks(current_user: User = Depends(get_current_user)):
    """List all portfolio stocks with computed returns and factor scores."""
    try:
        stocks = svc.get_enriched_stocks(current_user.id)
        return {'data': stocks}
    except Exception as e:
        logger.error('[PORTFOLIO_MGMT] list_stocks failed: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.post('/stocks', status_code=201)
async def create_stock(payload: PortfolioStockIn, current_user: User = Depends(get_current_user)):
    """Add a new stock to the portfolio."""
    existing = svc.get_stock(payload.stock_code, current_user.id)
    if existing:
        raise HTTPException(status_code=409, detail=f'Stock {payload.stock_code} already exists')
    try:
        record = svc.upsert_stock(payload.model_dump(), current_user.id)
        return record
    except Exception as e:
        logger.error('[PORTFOLIO_MGMT] create_stock failed: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.put('/stocks/{code}')
async def update_stock(code: str, payload: PortfolioStockIn, current_user: User = Depends(get_current_user)):
    """Update valuation assumptions for a portfolio stock."""
    existing = svc.get_stock(code, current_user.id)
    if not existing:
        raise HTTPException(status_code=404, detail=f'Stock {code} not found')
    data = payload.model_dump()
    data['stock_code'] = code
    try:
        record = svc.upsert_stock(data, current_user.id)
        return record
    except Exception as e:
        logger.error('[PORTFOLIO_MGMT] update_stock failed: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.delete('/stocks/{code}')
async def delete_stock(code: str, current_user: User = Depends(get_current_user)):
    """Remove a stock from the portfolio."""
    found = svc.delete_stock(code, current_user.id)
    if not found:
        raise HTTPException(status_code=404, detail=f'Stock {code} not found')
    return {'deleted': code}


# ---------------------------------------------------------------------------
# Trigger prices
# ---------------------------------------------------------------------------

@router.get('/trigger-prices')
async def get_trigger_prices(current_user: User = Depends(get_current_user)):
    """Fetch latest market caps and compute buy/sell trigger prices."""
    try:
        stocks = svc.list_stocks(current_user.id)
        rows = []
        for s in stocks:
            mktcap = s.get('market_cap')
            tp = svc.calc_trigger_prices(s, mktcap)
            rows.append({
                'stock_code': s['stock_code'],
                'stock_name': s.get('stock_name', ''),
                'market_cap': mktcap,
                **tp,
            })
        return {'data': rows}
    except Exception as e:
        logger.error('[PORTFOLIO_MGMT] trigger_prices failed: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


# ---------------------------------------------------------------------------
# Optimizer
# ---------------------------------------------------------------------------

@router.post('/optimize')
async def run_optimize(current_user: User = Depends(get_current_user)):
    """Run the portfolio optimizer and persist the result."""
    try:
        result = svc.run_full_optimize(current_user.id)
        return result
    except Exception as e:
        logger.error('[PORTFOLIO_MGMT] optimize failed: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.get('/optimizer-runs')
async def list_optimizer_runs(limit: int = Query(default=10, le=50), current_user: User = Depends(get_current_user)):
    """List recent optimizer run summaries."""
    try:
        runs = svc.list_optimizer_runs(current_user.id, limit)
        return {'data': runs}
    except Exception as e:
        logger.error('[PORTFOLIO_MGMT] list_runs failed: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')
