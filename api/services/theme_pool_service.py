# -*- coding: utf-8 -*-
"""
Theme Pool Service - business logic for thematic stock selection
"""
import logging
from datetime import datetime, date

from sqlalchemy import select, func, case, delete
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.theme_pool import (
    ThemePool, ThemePoolStock, ThemePoolScore, ThemePoolVote,
    ThemeStatus, HumanStatus,
)
from api.models.user import User

logger = logging.getLogger('myTrader.api')


def _enum_val(v):
    """Safely extract .value from enum or return string as-is."""
    return v.value if hasattr(v, 'value') else v


# Valid status transitions
_VALID_TRANSITIONS = {
    ThemeStatus.DRAFT: {ThemeStatus.ACTIVE},
    ThemeStatus.ACTIVE: {ThemeStatus.ARCHIVED},
    ThemeStatus.ARCHIVED: {ThemeStatus.ACTIVE},
}


# ------------------------------------------------------------------
# Theme CRUD
# ------------------------------------------------------------------

async def create_theme(
    db: AsyncSession,
    user_id: int,
    name: str,
    description: str = None,
) -> ThemePool:
    theme = ThemePool(
        name=name,
        description=description,
        created_by=user_id,
    )
    db.add(theme)
    await db.flush()
    await db.refresh(theme)
    logger.info('[THEME_POOL] created theme=%d name=%s by user=%d', theme.id, name, user_id)
    return theme


async def list_themes(
    db: AsyncSession,
    status_filter: str = None,
) -> list:
    """List themes with stock count."""
    stock_count_sq = (
        select(
            ThemePoolStock.theme_id,
            func.count(ThemePoolStock.id).label('stock_count'),
        )
        .group_by(ThemePoolStock.theme_id)
        .subquery()
    )

    stmt = (
        select(ThemePool, func.coalesce(stock_count_sq.c.stock_count, 0).label('stock_count'))
        .outerjoin(stock_count_sq, ThemePool.id == stock_count_sq.c.theme_id)
    )

    if status_filter:
        stmt = stmt.where(ThemePool.status == status_filter)

    stmt = stmt.order_by(ThemePool.updated_at.desc())
    result = await db.execute(stmt)
    rows = result.all()

    themes = []
    for theme, count in rows:
        # fetch creator email
        creator = await db.get(User, theme.created_by)
        themes.append({
            'id': theme.id,
            'name': theme.name,
            'description': theme.description,
            'status': _enum_val(theme.status),
            'created_by': theme.created_by,
            'creator_email': creator.email if creator else None,
            'stock_count': count,
            'created_at': theme.created_at,
            'updated_at': theme.updated_at,
        })
    return themes


async def get_theme(db: AsyncSession, theme_id: int) -> ThemePool:
    theme = await db.get(ThemePool, theme_id)
    return theme


async def update_theme(
    db: AsyncSession,
    theme: ThemePool,
    name: str = None,
    description: str = None,
) -> ThemePool:
    if name is not None:
        theme.name = name
    if description is not None:
        theme.description = description
    theme.updated_at = datetime.utcnow()
    await db.flush()
    await db.refresh(theme)
    return theme


async def transition_status(
    db: AsyncSession,
    theme: ThemePool,
    new_status_str: str,
) -> ThemePool:
    new_status = ThemeStatus(new_status_str)
    current_val = _enum_val(theme.status)
    current = ThemeStatus(current_val)

    allowed = _VALID_TRANSITIONS.get(current, set())
    if new_status not in allowed:
        raise ValueError(
            f'Cannot transition from {current.value} to {new_status.value}. '
            f'Allowed: {[s.value for s in allowed]}'
        )

    theme.status = new_status.value
    theme.updated_at = datetime.utcnow()
    await db.flush()
    await db.refresh(theme)
    logger.info('[THEME_POOL] theme=%d status %s -> %s', theme.id, current.value, new_status.value)
    return theme


