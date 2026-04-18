'use client';

import { useAgentStore } from '@/lib/agent-store';
import { useAgentChat } from '@/hooks/useAgentChat';
import MessageList from './MessageList';
import QuickActions from './QuickActions';
import InputBar from './InputBar';

export default function ChatPanel() {
  const { isOpen, mode, setOpen, setMode, newConversation } = useAgentStore();
  const { sendMessage, cancel, isStreaming } = useAgentChat();

  if (!isOpen) return null;

  const isFullscreen = mode === 'fullscreen';

  return (
    <>
      <style>{`
        .agent-panel {
          position: fixed;
          z-index: 9999;
          background: var(--bg-panel, #fff);
          border: 1px solid var(--border-subtle);
          display: flex;
          flex-direction: column;
          overflow: hidden;
          transition: all 0.2s ease;
        }
        .agent-panel.floating {
          right: 24px;
          bottom: 24px;
          width: 400px;
          height: 600px;
          border-radius: 12px;
          box-shadow: 0 8px 32px rgba(0,0,0,0.12);
        }
        .agent-panel.fullscreen {
          right: 0;
          top: 0;
          width: 50%;
          height: 100vh;
          border-radius: 0;
          border-left: 1px solid var(--border-solid);
          box-shadow: -4px 0 20px rgba(0,0,0,0.08);
        }
        .agent-panel-header {
          display: flex;
          align-items: center;
          padding: 10px 12px;
          border-bottom: 1px solid var(--border-subtle);
          background: var(--bg-panel);
          gap: 8px;
          flex-shrink: 0;
        }
        .agent-panel-title {
          font-size: 14px;
          font-weight: 600;
          color: var(--text-primary);
          flex: 1;
        }
        .agent-panel-btn {
          width: 28px;
          height: 28px;
          border: none;
          background: none;
          cursor: pointer;
          border-radius: 4px;
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--text-secondary);
          font-size: 16px;
        }
        .agent-panel-btn:hover {
          background: var(--bg-nav-hover);
          color: var(--text-primary);
        }
        @media (max-width: 767px) {
          .agent-panel.floating {
            right: 0;
            bottom: 0;
            width: 100%;
            height: 100%;
            border-radius: 0;
          }
          .agent-panel.fullscreen {
            width: 100%;
          }
        }
      `}</style>
      <div className={`agent-panel ${isFullscreen ? 'fullscreen' : 'floating'}`}>
        {/* Header */}
        <div className="agent-panel-header">
          <span className="agent-panel-title">交易助手</span>
          <button
            className="agent-panel-btn"
            onClick={newConversation}
            title="New conversation"
          >
            +
          </button>
          <button
            className="agent-panel-btn"
            onClick={() => setMode(isFullscreen ? 'floating' : 'fullscreen')}
            title={isFullscreen ? 'Minimize' : 'Fullscreen'}
          >
            {isFullscreen ? '[-]' : '[+]'}
          </button>
          <button
            className="agent-panel-btn"
            onClick={() => {
              if (isStreaming) cancel();
              setOpen(false);
            }}
            title="Close"
          >
            x
          </button>
        </div>

        {/* Messages */}
        <MessageList />

        {/* Quick Actions */}
        <QuickActions onSend={sendMessage} />

        {/* Input */}
        <InputBar onSend={sendMessage} />
      </div>
    </>
  );
}
