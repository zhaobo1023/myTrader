'use client';

import { useMemo } from 'react';
import { useAgentStore } from '@/lib/agent-store';

interface QuickAction {
  label: string;
  message: string;
}

const PAGE_ACTIONS: Record<string, QuickAction[]> = {
  market: [
    { label: 'Technical Analysis', message: 'Help me analyze the technical indicators of this stock' },
    { label: 'Add to Watchlist', message: 'Help me add this stock to my watchlist' },
    { label: 'AI Interpretation', message: 'Help me interpret the current trend of this stock' },
  ],
  dashboard: [
    { label: 'Portfolio Diagnosis', message: 'Help me diagnose my current portfolio' },
    { label: 'Risk Check', message: 'Check my portfolio risk levels' },
    { label: 'Rebalance Advice', message: 'Give me rebalancing suggestions' },
  ],
  analysis: [
    { label: 'Deep Analysis', message: 'Perform a deep analysis on this stock' },
    { label: 'Buffett View', message: 'Analyze this stock from Buffett value investing perspective' },
    { label: 'Compare', message: 'Help me compare with industry peers' },
  ],
  strategy: [
    { label: 'Strategy Review', message: 'Evaluate the performance of this strategy' },
    { label: 'Optimize Params', message: 'Suggest parameter optimization for this strategy' },
  ],
  sentiment: [
    { label: 'Hot Topics', message: 'Interpret current market hot topics and sentiment' },
    { label: 'Impact Analysis', message: 'Analyze how current news impacts my portfolio' },
  ],
  positions: [
    { label: 'Position Scan', message: 'Scan my positions for technical signals' },
    { label: 'Risk Alert', message: 'Check if any positions need attention' },
  ],
};

const DEFAULT_ACTIONS: QuickAction[] = [
  { label: 'Portfolio Overview', message: 'Show me my portfolio overview' },
  { label: 'Market Sentiment', message: 'What is the current market sentiment?' },
  { label: 'Hot Sectors', message: 'Which sectors are hot today?' },
];

interface QuickActionsProps {
  onSend: (message: string) => void;
}

export default function QuickActions({ onSend }: QuickActionsProps) {
  const pageContext = useAgentStore((s) => s.pageContext);
  const isStreaming = useAgentStore((s) => s.isStreaming);
  const messages = useAgentStore((s) => s.messages);

  const actions = useMemo(() => {
    const page = (pageContext.page as string) || '';
    const stockCode = pageContext.stock_code as string;
    let acts = PAGE_ACTIONS[page] || DEFAULT_ACTIONS;

    // Inject stock code into messages if available
    if (stockCode) {
      acts = acts.map((a) => ({
        ...a,
        message: a.message.replace('this stock', `stock ${stockCode}`),
      }));
    }
    return acts;
  }, [pageContext]);

  // Hide quick actions after first message
  if (messages.length > 0) return null;

  return (
    <>
      <style>{`
        .agent-quick-actions {
          display: flex;
          gap: 6px;
          padding: 8px 12px;
          overflow-x: auto;
          scrollbar-width: none;
        }
        .agent-quick-actions::-webkit-scrollbar { display: none; }
        .agent-quick-btn {
          flex-shrink: 0;
          padding: 6px 12px;
          border: 1px solid var(--border-subtle);
          border-radius: 16px;
          background: var(--bg-panel);
          color: var(--text-secondary);
          font-size: 12px;
          cursor: pointer;
          white-space: nowrap;
          transition: all 0.15s;
        }
        .agent-quick-btn:hover {
          border-color: var(--accent);
          color: var(--accent);
          background: var(--bg-nav-hover);
        }
        .agent-quick-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
      `}</style>
      <div className="agent-quick-actions">
        {actions.map((a) => (
          <button
            key={a.label}
            className="agent-quick-btn"
            onClick={() => onSend(a.message)}
            disabled={isStreaming}
          >
            {a.label}
          </button>
        ))}
      </div>
    </>
  );
}
