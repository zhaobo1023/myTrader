'use client';

import { useAgentStore } from '@/lib/agent-store';

export default function FloatingButton() {
  const { isOpen, toggle } = useAgentStore();

  if (isOpen) return null;

  return (
    <>
      <style>{`
        .agent-fab {
          position: fixed;
          right: 24px;
          bottom: 24px;
          width: 48px;
          height: 48px;
          border-radius: 50%;
          background: var(--accent, #2563eb);
          color: #fff;
          border: none;
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          box-shadow: 0 4px 12px rgba(0,0,0,0.15);
          z-index: 9990;
          transition: transform 0.2s, box-shadow 0.2s;
        }
        .agent-fab:hover {
          transform: scale(1.1);
          box-shadow: 0 6px 20px rgba(0,0,0,0.25);
        }
        .agent-fab:active {
          transform: scale(0.95);
        }
        @media (max-width: 767px) {
          .agent-fab {
            right: 16px;
            bottom: 16px;
          }
        }
      `}</style>
      <button className="agent-fab" onClick={toggle} title="交易助手">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 2a3 3 0 0 0-3 3v1H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-3V5a3 3 0 0 0-3-3z" />
          <circle cx="9" cy="12" r="1" fill="currentColor" />
          <circle cx="15" cy="12" r="1" fill="currentColor" />
          <path d="M9 16c.5.5 1.5 1 3 1s2.5-.5 3-1" />
        </svg>
      </button>
    </>
  );
}
