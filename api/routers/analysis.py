# -*- coding: utf-8 -*-
"""
Analysis router - technical and fundamental analysis endpoints
"""
import logging

from fastapi import APIRouter, HTTPException, Query, Depends

from api.schemas.analysis import TechnicalAnalysisResponse, FundamentalAnalysisResponse
from api.services import analysis_service
from api.middleware.auth import get_current_user
from api.models.user import User

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/analysis', tags=['analysis'])


@router.get('/technical', response_model=TechnicalAnalysisResponse)
async def technical_analysis(
    code: str = Query(..., description="Stock code"),
    current_user: User = Depends(get_current_user),
):
    """Generate technical analysis report for a stock. Requires authentication."""
    result = await analysis_service.get_technical_analysis(code)
    if not result.get('trade_date'):
        raise HTTPException(status_code=404, detail=f'No data found for stock {code}')
    return result


@router.get('/fundamental', response_model=FundamentalAnalysisResponse)
async def fundamental_analysis(
    code: str = Query(..., description="Stock code"),
    current_user: User = Depends(get_current_user),
):
    """Generate fundamental analysis report for a stock. Requires authentication."""
    result = await analysis_service.get_fundamental_analysis(code)
    return result
