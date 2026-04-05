# -*- coding: utf-8 -*-
"""
API Key authentication via X-API-Key header
"""
import hashlib
import logging
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from sqlalchemy import text

from api.dependencies import get_db

logger = logging.getLogger('myTrader.api')
api_key_header = APIKeyHeader(name='X-API-Key', auto_error=False)


def verify_api_key(api_key: Optional[str] = Depends(api_key_header)):
    """Validate API key from X-API-Key header. Returns user_id if valid."""
    if not api_key or not api_key.startswith('mtk_'):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Invalid or missing API key',
        )

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    db = get_db()

    try:
        result = db.execute(
            text(
                "SELECT user_id FROM api_keys "
                "WHERE key_hash = :hash AND revoked_at IS NULL"
            ),
            {"hash": key_hash},
        )
        row = result.fetchone()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='API key not found or revoked',
            )

        user_id = row['user_id'] if isinstance(row, dict) else row[0]

        # Update last_used
        db.execute(
            text("UPDATE api_keys SET last_used = NOW() WHERE key_hash = :hash"),
            {"hash": key_hash},
        )
        db.commit()

        return user_id
    except HTTPException:
        raise
    except Exception as e:
        logger.error('[API_KEY_AUTH] Verification failed: %s', e)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='API key verification failed',
        )
