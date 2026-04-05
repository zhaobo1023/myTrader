# -*- coding: utf-8 -*-
"""
Portfolio router - holdings aggregation, PnL
"""
import logging

from fastapi import APIRouter, Query, Depends

from api.middleware.auth import get_current_user
from api.models.user import User
from api.services import portfolio_service

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/portfolio', tags=['portfolio'])


@router.get('/summary')
async def get_portfolio_summary(
    current_user: User = Depends(get_current_user),
):
    """Get portfolio summary with all holdings, PnL, and total value."""
    return await portfolio_service.get_portfolio_summary(current_user.id)


@router.get('/history')
async def get_portfolio_history(
    days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
):
    """Get portfolio value history for PnL chart."""
    return await portfolio_service.get_portfolio_history(current_user.id, days)
