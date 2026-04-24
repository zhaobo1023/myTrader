# -*- coding: utf-8 -*-
"""
Trade operation log router - 调仓操作日志
"""
import csv
import io
import logging
import re
from collections import Counter
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
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
    stock_code: Optional[str] = Query(default=None, max_length=20, description='Filter by stock code'),
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
    if stock_code:
        query = query.where(TradeOperationLog.stock_code == stock_code)
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


@router.get('/export')
async def export_trade_logs(
    operation_type: Optional[str] = Query(default=None, max_length=20),
    from_date: Optional[str] = Query(default=None, description='YYYY-MM-DD'),
    to_date: Optional[str] = Query(default=None, description='YYYY-MM-DD'),
    stock_code: Optional[str] = Query(default=None, max_length=20),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """导出调仓日志为 CSV 文件。"""
    _date_re = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    if from_date and not _date_re.match(from_date):
        raise HTTPException(status_code=400, detail='from_date 格式应为 YYYY-MM-DD')
    if to_date and not _date_re.match(to_date):
        raise HTTPException(status_code=400, detail='to_date 格式应为 YYYY-MM-DD')

    query = select(TradeOperationLog).where(
        TradeOperationLog.user_id == current_user.id
    )
    if operation_type:
        query = query.where(TradeOperationLog.operation_type == operation_type)
    if stock_code:
        query = query.where(TradeOperationLog.stock_code == stock_code)
    if from_date:
        query = query.where(TradeOperationLog.created_at >= f'{from_date} 00:00:00')
    if to_date:
        query = query.where(TradeOperationLog.created_at <= f'{to_date} 23:59:59')
    query = query.order_by(desc(TradeOperationLog.created_at))

    result = await db.execute(query)
    items = result.scalars().all()

    op_labels = {
        'open_position': '建仓',
        'add_reduce': '加减仓',
        'close_position': '清仓',
        'move_to_candidate': '移入候选池',
        'manual_note': '手动备注',
        'modify_info': '信息修改',
    }

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['时间', '操作类型', '股票代码', '股票名称', '操作详情', '来源'])
    for log in items:
        writer.writerow([
            log.created_at.strftime('%Y-%m-%d %H:%M:%S') if log.created_at else '',
            op_labels.get(log.operation_type, log.operation_type),
            log.stock_code or '',
            log.stock_name or '',
            log.detail or '',
            '自动' if log.source == 'auto' else '手动',
        ])

    buf.seek(0)
    filename = 'trade_logs.csv'
    return StreamingResponse(
        iter(['\ufeff' + buf.getvalue()]),
        media_type='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@router.get('/stats')
async def trade_log_stats(
    days: int = Query(default=30, ge=1, le=365),
    stock_code: Optional[str] = Query(default=None, max_length=20, description='Limit stats to one stock'),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """调仓日志统计 - 整体或按个股"""
    import json
    from datetime import datetime, timedelta

    since = datetime.utcnow() - timedelta(days=days)
    query = select(TradeOperationLog).where(
        TradeOperationLog.user_id == current_user.id,
        TradeOperationLog.created_at >= since,
    )
    if stock_code:
        query = query.where(TradeOperationLog.stock_code == stock_code)
    result = await db.execute(query)
    logs = result.scalars().all()

    type_counts = Counter(log.operation_type for log in logs)

    # Per-stock summary (top 10 by activity)
    stock_counts: dict = {}
    for log in logs:
        if log.stock_code:
            key = log.stock_code
            if key not in stock_counts:
                stock_counts[key] = {'stock_code': key, 'stock_name': log.stock_name or key, 'total': 0, 'open': 0, 'close': 0, 'add_reduce': 0}
            stock_counts[key]['total'] += 1
            if log.operation_type == 'open_position':
                stock_counts[key]['open'] += 1
            elif log.operation_type == 'close_position':
                stock_counts[key]['close'] += 1
            elif log.operation_type == 'add_reduce':
                stock_counts[key]['add_reduce'] += 1

    top_stocks = sorted(stock_counts.values(), key=lambda x: x['total'], reverse=True)[:10]

    # Close-position summary
    close_logs = [log for log in logs if log.operation_type == 'close_position']
    close_summary = {
        'count': len(close_logs),
        'stocks': list({log.stock_code: log.stock_name for log in close_logs if log.stock_code}.items())[:20],
    }

    return {
        'period_days': days,
        'stock_code': stock_code,
        'total': len(logs),
        'by_type': dict(type_counts),
        'top_stocks': top_stocks,
        'close_summary': close_summary,
    }
