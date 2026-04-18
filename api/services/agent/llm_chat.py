# -*- coding: utf-8 -*-
"""
AgentLLMClient - streaming LLM client with function calling support.

Uses DashScope (Qwen) via OpenAI-compatible API.
"""
from __future__ import annotations

import json
import logging
import os
from typing import AsyncIterator

logger = logging.getLogger('myTrader.agent.llm')

_LLM_TIMEOUT = float(os.getenv('AGENT_LLM_TIMEOUT', '90'))


class AgentLLMClient:
    """Streaming LLM client for agent function calling."""

    def __init__(self, model_alias: str = "qwen"):
        from api.services.llm_client_factory import SUPPORTED_ALIASES, _DEFAULT_ALIAS
        cfg = SUPPORTED_ALIASES.get(model_alias, SUPPORTED_ALIASES[_DEFAULT_ALIAS])
        self.model = cfg['model']
        self.base_url = cfg['base_url']
        self._api_key_env = cfg['api_key_env']

    @property
    def api_key(self) -> str:
        return os.getenv(self._api_key_env, '')

    async def chat_stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float = 0.7,
    ) -> AsyncIterator[dict]:
        """Stream a chat completion with optional function calling.

        Yields events:
            {"type": "token", "content": "..."}
            {"type": "tool_calls", "calls": [...]}
            {"type": "finish", "reason": "stop|tool_calls"}
        """
        import asyncio
        import httpx
        from openai import OpenAI

        key = self.api_key
        if not key:
            yield {"type": "error", "message": f"API key {self._api_key_env} not set"}
            return

        client = OpenAI(
            api_key=key,
            base_url=self.base_url,
            http_client=httpx.Client(timeout=_LLM_TIMEOUT),
        )

        kwargs = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools

        try:
            response = await asyncio.get_running_loop().run_in_executor(
                None,
                lambda: client.chat.completions.create(**kwargs),
            )
        except Exception as e:
            logger.error('[AgentLLMClient] API call failed: %s', e)
            yield {"type": "error", "message": str(e)}
            return

        tool_calls_buffer: dict[int, dict] = {}
        finish_reason = None

        try:
            for chunk in response:
                if not chunk.choices:
                    continue

                choice = chunk.choices[0]
                delta = choice.delta
                finish_reason = choice.finish_reason

                # Text content
                if delta and delta.content:
                    yield {"type": "token", "content": delta.content}

                # Tool call incremental assembly
                if delta and delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_buffer:
                            tool_calls_buffer[idx] = {
                                "id": tc.id or "",
                                "name": "",
                                "arguments": "",
                            }
                        if tc.id and not tool_calls_buffer[idx]["id"]:
                            tool_calls_buffer[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_buffer[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_buffer[idx]["arguments"] += tc.function.arguments
        except Exception as e:
            logger.error('[AgentLLMClient] stream processing error: %s', e)
            yield {"type": "error", "message": str(e)}
            return

        # Emit assembled tool calls
        if tool_calls_buffer:
            calls = []
            for idx in sorted(tool_calls_buffer.keys()):
                tc = tool_calls_buffer[idx]
                # Parse arguments JSON
                try:
                    args = json.loads(tc["arguments"]) if tc["arguments"] else {}
                except json.JSONDecodeError:
                    args = {}
                calls.append({
                    "id": tc["id"],
                    "name": tc["name"],
                    "arguments": args,
                })
            yield {"type": "tool_calls", "calls": calls}

        yield {"type": "finish", "reason": finish_reason or "stop"}
