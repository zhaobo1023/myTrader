'use client';

import { useEffect, useRef } from 'react';
import { useAgentStore } from '@/lib/agent-store';
import type { AgentMessage } from '@/lib/agent-store';
import ToolCallCard from './ToolCallCard';
import ActionConfirm from './ActionConfirm';

function UserMessage({ msg }: { msg: AgentMessage }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
      <div
        style={{
          maxWidth: '80%',
          padding: '8px 12px',
          borderRadius: '12px 12px 2px 12px',
          background: 'var(--accent, #2563eb)',
          color: '#fff',
          fontSize: 14,
          lineHeight: 1.5,
          wordBreak: 'break-word',
        }}
      >
        {msg.content}
      </div>
    </div>
  );
}

function AssistantMessage({ msg }: { msg: AgentMessage }) {
  const isStreaming = useAgentStore((s) => s.isStreaming);
  const isLatest =
    useAgentStore(
      (s) => s.messages.filter((m) => m.role === 'assistant').pop()?.id,
    ) === msg.id;

  return (
    <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 8 }}>
      <div style={{ maxWidth: '85%' }}>
        {/* Tool calls */}
        {msg.toolCalls?.map((tc) => (
          <ToolCallCard key={tc.callId} tc={tc} />
        ))}

        {/* Text content */}
        {msg.content && (
          <div
            style={{
              padding: '8px 12px',
              borderRadius: '12px 12px 12px 2px',
              background: 'var(--bg-panel)',
              border: '1px solid var(--border-subtle)',
              fontSize: 14,
              lineHeight: 1.6,
              color: 'var(--text-primary)',
              wordBreak: 'break-word',
              whiteSpace: 'pre-wrap',
            }}
          >
            {msg.content}
            {isStreaming && isLatest && (
              <span
                style={{
                  display: 'inline-block',
                  width: 6,
                  height: 14,
                  marginLeft: 2,
                  background: 'var(--accent)',
                  animation: 'blink 1s step-end infinite',
                  verticalAlign: 'text-bottom',
                }}
              />
            )}
          </div>
        )}

        {/* Thinking state */}
        {!msg.content && !msg.toolCalls?.length && isStreaming && isLatest && (
          <div
            style={{
              padding: '8px 12px',
              borderRadius: '12px 12px 12px 2px',
              background: 'var(--bg-panel)',
              border: '1px solid var(--border-subtle)',
              fontSize: 13,
              color: 'var(--text-muted)',
            }}
          >
            思考中...
          </div>
        )}

        {/* Action confirm */}
        {msg.action && <ActionConfirm action={msg.action} />}
      </div>
    </div>
  );
}

export default function MessageList() {
  const messages = useAgentStore((s) => s.messages);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto scroll to bottom
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <>
      <style>{`
        .agent-message-list {
          flex: 1;
          overflow-y: auto;
          padding: 12px;
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        @keyframes blink {
          50% { opacity: 0; }
        }
      `}</style>
      <div className="agent-message-list">
        {messages.length === 0 && (
          <div
            style={{
              textAlign: 'center',
              color: 'var(--text-muted)',
              fontSize: 13,
              paddingTop: 40,
            }}
          >
            有什么可以帮您？支持持仓查询、技术分析、市场情绪等。
          </div>
        )}
        {messages.map((msg) =>
          msg.role === 'user' ? (
            <UserMessage key={msg.id} msg={msg} />
          ) : msg.role === 'assistant' ? (
            <AssistantMessage key={msg.id} msg={msg} />
          ) : null,
        )}
        <div ref={bottomRef} />
      </div>
    </>
  );
}
