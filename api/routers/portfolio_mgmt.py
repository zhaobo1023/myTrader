# -*- coding: utf-8 -*-
"""
Portfolio Management router
GET/POST/PUT/DELETE /api/portfolio-mgmt/*
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from api.schemas.portfolio_mgmt import (
    PortfolioStockIn,
    PortfolioStockRow,
    TriggerPriceRow,
    OptimizerResult,
    PortfolioOverview,
)
from api.services import portfolio_mgmt_service as svc

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/portfolio-mgmt', tags=['portfolio-mgmt'])

# Single-user MVP: user_id fixed to 0
_USER_ID = 0


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

@router.get('/overview', response_model=PortfolioOverview)
async def get_overview():
    """Portfolio overview: metrics, industry breakdown, bubble chart data."""
    try:
        data = svc.get_portfolio_overview(_USER_ID)
        return data
    except Exception as e:
        logger.error('[PORTFOLIO_MGMT] overview failed: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Stock CRUD
# ---------------------------------------------------------------------------

@router.get('/stocks')
async def list_stocks():
    """List all portfolio stocks with computed returns and factor scores."""
    try:
        stocks = svc.get_enriched_stocks(_USER_ID)
        return {'data': stocks}
    except Exception as e:
        logger.error('[PORTFOLIO_MGMT] list_stocks failed: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post('/stocks', status_code=201)
async def create_stock(payload: PortfolioStockIn):
    """Add a new stock to the portfolio."""
    existing = svc.get_stock(payload.stock_code, _USER_ID)
    if existing:
        raise HTTPException(status_code=409, detail=f'Stock {payload.stock_code} already exists')
    try:
        record = svc.upsert_stock(payload.model_dump(), _USER_ID)
        return record
    except Exception as e:
        logger.error('[PORTFOLIO_MGMT] create_stock failed: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


@router.put('/stocks/{code}')
async def update_stock(code: str, payload: PortfolioStockIn):
    """Update valuation assumptions for a portfolio stock."""
    existing = svc.get_stock(code, _USER_ID)
    if not existing:
        raise HTTPException(status_code=404, detail=f'Stock {code} not found')
    data = payload.model_dump()
    data['stock_code'] = code
    try:
        record = svc.upsert_stock(data, _USER_ID)
        return record
    except Exception as e:
        logger.error('[PORTFOLIO_MGMT] update_stock failed: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete('/stocks/{code}')
async def delete_stock(code: str):
    """Remove a stock from the portfolio."""
    found = svc.delete_stock(code, _USER_ID)
    if not found:
        raise HTTPException(status_code=404, detail=f'Stock {code} not found')
    return {'deleted': code}


# ---------------------------------------------------------------------------
# Trigger prices
# ---------------------------------------------------------------------------

@router.get('/trigger-prices')
async def get_trigger_prices():
    """Fetch latest market caps and compute buy/sell trigger prices."""
    try:
        stocks = svc.list_stocks(_USER_ID)
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
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Optimizer
# ---------------------------------------------------------------------------

@router.post('/optimize')
async def run_optimize():
    """Run the portfolio optimizer and persist the result."""
    try:
        result = svc.run_full_optimize(_USER_ID)
        return result
    except Exception as e:
        logger.error('[PORTFOLIO_MGMT] optimize failed: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/optimizer-runs')
async def list_optimizer_runs(limit: int = Query(default=10, le=50)):
    """List recent optimizer run summaries."""
    try:
        runs = svc.list_optimizer_runs(_USER_ID, limit)
        return {'data': runs}
    except Exception as e:
        logger.error('[PORTFOLIO_MGMT] list_runs failed: %s', e)
        raise HTTPException(status_code=500, detail=str(e))
