"""
Unit tests for api/services/akshare_cache.py (M2-T3)
- CachedAKShareFetcher: Redis-backed wrapper around AKShareConceptFetcher
- TTL behaviour, cache hit/miss, fallback on Redis error
"""
import asyncio
import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch, call

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from api.services.akshare_cache import CachedAKShareFetcher, BOARDS_CACHE_KEY, BOARD_STOCKS_KEY_PREFIX, CACHE_TTL_SECONDS


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_redis(get_return=None, set_ok=True):
    """Return an AsyncMock Redis client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=get_return)
    redis.setex = AsyncMock(return_value=True)
    return redis


def _make_inner_fetcher(boards=None, stocks=None):
    """Return an AsyncMock AKShareConceptFetcher."""
    fetcher = AsyncMock()
    fetcher.get_all_boards = AsyncMock(return_value=boards or ['特高压', '智能电网'])
    fetcher.get_board_stocks = AsyncMock(return_value=stocks or [
        {'code': '000001', 'name': '平安银行'},
    ])
    return fetcher


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# TestCacheConstants
# ---------------------------------------------------------------------------

class TestCacheConstants(unittest.TestCase):
    def test_boards_cache_key_is_string(self):
        self.assertIsInstance(BOARDS_CACHE_KEY, str)
        self.assertTrue(len(BOARDS_CACHE_KEY) > 0)

    def test_board_stocks_key_prefix_is_string(self):
        self.assertIsInstance(BOARD_STOCKS_KEY_PREFIX, str)

    def test_cache_ttl_is_6_hours(self):
        self.assertEqual(CACHE_TTL_SECONDS, 6 * 3600)


# ---------------------------------------------------------------------------
# TestGetAllBoardsCaching
# ---------------------------------------------------------------------------

class TestGetAllBoardsCaching(unittest.TestCase):

    def test_cache_miss_calls_inner_and_stores(self):
        """On cache miss, fetches from AKShare and writes to Redis."""
        inner = _make_inner_fetcher(boards=['特高压', '智能电网'])
        redis = _make_redis(get_return=None)
        cached = CachedAKShareFetcher(inner=inner, redis=redis)

        result = _run(cached.get_all_boards())

        inner.get_all_boards.assert_awaited_once()
        redis.setex.assert_awaited_once()
        # TTL arg is second positional arg to setex
        args = redis.setex.call_args[0]
        self.assertEqual(args[1], CACHE_TTL_SECONDS)
        self.assertEqual(result, ['特高压', '智能电网'])

    def test_cache_hit_returns_cached_value(self):
        """On cache hit, inner fetcher is NOT called."""
        boards = ['特高压', '智能电网']
        inner = _make_inner_fetcher()
        redis = _make_redis(get_return=json.dumps(boards).encode())
        cached = CachedAKShareFetcher(inner=inner, redis=redis)

        result = _run(cached.get_all_boards())

        inner.get_all_boards.assert_not_awaited()
        self.assertEqual(result, boards)

    def test_redis_error_falls_back_to_inner(self):
        """If Redis.get raises, still returns data from inner fetcher."""
        inner = _make_inner_fetcher(boards=['特高压'])
        redis = _make_redis()
        redis.get = AsyncMock(side_effect=Exception('redis down'))
        cached = CachedAKShareFetcher(inner=inner, redis=redis)

        result = _run(cached.get_all_boards())

        inner.get_all_boards.assert_awaited_once()
        self.assertEqual(result, ['特高压'])

    def test_redis_setex_error_does_not_crash(self):
        """If Redis.setex raises (write failure), result still returned."""
        inner = _make_inner_fetcher(boards=['特高压'])
        redis = _make_redis(get_return=None)
        redis.setex = AsyncMock(side_effect=Exception('write failed'))
        cached = CachedAKShareFetcher(inner=inner, redis=redis)

        result = _run(cached.get_all_boards())
        self.assertEqual(result, ['特高压'])


# ---------------------------------------------------------------------------
# TestGetBoardStocksCaching
# ---------------------------------------------------------------------------

class TestGetBoardStocksCaching(unittest.TestCase):

    def test_cache_miss_calls_inner_and_stores(self):
        stocks = [{'code': '000001', 'name': '平安银行'}]
        inner = _make_inner_fetcher(stocks=stocks)
        redis = _make_redis(get_return=None)
        cached = CachedAKShareFetcher(inner=inner, redis=redis)

        result = _run(cached.get_board_stocks('特高压'))

        inner.get_board_stocks.assert_awaited_once_with('特高压')
        redis.setex.assert_awaited_once()
        self.assertEqual(result, stocks)

    def test_cache_hit_returns_cached_value(self):
        stocks = [{'code': '600519', 'name': '贵州茅台'}]
        inner = _make_inner_fetcher()
        redis = _make_redis(get_return=json.dumps(stocks).encode())
        cached = CachedAKShareFetcher(inner=inner, redis=redis)

        result = _run(cached.get_board_stocks('某板块'))

        inner.get_board_stocks.assert_not_awaited()
        self.assertEqual(result, stocks)

    def test_board_stocks_key_includes_board_name(self):
        """Cache key for board stocks must include the board name."""
        inner = _make_inner_fetcher()
        redis = _make_redis(get_return=None)
        cached = CachedAKShareFetcher(inner=inner, redis=redis)

        _run(cached.get_board_stocks('特高压'))

        # The key passed to setex must contain '特高压'
        key_arg = redis.setex.call_args[0][0]
        self.assertIn('特高压', key_arg)

    def test_different_boards_use_different_keys(self):
        """Two different boards must produce different cache keys."""
        inner = _make_inner_fetcher()
        redis = _make_redis(get_return=None)
        cached = CachedAKShareFetcher(inner=inner, redis=redis)

        _run(cached.get_board_stocks('特高压'))
        _run(cached.get_board_stocks('智能电网'))

        calls = redis.setex.call_args_list
        keys = [c[0][0] for c in calls]
        self.assertEqual(len(set(keys)), 2)

    def test_redis_error_falls_back_to_inner(self):
        stocks = [{'code': '000001', 'name': '平安银行'}]
        inner = _make_inner_fetcher(stocks=stocks)
        redis = _make_redis()
        redis.get = AsyncMock(side_effect=Exception('redis down'))
        cached = CachedAKShareFetcher(inner=inner, redis=redis)

        result = _run(cached.get_board_stocks('特高压'))

        inner.get_board_stocks.assert_awaited_once()
        self.assertEqual(result, stocks)


if __name__ == '__main__':
    unittest.main()
