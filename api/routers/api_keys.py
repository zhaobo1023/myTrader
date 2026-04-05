# -*- coding: utf-8 -*-
"""
API Key management router
"""
import hashlib
import secrets
import logging

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.middleware.auth import get_current_user
from api.models.user import User

logger = logging.getLogger('myTrader.api')
router = APIRouter(prefix='/api/api-keys', tags=['api-keys'])

API_KEY_PREFIX_LEN = 8


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


@router.post('/')
async def create_api_key(
    name: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a new API key. The plain key is shown only once."""
    raw_key = f"mtk_{secrets.token_urlsafe(32)}"
    key_hash = _hash_key(raw_key)
    key_prefix = raw_key[:API_KEY_PREFIX_LEN]

    try:
        await db.execute(
            text(
                "INSERT INTO api_keys (user_id, key_hash, key_prefix, name) "
                "VALUES (:uid, :hash, :prefix, :name)"
            ),
            {"uid": current_user.id, "hash": key_hash, "prefix": key_prefix, "name": name},
        )
        await db.commit()
        last_id_result = await db.execute(text("SELECT LAST_INSERT_ID() as id"))
        new_id = last_id_result.scalar()
        return {
            'id': new_id,
            'key': raw_key,
            'prefix': key_prefix,
            'name': name,
            'message': 'Save this key now - it will not be shown again',
        }
    except Exception as e:
        logger.error('[API_KEY] Create failed: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get('/')
async def list_api_keys(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all API keys for the current user (key value never returned)."""
    try:
        result = await db.execute(
            text(
                "SELECT id, key_prefix, name, last_used, revoked_at, created_at "
                "FROM api_keys WHERE user_id = :uid ORDER BY id DESC"
            ),
            {"uid": current_user.id},
        )
        return {'keys': [dict(row) for row in result.mappings()]}
    except Exception as e:
        logger.error('[API_KEY] List failed: %s', e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete('/{key_id}')
async def revoke_api_key(
    key_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Revoke an API key."""
    try:
        await db.execute(
            text("UPDATE api_keys SET revoked_at = NOW() WHERE id = :kid AND user_id = :uid"),
            {"kid": key_id, "uid": current_user.id},
        )
        await db.commit()
        return {'message': 'API key revoked'}
    except Exception as e:
        logger.error('[API_KEY] Revoke failed: %s', e)
        raise HTTPException(status_code=500, detail=str(e))
