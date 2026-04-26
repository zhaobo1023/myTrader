# -*- coding: utf-8 -*-
"""
WeChat Feed (公众号订阅) router
Integration with wechat2rss service
"""
import logging
import os
import sqlite3
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.middleware.auth import get_current_user
from api.models.user import User
from api.models.wechat_feed import WechatFeed

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/wechat-feed', tags=['wechat_feed'])

# Configuration
WECHAT_RSS_DB = os.environ.get('WECHAT_RSS_DB', '/root/wechat2rss/data/res.db')


# ============================================================
# Schema
# ============================================================

class WechatFeedResponse(BaseModel):
    id: Optional[int] = None
    feed_id: str
    name: str
    description: Optional[str] = None
    url: Optional[str] = None
    is_active: int = 1
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class AddFeedRequest(BaseModel):
    feed_id: str
    name: str
    description: Optional[str] = None
    url: Optional[str] = None


# ============================================================
# Helpers
# ============================================================

def get_wechat_rss_connection():
    """Get connection to wechat2rss SQLite database."""
    if not os.path.exists(WECHAT_RSS_DB):
        raise HTTPException(status_code=500, detail=f'wechat2rss database not found at {WECHAT_RSS_DB}')
    return sqlite3.connect(WECHAT_RSS_DB)


def sync_feeds_from_rss():
    """Sync feeds from wechat2rss to local database."""
    try:
        conn = get_wechat_rss_connection()
        cursor = conn.cursor()

        # Get all rsses from wechat2rss
        cursor.execute('SELECT feed_id, name FROM rsses WHERE enabled = 1')
        feeds = cursor.fetchall()
        conn.close()

        return feeds
    except Exception as e:
        logger.error('[WECHAT] Error syncing feeds from RSS: %s', e)
        raise HTTPException(status_code=500, detail=f'Failed to sync feeds: {str(e)}')


# ============================================================
# Endpoints
# ============================================================

@router.get('/list', response_model=List[WechatFeedResponse])
async def list_feeds(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all subscribed WeChat feeds (public feeds)."""
    try:
        # For now, only admin can see feeds
        if current_user.tier != 'admin':
            raise HTTPException(status_code=403, detail='Only admin can access')

        # Read from wechat2rss database directly
        conn = get_wechat_rss_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT feed_id, name FROM rsses WHERE enabled = 1 ORDER BY name')
        rss_feeds = cursor.fetchall()
        conn.close()

        result = []
        for feed_id, name in rss_feeds:
            result.append(WechatFeedResponse(
                feed_id=feed_id,
                name=name,
            ))

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error('[WECHAT] List feeds failed: %s', e)
        raise HTTPException(status_code=500, detail='Failed to list feeds')


@router.post('/add', response_model=WechatFeedResponse)
async def add_feed(
    request: AddFeedRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a new WeChat feed subscription."""
    try:
        # Only admin can add feeds
        if current_user.tier != 'admin':
            raise HTTPException(status_code=403, detail='Only admin can add feeds')

        # Check if feed already exists in local DB
        result = await db.execute(
            text('SELECT id FROM wechat_feeds WHERE feed_id = :feed_id'),
            {'feed_id': request.feed_id}
        )
        existing = result.fetchone()

        if existing:
            raise HTTPException(status_code=400, detail='Feed already exists')

        # Validate feed exists in wechat2rss
        conn = get_wechat_rss_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT 1 FROM rsses WHERE feed_id = ?', (request.feed_id,))
        rss_exists = cursor.fetchone()
        conn.close()

        if not rss_exists:
            raise HTTPException(status_code=400, detail='Feed not found in wechat2rss')

        # Save to local database
        feed = WechatFeed(
            feed_id=request.feed_id,
            name=request.name,
            description=request.description,
            url=request.url,
            is_active=1,
        )
        db.add(feed)
        await db.commit()
        await db.refresh(feed)

        logger.info('[WECHAT] Feed added: %s (%s)', feed.feed_id, feed.name)

        return WechatFeedResponse.from_orm(feed)
    except HTTPException:
        raise
    except Exception as e:
        logger.error('[WECHAT] Add feed failed: %s', e)
        raise HTTPException(status_code=500, detail='Failed to add feed')


@router.delete('/{feed_id}')
async def delete_feed(
    feed_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a WeChat feed subscription from local tracking."""
    try:
        # Only admin can delete feeds
        if current_user.tier != 'admin':
            raise HTTPException(status_code=403, detail='Only admin can delete feeds')

        result = await db.execute(
            text('SELECT id FROM wechat_feeds WHERE feed_id = :feed_id'),
            {'feed_id': feed_id}
        )
        feed = result.fetchone()

        if not feed:
            raise HTTPException(status_code=404, detail='Feed not found')

        # Mark as inactive instead of delete
        await db.execute(
            text('UPDATE wechat_feeds SET is_active = 0 WHERE feed_id = :feed_id'),
            {'feed_id': feed_id}
        )
        await db.commit()

        logger.info('[WECHAT] Feed deleted: %s', feed_id)

        return {'message': 'Feed deleted successfully', 'feed_id': feed_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error('[WECHAT] Delete feed failed: %s', e)
        raise HTTPException(status_code=500, detail='Failed to delete feed')


@router.post('/sync')
async def sync_feeds(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Sync feeds from wechat2rss to local database."""
    try:
        # Only admin can sync
        if current_user.tier != 'admin':
            raise HTTPException(status_code=403, detail='Only admin can sync')

        feeds = sync_feeds_from_rss()

        synced_count = 0
        for feed_id, name in feeds:
            # Check if already exists
            result = await db.execute(
                text('SELECT id FROM wechat_feeds WHERE feed_id = :feed_id'),
                {'feed_id': feed_id}
            )
            existing = result.fetchone()

            if not existing:
                feed = WechatFeed(
                    feed_id=feed_id,
                    name=name,
                    is_active=1,
                )
                db.add(feed)
                synced_count += 1

        await db.commit()

        logger.info('[WECHAT] Synced %d new feeds', synced_count)

        return {
            'message': 'Sync completed',
            'synced_count': synced_count,
            'total_feeds': len(feeds),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error('[WECHAT] Sync feeds failed: %s', e)
        raise HTTPException(status_code=500, detail='Failed to sync feeds')


@router.get('/articles-export')
async def get_articles_export(
    current_user: User = Depends(get_current_user),
    days: int = Query(1, ge=1, le=30),
):
    """Get exported articles from wechat2rss (past N days)."""
    try:
        # Only admin can access
        if current_user.tier != 'admin':
            raise HTTPException(status_code=403, detail='Only admin can access')

        conn = get_wechat_rss_connection()
        cursor = conn.cursor()

        # Get feeds mapping
        cursor.execute('SELECT feed_id, name FROM rsses WHERE enabled = 1')
        feeds = {row[0]: row[1] for row in cursor.fetchall()}

        # Get articles from past N days
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')

        cursor.execute('''
            SELECT feed_id, COUNT(*) as count, MAX(created) as latest
            FROM articles
            WHERE created >= ?
            GROUP BY feed_id
            ORDER BY latest DESC
        ''', (cutoff,))

        result = []
        for feed_id, count, latest in cursor.fetchall():
            result.append({
                'feed_id': feed_id,
                'name': feeds.get(feed_id, 'Unknown'),
                'article_count': count,
                'latest_article': latest,
            })

        conn.close()

        return {
            'period_days': days,
            'feeds': result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error('[WECHAT] Get articles export failed: %s', e)
        raise HTTPException(status_code=500, detail='Failed to get articles')
