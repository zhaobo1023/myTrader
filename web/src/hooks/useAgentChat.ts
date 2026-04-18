'use client';

import { useCallback, useRef } from 'react';
import { useAgentStore, nextMsgId } from '@/lib/agent-store';
import type { AgentToolCall, AgentAction } from '@/lib/agent-store';

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || '';
const SSE_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes

/**
 * Hook for agent chat SSE communication.
 *
 * Handles streaming events: thinking, tool_call, tool_result, token, action, done, error.
 */
export function useAgentChat() {
  const abortRef = useRef<AbortController | null>(null);

  const {
    conversationId,
    activeSkill,
    pageContext,
    addMessage,
    updateLastAssistantContent,
    addToolCallToLastAssistant,
    updateToolCallResult,
    addActionToLastAssistant,
    setStreaming,
    setConversationId,
  } = useAgentStore();

  const sendMessage = useCallback(
    async (content: string) => {
      // Add user message
      addMessage({
        id: nextMsgId(),
        role: 'user',
        content,
        timestamp: Date.now(),
      });

      // Add empty assistant message for streaming
      addMessage({
        id: nextMsgId(),
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
      });

      setStreaming(true);

      // Abort previous stream
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      const timeoutId = setTimeout(() => controller.abort(), SSE_TIMEOUT_MS);

      try {
        const token =
          typeof window !== 'undefined'
            ? localStorage.getItem('access_token')
            : null;

        const resp = await fetch(`${BASE_URL}/api/agent/chat`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({
            message: content,
            conversation_id: conversationId,
            active_skill: activeSkill,
            page_context: pageContext,
          }),
          signal: controller.signal,
        });

        if (!resp.ok) {
          const errText = await resp.text().catch(() => '');
          throw new Error(`Request failed: ${resp.status} ${errText}`);
        }

        const reader = resp.body?.getReader();
        if (!reader) throw new Error('Response body not readable');

        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split('\n\n');
          buffer = parts.pop() ?? '';

          for (const chunk of parts) {
            for (const line of chunk.split('\n')) {
              if (!line.startsWith('data: ')) continue;

              let event: Record<string, unknown>;
              try {
                event = JSON.parse(line.slice(6));
              } catch {
                continue;
              }

              const type = event.type as string;

              switch (type) {
                case 'thinking':
                  // Could show thinking indicator
                  break;

                case 'tool_call': {
                  const tc: AgentToolCall = {
                    callId: event.call_id as string,
                    name: event.name as string,
                    params: (event.params as Record<string, unknown>) || {},
                    loading: true,
                  };
                  addToolCallToLastAssistant(tc);
                  break;
                }

                case 'tool_result':
                  updateToolCallResult(
                    event.call_id as string,
                    (event.result as Record<string, unknown>) || {},
                    (event.duration_ms as number) || 0,
                    (event.success as boolean) ?? true,
                  );
                  break;

                case 'token':
                  updateLastAssistantContent(event.content as string);
                  break;

                case 'action': {
                  const action: AgentAction = {
                    action: event.action as string,
                    payload: (event.payload as Record<string, unknown>) || {},
                  };
                  addActionToLastAssistant(action);
                  break;
                }

                case 'done':
                  if (event.conversation_id) {
                    setConversationId(event.conversation_id as string);
                  }
                  break;

                case 'error':
                  updateLastAssistantContent(
                    `\n\n[ERROR] ${event.message || 'Unknown error'}`,
                  );
                  break;
              }
            }
          }
        }
      } catch (err: unknown) {
        if ((err as Error).name === 'AbortError') {
          updateLastAssistantContent('\n\n[INFO] 请求已取消。');
        } else {
          updateLastAssistantContent(
            `\n\n[ERROR] ${(err as Error).message || '网络错误'}`,
          );
        }
      } finally {
        clearTimeout(timeoutId);
        setStreaming(false);
        abortRef.current = null;
      }
    },
    [
      conversationId,
      activeSkill,
      pageContext,
      addMessage,
      updateLastAssistantContent,
      addToolCallToLastAssistant,
      updateToolCallResult,
      addActionToLastAssistant,
      setStreaming,
      setConversationId,
    ],
  );

  const cancel = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const isStreaming = useAgentStore((s) => s.isStreaming);

  return { sendMessage, cancel, isStreaming };
}