async def delete_theme(db: AsyncSession, theme: ThemePool) -> None:
    current_val = _enum_val(theme.status)
    if current_val != ThemeStatus.DRAFT.value:
        raise ValueError('Only draft themes can be deleted')
    await db.delete(theme)
    await db.flush()
    logger.info('[THEME_POOL] deleted theme=%d', theme.id)


# ------------------------------------------------------------------
# Stock management
# ------------------------------------------------------------------

async def add_stock(
    db: AsyncSession,
    theme_id: int,
    user_id: int,
    stock_code: str,
    stock_name: str = '',
    reason: str = None,
) -> ThemePoolStock:
    # check duplicate
    existing = await db.execute(
        select(ThemePoolStock).where(
            ThemePoolStock.theme_id == theme_id,
            ThemePoolStock.stock_code == stock_code,
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError(f'{stock_code} already in this theme pool')

    # try to get entry price from trade_stock_daily
    entry_price = await _get_latest_close(stock_code)

    stock = ThemePoolStock(
        theme_id=theme_id,
        stock_code=stock_code,
        stock_name=stock_name,
        recommended_by=user_id,
        reason=reason,
        entry_price=entry_price,
        entry_date=date.today(),
    )
    db.add(stock)
    await db.flush()
    await db.refresh(stock)
    logger.info('[THEME_POOL] theme=%d added stock=%s by user=%d', theme_id, stock_code, user_id)
    return stock


async def list_stocks(
    db: AsyncSession,
    theme_id: int,
    user_id: int,
    human_status_filter: str = None,
    sort_by: str = 'total_score',
) -> list:
    """List stocks with latest score and vote summary."""
    # latest score subquery
    latest_date_sq = (
        select(
            ThemePoolScore.theme_stock_id,
            func.max(ThemePoolScore.score_date).label('max_date'),
        )
        .group_by(ThemePoolScore.theme_stock_id)
        .subquery()
    )

    # vote summary subquery
    vote_sq = (
        select(
            ThemePoolVote.theme_stock_id,
            func.sum(case((ThemePoolVote.vote == 1, 1), else_=0)).label('up_votes'),
            func.sum(case((ThemePoolVote.vote == -1, 1), else_=0)).label('down_votes'),
        )
        .group_by(ThemePoolVote.theme_stock_id)
        .subquery()
    )

    # current user's vote subquery
    my_vote_sq = (
        select(
            ThemePoolVote.theme_stock_id,
            ThemePoolVote.vote.label('my_vote'),
        )
        .where(ThemePoolVote.user_id == user_id)
        .subquery()
    )

    stmt = (
        select(
            ThemePoolStock,
            ThemePoolScore,
            func.coalesce(vote_sq.c.up_votes, 0).label('up_votes'),
            func.coalesce(vote_sq.c.down_votes, 0).label('down_votes'),
            my_vote_sq.c.my_vote,
        )
        .outerjoin(
            latest_date_sq,
            ThemePoolStock.id == latest_date_sq.c.theme_stock_id,
        )
        .outerjoin(
            ThemePoolScore,
            (ThemePoolScore.theme_stock_id == ThemePoolStock.id)
            & (ThemePoolScore.score_date == latest_date_sq.c.max_date),
        )
        .outerjoin(vote_sq, ThemePoolStock.id == vote_sq.c.theme_stock_id)
        .outerjoin(my_vote_sq, ThemePoolStock.id == my_vote_sq.c.theme_stock_id)
        .where(ThemePoolStock.theme_id == theme_id)
    )

    if human_status_filter:
        stmt = stmt.where(ThemePoolStock.human_status == human_status_filter)

    # sorting -- MySQL lacks NULLS LAST, use CASE to push NULLs to bottom
    def _nulls_last_desc(col):
        return [case((col.is_(None), 1), else_=0), col.desc()]

    sort_map = {
        'total_score': _nulls_last_desc(ThemePoolScore.total_score),
        'added_at': [ThemePoolStock.added_at.desc()],
        'return_5d': _nulls_last_desc(ThemePoolScore.return_5d),
        'return_20d': _nulls_last_desc(ThemePoolScore.return_20d),
        'rps_20': _nulls_last_desc(ThemePoolScore.rps_20),
    }
    order_clauses = sort_map.get(sort_by, [ThemePoolStock.added_at.desc()])
    for clause in order_clauses:
        stmt = stmt.order_by(clause)

    result = await db.execute(stmt)
    rows = result.all()

    items = []
    for stock, score, up_votes, down_votes, my_vote in rows:
        # fetch recommender email
        recommender = await db.get(User, stock.recommended_by)
        score_item = None
        if score:
            score_item = {
                'score_date': score.score_date,
                'rps_20': score.rps_20,
                'rps_60': score.rps_60,
                'rps_120': score.rps_120,
                'rps_250': score.rps_250,
                'tech_score': score.tech_score,
                'tech_signals': score.tech_signals,
                'fundamental_score': score.fundamental_score,
                'fundamental_data': score.fundamental_data,
                'total_score': score.total_score,
                'return_5d': score.return_5d,
                'return_10d': score.return_10d,
                'return_20d': score.return_20d,
                'return_60d': score.return_60d,
            }
        items.append({
            'id': stock.id,
            'theme_id': stock.theme_id,
            'stock_code': stock.stock_code,
            'stock_name': stock.stock_name,
            'recommended_by': stock.recommended_by,
            'recommender_email': recommender.email if recommender else None,
            'reason': stock.reason,
            'entry_price': stock.entry_price,
            'entry_date': stock.entry_date,
            'human_status': _enum_val(stock.human_status),
            'note': stock.note,
            'added_at': stock.added_at,
            'latest_score': score_item,
            'up_votes': int(up_votes),
            'down_votes': int(down_votes),
            'my_vote': int(my_vote) if my_vote is not None else None,
        })
    return items


async def remove_stock(db: AsyncSession, theme_id: int, stock_code: str) -> bool:
    result = await db.execute(
        delete(ThemePoolStock).where(
            ThemePoolStock.theme_id == theme_id,
            ThemePoolStock.stock_code == stock_code,
        )
    )
    if result.rowcount == 0:
        return False
    logger.info('[THEME_POOL] theme=%d removed stock=%s', theme_id, stock_code)
    return True


async def update_human_status(
    db: AsyncSession,
    stock_id: int,
    new_status_str: str,
) -> ThemePoolStock:
    stock = await db.get(ThemePoolStock, stock_id)
    if not stock:
        return None
    # validate then store as string
    HumanStatus(new_status_str)  # raises ValueError if invalid
    stock.human_status = new_status_str
    await db.flush()
    await db.refresh(stock)
    return stock


async def update_note(
    db: AsyncSession,
    stock_id: int,
    note: str,
) -> ThemePoolStock:
    stock = await db.get(ThemePoolStock, stock_id)
    if not stock:
        return None
    stock.note = note
    await db.flush()
    await db.refresh(stock)
    return stock


async def update_reason(
    db: AsyncSession,
    stock_id: int,
    reason: str,
) -> ThemePoolStock:
    stock = await db.get(ThemePoolStock, stock_id)
    if not stock:
        return None
    stock.reason = reason
    await db.flush()
    await db.refresh(stock)
    return stock


# ------------------------------------------------------------------
# Voting
# ------------------------------------------------------------------

async def vote_stock(
    db: AsyncSession,
    stock_id: int,
    user_id: int,
    vote_value: int,
) -> dict:
    if vote_value not in (1, -1):
        raise ValueError('vote must be 1 or -1')

    # upsert: check existing vote from this user
    existing = await db.execute(
        select(ThemePoolVote).where(
            ThemePoolVote.theme_stock_id == stock_id,
            ThemePoolVote.user_id == user_id,
        )
    )
    vote_obj = existing.scalar_one_or_none()

    if vote_obj:
        vote_obj.vote = vote_value
        vote_obj.voted_at = datetime.utcnow()
    else:
        vote_obj = ThemePoolVote(
            theme_stock_id=stock_id,
            user_id=user_id,
            vote=vote_value,
        )
        db.add(vote_obj)

    await db.flush()
    return await _get_vote_summary(db, stock_id, user_id)


async def remove_vote(
    db: AsyncSession,
    stock_id: int,
    user_id: int,
) -> dict:
    await db.execute(
        delete(ThemePoolVote).where(
            ThemePoolVote.theme_stock_id == stock_id,
            ThemePoolVote.user_id == user_id,
        )
    )
    await db.flush()
    return await _get_vote_summary(db, stock_id, user_id)


async def _get_vote_summary(db: AsyncSession, stock_id: int, user_id: int) -> dict:
    result = await db.execute(
        select(
            func.sum(case((ThemePoolVote.vote == 1, 1), else_=0)).label('up'),
            func.sum(case((ThemePoolVote.vote == -1, 1), else_=0)).label('down'),
        ).where(ThemePoolVote.theme_stock_id == stock_id)
    )
    row = result.one()
    up = int(row.up or 0)
    down = int(row.down or 0)

    # current user's vote
    my = await db.execute(
        select(ThemePoolVote.vote).where(
            ThemePoolVote.theme_stock_id == stock_id,
            ThemePoolVote.user_id == user_id,
        )
    )
    my_vote = my.scalar_one_or_none()

    return {'up_votes': up, 'down_votes': down, 'my_vote': my_vote}


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

async def _get_latest_close(stock_code: str) -> float:
    """Get latest close price from trade_stock_daily via config.db (sync)."""
    try:
        from config.db import execute_query
        rows = execute_query(
            "SELECT close_price FROM trade_stock_daily WHERE stock_code = %s "
            "ORDER BY trade_date DESC LIMIT 1",
            (stock_code,),
            env='online',
        )
        rows = list(rows)
        if rows:
            return float(rows[0]['close_price'])
    except Exception as e:
        logger.warning('[THEME_POOL] failed to get close price for %s: %s', stock_code, str(e))
    return None


async def get_price_history(db: AsyncSession, theme_id: int, days: int = 60) -> list:
    """Get daily close prices for all stocks in a theme.

    Returns the most recent `days` trading days of price data.
    If stock has entry_price, marks the entry date for reference.
    """
    from config.db import execute_query

    # Get all stocks
    result = await db.execute(
        select(ThemePoolStock).where(ThemePoolStock.theme_id == theme_id)
    )
    stocks = result.scalars().all()

    if not stocks:
        return []

    history = []
    for stock in stocks:
        try:
            rows = list(execute_query(
                "SELECT trade_date, open_price, high_price, low_price, close_price, volume "
                "FROM trade_stock_daily "
                "WHERE stock_code = %s "
                "ORDER BY trade_date DESC LIMIT %s",
                (stock.stock_code, days),
                env='online',
            ))
            if rows:
                # Reverse to chronological order
                rows.reverse()
                prices = [
                    {
                        'date': str(r['trade_date']),
                        'open': float(r['open_price']) if r.get('open_price') else None,
                        'high': float(r['high_price']) if r.get('high_price') else None,
                        'low': float(r['low_price']) if r.get('low_price') else None,
                        'close': float(r['close_price']) if r.get('close_price') else None,
                        'volume': float(r['volume']) if r.get('volume') else None,
                    }
                    for r in rows
                ]
                history.append({
                    'stock_code': stock.stock_code,
                    'stock_name': stock.stock_name,
                    'entry_date': str(stock.entry_date),
                    'entry_price': float(stock.entry_price) if stock.entry_price else None,
                    'prices': prices,
                })
        except Exception as e:
            logger.warning('[THEME_POOL] price history failed for %s: %s', stock.stock_code, e)

    return history
