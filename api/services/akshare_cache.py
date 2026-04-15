"""
Redis-backed caching layer for AKShareConceptFetcher.

Usage:
    from api.services.akshare_cache import CachedAKShareFetcher
    from api.services.theme_llm_service import AKShareConceptFetcher

    fetcher = CachedAKShareFetcher(inner=AKShareConceptFetcher(), redis=redis_client)
    boards = await fetcher.get_all_boards()          # cached for 6 hours
    stocks = await fetcher.get_board_stocks('特高压') # cached per board
"""
import json
import logging

logger = logging.getLogger('myTrader.akshare_cache')

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BOARDS_CACHE_KEY = 'akshare:concept_boards'
BOARD_STOCKS_KEY_PREFIX = 'akshare:board_stocks:'
CACHE_TTL_SECONDS = 6 * 3600  # 6 hours


# ---------------------------------------------------------------------------
# Cached fetcher
# ---------------------------------------------------------------------------

class CachedAKShareFetcher:
    """Wraps AKShareConceptFetcher with a Redis cache layer.

    Falls back gracefully to the inner fetcher on any Redis error so that
    a Redis outage does not break the LLM skill pipeline.
    """

    def __init__(self, inner, redis):
        """
        Args:
            inner: AKShareConceptFetcher instance (or compatible async interface).
            redis: An async Redis client (e.g. from api.dependencies).
        """
        self._inner = inner
        self._redis = redis

    async def get_all_boards(self) -> list[str]:
        """Return all Eastmoney concept board names (cached)."""
        # 1. try cache
        try:
            raw = await self._redis.get(BOARDS_CACHE_KEY)
            if raw is not None:
                return json.loads(raw)
        except Exception as e:
            logger.warning('[CachedAKShareFetcher] redis get boards failed: %s', e)

        # 2. fetch from AKShare
        boards = await self._inner.get_all_boards()

        # 3. write to cache (best-effort)
        try:
            await self._redis.setex(BOARDS_CACHE_KEY, CACHE_TTL_SECONDS, json.dumps(boards, ensure_ascii=False))
        except Exception as e:
            logger.warning('[CachedAKShareFetcher] redis setex boards failed: %s', e)

        return boards

    async def get_board_stocks(self, board_name: str) -> list[dict]:
        """Return component stocks for a board name (cached per board)."""
        cache_key = f'{BOARD_STOCKS_KEY_PREFIX}{board_name}'

        # 1. try cache
        try:
            raw = await self._redis.get(cache_key)
            if raw is not None:
                return json.loads(raw)
        except Exception as e:
            logger.warning('[CachedAKShareFetcher] redis get board_stocks %r failed: %s', board_name, e)

        # 2. fetch from AKShare
        stocks = await self._inner.get_board_stocks(board_name)

        # 3. write to cache (best-effort)
        try:
            await self._redis.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(stocks, ensure_ascii=False))
        except Exception as e:
            logger.warning('[CachedAKShareFetcher] redis setex board_stocks %r failed: %s', board_name, e)

        return stocks
