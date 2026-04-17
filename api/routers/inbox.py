# -*- coding: utf-8 -*-
"""
Inbox router - user messages / notifications
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update

from api.dependencies import get_db
from api.models.user import User
from api.models.inbox_message import InboxMessage
from api.middleware.auth import get_current_user
from api.schemas.inbox import InboxMessageResponse, InboxListResponse, UnreadCountResponse

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/inbox', tags=['inbox'])


def _to_response(msg: InboxMessage) -> InboxMessageResponse:
    return InboxMessageResponse(
        id=msg.id,
        message_type=msg.message_type,
        title=msg.title,
        content=msg.content,
        metadata_json=msg.metadata_json,
        is_read=msg.is_read,
        created_at=msg.created_at.isoformat() if msg.created_at else '',
    )


@router.get('', response_model=InboxListResponse)
async def list_messages(
    message_type: Optional[str] = Query(default=None),
    is_read: Optional[bool] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List inbox messages with pagination and filters."""
    base = select(InboxMessage).where(InboxMessage.user_id == current_user.id)
    if message_type:
        base = base.where(InboxMessage.message_type == message_type)
    if is_read is not None:
        base = base.where(InboxMessage.is_read == is_read)

    # Total count
    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Unread count
    unread_q = select(func.count()).where(
        InboxMessage.user_id == current_user.id,
        InboxMessage.is_read == False,
    )
    unread_count = (await db.execute(unread_q)).scalar() or 0

    # Paginated items
    offset = (page - 1) * page_size
    items_q = base.order_by(InboxMessage.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(items_q)
    items = result.scalars().all()

    return InboxListResponse(
        items=[_to_response(m) for m in items],
        total=total,
        unread_count=unread_count,
    )


@router.get('/unread-count', response_model=UnreadCountResponse)
async def get_unread_count(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get unread message count (for sidebar badge)."""
    result = await db.execute(
        select(func.count()).where(
            InboxMessage.user_id == current_user.id,
            InboxMessage.is_read == False,
        )
    )
    count = result.scalar() or 0
    return UnreadCountResponse(unread_count=count)


@router.get('/{message_id}', response_model=InboxMessageResponse)
async def get_message(
    message_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a single message and mark it as read."""
    result = await db.execute(
        select(InboxMessage).where(
            InboxMessage.id == message_id,
            InboxMessage.user_id == current_user.id,
        )
    )
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail='Message not found')
    msg.is_read = True
    return _to_response(msg)


@router.patch('/{message_id}/read')
async def mark_read(
    message_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a message as read."""
    result = await db.execute(
        select(InboxMessage).where(
            InboxMessage.id == message_id,
            InboxMessage.user_id == current_user.id,
        )
    )
    msg = result.scalar_one_or_none()
    if not msg:
        raise HTTPException(status_code=404, detail='Message not found')
    msg.is_read = True
    return {'message': 'Marked as read'}


@router.post('/mark-all-read')
async def mark_all_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark all messages as read."""
    await db.execute(
        update(InboxMessage)
        .where(InboxMessage.user_id == current_user.id, InboxMessage.is_read == False)
        .values(is_read=True)
    )
    return {'message': 'All messages marked as read'}


@router.delete('/{message_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_message(
    message_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a message."""
    from sqlalchemy import delete as sql_delete
    result = await db.execute(
        sql_delete(InboxMessage).where(
            InboxMessage.id == message_id,
            InboxMessage.user_id == current_user.id,
        )
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail='Message not found')
