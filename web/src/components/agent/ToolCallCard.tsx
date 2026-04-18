'use client';

import { useState } from 'react';
import type { AgentToolCall } from '@/lib/agent-store';

const TOOL_LABELS: Record<string, string> = {
  query_portfolio: '查询持仓',
  get_stock_indicators: '技术指标',
  search_knowledge: '知识检索',
  query_database: '数据查询',
  get_fear_index: '恐慌指数',
  search_news: '新闻搜索',
  get_hot_sectors: '热门板块',
  run_tech_scan: '技术扫描',
  add_watchlist: '添加关注',
  add_position: '添加持仓',
};

export default function ToolCallCard({ tc }: { tc: AgentToolCall }) {
  const [expanded, setExpanded] = useState(false);
  const label = TOOL_LABELS[tc.name] || tc.name;

  return (
    <>
      <style>{`
        .tool-card {
          margin: 4px 0;
          border: 1px solid var(--border-subtle);
          border-radius: 6px;
          font-size: 12px;
          overflow: hidden;
        }
        .tool-card-header {
          display: flex;
          align-items: center;
          gap: 6px;
          padding: 6px 10px;
          cursor: pointer;
          background: var(--bg-canvas);
          color: var(--text-secondary);
        }
        .tool-card-header:hover {
          background: var(--bg-nav-hover);
        }
        .tool-card-status {
          width: 8px;
          height: 8px;
          border-radius: 50%;
        }
        .tool-card-status.loading {
          background: var(--amber, #f59e0b);
          animation: pulse 1s infinite;
        }
        .tool-card-status.success { background: var(--green, #22c55e); }
        .tool-card-status.error { background: var(--red, #ef4444); }
        .tool-card-body {
          padding: 8px 10px;
          border-top: 1px solid var(--border-subtle);
          background: var(--bg-canvas);
          overflow-x: auto;
        }
        .tool-card-body pre {
          margin: 0;
          font-size: 11px;
          white-space: pre-wrap;
          word-break: break-all;
          color: var(--text-secondary);
        }
        .tool-card-duration {
          margin-left: auto;
          color: var(--text-muted);
          font-size: 11px;
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
      <div className="tool-card">
        <div className="tool-card-header" onClick={() => setExpanded(!expanded)}>
          <span
            className={`tool-card-status ${tc.loading ? 'loading' : tc.success === false ? 'error' : 'success'}`}
          />
          <span>{tc.loading ? `调用 ${label}...` : `[工具] ${label}`}</span>
          {tc.durationMs != null && (
            <span className="tool-card-duration">{Math.round(tc.durationMs)}ms</span>
          )}
          <span style={{ marginLeft: 'auto', fontSize: 10 }}>
            {expanded ? '[-]' : '[+]'}
          </span>
        </div>
        {expanded && (
          <div className="tool-card-body">
            <div style={{ marginBottom: 4, fontWeight: 600 }}>参数:</div>
            <pre>{JSON.stringify(tc.params, null, 2)}</pre>
            {tc.result && (
              <>
                <div style={{ marginTop: 8, marginBottom: 4, fontWeight: 600 }}>结果:</div>
                <pre>{JSON.stringify(tc.result, null, 2)}</pre>
              </>
            )}
          </div>
        )}
      </div>
    </>
  );
}
