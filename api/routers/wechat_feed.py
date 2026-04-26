# -*- coding: utf-8 -*-
"""
WeChat Feed (公众号订阅) router
Integration with wechat2rss service
"""
import asyncio
import logging
import os
import sqlite3
from typing import Optional, List
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.middleware.auth import require_admin
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

    model_config = {'from_attributes': True}


class AddFeedRequest(BaseModel):
    feed_id: str
    name: str
    description: Optional[str] = None
    url: Optional[str] = None


# ============================================================
# Helpers
# ============================================================

def _query_rss_db(sql: str, params: tuple = ()) -> list:
    """Execute a query against wechat2rss SQLite database (synchronous).

    Always closes the connection, even on error.
    """
    if not os.path.exists(WECHAT_RSS_DB):
        raise HTTPException(
            status_code=500,
            detail='wechat2rss database not available',
        )
    conn = sqlite3.connect(WECHAT_RSS_DB)
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return cursor.fetchall()
    finally:
        conn.close()


async def _query_rss_db_async(sql: str, params: tuple = ()) -> list:
    """Run a synchronous SQLite query in a thread to avoid blocking the event loop."""
    return await asyncio.to_thread(_query_rss_db, sql, params)


# ============================================================
# Endpoints
# ============================================================

@router.get('/list', response_model=List[WechatFeedResponse])
async def list_feeds(
    current_user: User = Depends(require_admin),
):
    """List all subscribed WeChat feeds from wechat2rss."""
    try:
        rows = await _query_rss_db_async(
            'SELECT feed_id, name FROM rsses ORDER BY name'
        )
        return [
            WechatFeedResponse(feed_id=fid, name=name)
            for fid, name in rows
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error('[WECHAT] List feeds failed: %s', e)
        raise HTTPException(status_code=500, detail='Failed to list feeds')


@router.post('/add', response_model=WechatFeedResponse)
async def add_feed(
    request: AddFeedRequest,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Add a new WeChat feed subscription to local tracking."""
    try:
        # Check if feed already exists in local DB
        result = await db.execute(
            text('SELECT id FROM wechat_feeds WHERE feed_id = :feed_id'),
            {'feed_id': request.feed_id},
        )
        if result.fetchone():
            raise HTTPException(status_code=400, detail='Feed already exists')

        # Validate feed exists in wechat2rss
        rows = await _query_rss_db_async(
            'SELECT 1 FROM rsses WHERE feed_id = ?', (request.feed_id,)
        )
        if not rows:
            raise HTTPException(
                status_code=400, detail='Feed not found in wechat2rss'
            )

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
        return WechatFeedResponse.model_validate(feed)
    except HTTPException:
        raise
    except Exception as e:
        logger.error('[WECHAT] Add feed failed: %s', e)
        raise HTTPException(status_code=500, detail='Failed to add feed')


@router.delete('/{feed_id}')
async def delete_feed(
    feed_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Delete a WeChat feed subscription from local tracking (soft-delete)."""
    try:
        result = await db.execute(
            text('SELECT id FROM wechat_feeds WHERE feed_id = :feed_id'),
            {'feed_id': feed_id},
        )
        if not result.fetchone():
            raise HTTPException(status_code=404, detail='Feed not found')

        await db.execute(
            text('UPDATE wechat_feeds SET is_active = 0 WHERE feed_id = :feed_id'),
            {'feed_id': feed_id},
        )
        await db.commit()

        logger.info('[WECHAT] Feed deactivated: %s', feed_id)
        return {'message': 'Feed deactivated', 'feed_id': feed_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error('[WECHAT] Delete feed failed: %s', e)
        raise HTTPException(status_code=500, detail='Failed to delete feed')


@router.post('/sync')
async def sync_feeds(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Sync feeds from wechat2rss to local database."""
    try:
        feeds = await _query_rss_db_async(
            'SELECT feed_id, name FROM rsses'
        )

        synced_count = 0
        for feed_id, name in feeds:
            result = await db.execute(
                text('SELECT id FROM wechat_feeds WHERE feed_id = :feed_id'),
                {'feed_id': feed_id},
            )
            if not result.fetchone():
                db.add(WechatFeed(feed_id=feed_id, name=name, is_active=1))
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
    current_user: User = Depends(require_admin),
    days: int = Query(1, ge=1, le=30),
):
    """Get article statistics per feed from wechat2rss (past N days)."""
    try:
        # Get feeds mapping
        feed_rows = await _query_rss_db_async(
            'SELECT feed_id, name FROM rsses'
        )
        feeds_map = {row[0]: row[1] for row in feed_rows}

        cutoff = (datetime.now() - timedelta(days=days)).strftime(
            '%Y-%m-%d %H:%M:%S'
        )

        article_rows = await _query_rss_db_async(
            '''
            SELECT feed_id, COUNT(*) as count, MAX(created) as latest
            FROM articles
            WHERE created >= ?
            GROUP BY feed_id
            ORDER BY latest DESC
            ''',
            (cutoff,),
        )

        result = [
            {
                'feed_id': fid,
                'name': feeds_map.get(fid, 'Unknown'),
                'article_count': count,
                'latest_article': latest,
            }
            for fid, count, latest in article_rows
        ]

        return {'period_days': days, 'feeds': result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error('[WECHAT] Get articles export failed: %s', e)
        raise HTTPException(status_code=500, detail='Failed to get articles')
