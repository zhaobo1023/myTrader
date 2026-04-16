# api/routers/watchlist.py
# -*- coding: utf-8 -*-
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from api.dependencies import get_db
from api.models.watchlist import UserWatchlist
from api.schemas.watchlist import WatchlistAddRequest, WatchlistItem, WatchlistResponse

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/watchlist', tags=['watchlist'])


@router.get('', response_model=WatchlistResponse)
async def list_watchlist(
    db: AsyncSession = Depends(get_db),
):
    """Get shared watchlist (no auth required)"""
    result = await db.execute(
        select(UserWatchlist)
        .order_by(UserWatchlist.added_at.desc())
    )
    items = result.scalars().all()
    return WatchlistResponse(
        items=[WatchlistItem.model_validate(i) for i in items],
        total=len(items),
    )


@router.post('', response_model=WatchlistItem, status_code=status.HTTP_201_CREATED)
async def add_to_watchlist(
    req: WatchlistAddRequest,
    db: AsyncSession = Depends(get_db),
):
    """Add stock to watchlist (no auth required, shared watchlist)"""
    existing = await db.execute(
        select(UserWatchlist).where(
            UserWatchlist.stock_code == req.stock_code,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'{req.stock_code} already in watchlist',
        )

    item = UserWatchlist(
        user_id=0,
        stock_code=req.stock_code,
        stock_name=req.stock_name,
        note=req.note,
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)
    logger.info('[WATCHLIST] added stock=%s', req.stock_code)
    return WatchlistItem.model_validate(item)


@router.delete('/{stock_code}', status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_watchlist(
    stock_code: str,
    db: AsyncSession = Depends(get_db),
):
    """Remove stock from watchlist (no auth required)"""
    result = await db.execute(
        delete(UserWatchlist).where(
            UserWatchlist.stock_code == stock_code,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail=f'{stock_code} not in watchlist')
    logger.info('[WATCHLIST] removed stock=%s', stock_code)
