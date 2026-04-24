'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { useAddToPositions } from '@/hooks/useStockAdd';
import { candidatePoolApi, MemoItem } from '@/lib/candidate-pool-api';
import StockSearchInput from '@/components/stock/StockSearchInput';
import type { StockSearchResult } from '@/lib/api-client';
import { chartApi } from '@/lib/chart-api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface EntrySnapshot {
  rps_250?: number | null;
  rps_120?: number | null;
  close?: number | null;
  score?: number | null;
  signal_strength?: string | null;
  signals?: string[];
  industry_name?: string | null;
  strategy_name?: string | null;
}

interface CandidateStock {
  id: number;
  stock_code: string;
  stock_name: string;
  source_type: 'industry' | 'strategy' | 'manual';
  source_detail: string | null;
  add_date: string | null;
  status: 'watching' | 'focused' | 'excluded';
  memo: string | null;
  entry_snapshot: EntrySnapshot;
  // monitor
  monitor_date: string | null;
  close: number | null;
  rps_250: number | null;
  rps_120: number | null;
  rps_slope: number | null;
  pct_since_add: number | null;
  rps_change: number | null;
  signals: string[];
  alert_level: 'red' | 'yellow' | 'green' | 'info';
}

interface HistoryRow {
  trade_date: string;
  close: number | null;
  rps_250: number | null;
  pct_since_add: number | null;
  signals: string[];
  alert_level: string;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const STATUS_LABELS: Record<string, string> = {
  watching: '观察中',
  focused: '重点关注',
  excluded: '已排除',
};

const STATUS_COLORS: Record<string, { color: string; bg: string }> = {
  watching:  { color: 'var(--text-secondary)', bg: 'var(--bg-tag)' },
  focused:   { color: '#5e6ad2', bg: 'rgba(94,106,210,0.12)' },
  excluded:  { color: 'var(--text-muted)', bg: 'var(--bg-surface)' },
};

const ALERT_COLORS: Record<string, string> = {
  red: '#e5534b', yellow: '#c69026', green: '#27a644', info: 'var(--text-muted)',
};

const ALERT_BG: Record<string, string> = {
  red: 'rgba(229,83,75,0.08)', yellow: 'rgba(198,144,38,0.08)',
  green: 'rgba(39,166,68,0.08)', info: 'transparent',
};

const SOURCE_LABELS: Record<string, string> = {
  industry: '行业', strategy: '策略', manual: '手动',
};

function pctColor(v: number | null): string {
  if (v == null) return 'var(--text-muted)';
  if (v > 0) return '#27a644';
  if (v < 0) return '#e5534b';
  return 'var(--text-secondary)';
}

function pctFmt(v: number | null): string {
  if (v == null) return '--';
  return (v > 0 ? '+' : '') + v.toFixed(2) + '%';
}

function fmt(v: number | null | undefined, d = 1): string {
  if (v == null) return '--';
  return v.toFixed(d);
}

// ---------------------------------------------------------------------------
// Alert badge
// ---------------------------------------------------------------------------
function AlertBadge({ level, signals }: { level: string; signals: string[] }) {
  const color = ALERT_COLORS[level] || 'var(--text-muted)';
  const bg = ALERT_BG[level] || 'transparent';
  if (level === 'info' && signals.length === 0) {
    return <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>-</span>;
  }
  return (
    <span style={{ display: 'inline-flex', flexDirection: 'column', gap: '2px' }}>
      {signals.slice(0, 2).map((s, i) => (
        <span key={i} style={{
          fontSize: '10px', padding: '1px 6px', borderRadius: '3px',
          color, background: bg, fontWeight: 510, whiteSpace: 'nowrap',
        }}>
          {s}
        </span>
      ))}
      {signals.length > 2 && (
        <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>+{signals.length - 2}</span>
      )}
    </span>
  );
}

// ---------------------------------------------------------------------------
// History panel
// ---------------------------------------------------------------------------
function HistoryPanel({ stockCode, stockName }: { stockCode: string; stockName: string }) {
  const [data, setData] = useState<HistoryRow[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    candidatePoolApi.history(stockCode, 30)
      .then(r => setData(((r.data as { data?: HistoryRow[] }).data || []).reverse()))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [stockCode]);

  if (loading) return <div style={{ padding: '12px', fontSize: '12px', color: 'var(--text-muted)' }}>加载中...</div>;
  if (!data.length) return <div style={{ padding: '12px', fontSize: '12px', color: 'var(--text-muted)' }}>暂无监控数据</div>;

  return (
    <div style={{ padding: '12px 16px' }}>
      <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px', fontWeight: 510 }}>
        {stockName} · 近30日监控记录
      </div>
      <div className="table-scroll">
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px', minWidth: '380px' }}>
          <thead>
            <tr>
              {['日期', '收盘', 'RPS250', '加入涨跌', '信号', '级别'].map(h => (
                <th key={h} style={{ padding: '4px 8px', textAlign: 'left', color: 'var(--text-muted)', fontWeight: 400, borderBottom: '1px solid var(--border-subtle)', whiteSpace: 'nowrap' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.map((r, i) => (
              <tr key={i} style={{ background: i % 2 === 0 ? 'transparent' : 'var(--bg-card)' }}>
                <td style={{ padding: '4px 8px', color: 'var(--text-muted)' }}>{r.trade_date}</td>
                <td style={{ padding: '4px 8px' }}>{fmt(r.close, 2)}</td>
                <td style={{ padding: '4px 8px', color: (r.rps_250 ?? 0) >= 80 ? '#27a644' : 'var(--text-secondary)' }}>{fmt(r.rps_250)}</td>
                <td style={{ padding: '4px 8px', color: pctColor(r.pct_since_add) }}>{pctFmt(r.pct_since_add)}</td>
                <td style={{ padding: '4px 8px', color: 'var(--text-secondary)' }}>{r.signals.slice(0, 2).join(' / ') || '-'}</td>
                <td style={{ padding: '4px 8px' }}>
                  <span style={{ fontSize: '10px', color: ALERT_COLORS[r.alert_level] || 'var(--text-muted)' }}>
                    {r.alert_level === 'info' ? '-' : r.alert_level.toUpperCase()}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Mini K-line panel (sparkline using SVG path)
// ---------------------------------------------------------------------------
function KLinePanel({ stockCode }: { stockCode: string }) {
  const [prices, setPrices] = useState<number[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    chartApi.kline(stockCode, 'daily', 60)
      .then(r => {
        const pts = (r.data.data || []).map(d => d.close).filter(v => v != null) as number[];
        setPrices(pts);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [stockCode]);

  if (loading) return <div style={{ padding: '12px', fontSize: '12px', color: 'var(--text-muted)' }}>加载K线...</div>;
  if (!prices.length) return <div style={{ padding: '12px', fontSize: '12px', color: 'var(--text-muted)' }}>暂无K线数据</div>;

  const W = 400;
  const H = 80;
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  const range = max - min || 1;
  const pts = prices.map((p, i) => {
    const x = (i / (prices.length - 1)) * W;
    const y = H - ((p - min) / range) * H;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  const pathD = 'M' + pts.join('L');
  const lastClose = prices[prices.length - 1];
  const firstClose = prices[0];
  const lineColor = lastClose >= firstClose ? '#27a644' : '#e5534b';

  return (
    <div style={{ padding: '12px 16px' }}>
      <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px' }}>近60日收盘走势</div>
      <svg width={W} height={H} style={{ display: 'block', maxWidth: '100%' }}>
        <path d={pathD} fill="none" stroke={lineColor} strokeWidth="1.5" />
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Memos panel
// ---------------------------------------------------------------------------
function MemosPanel({ stockCode }: { stockCode: string }) {
  const [memos, setMemos] = useState<MemoItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [newContent, setNewContent] = useState('');
  const [adding, setAdding] = useState(false);

  const loadMemos = useCallback(() => {
    setLoading(true);
    candidatePoolApi.listMemos(stockCode)
      .then(r => setMemos((r.data as { data?: MemoItem[] }).data || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [stockCode]);

  useEffect(() => { loadMemos(); }, [loadMemos]);

  async function handleAdd() {
    if (!newContent.trim()) return;
    setAdding(true);
    try {
      await candidatePoolApi.addMemo(stockCode, newContent.trim());
      setNewContent('');
      loadMemos();
    } catch {
      // ignore
    } finally {
      setAdding(false);
    }
  }

  async function handleDelete(id: number) {
    try {
      await candidatePoolApi.deleteMemo(stockCode, id);
      setMemos(prev => prev.filter(m => m.id !== id));
    } catch {
      // ignore
    }
  }

  return (
    <div style={{ padding: '10px 16px', borderBottom: '1px solid var(--border-subtle)' }}>
      <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '8px' }}>备注记录</div>

      {/* Add new memo */}
      <div style={{ display: 'flex', gap: '6px', marginBottom: memos.length ? '10px' : '0' }}>
        <input
          value={newContent}
          onChange={e => setNewContent(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleAdd(); } }}
          placeholder="添加备注（Enter 提交）"
          style={{ flex: 1, fontSize: '12px', padding: '5px 8px', borderRadius: '5px', border: '1px solid var(--border-std)', background: 'var(--bg-input)', color: 'var(--text-primary)' }}
        />
        <button
          onClick={handleAdd}
          disabled={adding || !newContent.trim()}
          style={{ fontSize: '11px', padding: '5px 12px', borderRadius: '5px', background: newContent.trim() ? 'var(--accent)' : 'var(--bg-card)', color: newContent.trim() ? '#fff' : 'var(--text-muted)', border: 'none', cursor: newContent.trim() ? 'pointer' : 'default' }}
        >
          {adding ? '...' : '添加'}
        </button>
      </div>

      {/* Memo list */}
      {loading && <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>加载中...</div>}
      {!loading && memos.map(m => (
        <div key={m.id} style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', padding: '6px 0', borderTop: '1px solid var(--border-subtle)' }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: '12px', color: 'var(--text-primary)' }}>{m.content}</div>
            <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '2px' }}>{m.created_at.slice(0, 16)}</div>
          </div>
          <button
            onClick={() => handleDelete(m.id)}
            style={{ fontSize: '11px', color: '#e5534b', background: 'none', border: 'none', cursor: 'pointer', padding: '0 2px', flexShrink: 0 }}
          >
            删除
          </button>
        </div>
      ))}
      {!loading && memos.length === 0 && (
        <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>暂无备注</div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stock row
// ---------------------------------------------------------------------------
function StockRow({
  stock,
  expanded,
  onToggleExpand,
  onStatusChange,
  onRemove,
  onUpgrade,
  upgrading,
}: {
  stock: CandidateStock;
  expanded: boolean;
  onToggleExpand: () => void;
  onStatusChange: (code: string, status: string) => void;
  onRemove: (code: string) => void;
  onUpgrade: (stock: CandidateStock, level: string) => void;
  upgrading: boolean;
}) {
  const [showLevelPicker, setShowLevelPicker] = useState(false);
  const [showKLine, setShowKLine] = useState(false);

  const statusStyle = STATUS_COLORS[stock.status] || STATUS_COLORS.watching;
  const alertColor = ALERT_COLORS[stock.alert_level] || 'var(--text-muted)';
  const rowBg = stock.alert_level === 'red' ? 'rgba(229,83,75,0.03)' : 'transparent';

  return (
    <>
      <tr
        style={{ background: expanded ? 'var(--bg-card-hover)' : rowBg, cursor: 'pointer', opacity: stock.status === 'excluded' ? 0.6 : 1 }}
        onClick={onToggleExpand}
        onMouseEnter={e => { if (!expanded) (e.currentTarget as HTMLTableRowElement).style.background = 'var(--bg-card-hover)'; }}
        onMouseLeave={e => { if (!expanded) (e.currentTarget as HTMLTableRowElement).style.background = rowBg; }}
      >
        {/* Alert indicator */}
        <td style={{ padding: '10px 6px 10px 14px', width: '4px' }}>
          <div style={{ width: '3px', height: '28px', borderRadius: '2px', background: alertColor }} />
        </td>
        <td style={{ padding: '10px 12px', borderBottom: '1px solid var(--border-subtle)' }}>
          <div style={{ fontWeight: 510, color: 'var(--text-primary)', fontSize: '13px' }}>{stock.stock_name}</div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'var(--font-geist-mono)', marginTop: '1px' }}>{stock.stock_code}</div>
        </td>
        <td style={{ padding: '10px 12px', borderBottom: '1px solid var(--border-subtle)', whiteSpace: 'nowrap' }}>
          <span style={{ fontSize: '11px', padding: '2px 7px', borderRadius: '10px', color: statusStyle.color, background: statusStyle.bg }}>
            {STATUS_LABELS[stock.status] || stock.status}
          </span>
        </td>
        <td style={{ padding: '10px 12px', borderBottom: '1px solid var(--border-subtle)', fontSize: '11px', color: 'var(--text-muted)' }}>
          <div>{SOURCE_LABELS[stock.source_type] || stock.source_type}</div>
          {stock.source_detail && <div style={{ color: 'var(--text-tertiary)' }}>{stock.source_detail}</div>}
        </td>
        <td style={{ padding: '10px 12px', borderBottom: '1px solid var(--border-subtle)', fontSize: '12px', color: 'var(--text-muted)' }}>
          {stock.add_date || '--'}
        </td>
        <td style={{ padding: '10px 12px', borderBottom: '1px solid var(--border-subtle)', fontFamily: 'var(--font-geist-mono)', fontSize: '12px' }}>
          <div style={{ fontWeight: 510, color: 'var(--text-primary)' }}>{fmt(stock.close, 2)}</div>
          <div style={{ fontSize: '11px', color: pctColor(stock.pct_since_add) }}>{pctFmt(stock.pct_since_add)}</div>
        </td>
        <td style={{ padding: '10px 12px', borderBottom: '1px solid var(--border-subtle)', fontFamily: 'var(--font-geist-mono)', fontSize: '12px' }}>
          <div style={{ color: (stock.rps_250 ?? 0) >= 80 ? '#27a644' : 'var(--text-secondary)' }}>{fmt(stock.rps_250)}</div>
          {stock.rps_change != null && (
            <div style={{ fontSize: '11px', color: pctColor(stock.rps_change) }}>
              {stock.rps_change > 0 ? '+' : ''}{stock.rps_change.toFixed(1)}
            </div>
          )}
        </td>
        <td style={{ padding: '10px 12px', borderBottom: '1px solid var(--border-subtle)' }}>
          <AlertBadge level={stock.alert_level} signals={stock.signals} />
        </td>
        <td style={{ padding: '10px 14px', borderBottom: '1px solid var(--border-subtle)', textAlign: 'right' }}>
          <span style={{ fontSize: '11px', color: 'var(--accent)' }}>{expanded ? '收起' : '详情'}</span>
        </td>
      </tr>

      {/* Expanded row */}
      {expanded && (
        <tr>
          <td colSpan={9} style={{ padding: 0, borderBottom: '1px solid var(--border-subtle)', background: 'var(--bg-elevated)' }}>
            <div onClick={e => e.stopPropagation()}>
              {/* Action bar */}
              <div style={{ padding: '10px 16px', display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center', borderBottom: '1px solid var(--border-subtle)' }}>
                <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>状态：</span>
                {(['watching', 'focused', 'excluded'] as const).map(s => (
                  <button
                    key={s}
                    onClick={() => onStatusChange(stock.stock_code, s)}
                    style={{
                      fontSize: '11px', padding: '3px 10px', borderRadius: '10px',
                      border: stock.status === s ? 'none' : '1px solid var(--border-subtle)',
                      background: stock.status === s ? STATUS_COLORS[s].bg : 'transparent',
                      color: stock.status === s ? STATUS_COLORS[s].color : 'var(--text-muted)',
                      cursor: 'pointer', fontWeight: stock.status === s ? 510 : 400,
                    }}
                  >
                    {STATUS_LABELS[s]}
                  </button>
                ))}
                <div style={{ flex: 1 }} />
                <button
                  onClick={() => setShowKLine(v => !v)}
                  style={{ fontSize: '11px', color: 'var(--text-secondary)', background: 'none', border: '1px solid var(--border-subtle)', borderRadius: '6px', padding: '3px 10px', cursor: 'pointer' }}
                >
                  {showKLine ? '收起K线' : '查看K线'}
                </button>
                {showLevelPicker ? (
                  <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>级别：</span>
                    {['L1', 'L2', 'L3'].map(lv => (
                      <button
                        key={lv}
                        onClick={() => { onUpgrade(stock, lv); setShowLevelPicker(false); }}
                        disabled={upgrading}
                        style={{ fontSize: '11px', padding: '3px 8px', borderRadius: '4px', border: '1px solid var(--accent)', background: 'rgba(94,106,210,0.08)', color: 'var(--accent)', cursor: upgrading ? 'default' : 'pointer', fontWeight: 510 }}
                      >
                        {lv}
                      </button>
                    ))}
                    <button onClick={() => setShowLevelPicker(false)} style={{ fontSize: '11px', padding: '3px 6px', borderRadius: '4px', background: 'none', border: '1px solid var(--border-subtle)', color: 'var(--text-muted)', cursor: 'pointer' }}>取消</button>
                  </div>
                ) : (
                  <button
                    onClick={() => setShowLevelPicker(true)}
                    disabled={upgrading}
                    style={{ fontSize: '11px', color: '#27a644', background: 'none', border: '1px solid rgba(39,166,68,0.3)', borderRadius: '6px', padding: '3px 10px', cursor: upgrading ? 'default' : 'pointer', marginRight: '6px' }}
                  >
                    {upgrading ? '升级中...' : '升级持仓'}
                  </button>
                )}
                <button
                  onClick={() => onRemove(stock.stock_code)}
                  style={{ fontSize: '11px', color: '#e5534b', background: 'none', border: '1px solid rgba(229,83,75,0.3)', borderRadius: '6px', padding: '3px 10px', cursor: 'pointer' }}
                >
                  移出观察池
                </button>
              </div>

              {/* K-line (collapsible) */}
              {showKLine && <KLinePanel stockCode={stock.stock_code} />}

              {/* Entry snapshot */}
              <div style={{ padding: '10px 16px', display: 'flex', gap: '24px', flexWrap: 'wrap', borderBottom: '1px solid var(--border-subtle)', fontSize: '12px' }}>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>加入时 RPS250：</span>
                  <span style={{ color: 'var(--text-primary)', fontWeight: 510 }}>
                    {stock.entry_snapshot?.rps_250 != null ? fmt(stock.entry_snapshot.rps_250) : '--'}
                  </span>
                </div>
                <div>
                  <span style={{ color: 'var(--text-muted)' }}>加入时收盘：</span>
                  <span style={{ color: 'var(--text-primary)', fontWeight: 510 }}>
                    {stock.entry_snapshot?.close != null ? fmt(stock.entry_snapshot.close, 2) : '--'}
                  </span>
                </div>
                {stock.entry_snapshot?.score != null && (
                  <div>
                    <span style={{ color: 'var(--text-muted)' }}>策略得分：</span>
                    <span style={{ color: 'var(--accent)', fontWeight: 510 }}>{fmt(stock.entry_snapshot.score, 3)}</span>
                  </div>
                )}
                {stock.entry_snapshot?.signals && stock.entry_snapshot.signals.length > 0 && (
                  <div>
                    <span style={{ color: 'var(--text-muted)' }}>加入时信号：</span>
                    <span style={{ color: 'var(--text-secondary)' }}>{stock.entry_snapshot.signals.join(', ')}</span>
                  </div>
                )}
              </div>

              {/* Multi-memos */}
              <MemosPanel stockCode={stock.stock_code} />

              {/* History */}
              <HistoryPanel stockCode={stock.stock_code} stockName={stock.stock_name} />
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Main Content
// ---------------------------------------------------------------------------

const PREF_KEY = 'candidate_pool_prefs';

function loadPrefs(): { filterStatus: string; filterSource: string } {
  try {
    const raw = localStorage.getItem(PREF_KEY);
    if (raw) return JSON.parse(raw);
  } catch { /* ignore */ }
  return { filterStatus: 'active', filterSource: '' };
}

function savePrefs(prefs: { filterStatus: string; filterSource: string }) {
  try { localStorage.setItem(PREF_KEY, JSON.stringify(prefs)); } catch { /* ignore */ }
}

export default function CandidatePoolContent() {
  const addPos = useAddToPositions();
  const [stocks, setStocks] = useState<CandidateStock[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterStatus, setFilterStatus] = useState<string>(() => loadPrefs().filterStatus);
  const [filterSource, setFilterSource] = useState<string>(() => loadPrefs().filterSource);
  const [expandedCode, setExpandedCode] = useState<string | null>(null);
  const [upgradingCode, setUpgradingCode] = useState<string | null>(null);

  // Persist filter preferences
  useEffect(() => {
    savePrefs({ filterStatus, filterSource });
  }, [filterStatus, filterSource]);

  // Add stock form state
  const [selectedStock, setSelectedStock] = useState<StockSearchResult | null>(null);
  const [addingStock, setAddingStock] = useState(false);

  const loadStocks = useCallback(async () => {
    setLoading(true);
    try {
      // 'active' is a UI-only filter: fetch watching + focused
      const params: { status?: string; source_type?: string } = {};
      if (filterStatus && filterStatus !== 'active') params.status = filterStatus;
      if (filterSource) params.source_type = filterSource;
      const res = await candidatePoolApi.list(params);
      let data = (res.data as { data?: CandidateStock[] }).data || [];
      // client-side: when filterStatus='active', hide excluded
      if (filterStatus === 'active') {
        data = data.filter(s => s.status !== 'excluded');
      }
      setStocks(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [filterStatus, filterSource]);

  useEffect(() => { loadStocks(); }, [loadStocks]);

  async function handleAddStock() {
    if (!selectedStock) return;
    setAddingStock(true);
    try {
      await candidatePoolApi.add({
        stock_code: selectedStock.stock_code,
        stock_name: selectedStock.stock_name,
        source_type: 'manual',
      });
      setSelectedStock(null);
      loadStocks();
      setActionMsg(`${selectedStock.stock_name} 已加入候选池`);
      setTimeout(() => setActionMsg(null), 3000);
    } catch {
      setActionMsg('添加失败');
    } finally {
      setAddingStock(false);
    }
  }

  async function handleStatusChange(code: string, status: string) {
    try {
      await candidatePoolApi.updateStatus(code, status);
      loadStocks();
    } catch {
      setActionMsg('状态更新失败');
    }
  }

  async function handleRemove(code: string) {
    if (!confirm('确认将该股票移出观察池？')) return;
    try {
      await candidatePoolApi.remove(code);
      setExpandedCode(null);
      loadStocks();
    } catch {
      setActionMsg('移除失败');
    }
  }

  async function handleUpgrade(stock: CandidateStock, level: string) {
    setUpgradingCode(stock.stock_code);
    try {
      await addPos.mutateAsync({ stock_code: stock.stock_code, stock_name: stock.stock_name, level });
      const shouldRemove = confirm(`${stock.stock_name} 已加入实盘持仓(${level})，是否同时从候选观察移除？`);
      if (shouldRemove) {
        try {
          await candidatePoolApi.remove(stock.stock_code);
          setExpandedCode(null);
          loadStocks();
        } catch {
          setActionMsg('从候选观察移除失败，请手动移除');
        }
      }
    } catch {
      setActionMsg('升级持仓失败');
    } finally {
      setUpgradingCode(null);
    }
  }

  const alertCounts = stocks.reduce((acc, s) => {
    if (s.monitor_date) acc[s.alert_level] = (acc[s.alert_level] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  const selectStyle: React.CSSProperties = {
    fontSize: '12px', padding: '5px 10px', borderRadius: '6px',
    border: '1px solid var(--border-subtle)', background: 'var(--bg-input)',
    color: 'var(--text-secondary)', cursor: 'pointer',
  };

  return (
    <>
      {/* Header */}
      <div style={{ marginBottom: '16px', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '16px', flexWrap: 'wrap' }}>
        <div>
          <h2 style={{ fontSize: '16px', fontWeight: 580, color: 'var(--text-primary)', margin: '0 0 4px' }}>候选观察</h2>
          <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: 0 }}>
            从行业或策略加入的候选股票，每日盘后自动监控技术面
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
          <button onClick={loadStocks} style={{ fontSize: '12px', padding: '6px 12px', borderRadius: '6px', background: 'transparent', color: 'var(--text-muted)', border: '1px solid var(--border-subtle)', cursor: 'pointer' }}>
            刷新
          </button>
        </div>
      </div>

      {/* Search add */}
      <div style={{ marginBottom: '16px', display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
        <StockSearchInput
          onSelect={setSelectedStock}
          placeholder="搜索添加个股或ETF到候选池..."
          width="280px"
        />
        {selectedStock && (
          <>
            <span style={{ fontSize: '13px', color: 'var(--text-primary)', fontWeight: 510 }}>
              {selectedStock.stock_name} <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>{selectedStock.stock_code}</span>
            </span>
            <button
              onClick={handleAddStock}
              disabled={addingStock}
              style={{ fontSize: '12px', padding: '5px 14px', borderRadius: '6px', background: 'var(--accent)', color: '#fff', border: 'none', cursor: addingStock ? 'default' : 'pointer', opacity: addingStock ? 0.6 : 1 }}
            >
              {addingStock ? '添加中...' : '加入候选池'}
            </button>
            <button
              onClick={() => setSelectedStock(null)}
              style={{ fontSize: '12px', padding: '5px 10px', borderRadius: '6px', background: 'transparent', color: 'var(--text-muted)', border: '1px solid var(--border-subtle)', cursor: 'pointer' }}
            >
              取消
            </button>
          </>
        )}
      </div>

      {/* Alert summary bar */}
      {Object.keys(alertCounts).length > 0 && (
        <div style={{ marginBottom: '16px', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
          {(['red', 'yellow', 'green', 'info'] as const).map(level => {
            const cnt = alertCounts[level] || 0;
            if (!cnt) return null;
            return (
              <span key={level} style={{ fontSize: '12px', padding: '4px 12px', borderRadius: '20px', color: ALERT_COLORS[level], background: ALERT_BG[level] || 'var(--bg-tag)', border: `1px solid ${ALERT_COLORS[level]}40`, fontWeight: 510 }}>
                {level === 'red' ? '需关注' : level === 'yellow' ? '提醒' : level === 'green' ? '积极信号' : '正常'} {cnt}
              </span>
            );
          })}
        </div>
      )}

      {/* Filters */}
      <div style={{ marginBottom: '16px', display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'center' }}>
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)} style={selectStyle}>
          <option value='active'>观察中 + 重点关注</option>
          <option value=''>全部（含已排除）</option>
          <option value='watching'>观察中</option>
          <option value='focused'>重点关注</option>
          <option value='excluded'>仅已排除</option>
        </select>
        <select value={filterSource} onChange={e => setFilterSource(e.target.value)} style={selectStyle}>
          <option value=''>全部来源</option>
          <option value='industry'>行业</option>
          <option value='strategy'>策略</option>
          <option value='manual'>手动</option>
        </select>
        <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>共 {stocks.length} 只</span>
      </div>

      {/* Table */}
      {loading ? (
        <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>加载中...</div>
      ) : stocks.length === 0 ? (
        <div style={{ padding: '60px 20px', textAlign: 'center', background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: '10px', color: 'var(--text-muted)', fontSize: '13px' }}>
          {filterStatus === 'active' ? '候选观察为空，搜索添加个股或从「行业」「策略」页面加入' : '无匹配记录'}
        </div>
      ) : (
        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: '10px', overflow: 'hidden' }}>
          <div className="table-scroll">
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', minWidth: '700px' }}>
              <thead>
                <tr style={{ background: 'var(--bg-panel)', borderBottom: '1px solid var(--border-subtle)' }}>
                  <th style={{ width: '4px', padding: '0' }} />
                  {['股票', '状态', '来源', '加入日', '价格/涨跌', 'RPS250/变化', '今日信号', ''].map(h => (
                    <th key={h} style={{ padding: '9px 12px', textAlign: 'left', fontWeight: 510, color: 'var(--text-muted)', fontSize: '11px', whiteSpace: 'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {stocks.map(stock => (
                  <StockRow
                    key={stock.stock_code}
                    stock={stock}
                    expanded={expandedCode === stock.stock_code}
                    onToggleExpand={() => setExpandedCode(prev => prev === stock.stock_code ? null : stock.stock_code)}
                    onStatusChange={handleStatusChange}
                    onRemove={handleRemove}
                    onUpgrade={handleUpgrade}
                    upgrading={upgradingCode === stock.stock_code}
                  />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}
