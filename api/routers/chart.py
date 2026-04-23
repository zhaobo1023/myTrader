# -*- coding: utf-8 -*-
"""
Chart Router - K-line + technical indicator endpoints

Endpoints:
  GET /api/chart/kline/{stock_code}  - K-line data (daily/weekly/monthly)
  GET /api/chart/indicators/{stock_code}  - Technical indicators
  GET /api/chart/combined/{stock_code}  - Merged K-line + indicators
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Depends

from api.middleware.auth import get_current_user
from api.models.user import User
from api.services import chart_service as svc

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/chart', tags=['chart'])


@router.get('/kline/{stock_code}')
async def get_kline(
    stock_code: str,
    period: str = Query(default='daily', description='daily|weekly|monthly'),
    limit: int = Query(default=500, ge=30, le=2000),
    current_user: User = Depends(get_current_user),
):
    """K-line OHLCV data for a stock."""
    if period not in ('daily', 'weekly', 'monthly'):
        raise HTTPException(status_code=400, detail='period must be daily|weekly|monthly')
    try:
        return svc.get_kline_data(stock_code, period=period, limit=limit)
    except Exception as e:
        logger.error('[chart] get_kline error: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.get('/indicators/{stock_code}')
async def get_indicators(
    stock_code: str,
    limit: int = Query(default=500, ge=30, le=2000),
    current_user: User = Depends(get_current_user),
):
    """Precomputed technical indicators (MA/MACD/RSI/KDJ/BOLL)."""
    try:
        return svc.get_technical_indicators(stock_code, limit=limit)
    except Exception as e:
        logger.error('[chart] get_indicators error: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')


@router.get('/combined/{stock_code}')
async def get_combined(
    stock_code: str,
    period: str = Query(default='daily', description='daily|weekly|monthly'),
    limit: int = Query(default=500, ge=30, le=2000),
    current_user: User = Depends(get_current_user),
):
    """Merged K-line + technical indicators (primary endpoint for chart)."""
    if period not in ('daily', 'weekly', 'monthly'):
        raise HTTPException(status_code=400, detail='period must be daily|weekly|monthly')
    try:
        return svc.get_kline_with_indicators(stock_code, period=period, limit=limit)
    except Exception as e:
        logger.error('[chart] get_combined error: %s', e)
        raise HTTPException(status_code=500, detail='Internal server error')
