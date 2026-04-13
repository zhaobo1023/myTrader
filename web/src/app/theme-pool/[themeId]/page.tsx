'use client';

import React, { useState, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import AppShell from '@/components/layout/AppShell';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  themePoolApi, marketApi,
  ThemePoolItem, ThemeStockItem, StockSearchResult,
} from '@/lib/api-client';
import MiniSparkline from '@/components/market/MiniSparkline';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function pct(v: number | null | undefined): string {
  if (v == null) return '-';
  return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;
}

function score(v: number | null | undefined): string {
  if (v == null) return '-';
  return v.toFixed(0);
}

function returnColor(v: number | null | undefined): string {
  if (v == null) return 'var(--text-muted)';
  return v >= 0 ? '#16a34a' : '#ef4444';
}

const STATUS_LABELS: Record<string, string> = {
  draft: '草稿', active: '已上线', archived: '已归档',
};
const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  draft: { bg: '#f3f4f6', text: '#6b7280' },
  active: { bg: '#dcfce7', text: '#16a34a' },
  archived: { bg: '#fef3c7', text: '#d97706' },
};
const HUMAN_STATUS_LABELS: Record<string, string> = {
  normal: '普通', focused: '重点关注', watching: '观察', excluded: '已剔除',
};
const HUMAN_STATUS_COLORS: Record<string, string> = {
  normal: 'var(--text-muted)', focused: '#3b82f6', watching: '#f59e0b', excluded: '#9ca3af',
};
const FILTER_LABELS: Record<string, string> = {
  '': '全部', focused: '重点关注', watching: '观察', normal: '普通', excluded: '已剔除',
};

