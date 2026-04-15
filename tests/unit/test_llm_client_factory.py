"""
Unit tests for api/services/llm_client_factory.py (M2-T1 + M2-T2)
- LLMClientFactory: multi-model alias routing
- with_retry: JSON-parse-failure auto-retry, 30s timeout behaviour
"""
import asyncio
import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from api.services.llm_client_factory import (
    LLMClientFactory,
    SUPPORTED_ALIASES,
    get_llm_client,
    llm_call_with_retry,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_factory(alias: str) -> LLMClientFactory:
    return LLMClientFactory(alias)


# ---------------------------------------------------------------------------
# TestSupportedAliases
# ---------------------------------------------------------------------------

class TestSupportedAliases(unittest.TestCase):
    """SUPPORTED_ALIASES must contain the four documented models."""

    def test_qwen_present(self):
        self.assertIn('qwen', SUPPORTED_ALIASES)

    def test_qwen_fast_present(self):
        self.assertIn('qwen-fast', SUPPORTED_ALIASES)

    def test_deepseek_present(self):
        self.assertIn('deepseek', SUPPORTED_ALIASES)

    def test_doubao_present(self):
        self.assertIn('doubao', SUPPORTED_ALIASES)

    def test_each_alias_has_model_and_base_url(self):
        for alias, cfg in SUPPORTED_ALIASES.items():
            self.assertIn('model', cfg, f"{alias} missing 'model'")
            self.assertIn('base_url', cfg, f"{alias} missing 'base_url'")
            self.assertIn('api_key_env', cfg, f"{alias} missing 'api_key_env'")


# ---------------------------------------------------------------------------
# TestLLMClientFactory
# ---------------------------------------------------------------------------

class TestLLMClientFactory(unittest.TestCase):
    """LLMClientFactory resolves aliases and exposes model/base_url."""

    def test_qwen_alias_resolves(self):
        f = _make_factory('qwen')
        self.assertIn('qwen', f.model.lower())

    def test_deepseek_alias_resolves(self):
        f = _make_factory('deepseek')
        self.assertIn('deepseek', f.model.lower())

    def test_unknown_alias_falls_back_to_qwen(self):
        f = _make_factory('nonexistent-model-xyz')
        self.assertIn('qwen', f.model.lower())

    def test_factory_exposes_base_url(self):
        f = _make_factory('qwen')
        self.assertTrue(f.base_url.startswith('http'))

    def test_get_llm_client_env_default(self):
        """get_llm_client() with no arg reads LLM_MODEL_ALIAS env var."""
        with patch.dict(os.environ, {'LLM_MODEL_ALIAS': 'deepseek'}):
            f = get_llm_client()
            self.assertIn('deepseek', f.model.lower())

    def test_get_llm_client_explicit_alias(self):
        f = get_llm_client('qwen-fast')
        self.assertIn('qwen', f.model.lower())


# ---------------------------------------------------------------------------
# TestLlmCallWithRetry
# ---------------------------------------------------------------------------

class TestLlmCallWithRetry(unittest.TestCase):
    """llm_call_with_retry retries once on JSON-parse failure, then raises."""

    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_success_on_first_call(self):
        """First call succeeds -> result returned, no retry."""
        call_count = 0

        async def fake_call(**kwargs):
            nonlocal call_count
            call_count += 1
            return '["A", "B"]'

        result = self._run(llm_call_with_retry(fake_call))
        self.assertEqual(result, '["A", "B"]')
        self.assertEqual(call_count, 1)

    def test_retry_on_json_parse_failure(self):
        """First call returns bad JSON -> retries once -> second call used."""
        responses = ['not json at all', '["ok"]']
        call_count = 0

        async def fake_call(**kwargs):
            nonlocal call_count
            r = responses[call_count]
            call_count += 1
            return r

        # The contract: llm_call_with_retry calls the function, validates JSON,
        # retries once if invalid, raises on second failure.
        # Here second call is valid JSON so it should succeed.
        result = self._run(llm_call_with_retry(fake_call, validate_json=True))
        self.assertEqual(call_count, 2)
        self.assertEqual(result, '["ok"]')

    def test_raises_after_two_failures(self):
        """Both calls return bad JSON -> ValueError raised."""
        async def fake_call(**kwargs):
            return 'totally not json'

        with self.assertRaises((ValueError, json.JSONDecodeError)):
            self._run(llm_call_with_retry(fake_call, validate_json=True))

    def test_no_retry_when_validate_json_false(self):
        """With validate_json=False, bad JSON is returned as-is."""
        call_count = 0

        async def fake_call(**kwargs):
            nonlocal call_count
            call_count += 1
            return 'not json'

        result = self._run(llm_call_with_retry(fake_call, validate_json=False))
        self.assertEqual(result, 'not json')
        self.assertEqual(call_count, 1)

    def test_kwargs_passed_through(self):
        """Extra kwargs are forwarded to the underlying callable."""
        received = {}

        async def fake_call(**kwargs):
            received.update(kwargs)
            return '[]'

        self._run(llm_call_with_retry(fake_call, validate_json=True,
                                       prompt='hello', temperature=0.3))
        self.assertEqual(received.get('prompt'), 'hello')
        self.assertAlmostEqual(received.get('temperature'), 0.3)

    def test_timeout_respected(self):
        """If the call exceeds timeout_sec, asyncio.TimeoutError is raised."""
        async def slow_call(**kwargs):
            await asyncio.sleep(10)
            return '[]'

        with self.assertRaises(asyncio.TimeoutError):
            self._run(llm_call_with_retry(slow_call, validate_json=False, timeout_sec=0.05))


if __name__ == '__main__':
    unittest.main()
