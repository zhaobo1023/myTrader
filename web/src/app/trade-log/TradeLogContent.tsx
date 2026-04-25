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

const MANUAL_OP_TYPES = [
  { key: 'open_position', label: '建仓' },
  { key: 'add_reduce', label: '加减仓' },
  { key: 'close_position', label: '清仓' },
  { key: 'manual_note', label: '备注' },
];

function ManualTradeForm({ onDone }: { onDone: () => void }) {
  const [opType, setOpType] = useState('manual_note');
  const [stockCode, setStockCode] = useState('');
  const [stockName, setStockName] = useState('');
  const [price, setPrice] = useState('');
  const [shares, setShares] = useState('');
  const [detail, setDetail] = useState('');

  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: (data: { operation_type?: string; stock_code?: string; stock_name?: string; detail?: string; before_value?: string; after_value?: string }) =>
      tradeLogApi.create(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['trade-logs'] });
      onDone();
    },
  });

  const isTradeOp = opType !== 'manual_note';

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (isTradeOp && !stockCode.trim()) return;
    if (!isTradeOp && !detail.trim()) return;

    const afterValue: Record<string, unknown> = {};
    if (price) afterValue.price = parseFloat(price);
    if (shares) afterValue.shares = parseInt(shares, 10);

    const detailParts: string[] = [];
    if (isTradeOp) {
      const opLabel = MANUAL_OP_TYPES.find(t => t.key === opType)?.label || opType;
      if (price) detailParts.push(`${opLabel} ${shares || '?'}股 @ ${price}`);
      if (detail.trim()) detailParts.push(detail.trim());
    }

    mutation.mutate({
      operation_type: opType,
      stock_code: stockCode.trim() || undefined,
      stock_name: stockName.trim() || undefined,
      detail: isTradeOp ? (detailParts.join(' | ') || undefined) : detail.trim(),
      after_value: Object.keys(afterValue).length > 0 ? JSON.stringify(afterValue) : undefined,
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
        手动录入调仓记录
      </div>

      {/* Operation type */}
      <div style={{ display: 'flex', gap: '6px', marginBottom: '10px' }}>
        {MANUAL_OP_TYPES.map(t => (
          <button
            key={t.key}
            type="button"
            onClick={() => setOpType(t.key)}
            style={{
              fontSize: '12px', padding: '4px 12px', borderRadius: '4px',
              border: opType === t.key ? '1px solid var(--accent)' : '1px solid var(--border-subtle)',
              background: opType === t.key ? 'rgba(94,106,210,0.12)' : 'transparent',
              color: opType === t.key ? 'var(--accent)' : 'var(--text-muted)',
              cursor: 'pointer', fontWeight: opType === t.key ? 510 : 400,
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Stock info */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '8px', flexWrap: 'wrap' }}>
        <input
          value={stockCode}
          onChange={e => setStockCode(e.target.value)}
          placeholder={isTradeOp ? '股票代码 (必填)' : '股票代码 (选填)'}
          style={{ ...inputStyle, width: '140px' }}
        />
        <input
          value={stockName}
          onChange={e => setStockName(e.target.value)}
          placeholder="股票名称 (选填)"
          style={{ ...inputStyle, width: '140px' }}
        />
        {isTradeOp && (
          <>
            <input
              value={price}
              onChange={e => setPrice(e.target.value)}
              placeholder="成交价"
              type="number"
              step="0.01"
              style={{ ...inputStyle, width: '110px' }}
            />
            {opType !== 'close_position' && (
              <input
                value={shares}
                onChange={e => setShares(e.target.value)}
                placeholder="股数"
                type="number"
                min="1"
                style={{ ...inputStyle, width: '100px' }}
              />
            )}
          </>
        )}
      </div>

      <textarea
        value={detail}
        onChange={e => setDetail(e.target.value)}
        placeholder={isTradeOp ? '操作原因/备注 (选填)' : '记录调仓思路、市场观察、操作原因...'}
        rows={2}
        style={{
          ...inputStyle, width: '100%', marginBottom: '10px', resize: 'vertical',
          fontFamily: 'inherit',
        }}
      />
      <div style={{ display: 'flex', gap: '8px' }}>
        <button
          type="submit"
          disabled={mutation.isPending || (isTradeOp ? !stockCode.trim() : !detail.trim())}
          style={{
            fontSize: '12px', padding: '6px 18px', borderRadius: '6px',
            background: mutation.isPending ? 'var(--bg-card-hover)' : 'var(--accent)',
            color: mutation.isPending ? 'var(--text-muted)' : '#fff',
            border: 'none', cursor: mutation.isPending ? 'default' : 'pointer', fontWeight: 510,
            opacity: (isTradeOp ? !stockCode.trim() : !detail.trim()) ? 0.5 : 1,
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
  const [keyword, setKeyword] = useState('');
  const [debouncedKeyword, setDebouncedKeyword] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [page, setPage] = useState(1);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState(false);
  const pageSize = 50;
  const debounceRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  function handleKeywordChange(val: string) {
    setKeyword(val);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      setDebouncedKeyword(val.trim());
      setPage(1);
    }, 400);
  }

  const { data, isLoading, error } = useQuery({
    queryKey: ['trade-logs', activeType, debouncedKeyword, page],
    queryFn: () => tradeLogApi.list({
      operation_type: activeType || undefined,
      keyword: debouncedKeyword || undefined,
      page,
      page_size: pageSize,
    }),
  });

  const items = data?.data?.items || [];
  const total = data?.data?.total || 0;
  const totalPages = Math.ceil(total / pageSize);

  const filterBtnStyle = (active: boolean): React.CSSProperties => ({
    fontSize: '12px', padding: '4px 12px', borderRadius: '4px',
    border: active ? '1px solid var(--accent)' : '1px solid var(--border-subtle)',
    background: active ? 'rgba(94,106,210,0.12)' : 'transparent',
    color: active ? 'var(--accent)' : 'var(--text-muted)',
    cursor: 'pointer', fontWeight: active ? 510 : 400,
  });

  return (
    <div>
      {/* Toolbar: filter tabs + search + actions */}
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

        {/* Keyword search */}
        <div style={{ position: 'relative', marginLeft: '4px' }}>
          <input
            value={keyword}
            onChange={e => handleKeywordChange(e.target.value)}
            placeholder="搜索股票名称或代码"
            style={{
              fontSize: '12px', padding: '5px 10px', paddingRight: keyword ? '26px' : '10px',
              borderRadius: '5px',
              border: `1px solid ${debouncedKeyword ? 'var(--accent)' : 'var(--border-subtle)'}`,
              background: 'var(--bg-input)', color: 'var(--text-primary)', width: '180px',
            }}
          />
          {keyword && (
            <button
              onClick={() => { setKeyword(''); setDebouncedKeyword(''); setPage(1); }}
              style={{
                position: 'absolute', right: '6px', top: '50%', transform: 'translateY(-50%)',
                fontSize: '11px', color: 'var(--text-muted)', background: 'none', border: 'none',
                cursor: 'pointer', padding: '0 2px', lineHeight: 1,
              }}
            >
              x
            </button>
          )}
        </div>

        <div style={{ flex: 1 }} />
        <button
          disabled={exporting}
          onClick={async () => {
            setExporting(true);
            setExportError(false);
            try { await tradeLogApi.export({ operation_type: activeType || undefined }); }
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
          + 录入记录
        </button>
      </div>

      {/* Manual trade form */}
      {showForm && <ManualTradeForm onDone={() => setShowForm(false)} />}

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
