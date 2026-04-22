'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import type { AgentAction } from '@/lib/agent-store';
import { watchlistApi, positionsApi } from '@/lib/api-client';

const ACTION_LABELS: Record<string, string> = {
  add_watchlist: '添加到关注列表',
  add_position: '添加到持仓',
  trade_position: '调仓操作',
  navigate: '页面跳转',
  show_chart: '查看图表',
};

export default function ActionConfirm({ action }: { action: AgentAction }) {
  const [status, setStatus] = useState<'pending' | 'confirmed' | 'cancelled' | 'error'>('pending');
  const router = useRouter();

  const label = ACTION_LABELS[action.action] || action.action;
  const payload = action.payload || {};

  const handleConfirm = useCallback(async () => {
    try {
      switch (action.action) {
        case 'add_watchlist':
          await watchlistApi.add(
            payload.stock_code as string,
            payload.stock_name as string,
            (payload.note as string) || '',
          );
          break;
        case 'trade_position': {
          // Look up position id by stock_code, then call trade API
          const stockCode = (payload.stock_code as string || '').split('.')[0];
          const listRes = await positionsApi.list({ active_only: true });
          const pos = listRes.items.find(
            (p) => (p.stock_code || '').split('.')[0] === stockCode
          );
          if (!pos) throw new Error(`未找到持仓 ${payload.stock_code}`);
          await positionsApi.trade(pos.id, {
            action: payload.action as 'add' | 'reduce' | 'close',
            price: Number(payload.price),
            shares: payload.shares ? Number(payload.shares) : undefined,
          });
          break;
        }
        case 'navigate':
          router.push(payload.path as string);
          break;
        // Other actions can be added here
      }
      setStatus('confirmed');
    } catch {
      setStatus('error');
    }
  }, [action.action, payload, router]);

  const handleCancel = useCallback(() => {
    setStatus('cancelled');
  }, []);

  const description =
    action.action === 'add_watchlist'
      ? `${payload.stock_name || ''}(${payload.stock_code || ''})`
      : action.action === 'trade_position'
        ? `${payload.stock_code || ''} · ${payload.action === 'add' ? '加仓' : payload.action === 'reduce' ? '减仓' : '清仓'} · @${payload.price}${payload.shares ? ` · ${payload.shares}股` : ''}`
        : action.action === 'navigate'
          ? `${payload.path || ''}`
          : JSON.stringify(payload);

  return (
    <>
      <style>{`
        .action-confirm {
          margin: 8px 0;
          padding: 10px 12px;
          border: 1px solid var(--border-subtle);
          border-radius: 8px;
          background: var(--bg-canvas);
          font-size: 13px;
        }
        .action-confirm-desc {
          color: var(--text-secondary);
          margin-bottom: 8px;
        }
        .action-confirm-btns {
          display: flex;
          gap: 8px;
        }
        .action-confirm-btn {
          padding: 4px 12px;
          border: 1px solid var(--border-subtle);
          border-radius: 4px;
          cursor: pointer;
          font-size: 12px;
          background: var(--bg-panel);
          color: var(--text-primary);
        }
        .action-confirm-btn.primary {
          background: var(--accent);
          color: #fff;
          border-color: var(--accent);
        }
        .action-confirm-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }
        .action-confirm-status {
          font-size: 12px;
          color: var(--text-muted);
          margin-top: 4px;
        }
      `}</style>
      <div className="action-confirm">
        <div style={{ fontWeight: 600, marginBottom: 4 }}>{label}</div>
        <div className="action-confirm-desc">{description}</div>
        {status === 'pending' ? (
          <div className="action-confirm-btns">
            <button className="action-confirm-btn primary" onClick={handleConfirm}>
              确认
            </button>
            <button className="action-confirm-btn" onClick={handleCancel}>
              取消
            </button>
          </div>
        ) : (
          <div className="action-confirm-status">
            {status === 'confirmed' && '[OK] 操作已执行'}
            {status === 'cancelled' && '[CANCELLED] 已取消'}
            {status === 'error' && '[ERROR] 操作失败'}
          </div>
        )}
      </div>
    </>
  );
}
