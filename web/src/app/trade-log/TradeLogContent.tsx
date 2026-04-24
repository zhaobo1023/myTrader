'use client';

import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { tradeLogApi, TradeLogItem } from '@/lib/api-client';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const OP_TYPE_LABELS: Record<string, string> = {
  open_position: '建仓',
  add_reduce: '加减仓',
  close_position: '清仓',
  move_to_candidate: '移入候选池',
  manual_note: '手动备注',
  modify_info: '信息修改',
};

const OP_TYPE_COLORS: Record<string, string> = {
  open_position: '#27a644',
  add_reduce: '#5e6ad2',
  close_position: '#e5534b',
  move_to_candidate: '#c69026',
  manual_note: '#636e7b',
  modify_info: '#8b949e',
};

const FILTER_TABS = [
  { key: '', label: '全部' },
  { key: 'open_position', label: '建仓' },
  { key: 'add_reduce', label: '加减仓' },
  { key: 'close_position', label: '清仓' },
  { key: 'move_to_candidate', label: '移入候选池' },
  { key: 'manual_note', label: '手动备注' },
];

const SOURCE_LABELS: Record<string, string> = {
  auto: '自动',
  manual: '手动',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatTime(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  const hour = String(d.getHours()).padStart(2, '0');
  const min = String(d.getMinutes()).padStart(2, '0');
  return `${month}-${day} ${hour}:${min}`;
}

function formatDate(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function tryParseJson(s: string | null): Record<string, unknown> | null {
  if (!s) return null;
  try {
    return JSON.parse(s);
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Log Card
// ---------------------------------------------------------------------------

function LogCard({ item }: { item: TradeLogItem }) {
  const label = OP_TYPE_LABELS[item.operation_type] || item.operation_type;
  const color = OP_TYPE_COLORS[item.operation_type] || '#8b949e';
  const sourceLabel = SOURCE_LABELS[item.source] || item.source;

  const before = tryParseJson(item.before_value);
  const after = tryParseJson(item.after_value);

  // Build diff display for add_reduce
  let diffDisplay: React.ReactNode = null;
  if (item.operation_type === 'add_reduce' && before && after) {
    const oldS = before.shares ?? '?';
    const newS = after.shares ?? '?';
    const isAdd = Number(newS) > Number(oldS);
    diffDisplay = (
      <span style={{ fontSize: '11px', fontFamily: 'var(--font-geist-mono)', color: isAdd ? '#27a644' : '#e5534b' }}>
        {`${oldS} -> ${newS}股`}
      </span>
    );
  }

  return (
    <div style={{
      display: 'flex', gap: '12px', padding: '12px 0',
      borderBottom: '1px solid var(--border-subtle)',
    }}>
      {/* Timeline dot */}
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0, width: '48px' }}>
        <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginBottom: '4px' }}>
          {formatTime(item.created_at)}
        </span>
        <div style={{
          width: '10px', height: '10px', borderRadius: '50%', background: color, flexShrink: 0,
        }} />
      </div>

      {/* Content */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px', flexWrap: 'wrap' }}>
          {/* Type badge */}
          <span style={{
            fontSize: '11px', padding: '1px 8px', borderRadius: '4px',
            background: `${color}18`, color, fontWeight: 500,
          }}>
            {label}
          </span>

          {/* Stock name */}
          {item.stock_name && (
            <span style={{ fontSize: '13px', fontWeight: 510, color: 'var(--text-primary)' }}>
              {item.stock_name}
            </span>
          )}
          {item.stock_code && item.stock_code !== item.stock_name && (
            <span style={{ fontSize: '11px', fontFamily: 'var(--font-geist-mono)', color: 'var(--text-muted)' }}>
              {item.stock_code}
            </span>
          )}

          {/* Source */}
          <span style={{ fontSize: '10px', color: 'var(--text-tertiary)', marginLeft: 'auto' }}>
            {sourceLabel}
          </span>
        </div>

        {/* Detail */}
        {item.detail && (
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '2px' }}>
            {item.detail}
          </div>
        )}

        {/* Diff display */}
        {diffDisplay && (
          <div style={{ marginTop: '4px' }}>{diffDisplay}</div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Manual Note Form
// ---------------------------------------------------------------------------

function ManualNoteForm({ onDone }: { onDone: () => void }) {
  const [stockCode, setStockCode] = useState('');
  const [stockName, setStockName] = useState('');
  const [detail, setDetail] = useState('');

  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: (data: { stock_code?: string; stock_name?: string; detail?: string }) =>
      tradeLogApi.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['trade-logs'] });
      onDone();
    },
  });

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!detail.trim()) return;
    mutation.mutate({
      stock_code: stockCode.trim() || undefined,
      stock_name: stockName.trim() || undefined,
      detail: detail.trim(),
    });
  }

  const inputStyle: React.CSSProperties = {
    fontSize: '12px', padding: '6px 10px', borderRadius: '5px',
    border: '1px solid var(--border-subtle)', background: 'var(--bg-input)',
    color: 'var(--text-primary)', boxSizing: 'border-box',
  };

  return (
    <form onSubmit={handleSubmit} style={{
      background: 'var(--bg-card)', border: '1px solid var(--border-std)',
      borderRadius: '8px', padding: '14px 16px', marginBottom: '16px',
    }}>
      <div style={{ fontSize: '13px', fontWeight: 510, color: 'var(--text-primary)', marginBottom: '10px' }}>
        添加复盘备注
      </div>
      <div style={{ display: 'flex', gap: '8px', marginBottom: '8px', flexWrap: 'wrap' }}>
        <input
          value={stockCode}
          onChange={e => setStockCode(e.target.value)}
          placeholder="股票代码 (选填)"
          style={{ ...inputStyle, width: '140px' }}
        />
        <input
          value={stockName}
          onChange={e => setStockName(e.target.value)}
          placeholder="股票名称 (选填)"
          style={{ ...inputStyle, width: '140px' }}
        />
      </div>
      <textarea
        value={detail}
        onChange={e => setDetail(e.target.value)}
        placeholder="记录调仓思路、市场观察、操作原因..."
        rows={2}
        style={{
          ...inputStyle, width: '100%', marginBottom: '10px', resize: 'vertical',
          fontFamily: 'inherit',
        }}
      />
      <div style={{ display: 'flex', gap: '8px' }}>
        <button
          type="submit"
          disabled={mutation.isPending || !detail.trim()}
          style={{
            fontSize: '12px', padding: '6px 18px', borderRadius: '6px',
            background: mutation.isPending || !detail.trim() ? 'var(--bg-card-hover)' : 'var(--accent)',
            color: mutation.isPending || !detail.trim() ? 'var(--text-muted)' : '#fff',
            border: 'none', cursor: mutation.isPending ? 'default' : 'pointer', fontWeight: 510,
          }}
        >
          {mutation.isPending ? '提交中...' : '提交'}
        </button>
        <button
          type="button"
          onClick={onDone}
          style={{
            fontSize: '12px', padding: '6px 18px', borderRadius: '6px',
            background: 'transparent', color: 'var(--text-muted)',
            border: '1px solid var(--border-subtle)', cursor: 'pointer',
          }}
        >
          取消
        </button>
        {mutation.isError && (
          <span style={{ fontSize: '12px', color: '#e5534b', alignSelf: 'center' }}>
            提交失败
          </span>
        )}
      </div>
    </form>
  );
}

