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
