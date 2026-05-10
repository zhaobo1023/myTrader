"""
LLM client factory: multi-model alias routing + retry wrapper.

Usage:
    factory = get_llm_client()                    # reads LLM_MODEL_ALIAS env var
    factory = get_llm_client('deepseek')          # explicit alias
    factory = get_llm_client_for_scene('agent_chat')  # scene-based from DB
    text = await llm_call_with_retry(factory.call, prompt='...', validate_json=True)
"""
import asyncio
import json
import logging
from typing import Optional

from config.settings import LLM_HTTP_TIMEOUT as _LLM_HTTP_TIMEOUT
from config.settings import LLM_MODEL_ALIAS as _LLM_MODEL_ALIAS_DEFAULT
from config.settings import RAG_API_KEY
from config.settings import DEEPSEEK_API_KEY
from config.settings import DOUBAO_API_KEY

# Map api_key_env name -> actual value from settings
_API_KEY_MAP = {
    'RAG_API_KEY': RAG_API_KEY,
    'DEEPSEEK_API_KEY': DEEPSEEK_API_KEY,
    'DOUBAO_API_KEY': DOUBAO_API_KEY,
}

logger = logging.getLogger('myTrader.llm_factory')

# In-memory cache for DB config: scene -> config dict
# Invalidated when admin updates config via API.
_scene_config_cache: dict[str, dict] = {}
_scene_cache_loaded: bool = False

# ---------------------------------------------------------------------------
# Model catalogue
# ---------------------------------------------------------------------------

SUPPORTED_ALIASES: dict[str, dict] = {
    'qwen': {
        'model': 'qwen3.6-plus',
        'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        'api_key_env': 'RAG_API_KEY',
    },
    'qwen-fast': {
        'model': 'qwen3.6-plus',
        'base_url': 'https://dashscope.aliyuncs.com/compatible-mode/v1',
        'api_key_env': 'RAG_API_KEY',
    },
    'deepseek': {
        'model': 'deepseek-chat',
        'base_url': 'https://api.deepseek.com/v1',
        'api_key_env': 'DEEPSEEK_API_KEY',
    },
    'deepseek-v4-pro': {
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
        key = _API_KEY_MAP.get(self._api_key_env, '')
        if not key:
            logger.warning('[LLMClientFactory] no API key found for env var %r '
                           '(not in _API_KEY_MAP or value is empty)', self._api_key_env)
        return key

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
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._sync_call,
            prompt,
            system_prompt,
            temperature,
            max_tokens,
        )

    def call_sync(
        self,
        prompt: str,
        system_prompt: str = '',
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> str:
        """Synchronous LLM call (public API for non-async callers)."""
        return self._sync_call(prompt, system_prompt, temperature, max_tokens)

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
            # Disable SDK-level retries: the SDK retries on timeout by default,
            # which multiplies wall time (90s timeout * 3 attempts = 270s+).
            # llm_call_with_retry() handles retry logic at the application level.
            max_retries=0,
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
    """Return a factory for the given alias (or LLM_MODEL_ALIAS setting)."""
    resolved = alias or _LLM_MODEL_ALIAS_DEFAULT or _DEFAULT_ALIAS
    return LLMClientFactory(resolved)


# ---------------------------------------------------------------------------
# Scene-based config from DB
# ---------------------------------------------------------------------------

def _load_scene_config_from_db() -> dict[str, dict]:
    """Load all scene configs from llm_model_config table. Returns scene -> config dict."""
    try:
        from config.db import execute_query
        rows = execute_query(
            "SELECT scene, alias, model, base_url, api_key_env, enabled "
            "FROM llm_model_config WHERE enabled = 1",
        )
        if not rows:
            return {}
        result = {}
        for row in rows:
            scene = row['scene']
            result[scene] = {
                'alias': row['alias'],
                'model': row['model'],
                'base_url': row['base_url'],
                'api_key_env': row['api_key_env'],
            }
        return result
    except Exception as e:
        logger.warning('[llm_factory] failed to load scene config from DB: %s', e)
        return {}


def _ensure_scene_cache():
    """Populate the in-memory cache if not yet loaded."""
    global _scene_cache_loaded, _scene_config_cache
    if not _scene_cache_loaded:
        _scene_config_cache = _load_scene_config_from_db()
        _scene_cache_loaded = True


def get_llm_client_for_scene(scene: str) -> LLMClientFactory:
    """Return a factory configured for a specific usage scene.

    Looks up the scene in the DB config table first; falls back to
    the default alias if no DB config is found.
    """
    _ensure_scene_cache()
    cfg = _scene_config_cache.get(scene)
    if cfg is None:
        logger.debug('[llm_factory] no DB config for scene %r, using default', scene)
        return get_llm_client()

    factory = LLMClientFactory.__new__(LLMClientFactory)
    factory.alias = cfg['alias']
    factory.model = cfg['model']
    factory.base_url = cfg['base_url']
    factory._api_key_env = cfg['api_key_env']
    return factory


def invalidate_scene_cache():
    """Invalidate the in-memory scene config cache.

    Called by the admin API after updating LLM config.
    """
    global _scene_cache_loaded, _scene_config_cache
    _scene_cache_loaded = False
    _scene_config_cache = {}
    logger.info('[llm_factory] scene config cache invalidated')


def get_all_scene_configs() -> dict[str, dict]:
    """Return current scene configs (from cache or DB). For admin API."""
    _ensure_scene_cache()
    return dict(_scene_config_cache)


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