// ---------------------------------------------------------------------------
// TradeLogContent (main)
// ---------------------------------------------------------------------------

export default function TradeLogContent() {
  const [activeType, setActiveType] = useState('');
  const [stockFilter, setStockFilter] = useState('');
  const [stockFilterInput, setStockFilterInput] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [page, setPage] = useState(1);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState(false);
  const pageSize = 50;

  const { data, isLoading, error } = useQuery({
    queryKey: ['trade-logs', activeType, stockFilter, page],
    queryFn: () => tradeLogApi.list({
      operation_type: activeType || undefined,
      stock_code: stockFilter || undefined,
      page,
      page_size: pageSize,
    }),
  });

  const { data: stats } = useQuery({
    queryKey: ['trade-logs-stats', stockFilter],
    queryFn: () => tradeLogApi.stats({ days: 90, stock_code: stockFilter || undefined }),
  });

  const items = data?.data?.items || [];
  const total = data?.data?.total || 0;
  const totalPages = Math.ceil(total / pageSize);
  const statsData = stats?.data;

  const filterBtnStyle = (active: boolean): React.CSSProperties => ({
    fontSize: '12px', padding: '4px 12px', borderRadius: '4px',
    border: active ? '1px solid var(--accent)' : '1px solid var(--border-subtle)',
    background: active ? 'rgba(94,106,210,0.12)' : 'transparent',
    color: active ? 'var(--accent)' : 'var(--text-muted)',
    cursor: 'pointer', fontWeight: active ? 510 : 400,
  });

  function applyStockFilter() {
    setStockFilter(stockFilterInput.trim().toUpperCase());
    setPage(1);
  }

  function clearStockFilter() {
    setStockFilter('');
    setStockFilterInput('');
    setPage(1);
  }

  return (
    <div>
      {/* Stats summary */}
      {statsData && (
        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '12px 16px', marginBottom: '16px' }}>
          <div style={{ display: 'flex', gap: '20px', flexWrap: 'wrap', fontSize: '12px', color: 'var(--text-muted)', marginBottom: statsData.top_stocks?.length ? '10px' : '0' }}>
            <span>近90天操作 <b style={{ color: 'var(--text-primary)' }}>{statsData.total}</b> 次</span>
            {Object.entries(statsData.by_type || {}).map(([type, count]) => (
              <span key={type}>
                {OP_TYPE_LABELS[type] || type} <b style={{ color: OP_TYPE_COLORS[type] || 'var(--text-primary)' }}>{count}</b>
              </span>
            ))}
            {statsData.close_summary?.count > 0 && (
              <span>清仓涉及 <b style={{ color: 'var(--text-primary)' }}>{statsData.close_summary.count}</b> 次 · {statsData.close_summary.stocks.length} 只</span>
            )}
          </div>
          {/* Top stocks */}
          {statsData.top_stocks && statsData.top_stocks.length > 0 && (
            <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
              {statsData.top_stocks.slice(0, 8).map(s => (
                <button
                  key={s.stock_code}
                  onClick={() => { setStockFilterInput(s.stock_code); setStockFilter(s.stock_code); setPage(1); }}
                  style={{
                    fontSize: '11px', padding: '2px 8px', borderRadius: '10px',
                    border: `1px solid ${stockFilter === s.stock_code ? 'var(--accent)' : 'var(--border-subtle)'}`,
                    background: stockFilter === s.stock_code ? 'rgba(94,106,210,0.12)' : 'transparent',
                    color: stockFilter === s.stock_code ? 'var(--accent)' : 'var(--text-secondary)',
                    cursor: 'pointer',
                  }}
                >
                  {s.stock_name} <span style={{ color: 'var(--text-muted)' }}>{s.total}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Toolbar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px', flexWrap: 'wrap' }}>
        {FILTER_TABS.map(tab => (
          <button
            key={tab.key}
            onClick={() => { setActiveType(tab.key); setPage(1); }}
            style={filterBtnStyle(activeType === tab.key)}
          >
            {tab.label}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <button
          disabled={exporting}
          onClick={async () => {
            setExporting(true);
            setExportError(false);
            try { await tradeLogApi.export({ operation_type: activeType || undefined, stock_code: stockFilter || undefined }); }
            catch { setExportError(true); }
            finally { setExporting(false); }
          }}
          style={{
            fontSize: '12px', padding: '4px 14px', borderRadius: '4px',
            background: 'transparent', color: 'var(--text-secondary)',
            border: '1px solid var(--border-subtle)', cursor: exporting ? 'wait' : 'pointer',
            opacity: exporting ? 0.6 : 1,
          }}
        >
          {exporting ? '导出中...' : '导出 CSV'}
        </button>
        {exportError && (
          <span style={{ fontSize: '12px', color: '#e5534b', alignSelf: 'center' }}>导出失败</span>
        )}
        <button
          onClick={() => setShowForm(true)}
          style={{ fontSize: '12px', padding: '4px 14px', borderRadius: '4px', background: 'var(--accent)', color: '#fff', border: 'none', cursor: 'pointer', fontWeight: 510 }}
        >
          + 备注记录
        </button>
      </div>

      {/* Stock filter */}
      <div style={{ display: 'flex', gap: '6px', alignItems: 'center', marginBottom: '16px' }}>
        <input
          value={stockFilterInput}
          onChange={e => setStockFilterInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') applyStockFilter(); }}
          placeholder="按股票代码筛选，如 600938.SH"
          style={{ fontSize: '12px', padding: '5px 10px', borderRadius: '5px', border: `1px solid ${stockFilter ? 'var(--accent)' : 'var(--border-subtle)'}`, background: 'var(--bg-input)', color: 'var(--text-primary)', width: '220px' }}
        />
        <button onClick={applyStockFilter} style={{ fontSize: '12px', padding: '5px 12px', borderRadius: '5px', background: 'var(--accent)', color: '#fff', border: 'none', cursor: 'pointer' }}>
          筛选
        </button>
        {stockFilter && (
          <button onClick={clearStockFilter} style={{ fontSize: '12px', padding: '5px 10px', borderRadius: '5px', background: 'transparent', color: 'var(--text-muted)', border: '1px solid var(--border-subtle)', cursor: 'pointer' }}>
            清除
          </button>
        )}
        {stockFilter && (
          <span style={{ fontSize: '12px', color: 'var(--accent)' }}>当前筛选：{stockFilter}</span>
        )}
      </div>

      {/* Manual note form */}
      {showForm && <ManualNoteForm onDone={() => setShowForm(false)} />}

      {/* Log list */}
      {isLoading && (
        <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--text-muted)', fontSize: '13px' }}>
          加载中...
        </div>
      )}

      {error && (
        <div style={{ textAlign: 'center', padding: '40px 0', color: '#e5534b', fontSize: '13px' }}>
          加载失败，请重试
        </div>
      )}

      {!isLoading && !error && items.length === 0 && (
        <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-tertiary)', fontSize: '13px' }}>
          暂无调仓记录
        </div>
      )}

      {items.map(item => (
        <LogCard key={item.id} item={item} />
      ))}

      {/* Pagination */}
      {totalPages > 1 && (
        <div style={{
          display: 'flex', justifyContent: 'center', gap: '8px', padding: '16px 0',
        }}>
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page <= 1}
            style={{
              fontSize: '12px', padding: '4px 12px', borderRadius: '4px',
              border: '1px solid var(--border-subtle)', background: 'transparent',
              color: page <= 1 ? 'var(--text-tertiary)' : 'var(--text-secondary)',
              cursor: page <= 1 ? 'default' : 'pointer',
            }}
          >
            上一页
          </button>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)', alignSelf: 'center' }}>
            {page} / {totalPages}
          </span>
          <button
            onClick={() => setPage(p => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            style={{
              fontSize: '12px', padding: '4px 12px', borderRadius: '4px',
              border: '1px solid var(--border-subtle)', background: 'transparent',
              color: page >= totalPages ? 'var(--text-tertiary)' : 'var(--text-secondary)',
              cursor: page >= totalPages ? 'default' : 'pointer',
            }}
          >
            下一页
          </button>
        </div>
      )}
    </div>
  );
}
