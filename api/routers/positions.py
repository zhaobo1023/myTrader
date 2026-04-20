# -*- coding: utf-8 -*-
"""
Positions router - user portfolio positions CRUD
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.dependencies import get_db
from api.models.user import User
from api.models.user_position import UserPosition
from api.middleware.auth import get_current_user
from api.schemas.positions import (
    PositionCreate,
    PositionUpdate,
    PositionResponse,
    PositionListResponse,
    PositionImportRequest,
)

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/positions', tags=['positions'])


def _to_response(p: UserPosition) -> PositionResponse:
    return PositionResponse(
        id=p.id,
        stock_code=p.stock_code,
        stock_name=p.stock_name,
        level=p.level,
        shares=p.shares,
        cost_price=p.cost_price,
        account=p.account,
        note=p.note,
        is_active=p.is_active,
        created_at=p.created_at.isoformat() if p.created_at else '',
        updated_at=p.updated_at.isoformat() if p.updated_at else '',
    )


@router.get('', response_model=PositionListResponse)
async def list_positions(
    level: Optional[str] = Query(default=None, description='Filter by level: L1/L2/L3'),
    active_only: bool = Query(default=True, description='Only active positions'),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List user's positions, optionally filtered by level."""
    query = select(UserPosition).where(UserPosition.user_id == current_user.id)
    if active_only:
        query = query.where(UserPosition.is_active == True)
    if level:
        query = query.where(UserPosition.level == level)
    query = query.order_by(UserPosition.level, UserPosition.stock_code)

    result = await db.execute(query)
    items = result.scalars().all()
    return PositionListResponse(
        items=[_to_response(p) for p in items],
        total=len(items),
    )


@router.post('', response_model=PositionResponse, status_code=status.HTTP_201_CREATED)
async def create_position(
    req: PositionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a new position."""
    # Check for duplicate (same user + stock_code + account)
    existing = await db.execute(
        select(UserPosition).where(
            UserPosition.user_id == current_user.id,
            UserPosition.stock_code == req.stock_code,
            UserPosition.account == req.account,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'{req.stock_code} already exists in positions',
        )

    position = UserPosition(
        user_id=current_user.id,
        stock_code=req.stock_code,
        stock_name=req.stock_name,
        level=req.level,
        shares=req.shares,
        cost_price=req.cost_price,
        account=req.account,
        note=req.note,
    )
    db.add(position)
    await db.flush()
    await db.refresh(position)
    logger.info('[POSITIONS] user=%s added stock=%s', current_user.id, req.stock_code)
    return _to_response(position)


@router.put('/{position_id}', response_model=PositionResponse)
async def update_position(
    position_id: int,
    req: PositionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a position."""
    result = await db.execute(
        select(UserPosition).where(
            UserPosition.id == position_id,
            UserPosition.user_id == current_user.id,
        )
    )
    position = result.scalar_one_or_none()
    if not position:
        raise HTTPException(status_code=404, detail='Position not found')

    update_data = req.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(position, key, value)

    return _to_response(position)


@router.delete('/{position_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_position(
    position_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Soft-delete a position (set is_active=False)."""
    result = await db.execute(
        select(UserPosition).where(
            UserPosition.id == position_id,
            UserPosition.user_id == current_user.id,
        )
    )
    position = result.scalar_one_or_none()
    if not position:
        raise HTTPException(status_code=404, detail='Position not found')
    position.is_active = False
    logger.info('[POSITIONS] user=%s deactivated position=%s', current_user.id, position_id)


@router.post('/risk-scan')
async def risk_scan(
    current_user: User = Depends(get_current_user),
):
    """Trigger a risk scan for the current user's portfolio."""
    import asyncio

    def _do_scan(user_id: int):
        import sys
        import os
        # Add trader project to path for risk_manager.scanner
        trader_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'trader')
        trader_path = os.path.normpath(trader_path)
        if trader_path not in sys.path:
            sys.path.insert(0, trader_path)

        from risk_manager.scanner import scan_portfolio
        return scan_portfolio(user_id=user_id, env='online')

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _do_scan, current_user.id)
        return result
    except Exception as exc:
        logger.error('[POSITIONS] risk_scan failed for user=%s: %s', current_user.id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post('/import', status_code=status.HTTP_201_CREATED)
async def import_positions(
    req: PositionImportRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Bulk import positions from JSON."""
    created = 0
    skipped = 0
    for item in req.items:
        existing = await db.execute(
            select(UserPosition).where(
                UserPosition.user_id == current_user.id,
                UserPosition.stock_code == item.stock_code,
                UserPosition.account == item.account,
            )
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        position = UserPosition(
            user_id=current_user.id,
            stock_code=item.stock_code,
            stock_name=item.stock_name,
            level=item.level,
            shares=item.shares,
            cost_price=item.cost_price,
            account=item.account,
            note=item.note,
        )
        db.add(position)
        created += 1

    await db.flush()
    logger.info('[POSITIONS] user=%s imported %s positions (%s skipped)', current_user.id, created, skipped)
    return {'created': created, 'skipped': skipped}
