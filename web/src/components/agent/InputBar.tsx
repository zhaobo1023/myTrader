'use client';

import { useState, useRef, useCallback } from 'react';
import { useAgentStore } from '@/lib/agent-store';

interface InputBarProps {
  onSend: (message: string) => void;
}

export default function InputBar({ onSend }: InputBarProps) {
  const [text, setText] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const isStreaming = useAgentStore((s) => s.isStreaming);

  const handleSend = useCallback(() => {
    const msg = text.trim();
    if (!msg || isStreaming) return;
    onSend(msg);
    setText('');
    inputRef.current?.focus();
  }, [text, isStreaming, onSend]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  return (
    <>
      <style>{`
        .agent-input-bar {
          display: flex;
          gap: 8px;
          padding: 12px;
          border-top: 1px solid var(--border-subtle);
          background: var(--bg-panel);
        }
        .agent-input-textarea {
          flex: 1;
          resize: none;
          border: 1px solid var(--border-subtle);
          border-radius: 8px;
          padding: 8px 12px;
          font-size: 14px;
          line-height: 1.4;
          background: var(--bg-canvas);
          color: var(--text-primary);
          outline: none;
          min-height: 36px;
          max-height: 100px;
        }
        .agent-input-textarea:focus {
          border-color: var(--accent);
        }
        .agent-send-btn {
          padding: 8px 16px;
          background: var(--accent, #2563eb);
          color: #fff;
          border: none;
          border-radius: 8px;
          cursor: pointer;
          font-size: 14px;
          white-space: nowrap;
          align-self: flex-end;
        }
        .agent-send-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .agent-send-btn:hover:not(:disabled) {
          filter: brightness(1.1);
        }
      `}</style>
      <div className="agent-input-bar">
        <textarea
          ref={inputRef}
          className="agent-input-textarea"
          placeholder="输入问题..."
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          disabled={isStreaming}
        />
        <button
          className="agent-send-btn"
          onClick={handleSend}
          disabled={!text.trim() || isStreaming}
        >
          {isStreaming ? '...' : '发送'}
        </button>
      </div>
    </>
  );
}
