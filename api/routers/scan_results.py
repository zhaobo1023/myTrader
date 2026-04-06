# api/routers/scan_results.py
# -*- coding: utf-8 -*-
from datetime import date
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.dependencies import get_db
from api.middleware.auth import get_current_user
from api.models.user import User
from api.models.scan_result import UserScanResult
from api.schemas.scan_result import ScanResultItem

router = APIRouter(prefix='/api/scan-results', tags=['scan-results'])


@router.get('', response_model=List[ScanResultItem])
async def list_scan_results(
    scan_date: Optional[date] = Query(None, description='Filter by date; omit for latest'),
    severity: Optional[str] = Query(None, description='Filter by severity: RED/YELLOW/GREEN/NONE'),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get scan results for the current user."""
    query = select(UserScanResult).where(UserScanResult.user_id == current_user.id)

    if scan_date:
        query = query.where(UserScanResult.scan_date == scan_date)
    else:
        latest_date_q = (
            select(UserScanResult.scan_date)
            .where(UserScanResult.user_id == current_user.id)
            .order_by(UserScanResult.scan_date.desc())
            .limit(1)
        )
        latest_result = await db.execute(latest_date_q)
        latest_date = latest_result.scalar_one_or_none()
        if latest_date:
            query = query.where(UserScanResult.scan_date == latest_date)

    if severity:
        query = query.where(UserScanResult.max_severity == severity.upper())

    query = query.order_by(UserScanResult.score.asc())
    result = await db.execute(query)
    return [ScanResultItem.model_validate(r) for r in result.scalars().all()]
