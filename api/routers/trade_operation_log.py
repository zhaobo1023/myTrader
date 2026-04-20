# -*- coding: utf-8 -*-
"""
Trade operation log router - 调仓操作日志
"""
import json
import logging
from typing import Optional
from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from api.dependencies import get_db
from api.models.user import User
from api.models.trade_operation_log import TradeOperationLog
from api.middleware.auth import get_current_user
from api.schemas.trade_operation_log import (
    TradeLogCreate,
    TradeLogResponse,
    TradeLogListResponse,
)

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/trade-logs', tags=['trade-logs'])


def _to_response(log: TradeOperationLog) -> TradeLogResponse:
    return TradeLogResponse(
        id=log.id,
        operation_type=log.operation_type,
        stock_code=log.stock_code,
        stock_name=log.stock_name,
        detail=log.detail,
        before_value=log.before_value,
        after_value=log.after_value,
        source=log.source,
        created_at=log.created_at.isoformat() if log.created_at else '',
    )


@router.get('', response_model=TradeLogListResponse)
async def list_trade_logs(
    operation_type: Optional[str] = Query(default=None, max_length=20),
    from_date: Optional[str] = Query(default=None, description='YYYY-MM-DD'),
    to_date: Optional[str] = Query(default=None, description='YYYY-MM-DD'),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询调仓操作日志"""
    query = select(TradeOperationLog).where(
        TradeOperationLog.user_id == current_user.id
    )

    if operation_type:
        query = query.where(TradeOperationLog.operation_type == operation_type)
    if from_date:
        query = query.where(TradeOperationLog.created_at >= f'{from_date} 00:00:00')
    if to_date:
        query = query.where(TradeOperationLog.created_at <= f'{to_date} 23:59:59')

    # Count total
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Fetch page
    query = query.order_by(desc(TradeOperationLog.created_at))
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = result.scalars().all()

    return TradeLogListResponse(
        items=[_to_response(log) for log in items],
        total=total,
    )


@router.post('', response_model=TradeLogResponse, status_code=201)
async def create_trade_log(
    req: TradeLogCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """手动添加调仓日志 (复盘/备注)"""
    log = TradeOperationLog(
        user_id=current_user.id,
        operation_type=req.operation_type or 'manual_note',
        stock_code=req.stock_code or '',
        stock_name=req.stock_name,
        detail=req.detail,
        source='manual',
    )
    db.add(log)
    await db.flush()
    await db.refresh(log)
    return _to_response(log)


@router.get('/stats')
async def trade_log_stats(
    days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """调仓日志统计"""
    from datetime import datetime, timedelta

    since = datetime.utcnow() - timedelta(days=days)
    query = select(TradeOperationLog).where(
        TradeOperationLog.user_id == current_user.id,
        TradeOperationLog.created_at >= since,
    )
    result = await db.execute(query)
    logs = result.scalars().all()

    type_counts = Counter(log.operation_type for log in logs)
    return {
        'period_days': days,
        'total': len(logs),
        'by_type': dict(type_counts),
    }
