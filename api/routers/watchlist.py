# api/routers/watchlist.py
# -*- coding: utf-8 -*-
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from api.dependencies import get_db
from api.models.watchlist import UserWatchlist
from api.models.user import User
from api.middleware.auth import get_current_user
from api.schemas.watchlist import WatchlistAddRequest, WatchlistItem, WatchlistResponse

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/watchlist', tags=['watchlist'])


@router.get('', response_model=WatchlistResponse)
async def list_watchlist(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get user's watchlist."""
    result = await db.execute(
        select(UserWatchlist)
        .where(UserWatchlist.user_id == current_user.id)
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
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add stock to user's watchlist."""
    existing = await db.execute(
        select(UserWatchlist).where(
            UserWatchlist.user_id == current_user.id,
            UserWatchlist.stock_code == req.stock_code,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'{req.stock_code} already in watchlist',
        )

    item = UserWatchlist(
        user_id=current_user.id,
        stock_code=req.stock_code,
        stock_name=req.stock_name,
        note=req.note,
    )
    db.add(item)
    await db.flush()
    await db.refresh(item)
    logger.info('[WATCHLIST] user=%s added stock=%s', current_user.id, req.stock_code)
    return WatchlistItem.model_validate(item)


@router.delete('/{stock_code}', status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_watchlist(
    stock_code: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove stock from user's watchlist."""
    result = await db.execute(
        delete(UserWatchlist).where(
            UserWatchlist.user_id == current_user.id,
            UserWatchlist.stock_code == stock_code,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail=f'{stock_code} not in watchlist')
    logger.info('[WATCHLIST] user=%s removed stock=%s', current_user.id, stock_code)
