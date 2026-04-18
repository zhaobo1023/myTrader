# -*- coding: utf-8 -*-
"""
AgentOrchestrator - core ReAct loop engine.

Drives the LLM -> Tool -> LLM cycle with SSE event streaming.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncIterator, Optional

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.user import User
from api.services.agent.conversation import ConversationStore
from api.services.agent.llm_chat import AgentLLMClient
from api.services.agent.prompts import build_system_prompt
from api.services.agent.schemas import AgentContext
from api.services.agent.tool_registry import ToolRegistry

logger = logging.getLogger('myTrader.agent.orchestrator')

MAX_ITERATIONS = 10


class AgentOrchestrator:
    """Core agent engine: receives user message, runs ReAct loop, yields SSE events."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        llm_client: AgentLLMClient,
        conversation_store: ConversationStore,
    ):
        self.registry = tool_registry
        self.llm = llm_client
        self.store = conversation_store

    async def chat(
        self,
        message: str,
        user: User,
        db: AsyncSession,
        redis: aioredis.Redis,
        conversation_id: Optional[str] = None,
        active_skill: Optional[str] = None,
        page_context: Optional[dict] = None,
    ) -> AsyncIterator[dict]:
        """Run a ReAct loop for the user's message.

        Yields SSE-compatible event dicts:
            thinking, tool_call, tool_result, token, action, done, error
        """
        # 1. Create or load conversation
        if not conversation_id:
            conversation_id = await self.store.create(user.id)

        # Save user message
        await self.store.save_message(conversation_id, "user", message)

        # 2. Build context
        ctx = AgentContext(
            user=user,
            db=db,
            redis=redis,
            conversation_id=conversation_id,
            page_context=page_context or {},
        )

        # 3. Get available tools for this user
        user_tools = self.registry.get_tools_for_user(user)
        openai_tools = [t.to_openai_tool() for t in user_tools]
        tool_names = [t.name for t in user_tools]

        # 4. Build system prompt
        active_skill_prompt = None
        if active_skill:
            skill_tool = self.registry.get_tool(active_skill)
            if skill_tool and hasattr(skill_tool, '_plugin_system_prompt'):
                active_skill_prompt = skill_tool._plugin_system_prompt

        system_prompt = build_system_prompt(
            page_context=page_context,
            active_skill_prompt=active_skill_prompt,
            tool_names=tool_names,
        )

        # 5. Load conversation history
        history = await self.store.get_messages_for_llm(conversation_id)

        # Build messages for LLM
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)

        # 6. ReAct Loop
        total_content = ""

        try:
            for iteration in range(MAX_ITERATIONS):
                yield {"type": "thinking", "iteration": iteration + 1}

                # Call LLM
                got_tool_calls = False
                current_content = ""
                current_tool_calls = []

                async for event in self.llm.chat_stream(messages, openai_tools):
                    event_type = event.get("type")

                    if event_type == "token":
                        content = event.get("content", "")
                        current_content += content
                        yield {"type": "token", "content": content}

                    elif event_type == "tool_calls":
                        got_tool_calls = True
                        current_tool_calls = event.get("calls", [])

                    elif event_type == "error":
                        yield {"type": "error", "message": event.get("message", "LLM error"), "code": "llm_error"}
                        return

                    elif event_type == "finish":
                        pass

                if not got_tool_calls:
                    # No tool calls - we have the final answer
                    total_content = current_content
                    # Save final assistant message
                    if total_content:
                        await self.store.save_message(conversation_id, "assistant", total_content)
                    break

                # Build assistant message with tool_calls for this iteration
                assistant_tool_calls = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"], ensure_ascii=False),
                        },
                    }
                    for tc in current_tool_calls
                ]
                messages.append({
                    "role": "assistant",
                    "content": current_content or None,
                    "tool_calls": assistant_tool_calls,
                })
                # Persist this iteration's assistant message immediately
                await self.store.save_message(
                    conversation_id, "assistant",
                    content=current_content or None,
                    tool_calls=assistant_tool_calls,
                )

                for tc in current_tool_calls:
                    call_id = tc["id"]
                    tool_name = tc["name"]
                    tool_args = tc["arguments"]

                    yield {
                        "type": "tool_call",
                        "name": tool_name,
                        "params": tool_args,
                        "call_id": call_id,
                    }

                    # Check if this is an action tool
                    tool_def = self.registry.get_tool(tool_name)
                    if tool_def and tool_def.category == "action":
                        # Emit action event for frontend confirmation
                        yield {
                            "type": "action",
                            "action": tool_name,
                            "payload": tool_args,
                        }
                        # For action tools, return a confirmation message to LLM
                        tool_result_str = json.dumps(
                            {"status": "pending_confirmation", "message": "Action sent to user for confirmation"},
                            ensure_ascii=False,
                        )
                    else:
                        # Execute non-action tool
                        result = await self.registry.execute(tool_name, tool_args, ctx)
                        result.call_id = call_id

                        yield {
                            "type": "tool_result",
                            "name": tool_name,
                            "result": result.result if result.success else {"error": result.error},
                            "call_id": call_id,
                            "duration_ms": round(result.duration_ms, 1),
                            "success": result.success,
                        }

                        tool_result_str = json.dumps(
                            result.result if result.success else {"error": result.error},
                            ensure_ascii=False,
                            default=str,
                        )

                    # Append tool result to messages and persist
                    tool_msg = {
                        "role": "tool",
                        "content": tool_result_str,
                        "tool_call_id": call_id,
                        "name": tool_name,
                    }
                    messages.append(tool_msg)
                    await self.store.save_message(
                        conversation_id, "tool",
                        content=tool_result_str,
                        tool_call_id=call_id,
                        tool_name=tool_name,
                    )
            else:
                # Hit max iterations
                yield {
                    "type": "token",
                    "content": "\n\n[INFO] 已达到最大工具调用次数限制，基于已有信息给出回答。",
                }

            yield {
                "type": "done",
                "conversation_id": conversation_id,
            }

        except Exception as e:
            logger.error('[Orchestrator] chat failed: %s', e, exc_info=True)
            yield {
                "type": "error",
                "message": str(e),
                "code": "orchestrator_error",
            }
