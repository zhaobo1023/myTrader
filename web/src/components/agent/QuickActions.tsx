'use client';

import { useMemo } from 'react';
import { useAgentStore } from '@/lib/agent-store';

interface QuickAction {
  label: string;
  message: string;
}

const PAGE_ACTIONS: Record<string, QuickAction[]> = {
  market: [
    { label: '技术分析', message: '帮我分析这只股票的技术指标' },
    { label: '加入自选', message: '帮我把这只股票加入自选' },
    { label: 'AI解读', message: '帮我解读这只股票当前的走势' },
  ],
  dashboard: [
    { label: '持仓诊断', message: '帮我诊断一下当前持仓情况' },
    { label: '风险检查', message: '检查一下我的持仓风险水平' },
    { label: '调仓建议', message: '给我一些仓位再平衡的建议' },
  ],
  analysis: [
    { label: '深度分析', message: '对这只股票做深度分析' },
    { label: '巴菲特视角', message: '从巴菲特价值投资角度分析这只股票' },
    { label: '同业对比', message: '帮我与同行业股票做对比分析' },
  ],
  strategy: [
    { label: '策略评估', message: '评估一下这个策略的表现' },
    { label: '参数优化', message: '为这个策略提供参数优化建议' },
  ],
  sentiment: [
    { label: '热点解读', message: '解读当前市场热点和情绪' },
    { label: '影响分析', message: '分析当前新闻对我持仓的影响' },
  ],
  positions: [
    { label: '技术扫描', message: '扫描我的持仓技术信号' },
    { label: '风险预警', message: '检查是否有持仓需要关注' },
  ],
};

const DEFAULT_ACTIONS: QuickAction[] = [
  { label: '持仓总览', message: '展示我的持仓概况' },
  { label: '市场情绪', message: '当前市场情绪如何？' },
  { label: '热门板块', message: '今天哪些板块最热？' },
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
        message: a.message.replace('这只股票', `${stockCode}`),
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