function StatusBadge({ status }: { status: string }) {
  const c = STATUS_COLORS[status] || STATUS_COLORS.draft;
  return (
    <span style={{
      display: 'inline-block', padding: '2px 8px', borderRadius: '4px',
      fontSize: '11px', fontWeight: 500, background: c.bg, color: c.text,
    }}>
      {STATUS_LABELS[status] || status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Add Stock Component
// ---------------------------------------------------------------------------

function AddStockSection({ themeId, onAdded }: { themeId: number; onAdded: () => void }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<StockSearchResult[]>([]);
  const [reason, setReason] = useState('');
  const [selected, setSelected] = useState<StockSearchResult | null>(null);
  const [searching, setSearching] = useState(false);

  const addMut = useMutation({
    mutationFn: (s: StockSearchResult) =>
      themePoolApi.addStock(themeId, s.stock_code, s.stock_name, reason || undefined),
    onSuccess: () => {
      setSelected(null);
      setQuery('');
      setReason('');
      setResults([]);
      onAdded();
    },
  });

  async function doSearch(q: string) {
    setQuery(q);
    if (q.length < 2) { setResults([]); return; }
    setSearching(true);
    try {
      const res = await marketApi.search(q);
      const list = Array.isArray(res.data) ? res.data : (res.data as any).data || [];
      setResults(list.slice(0, 8));
    } catch { setResults([]); }
    setSearching(false);
  }

  return (
    <div style={{
      padding: '12px 16px', borderRadius: '8px', marginBottom: '16px',
      border: '1px solid var(--border-subtle)', background: 'var(--bg-panel)',
    }}>
      <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
        <div style={{ flex: 1, position: 'relative' }}>
          <input
            value={query}
            onChange={(e) => doSearch(e.target.value)}
            placeholder="输入股票代码或名称搜索..."
            style={{
              width: '100%', padding: '7px 10px', borderRadius: '6px', fontSize: '12px',
              border: '1px solid var(--border-subtle)', background: 'var(--bg-canvas)',
              color: 'var(--text-primary)', outline: 'none', boxSizing: 'border-box',
            }}
          />
          {results.length > 0 && !selected && (
            <div style={{
              position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 10,
              background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)',
              borderRadius: '6px', marginTop: '4px', maxHeight: '200px', overflowY: 'auto',
            }}>
              {results.map((r) => (
                <div
                  key={r.stock_code}
                  onClick={() => { setSelected(r); setQuery(`${r.stock_code} ${r.stock_name}`); setResults([]); }}
                  style={{
                    padding: '6px 10px', fontSize: '12px', cursor: 'pointer',
                    color: 'var(--text-primary)',
                  }}
                  onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-nav-hover)'; }}
                  onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'transparent'; }}
                >
                  <span style={{ fontWeight: 500 }}>{r.stock_code}</span>
                  <span style={{ marginLeft: '8px', color: 'var(--text-secondary)' }}>{r.stock_name}</span>
                </div>
              ))}
            </div>
          )}
        </div>
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="推荐理由（选填）"
          style={{
            width: '200px', padding: '7px 10px', borderRadius: '6px', fontSize: '12px',
            border: '1px solid var(--border-subtle)', background: 'var(--bg-canvas)',
            color: 'var(--text-primary)', outline: 'none', boxSizing: 'border-box',
          }}
        />
        <button
          onClick={() => selected && addMut.mutate(selected)}
          disabled={!selected || addMut.isPending}
          style={{
            padding: '7px 14px', borderRadius: '6px', fontSize: '12px', fontWeight: 500,
            border: 'none', background: 'var(--accent)', color: '#fff',
            cursor: selected ? 'pointer' : 'not-allowed', opacity: selected ? 1 : 0.5,
            whiteSpace: 'nowrap',
          }}
        >
          + 添加
        </button>
      </div>
      {addMut.isError && (
        <div style={{ marginTop: '6px', fontSize: '11px', color: '#ef4444' }}>
          {(addMut.error as Error)?.message || '添加失败'}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Vote Button
// ---------------------------------------------------------------------------

function VoteButton({ stockId, upVotes, downVotes, myVote, onVoted }: {
  stockId: number;
  upVotes: number;
  downVotes: number;
  myVote: number | null;
  onVoted: () => void;
}) {
  const voteMut = useMutation({
    mutationFn: (v: number) => themePoolApi.vote(stockId, v),
    onSuccess: onVoted,
  });
  const unvoteMut = useMutation({
    mutationFn: () => themePoolApi.removeVote(stockId),
    onSuccess: onVoted,
  });

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
      <button
        onClick={(e) => { e.stopPropagation(); myVote === 1 ? unvoteMut.mutate() : voteMut.mutate(1); }}
        style={{
          padding: '2px 4px', border: 'none', borderRadius: '3px', cursor: 'pointer',
          fontSize: '12px', lineHeight: 1,
          background: myVote === 1 ? '#dcfce7' : 'transparent',
          color: myVote === 1 ? '#16a34a' : 'var(--text-muted)',
        }}
        title="看好"
      >
        +{upVotes}
      </button>
      <button
        onClick={(e) => { e.stopPropagation(); myVote === -1 ? unvoteMut.mutate() : voteMut.mutate(-1); }}
        style={{
          padding: '2px 4px', border: 'none', borderRadius: '3px', cursor: 'pointer',
          fontSize: '12px', lineHeight: 1,
          background: myVote === -1 ? '#fee2e2' : 'transparent',
          color: myVote === -1 ? '#ef4444' : 'var(--text-muted)',
        }}
        title="看空"
      >
        -{downVotes}
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Human Status Dropdown
// ---------------------------------------------------------------------------

function HumanStatusSelect({ stockId, current, onChanged }: {
  stockId: number; current: string; onChanged: () => void;
}) {
  const mut = useMutation({
    mutationFn: (s: string) => themePoolApi.updateHumanStatus(stockId, s),
    onSettled: () => onChanged(),
  });

  return (
    <select
      value={current}
      onChange={(e) => {
        const val = e.target.value;
        if (val !== current) mut.mutate(val);
      }}
      onClick={(e) => e.stopPropagation()}
      onBlur={(e) => e.stopPropagation()}
      onMouseDown={(e) => e.stopPropagation()}
      style={{
        padding: '2px 4px', borderRadius: '4px', fontSize: '11px',
        border: '1px solid var(--border-subtle)', background: 'var(--bg-canvas)',
        color: HUMAN_STATUS_COLORS[current] || 'var(--text-muted)',
        cursor: 'pointer', outline: 'none',
      }}
    >
      {Object.entries(HUMAN_STATUS_LABELS).map(([k, v]) => (
        <option key={k} value={k}>{v}</option>
      ))}
    </select>
  );
}

// ---------------------------------------------------------------------------
// Price Sparkline (inline in table)
// ---------------------------------------------------------------------------

function PriceSparkline({ prices, entryPrice }: {
  prices: { date: string; close: number }[];
  entryPrice: number | null;
}) {
  if (!prices || prices.length < 2) return <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>-</span>;

  const lastClose = prices[prices.length - 1].close;
  const isUp = entryPrice ? lastClose >= entryPrice : lastClose >= prices[0].close;
  const color = isUp ? '#16a34a' : '#ef4444';

  return <MiniSparkline data={prices} valueKey="close" width={80} height={28} color={color} />;
}

// ---------------------------------------------------------------------------
// Expanded K-line Chart (candlestick-like OHLC)
// ---------------------------------------------------------------------------

function ExpandedChart({ stock }: {
  stock: { stock_code: string; stock_name: string; entry_price: number | null; entry_date: string; prices: { date: string; open: number; high: number; low: number; close: number; volume: number }[] };
}) {
  if (!stock.prices || stock.prices.length < 2) {
    return <div style={{ padding: '16px', color: 'var(--text-muted)', fontSize: '12px' }}>No price data</div>;
  }

  const prices = stock.prices;
  const w = 600;
  const h = 200;
  const pad = { top: 10, right: 50, bottom: 24, left: 50 };
  const chartW = w - pad.left - pad.right;
  const chartH = h - pad.top - pad.bottom;

  const closes = prices.map(p => p.close);
  const allHighs = prices.map(p => p.high);
  const allLows = prices.map(p => p.low);
  const minV = Math.min(...allLows);
  const maxV = Math.max(...allHighs);
  const range = maxV - minV || 1;

  // Entry price line position
  const entryY = stock.entry_price
    ? pad.top + (1 - (stock.entry_price - minV) / range) * chartH
    : null;

  const toX = (i: number) => pad.left + (i / (prices.length - 1)) * chartW;
  const toY = (v: number) => pad.top + (1 - (v - minV) / range) * chartH;

  const candleW = Math.max(1, chartW / prices.length * 0.6);
  const lastClose = closes[closes.length - 1];
  const isUp = stock.entry_price ? lastClose >= stock.entry_price : lastClose >= closes[0];
  const lineColor = isUp ? '#16a34a' : '#ef4444';

  return (
    <div style={{ padding: '12px 16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
        <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
          {stock.stock_code} {stock.stock_name}
        </span>
        <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
          {prices[0].date} ~ {prices[prices.length - 1].date}
          {stock.entry_price && <span style={{ marginLeft: '8px' }}>Entry: {stock.entry_price.toFixed(2)}</span>}
        </span>
      </div>
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: 'block' }}>
        {/* Grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map((pct, i) => {
          const y = pad.top + pct * chartH;
          const val = maxV - pct * range;
          return (
            <g key={i}>
              <line x1={pad.left} y1={y} x2={w - pad.right} y2={y} stroke="#e5e7eb" strokeWidth="0.5" />
              <text x={pad.left - 4} y={y + 3} textAnchor="end" fontSize="9" fill="#9ca3af">{val.toFixed(1)}</text>
            </g>
          );
        })}
        {/* Entry price line */}
        {entryY !== null && (
          <line x1={pad.left} y1={entryY} x2={w - pad.right} y2={entryY} stroke="#f59e0b" strokeWidth="1" strokeDasharray="4,3" />
        )}
        {/* Candles */}
        {prices.map((p, i) => {
          const x = toX(i);
          const isGreen = p.close >= p.open;
          const bodyTop = toY(Math.max(p.open, p.close));
          const bodyBot = toY(Math.min(p.open, p.close));
          const bodyH = Math.max(1, bodyBot - bodyTop);
          return (
            <g key={i}>
              {/* Wick */}
              <line x1={x} y1={toY(p.high)} x2={x} y2={toY(p.low)} stroke={isGreen ? '#16a34a' : '#ef4444'} strokeWidth="1" />
              {/* Body */}
              <rect x={x - candleW / 2} y={bodyTop} width={candleW} height={bodyH} fill={isGreen ? '#16a34a' : '#ef4444'} rx="0.5" />
            </g>
          );
        })}
        {/* Close price line */}
        <polyline
          points={prices.map((p, i) => `${toX(i)},${toY(p.close)}`).join(' ')}
          fill="none" stroke={lineColor} strokeWidth="1" opacity="0.5"
        />
      </svg>
      <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
        Return: <span style={{ color: stock.entry_price ? (lastClose >= stock.entry_price ? '#16a34a' : '#ef4444') : 'var(--text-muted)' }}>
          {stock.entry_price ? `${((lastClose - stock.entry_price) / stock.entry_price * 100).toFixed(1)}%` : '-'}
        </span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Comparison Chart (normalized to 100)
// ---------------------------------------------------------------------------

function ComparisonChart({ stocks }: {
  stocks: { stock_code: string; stock_name: string; entry_price: number | null; prices: { date: string; close: number }[] }[];
}) {
  if (!stocks || stocks.length === 0) return null;

  // Normalize all stocks to 100 at their first data point
  const series = stocks.map(s => {
    if (!s.prices || s.prices.length < 2) return null;
    const base = s.prices[0].close;
    if (!base) return null;
    return {
      code: s.stock_code,
      name: s.stock_name,
      data: s.prices.map(p => ({ date: p.date, value: (p.close / base) * 100 })),
    };
  }).filter(Boolean) as { code: string; name: string; data: { date: string; value: number }[] }[];

  if (series.length === 0) return null;

  const w = 700;
  const h = 220;
  const pad = { top: 10, right: 10, bottom: 24, left: 40 };
  const chartW = w - pad.left - pad.right;
  const chartH = h - pad.top - pad.bottom;

  const allVals = series.flatMap(s => s.data.map(d => d.value));
  const minV = Math.min(...allVals);
  const maxV = Math.max(...allVals);
  const range = maxV - minV || 1;
  const numPoints = Math.max(...series.map(s => s.data.length));
  const toX = (i: number) => pad.left + (i / (numPoints - 1)) * chartW;
  const toY = (v: number) => pad.top + (1 - (v - minV) / range) * chartH;

  const colors = ['#3b82f6', '#ef4444', '#16a34a', '#f59e0b', '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16'];

  return (
    <div style={{ padding: '12px 16px' }}>
      <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '8px' }}>
        Normalized Comparison (base=100)
      </div>
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: 'block' }}>
        {/* 100 baseline */}
        {minV < 100 && maxV > 100 && (
          <line x1={pad.left} y1={toY(100)} x2={w - pad.right} y2={toY(100)} stroke="#9ca3af" strokeWidth="0.5" strokeDasharray="4,3" />
        )}
        {/* Y-axis labels */}
        {[0, 0.5, 1].map((pct, i) => {
          const val = minV + pct * range;
          const y = pad.top + pct * chartH;
          return <text key={i} x={pad.left - 4} y={y + 3} textAnchor="end" fontSize="9" fill="#9ca3af">{val.toFixed(0)}</text>;
        })}
        {/* Lines */}
        {series.map((s, si) => (
          <polyline
            key={s.code}
            points={s.data.map((d, i) => `${toX(i)},${toY(d.value)}`).join(' ')}
            fill="none"
            stroke={colors[si % colors.length]}
            strokeWidth="1.5"
            strokeLinejoin="round"
          />
        ))}
      </svg>
      {/* Legend */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', marginTop: '6px' }}>
        {series.map((s, i) => {
          const last = s.data[s.data.length - 1].value;
          const isUp = last >= 100;
          return (
            <span key={s.code} style={{ fontSize: '11px', color: colors[i % colors.length], display: 'flex', alignItems: 'center', gap: '4px' }}>
              <span style={{ width: '10px', height: '2px', background: colors[i % colors.length], display: 'inline-block' }} />
              {s.code} {s.name} <span style={{ color: isUp ? '#16a34a' : '#ef4444' }}>({last.toFixed(1)})</span>
            </span>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ThemeDetailPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const themeId = Number(params.themeId);

  const [statusFilter, setStatusFilter] = useState('');
  const [sortBy, setSortBy] = useState('total_score');
  const [editNote, setEditNote] = useState<{ id: number; note: string } | null>(null);
  const [editReason, setEditReason] = useState<{ id: number; reason: string } | null>(null);
  const [expandedStock, setExpandedStock] = useState<number | null>(null);
  const [showComparison, setShowComparison] = useState(false);

  // Fetch theme detail
  const { data: theme } = useQuery({
    queryKey: ['theme', themeId],
    queryFn: () => themePoolApi.getTheme(themeId).then((r) => r.data),
  });

  // Fetch stocks
  const { data: stocksData, isLoading: stocksLoading } = useQuery({
    queryKey: ['theme-stocks', themeId, statusFilter, sortBy],
    queryFn: () => themePoolApi.listStocks(themeId, {
      human_status: statusFilter || undefined,
      sort_by: sortBy,
    }).then((r) => r.data),
  });

  const stocks = stocksData?.items || [];

  // Fetch price history
  interface PriceStock {
    stock_code: string;
    stock_name: string;
    entry_date: string;
    entry_price: number | null;
    prices: { date: string; open: number; high: number; low: number; close: number; volume: number }[];
  }
  const { data: priceData } = useQuery({
    queryKey: ['theme-price-history', themeId],
    queryFn: () => themePoolApi.getPriceHistory(themeId, 60).then((r) => r.data),
    staleTime: 5 * 60 * 1000,
  });
  const priceMap = useMemo(() => {
    const m = new Map<string, PriceStock>();
    if (priceData?.stocks) {
      for (const s of priceData.stocks) m.set(s.stock_code, s);
    }
    return m;
  }, [priceData]);

  // Status change mutation
  const statusMut = useMutation({
    mutationFn: (s: string) => themePoolApi.changeStatus(themeId, s),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['theme', themeId] }),
  });

  // Score trigger mutation
  const [scoreMsg, setScoreMsg] = useState<string | null>(null);
  const scoreMut = useMutation({
    mutationFn: () => themePoolApi.triggerScore(themeId),
    onSuccess: () => {
      setScoreMsg('评分计算已启动，请稍后刷新');
      setTimeout(() => { setScoreMsg(null); refetchStocks(); }, 5000);
    },
  });

  // Delete mutation
  const deleteMut = useMutation({
    mutationFn: () => themePoolApi.deleteTheme(themeId),
    onSuccess: () => router.push('/theme-pool'),
  });

  // Remove stock mutation
  const removeMut = useMutation({
    mutationFn: (code: string) => themePoolApi.removeStock(themeId, code),
    onSuccess: () => refetchStocks(),
  });

  // Note mutation
  const noteMut = useMutation({
    mutationFn: ({ id, note }: { id: number; note: string }) => themePoolApi.updateNote(id, note),
    onSuccess: () => { setEditNote(null); refetchStocks(); },
  });

  // Reason mutation
  const reasonMut = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) => themePoolApi.updateReason(id, reason),
    onSuccess: () => { setEditReason(null); refetchStocks(); },
  });

  function refetchStocks() {
    queryClient.invalidateQueries({ queryKey: ['theme-stocks', themeId] });
  }

  const nextStatus = theme?.status === 'draft' ? 'active' : theme?.status === 'active' ? 'archived' : 'active';
  const nextStatusLabel = theme?.status === 'draft' ? '上线' : theme?.status === 'active' ? '归档' : '重新上线';

  // Table headers
  const columns = [
    { key: 'stock', label: '股票', width: '130px' },
    { key: 'recommender', label: '推荐人', width: '70px' },
    { key: 'reason', label: '推荐理由', width: '110px' },
    { key: 'rps_20', label: 'RPS20', width: '50px' },
    { key: 'tech', label: '技术面', width: '45px' },
    { key: 'fund', label: '基本面', width: '45px' },
    { key: 'total', label: '综合', width: '45px' },
    { key: 'return_5d', label: '5日%', width: '50px' },
    { key: 'return_20d', label: '20日%', width: '50px' },
    { key: 'trend', label: '走势', width: '95px' },
    { key: 'votes', label: '投票', width: '65px' },
    { key: 'status', label: '标记', width: '85px' },
    { key: 'actions', label: '', width: '60px' },
  ];

  return (
    <AppShell>
      {/* Header */}
      <div style={{ marginBottom: '16px' }}>
        <button
          onClick={() => router.push('/theme-pool')}
          style={{
            background: 'none', border: 'none', cursor: 'pointer', padding: 0,
            fontSize: '12px', color: 'var(--text-muted)', marginBottom: '8px', display: 'block',
          }}
        >
          &larr; 返回主题列表
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <h1 style={{ margin: 0, fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)' }}>
            {theme?.name || '...'}
          </h1>
          {theme && <StatusBadge status={theme.status} />}
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            {theme?.stock_count || 0} 只股票
          </span>
          <div style={{ flex: 1 }} />
          {theme && (
            <>
              <button
                onClick={() => scoreMut.mutate()}
                disabled={scoreMut.isPending}
                style={{
                  padding: '5px 12px', borderRadius: '6px', fontSize: '11px',
                  border: '1px solid var(--border-subtle)', background: 'transparent',
                  color: 'var(--accent)', cursor: scoreMut.isPending ? 'not-allowed' : 'pointer',
                  opacity: scoreMut.isPending ? 0.6 : 1,
                }}
              >
                {scoreMut.isPending ? '计算中...' : '计算评分'}
              </button>
              <button
                onClick={() => statusMut.mutate(nextStatus)}
                disabled={statusMut.isPending}
                style={{
                  padding: '5px 12px', borderRadius: '6px', fontSize: '11px',
                  border: '1px solid var(--border-subtle)', background: 'transparent',
                  color: 'var(--text-secondary)', cursor: 'pointer',
                }}
              >
                {nextStatusLabel}
              </button>
              {theme.status === 'draft' && (
                <button
                  onClick={() => { if (confirm('确定删除这个草稿主题?')) deleteMut.mutate(); }}
                  style={{
                    padding: '5px 12px', borderRadius: '6px', fontSize: '11px',
                    border: '1px solid #fecaca', background: 'transparent',
                    color: '#ef4444', cursor: 'pointer',
                  }}
                >
                  删除
                </button>
              )}
            </>
          )}
        </div>
        {theme?.description && (
          <p style={{ margin: '6px 0 0', fontSize: '12px', color: 'var(--text-secondary)' }}>
            {theme.description}
          </p>
        )}
      </div>

      {/* Status/Score messages */}
      {statusMut.isError && (
        <div style={{ marginBottom: '8px', padding: '8px 12px', borderRadius: '6px', background: '#fef2f2', color: '#ef4444', fontSize: '12px' }}>
          {(statusMut.error as any)?.response?.data?.detail || '状态变更失败'}
        </div>
      )}
      {scoreMsg && (
        <div style={{ marginBottom: '8px', padding: '8px 12px', borderRadius: '6px', background: '#f0fdf4', color: '#16a34a', fontSize: '12px' }}>
          {scoreMsg}
        </div>
      )}
      {scoreMut.isError && (
        <div style={{ marginBottom: '8px', padding: '8px 12px', borderRadius: '6px', background: '#fef2f2', color: '#ef4444', fontSize: '12px' }}>
          {(scoreMut.error as any)?.response?.data?.detail || '评分触发失败'}
        </div>
      )}

      {/* Add stock */}
      <AddStockSection themeId={themeId} onAdded={refetchStocks} />

      {/* Filters */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '12px', alignItems: 'center' }}>
        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>筛选:</span>
        {['', 'focused', 'watching', 'normal', 'excluded'].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            style={{
              padding: '3px 8px', borderRadius: '4px', fontSize: '11px',
              border: 'none', cursor: 'pointer',
              background: statusFilter === s ? 'var(--bg-nav-active)' : 'transparent',
              color: statusFilter === s ? 'var(--text-primary)' : 'var(--text-tertiary)',
            }}
          >
            {FILTER_LABELS[s]}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>排序:</span>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          style={{
            padding: '3px 8px', borderRadius: '4px', fontSize: '11px',
            border: '1px solid var(--border-subtle)', background: 'var(--bg-canvas)',
            color: 'var(--text-secondary)', outline: 'none',
          }}
        >
          <option value="total_score">综合评分</option>
          <option value="rps_20">RPS 20日</option>
          <option value="return_5d">5日涨跌幅</option>
          <option value="return_20d">20日涨跌幅</option>
          <option value="added_at">添加时间</option>
        </select>
      </div>

      {/* Stock table */}
      <div style={{ overflowX: 'auto' }}>
        <table style={{
          width: '100%', borderCollapse: 'collapse', fontSize: '12px',
        }}>
          <thead>
            <tr>
              {columns.map((col) => (
                <th
                  key={col.key}
                  style={{
                    padding: '8px 6px', textAlign: 'left', fontWeight: 500,
                    color: 'var(--text-muted)', borderBottom: '1px solid var(--border-subtle)',
                    width: col.width, whiteSpace: 'nowrap', fontSize: '11px',
                  }}
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {stocksLoading ? (
              <tr><td colSpan={columns.length} style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>加载中...</td></tr>
            ) : stocks.length === 0 ? (
              <tr><td colSpan={columns.length} style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>暂无股票，请在上方搜索添加</td></tr>
            ) : (
              stocks.map((s) => {
                const sc = s.latest_score;
                const isExcluded = s.human_status === 'excluded';
                return (
                  <React.Fragment key={s.id}>
                  <tr
                    style={{
                      borderBottom: '1px solid var(--border-subtle)',
                      opacity: isExcluded ? 0.45 : 1,
                    }}
                  >
                    {/* Stock */}
                    <td style={{ padding: '8px 6px' }}>
                      <div style={{ fontWeight: 510, color: 'var(--text-primary)' }}>{s.stock_code}</div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{s.stock_name}</div>
                    </td>
                    {/* Recommender */}
                    <td style={{ padding: '8px 6px', color: 'var(--text-secondary)' }}>
                      {s.recommender_email?.split('@')[0] || '-'}
                    </td>
                    {/* Reason */}
                    <td
                      style={{ padding: '8px 6px', color: 'var(--text-secondary)', maxWidth: '120px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', cursor: 'pointer' }}
                      title={s.reason || 'Click to edit'}
                      onClick={(e) => { e.stopPropagation(); setEditReason({ id: s.id, reason: s.reason || '' }); }}
                    >
                      {s.reason || <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>add</span>}
                    </td>
                    {/* RPS */}
                    <td style={{ padding: '8px 6px', color: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>
                      {score(sc?.rps_20)}
                    </td>
                    {/* Tech */}
                    <td style={{ padding: '8px 6px', color: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>
                      {score(sc?.tech_score)}
                    </td>
                    {/* Fund */}
                    <td style={{ padding: '8px 6px', color: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>
                      {score(sc?.fundamental_score)}
                    </td>
                    {/* Total */}
                    <td style={{ padding: '8px 6px', fontWeight: 600, color: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>
                      {score(sc?.total_score)}
                    </td>
                    {/* 5D return */}
                    <td style={{ padding: '8px 6px', color: returnColor(sc?.return_5d), fontVariantNumeric: 'tabular-nums' }}>
                      {pct(sc?.return_5d)}
                    </td>
                    {/* 20D return */}
                    <td style={{ padding: '8px 6px', color: returnColor(sc?.return_20d), fontVariantNumeric: 'tabular-nums' }}>
                      {pct(sc?.return_20d)}
                    </td>
                    {/* Trend sparkline */}
                    <td
                      style={{ padding: '8px 6px', cursor: 'pointer' }}
                      onClick={(e) => { e.stopPropagation(); setExpandedStock(expandedStock === s.id ? null : s.id); }}
                      title="Click to expand"
                    >
                      <PriceSparkline prices={priceMap.get(s.stock_code)?.prices || []} entryPrice={priceMap.get(s.stock_code)?.entry_price || null} />
                    </td>
                    {/* Votes */}
                    <td style={{ padding: '8px 6px' }}>
                      <VoteButton
                        stockId={s.id}
                        upVotes={s.up_votes}
                        downVotes={s.down_votes}
                        myVote={s.my_vote}
                        onVoted={refetchStocks}
                      />
                    </td>
                    {/* Human status */}
                    <td style={{ padding: '8px 6px' }}>
                      <HumanStatusSelect stockId={s.id} current={s.human_status} onChanged={refetchStocks} />
                    </td>
                    {/* Actions */}
                    <td style={{ padding: '8px 6px' }}>
                      <div style={{ display: 'flex', gap: '4px' }}>
                        <button
                          onClick={(e) => { e.stopPropagation(); setEditNote({ id: s.id, note: s.note || '' }); }}
                          title="编辑批注"
                          style={{
                            padding: '2px 6px', borderRadius: '3px', border: 'none',
                            background: 'transparent', color: 'var(--text-muted)',
                            cursor: 'pointer', fontSize: '11px',
                          }}
                        >
                          批注
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            if (confirm(`确定移除 ${s.stock_code}?`)) removeMut.mutate(s.stock_code);
                          }}
                          title="移除"
                          style={{
                            padding: '2px 6px', borderRadius: '3px', border: 'none',
                            background: 'transparent', color: '#ef4444',
                            cursor: 'pointer', fontSize: '11px',
                          }}
                        >
                          x
                        </button>
                      </div>
                    </td>
                  </tr>
                  {expandedStock === s.id && (
                    <tr>
                      <td colSpan={columns.length} style={{ padding: 0, borderBottom: '1px solid var(--border-subtle)' }}>
                        {priceMap.get(s.stock_code) && (
                          <ExpandedChart stock={priceMap.get(s.stock_code)!} />
                        )}
                      </td>
                    </tr>
                  )}
                  </React.Fragment>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Comparison chart panel */}
      {priceData?.stocks && priceData.stocks.length > 0 && (
        <div style={{ marginTop: '16px', border: '1px solid var(--border-subtle)', borderRadius: '8px', overflow: 'hidden' }}>
          <div
            style={{
              padding: '8px 16px', fontSize: '12px', fontWeight: 500,
              background: 'var(--bg-panel)', cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              borderBottom: showComparison ? '1px solid var(--border-subtle)' : 'none',
              color: 'var(--text-primary)',
            }}
            onClick={() => setShowComparison(!showComparison)}
          >
            <span>Relative Performance Comparison</span>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{showComparison ? 'Collapse' : 'Expand'}</span>
          </div>
          {showComparison && <ComparisonChart stocks={priceData.stocks} />}
        </div>
      )}

      {/* Note edit modal */}
      {editNote && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 1000,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }} onClick={() => setEditNote(null)}>
          <div style={{
            background: 'var(--bg-panel)', borderRadius: '10px', padding: '20px',
            width: '400px', maxWidth: '90vw',
          }} onClick={(e) => e.stopPropagation()}>
            <h4 style={{ margin: '0 0 12px', fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
              编辑批注
            </h4>
            <textarea
              value={editNote.note}
              onChange={(e) => setEditNote({ ...editNote, note: e.target.value })}
              rows={4}
              style={{
                width: '100%', padding: '8px 10px', borderRadius: '6px', fontSize: '12px',
                border: '1px solid var(--border-subtle)', background: 'var(--bg-canvas)',
                color: 'var(--text-primary)', outline: 'none', resize: 'vertical', boxSizing: 'border-box',
              }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '12px' }}>
              <button
                onClick={() => setEditNote(null)}
                style={{
                  padding: '6px 12px', borderRadius: '6px', fontSize: '11px',
                  border: '1px solid var(--border-subtle)', background: 'transparent',
                  color: 'var(--text-secondary)', cursor: 'pointer',
                }}
              >
                取消
              </button>
              <button
                onClick={() => noteMut.mutate({ id: editNote.id, note: editNote.note })}
                style={{
                  padding: '6px 12px', borderRadius: '6px', fontSize: '11px',
                  border: 'none', background: 'var(--accent)', color: '#fff', cursor: 'pointer',
                }}
              >
                保存
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reason edit modal */}
      {editReason && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 1000,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }} onClick={() => setEditReason(null)}>
          <div style={{
            background: 'var(--bg-panel)', borderRadius: '10px', padding: '20px',
            width: '400px', maxWidth: '90vw',
          }} onClick={(e) => e.stopPropagation()}>
            <h4 style={{ margin: '0 0 12px', fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
              Edit Reason
            </h4>
            <textarea
              value={editReason.reason}
              onChange={(e) => setEditReason({ ...editReason, reason: e.target.value })}
              rows={3}
              placeholder="Recommendation reason..."
              style={{
                width: '100%', padding: '8px 10px', borderRadius: '6px', fontSize: '12px',
                border: '1px solid var(--border-subtle)', background: 'var(--bg-canvas)',
                color: 'var(--text-primary)', outline: 'none', resize: 'vertical', boxSizing: 'border-box',
              }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '12px' }}>
              <button
                onClick={() => setEditReason(null)}
                style={{
                  padding: '6px 12px', borderRadius: '6px', fontSize: '11px',
                  border: '1px solid var(--border-subtle)', background: 'transparent',
                  color: 'var(--text-secondary)', cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                onClick={() => reasonMut.mutate({ id: editReason.id, reason: editReason.reason })}
                style={{
                  padding: '6px 12px', borderRadius: '6px', fontSize: '11px',
                  border: 'none', background: 'var(--accent)', color: '#fff', cursor: 'pointer',
                }}
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
