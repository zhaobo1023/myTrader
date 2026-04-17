"""
LLM client factory: multi-model alias routing + retry wrapper.

Usage:
    factory = get_llm_client()                    # reads LLM_MODEL_ALIAS env var
    factory = get_llm_client('deepseek')          # explicit alias
    text = await llm_call_with_retry(factory.call, prompt='...', validate_json=True)
"""
import asyncio
import json
import logging
import os
from typing import Optional

# HTTP timeout for LLM calls in seconds. Override with LLM_HTTP_TIMEOUT env var.
_LLM_HTTP_TIMEOUT = float(os.getenv('LLM_HTTP_TIMEOUT', '90'))

logger = logging.getLogger('myTrader.llm_factory')

# ---------------------------------------------------------------------------
# Model catalogue
# ---------------------------------------------------------------------------

SUPPORTED_ALIASES: dict[str, dict] = {
    'qwen': {
        'model': 'qwen3-max',
        'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        'api_key_env': 'RAG_API_KEY',
    },
    'qwen-fast': {
        'model': 'qwen3-8b',
        'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        'api_key_env': 'RAG_API_KEY',
    },
    'deepseek': {
        'model': 'deepseek-chat',
        'base_url': 'https://api.deepseek.com/v1',
        'api_key_env': 'DEEPSEEK_API_KEY',
    },
    'doubao': {
        'model': 'doubao-pro-128k',
        'base_url': 'https://ark.cn-beijing.volces.com/api/v3',
        'api_key_env': 'DOUBAO_API_KEY',
    },
}

_DEFAULT_ALIAS = 'qwen'


# ---------------------------------------------------------------------------
# Factory class
# ---------------------------------------------------------------------------

class LLMClientFactory:
    """Resolves a model alias to connection parameters and provides an async call method."""

    def __init__(self, alias: str = _DEFAULT_ALIAS):
        cfg = SUPPORTED_ALIASES.get(alias)
        if cfg is None:
            logger.warning('[LLMClientFactory] unknown alias %r, falling back to qwen', alias)
            cfg = SUPPORTED_ALIASES[_DEFAULT_ALIAS]
            alias = _DEFAULT_ALIAS

        self.alias = alias
        self.model: str = cfg['model']
        self.base_url: str = cfg['base_url']
        self._api_key_env: str = cfg['api_key_env']

    @property
    def api_key(self) -> str:
        return os.getenv(self._api_key_env, '')

    async def call(
        self,
        prompt: str,
        system_prompt: str = '',
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """Async LLM call using the OpenAI-compatible SDK.

        Wraps the synchronous LLMClient.generate() in a thread executor so
        FastAPI async handlers are not blocked.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._sync_call,
            prompt,
            system_prompt,
            temperature,
            max_tokens,
        )

    def _sync_call(
        self,
        prompt: str,
        system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        import httpx
        from openai import OpenAI

        key = self.api_key
        if not key:
            raise ValueError(f'API key env var {self._api_key_env!r} is not set')

        client = OpenAI(
            api_key=key,
            base_url=self.base_url,
            http_client=httpx.Client(timeout=_LLM_HTTP_TIMEOUT),
        )
        messages = []
        if system_prompt:
            messages.append({'role': 'system', 'content': system_prompt})
        messages.append({'role': 'user', 'content': prompt})

        resp = client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ''


def get_llm_client(alias: Optional[str] = None) -> LLMClientFactory:
    """Return a factory for the given alias (or LLM_MODEL_ALIAS env var)."""
    resolved = alias or os.getenv('LLM_MODEL_ALIAS', _DEFAULT_ALIAS)
    return LLMClientFactory(resolved)


# ---------------------------------------------------------------------------
# Retry wrapper
# ---------------------------------------------------------------------------

async def llm_call_with_retry(
    call_fn,
    *,
    validate_json: bool = True,
    timeout_sec: float = 30.0,
    **kwargs,
) -> str:
    """Call an async LLM function with optional JSON validation and one retry.

    Args:
        call_fn: Async callable that accepts **kwargs and returns str.
        validate_json: If True, parse the result as JSON; retry once on failure.
        timeout_sec: Overall timeout in seconds (asyncio.TimeoutError on breach).
        **kwargs: Forwarded to call_fn.

    Returns:
        The raw text returned by call_fn.

    Raises:
        asyncio.TimeoutError: If the total call time exceeds timeout_sec.
        ValueError / json.JSONDecodeError: If both attempts produce invalid JSON.
    """
    async def _attempt() -> str:
        result = await call_fn(**kwargs)
        if validate_json:
            json.loads(result)  # raises on bad JSON
        return result

    async def _run_with_retry() -> str:
        try:
            return await _attempt()
        except (json.JSONDecodeError, ValueError, OSError, ConnectionError) as first_err:
            logger.warning('[llm_call_with_retry] first attempt failed: %s — retrying', first_err)
            return await _attempt()  # second attempt; let exception propagate

    return await asyncio.wait_for(_run_with_retry(), timeout=timeout_sec)
