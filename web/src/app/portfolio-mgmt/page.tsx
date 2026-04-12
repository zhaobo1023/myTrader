'use client';

import React, { useState } from 'react';
import AppShell from '@/components/layout/AppShell';
import apiClient from '@/lib/api-client';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface MarketFactors {
  valuation: number;
  business: number;
  liquidity: number;
  industry_pref: number;
  total: number;
}

interface PortfolioStock {
  id: number;
  stock_code: string;
  stock_name: string;
  industry: string;
  tier: string;
  status: string;
  position_pct: number;
  profit_26: number | null;
  profit_27: number | null;
  pe_26: number | null;
  pe_27: number | null;
  net_cash_26: number;
  net_cash_27: number;
  cash_adj_coef: number;
  equity_adj: number;
  asset_growth_26: number;
  asset_growth_27: number;
  payout_ratio: number;
  research_depth: number;
  notes: string | null;
  updated_at: string | null;
  market_cap: number | null;
  tgt_26: number | null;
  tgt_27: number | null;
  return_27: number | null;
  growth_27: number | null;
  adj_return: number | null;
  market_factors: MarketFactors | null;
  suggested_pct: number | null;
}

interface TriggerRow {
  stock_code: string;
  stock_name: string;
  market_cap: number | null;
  tgt_27: number | null;
  return_27: number | null;
  strong_buy: number | null;
  add: number | null;
  reduce: number | null;
  clear: number | null;
  signal: string;
  signal_label: string;
}

interface OptimizerAllocation {
  stock_code: string;
  stock_name: string;
  industry: string;
  suggested_pct: number;
  return_27: number | null;
  growth_27: number | null;
  div_yield: number | null;
  valuation_gap: number | null;
}

interface OptimizerMetrics {
  stock_count: number;
  weighted_return_27: number | null;
  weighted_pe_27: number | null;
  yy_pct: number;
  leading_pct: number;
  cash_pct: number;
  constraints_met: boolean;
  constraint_violations: string[];
}

interface OptimizerResult {
  run_id: number;
  allocations: Record<string, number>;
  metrics: OptimizerMetrics;
  detail: OptimizerAllocation[];
  constraints_met: boolean;
}

interface IndustryWeight {
  industry: string;
  position_pct: number;
  stock_count: number;
}

interface BubblePoint {
  stock_code: string;
  stock_name: string;
  industry: string;
  growth_27: number | null;
  pe_27: number | null;
  position_pct: number;
  return_27: number | null;
}

interface PortfolioOverview {
  stock_count: number;
  weighted_return_27: number | null;
  weighted_pe_27: number | null;
  yy_pct: number;
  leading_pct: number;
  industry_weights: IndustryWeight[];
  bubble_data: BubblePoint[];
  latest_optimizer_run_id: number | null;
}

// Default empty form
const EMPTY_FORM = {
  stock_code: '',
  stock_name: '',
  industry: '',
  tier: '',
  status: 'hold',
  position_pct: 0,
  profit_26: '',
  profit_27: '',
  pe_26: '',
  pe_27: '',
  net_cash_26: 0,
  net_cash_27: 0,
  cash_adj_coef: 0.5,
  equity_adj: 0,
  asset_growth_26: 0,
  asset_growth_27: 0,
  payout_ratio: 0,
  research_depth: 80,
  notes: '',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function pct(v: number | null | undefined): string {
  if (v == null) return '-';
  return `${(v * 100).toFixed(1)}%`;
}

function num(v: number | null | undefined, decimals = 1): string {
  if (v == null) return '-';
  return v.toFixed(decimals);
}

const SIGNAL_COLORS: Record<string, string> = {
  STRONG_BUY: '#16a34a',
  ADD: '#22c55e',
  HOLD: '#6b7280',
  REDUCE: '#f59e0b',
  CLEAR: '#ef4444',
  NO_DATA: '#9ca3af',
};

const INDUSTRY_COLORS = [
  '#3b82f6', '#8b5cf6', '#ec4899', '#f59e0b',
  '#10b981', '#ef4444', '#06b6d4', '#f97316',
];

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function MetricCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div style={{
      background: 'var(--bg-panel)',
      border: '1px solid var(--border-subtle)',
      borderRadius: '8px',
      padding: '16px 20px',
    }}>
      <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '6px' }}>{label}</div>
      <div style={{ fontSize: '22px', fontWeight: 600, color: 'var(--text-primary)' }}>{value}</div>
      {sub && <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '4px' }}>{sub}</div>}
    </div>
  );
}

function Tab1Overview({ data }: { data: PortfolioOverview }) {
  // SVG bubble chart dimensions
  const W = 480;
  const H = 300;
  const PAD = 40;

  const bubbles = data.bubble_data.filter(b => b.growth_27 != null && b.pe_27 != null);
  const growths = bubbles.map(b => b.growth_27!);
  const pes = bubbles.map(b => b.pe_27!);
  const minG = Math.min(0, ...growths);
  const maxG = Math.max(50, ...growths);
  const minP = Math.min(0, ...pes);
  const maxP = Math.max(30, ...pes);

  function toX(g: number) {
    return PAD + ((g - minG) / (maxG - minG || 1)) * (W - 2 * PAD);
  }
  function toY(p: number) {
    return H - PAD - ((p - minP) / (maxP - minP || 1)) * (H - 2 * PAD);
  }

  const industryList = [...new Set(bubbles.map(b => b.industry))];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Metric cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '12px' }}>
        <MetricCard label="持股数" value={String(data.stock_count)} />
        <MetricCard label="2027E组合回报" value={pct(data.weighted_return_27)} />
        <MetricCard label="加权PE (2027E)" value={num(data.weighted_pe_27, 1) + 'x'} />
        <MetricCard label="Far Ahead 占比" value={`${data.yy_pct.toFixed(1)}%`} />
        <MetricCard label="Leading 占比" value={`${data.leading_pct.toFixed(1)}%`} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
        {/* Industry bars */}
        <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '16px' }}>
          <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '12px' }}>行业分布</div>
          {data.industry_weights.map((iw, idx) => (
            <div key={iw.industry} style={{ marginBottom: '8px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '3px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>{iw.industry || 'Other'}</span>
                <span style={{ color: 'var(--text-muted)' }}>{iw.position_pct.toFixed(1)}%</span>
              </div>
              <div style={{ height: '6px', background: 'var(--border-subtle)', borderRadius: '3px' }}>
                <div style={{
                  height: '100%',
                  width: `${Math.min(iw.position_pct, 100)}%`,
                  background: INDUSTRY_COLORS[idx % INDUSTRY_COLORS.length],
                  borderRadius: '3px',
                }} />
              </div>
            </div>
          ))}
        </div>

        {/* SVG bubble chart */}
        <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '16px' }}>
          <div style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '8px' }}>估值-增速矩阵 (X=增速%, Y=合理PE)</div>
          <svg width={W} height={H} style={{ overflow: 'visible' }}>
            {/* Axes */}
            <line x1={PAD} y1={H - PAD} x2={W - PAD} y2={H - PAD} stroke="var(--border-subtle)" strokeWidth="1" />
            <line x1={PAD} y1={PAD} x2={PAD} y2={H - PAD} stroke="var(--border-subtle)" strokeWidth="1" />
            {/* Labels */}
            <text x={W / 2} y={H - 8} fontSize="10" fill="var(--text-muted)" textAnchor="middle">增速 %</text>
            <text x={12} y={H / 2} fontSize="10" fill="var(--text-muted)" textAnchor="middle" transform={`rotate(-90,12,${H / 2})`}>合理PE</text>
            {/* Bubbles */}
            {bubbles.map((b, i) => {
              const cx = toX(b.growth_27!);
              const cy = toY(b.pe_27!);
              const r = Math.max(6, Math.min(20, b.position_pct * 0.8));
              const color = INDUSTRY_COLORS[industryList.indexOf(b.industry) % INDUSTRY_COLORS.length];
              return (
                <g key={b.stock_code}>
                  <circle cx={cx} cy={cy} r={r} fill={color} opacity={0.7} />
                  <text x={cx} y={cy + 3} fontSize="9" fill="white" textAnchor="middle">{b.stock_code.slice(0, 4)}</text>
                </g>
              );
            })}
          </svg>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inline edit form for stock
// ---------------------------------------------------------------------------

function StockEditRow({
  stock,
  onSave,
  onDelete,
}: {
  stock: PortfolioStock;
  onSave: (data: Record<string, unknown>) => void;
  onDelete: (code: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [form, setForm] = useState<Record<string, unknown>>({ ...stock });
  const [saving, setSaving] = useState(false);

  function handleChange(key: string, value: unknown) {
    setForm(prev => ({ ...prev, [key]: value }));
  }

  async function handleSave() {
    setSaving(true);
    await onSave(form);
    setSaving(false);
    setExpanded(false);
  }

  const signalBg = stock.market_factors
    ? stock.market_factors.total >= 70 ? '#dcfce7' : stock.market_factors.total >= 50 ? '#fef9c3' : '#fee2e2'
    : '#f3f4f6';

  return (
    <React.Fragment>
      <tr
        style={{ cursor: 'pointer', borderBottom: '1px solid var(--border-subtle)' }}
        onClick={() => setExpanded(e => !e)}
      >
        <td style={{ padding: '8px 10px', fontSize: '12px', color: 'var(--text-primary)', fontWeight: 500 }}>
          {stock.stock_code}
        </td>
        <td style={{ padding: '8px 10px', fontSize: '12px', color: 'var(--text-secondary)' }}>{stock.stock_name}</td>
        <td style={{ padding: '8px 10px', fontSize: '12px', color: 'var(--text-muted)' }}>{stock.industry}</td>
        <td style={{ padding: '8px 10px', fontSize: '11px' }}>
          <span style={{
            background: stock.tier === 'Far Ahead' ? '#dbeafe' : stock.tier === 'Leading' ? '#ede9fe' : '#f3f4f6',
            color: stock.tier === 'Far Ahead' ? '#1d4ed8' : stock.tier === 'Leading' ? '#7c3aed' : '#6b7280',
            padding: '2px 6px', borderRadius: '4px',
          }}>{stock.tier || '-'}</span>
        </td>
        <td style={{ padding: '8px 10px', fontSize: '12px', color: 'var(--text-secondary)' }}>{stock.position_pct.toFixed(1)}%</td>
        <td style={{ padding: '8px 10px', fontSize: '12px', color: stock.return_27 != null && stock.return_27 > 0 ? '#16a34a' : '#ef4444' }}>
          {pct(stock.return_27)}
        </td>
        <td style={{ padding: '8px 10px', fontSize: '11px' }}>
          {stock.market_factors && (
            <span style={{ background: signalBg, padding: '2px 6px', borderRadius: '4px', fontWeight: 500 }}>
              {stock.market_factors.total.toFixed(0)}
            </span>
          )}
        </td>
        <td style={{ padding: '8px 10px', fontSize: '12px', color: 'var(--text-muted)' }}>
          {pct(stock.adj_return)}
        </td>
        <td style={{ padding: '8px 10px', fontSize: '12px', color: '#7c3aed' }}>
          {stock.suggested_pct != null ? `${stock.suggested_pct}%` : '-'}
        </td>
        <td style={{ padding: '8px 10px', fontSize: '12px', color: 'var(--text-muted)' }}>
          {stock.suggested_pct != null && stock.position_pct != null
            ? `${(stock.suggested_pct - stock.position_pct).toFixed(1)}%`
            : '-'}
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={10} style={{ background: 'var(--bg-canvas)', padding: '12px 16px', borderBottom: '1px solid var(--border-subtle)' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px', marginBottom: '12px' }}>
              {[
                { key: 'profit_26', label: "2026E利润(亿)" },
                { key: 'profit_27', label: "2027E利润(亿)" },
                { key: 'pe_26', label: "2026E合理PE" },
                { key: 'pe_27', label: "2027E合理PE" },
                { key: 'net_cash_26', label: "2026E净现金(亿)" },
                { key: 'net_cash_27', label: "2027E净现金(亿)" },
                { key: 'equity_adj', label: "投资权益调整(亿)" },
                { key: 'asset_growth_27', label: "2027资产增值(亿)" },
                { key: 'payout_ratio', label: "分红回购率" },
                { key: 'research_depth', label: "研究深度(0-100)" },
                { key: 'position_pct', label: "当前仓位%" },
                { key: 'cash_adj_coef', label: "净现金折算系数" },
              ].map(({ key, label }) => (
                <div key={key}>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '3px' }}>{label}</div>
                  <input
                    type="number"
                    value={form[key] as string ?? ''}
                    onChange={e => handleChange(key, e.target.value === '' ? null : Number(e.target.value))}
                    style={{
                      width: '100%', padding: '5px 8px', fontSize: '12px',
                      background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)',
                      borderRadius: '4px', color: 'var(--text-primary)',
                    }}
                  />
                </div>
              ))}
              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '3px' }}>分级</div>
                <select
                  value={form['tier'] as string}
                  onChange={e => handleChange('tier', e.target.value)}
                  style={{ width: '100%', padding: '5px 8px', fontSize: '12px', background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)', borderRadius: '4px', color: 'var(--text-primary)' }}
                >
                  <option value="">-</option>
                  <option value="Far Ahead">Far Ahead</option>
                  <option value="Leading">Leading</option>
                </select>
              </div>
              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '3px' }}>状态</div>
                <select
                  value={form['status'] as string}
                  onChange={e => handleChange('status', e.target.value)}
                  style={{ width: '100%', padding: '5px 8px', fontSize: '12px', background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)', borderRadius: '4px', color: 'var(--text-primary)' }}
                >
                  <option value="hold">hold</option>
                  <option value="watch">watch</option>
                </select>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button
                onClick={handleSave}
                disabled={saving}
                style={{ padding: '6px 14px', fontSize: '12px', background: 'var(--accent)', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer' }}
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
              <button
                onClick={() => setExpanded(false)}
                style={{ padding: '6px 14px', fontSize: '12px', background: 'var(--bg-panel)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)', borderRadius: '6px', cursor: 'pointer' }}
              >
                Cancel
              </button>
              <button
                onClick={() => { if (confirm(`Remove ${stock.stock_code}?`)) onDelete(stock.stock_code); }}
                style={{ padding: '6px 14px', fontSize: '12px', background: '#fee2e2', color: '#ef4444', border: 'none', borderRadius: '6px', cursor: 'pointer', marginLeft: 'auto' }}
              >
                Delete
              </button>
            </div>
          </td>
        </tr>
      )}
    </React.Fragment>
  );
}

// ---------------------------------------------------------------------------
// Add stock modal
// ---------------------------------------------------------------------------

function AddStockModal({ onClose, onAdd }: { onClose: () => void; onAdd: (data: Record<string, unknown>) => Promise<void> }) {
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  function handleChange(key: string, value: unknown) {
    setForm(prev => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!form.stock_code.trim()) { setError('Stock code required'); return; }
    setSaving(true);
    setError('');
    try {
      await onAdd(form as unknown as Record<string, unknown>);
      onClose();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to add stock');
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 100,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{ background: 'var(--bg-panel)', borderRadius: '10px', padding: '24px', width: '560px', maxHeight: '80vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px' }}>
          <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>Add Stock</span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', fontSize: '18px' }}>x</button>
        </div>
        {error && <div style={{ color: '#ef4444', fontSize: '12px', marginBottom: '10px' }}>{error}</div>}
        <form onSubmit={handleSubmit}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '14px' }}>
            {[
              { key: 'stock_code', label: 'Stock Code*', type: 'text' },
              { key: 'stock_name', label: 'Name', type: 'text' },
              { key: 'industry', label: 'Industry', type: 'text' },
              { key: 'position_pct', label: 'Position %', type: 'number' },
              { key: 'profit_26', label: '2026E Profit (100M)', type: 'number' },
              { key: 'profit_27', label: '2027E Profit (100M)', type: 'number' },
              { key: 'pe_26', label: '2026E Fair PE', type: 'number' },
              { key: 'pe_27', label: '2027E Fair PE', type: 'number' },
              { key: 'payout_ratio', label: 'Payout Ratio (0-1)', type: 'number' },
              { key: 'research_depth', label: 'Research Depth', type: 'number' },
            ].map(({ key, label, type }) => (
              <div key={key}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '3px' }}>{label}</div>
                <input
                  type={type}
                  value={form[key as keyof typeof form] as string}
                  onChange={e => handleChange(key, type === 'number' ? (e.target.value === '' ? null : Number(e.target.value)) : e.target.value)}
                  style={{ width: '100%', padding: '6px 8px', fontSize: '12px', background: 'var(--bg-canvas)', border: '1px solid var(--border-subtle)', borderRadius: '4px', color: 'var(--text-primary)' }}
                />
              </div>
            ))}
            <div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '3px' }}>Tier</div>
              <select
                value={form.tier}
                onChange={e => handleChange('tier', e.target.value)}
                style={{ width: '100%', padding: '6px 8px', fontSize: '12px', background: 'var(--bg-canvas)', border: '1px solid var(--border-subtle)', borderRadius: '4px', color: 'var(--text-primary)' }}
              >
                <option value="">-</option>
                <option value="Far Ahead">Far Ahead</option>
                <option value="Leading">Leading</option>
              </select>
            </div>
          </div>
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
            <button type="button" onClick={onClose} style={{ padding: '7px 16px', fontSize: '12px', background: 'var(--bg-canvas)', border: '1px solid var(--border-subtle)', borderRadius: '6px', cursor: 'pointer', color: 'var(--text-secondary)' }}>Cancel</button>
            <button type="submit" disabled={saving} style={{ padding: '7px 16px', fontSize: '12px', background: 'var(--accent)', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer' }}>
              {saving ? 'Adding...' : 'Add Stock'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function PortfolioMgmtPage() {
  const [activeTab, setActiveTab] = useState<'overview' | 'stocks' | 'triggers' | 'optimize'>('overview');
  const [showAddModal, setShowAddModal] = useState(false);
  const qc = useQueryClient();

  // Queries
  const overviewQ = useQuery<PortfolioOverview>({
    queryKey: ['portfolio-mgmt-overview'],
    queryFn: async () => (await apiClient.get('/api/portfolio-mgmt/overview')).data,
  });

  const stocksQ = useQuery<{ data: PortfolioStock[] }>({
    queryKey: ['portfolio-mgmt-stocks'],
    queryFn: async () => (await apiClient.get('/api/portfolio-mgmt/stocks')).data,
  });

  const triggersQ = useQuery<{ data: TriggerRow[] }>({
    queryKey: ['portfolio-mgmt-triggers'],
    queryFn: async () => (await apiClient.get('/api/portfolio-mgmt/trigger-prices')).data,
    enabled: activeTab === 'triggers',
  });

  // Mutations
  const updateMut = useMutation({
    mutationFn: async ({ code, data }: { code: string; data: Record<string, unknown> }) =>
      (await apiClient.put(`/api/portfolio-mgmt/stocks/${code}`, data)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portfolio-mgmt-stocks'] });
      qc.invalidateQueries({ queryKey: ['portfolio-mgmt-overview'] });
    },
  });

  const deleteMut = useMutation({
    mutationFn: async (code: string) => (await apiClient.delete(`/api/portfolio-mgmt/stocks/${code}`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portfolio-mgmt-stocks'] });
      qc.invalidateQueries({ queryKey: ['portfolio-mgmt-overview'] });
    },
  });

  const addMut = useMutation({
    mutationFn: async (data: Record<string, unknown>) => (await apiClient.post('/api/portfolio-mgmt/stocks', data)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['portfolio-mgmt-stocks'] });
      qc.invalidateQueries({ queryKey: ['portfolio-mgmt-overview'] });
    },
  });

  const [optimizeResult, setOptimizeResult] = useState<OptimizerResult | null>(null);
  const [optimizeError, setOptimizeError] = useState('');
  const optimizeMut = useMutation({
    mutationFn: async () => (await apiClient.post('/api/portfolio-mgmt/optimize')).data as OptimizerResult,
    onSuccess: (data) => {
      setOptimizeResult(data);
      qc.invalidateQueries({ queryKey: ['portfolio-mgmt-stocks'] });
    },
    onError: (err: unknown) => {
      setOptimizeError(err instanceof Error ? err.message : 'Optimization failed');
    },
  });

  const TABS = [
    { key: 'overview', label: '概况' },
    { key: 'stocks', label: '持仓明细' },
    { key: 'triggers', label: '买卖触发价' },
    { key: 'optimize', label: '智能调仓' },
  ] as const;

  return (
    <AppShell topBar={<span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>组合管理</span>}>
      {showAddModal && (
        <AddStockModal
          onClose={() => setShowAddModal(false)}
          onAdd={async (data) => { await addMut.mutateAsync(data); }}
        />
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '4px', marginBottom: '20px', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0' }}>
        {TABS.map(t => (
          <button
            key={t.key}
            onClick={() => setActiveTab(t.key)}
            style={{
              padding: '8px 16px',
              fontSize: '13px',
              background: 'none',
              border: 'none',
              borderBottom: activeTab === t.key ? '2px solid var(--accent)' : '2px solid transparent',
              color: activeTab === t.key ? 'var(--accent)' : 'var(--text-tertiary)',
              cursor: 'pointer',
              fontWeight: activeTab === t.key ? 600 : 400,
              marginBottom: '-1px',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab 1: Overview */}
      {activeTab === 'overview' && (
        <div>
          {overviewQ.isLoading && <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Loading...</div>}
          {overviewQ.error && <div style={{ color: '#ef4444', fontSize: '13px' }}>Failed to load overview</div>}
          {overviewQ.data && <Tab1Overview data={overviewQ.data} />}
        </div>
      )}

      {/* Tab 2: Stock list */}
      {activeTab === 'stocks' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
              {stocksQ.data?.data?.length ?? 0} stocks &mdash; click row to expand and edit
            </span>
            <button
              onClick={() => setShowAddModal(true)}
              style={{ padding: '7px 14px', fontSize: '12px', background: 'var(--accent)', color: 'white', border: 'none', borderRadius: '6px', cursor: 'pointer' }}
            >
              + Add Stock
            </button>
          </div>
          {stocksQ.isLoading && <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Loading...</div>}
          {stocksQ.data && (
            <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)', borderRadius: '8px', overflow: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                    {['代码', '名称', '行业', '分级', '仓位', '2027E回报', '四因子', '调整回报', '建议仓位', '变动'].map(h => (
                      <th key={h} style={{ padding: '8px 10px', fontSize: '11px', color: 'var(--text-muted)', textAlign: 'left', whiteSpace: 'nowrap', fontWeight: 600 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {stocksQ.data.data.map(s => (
                    <StockEditRow
                      key={s.stock_code}
                      stock={s}
                      onSave={async (data) => updateMut.mutateAsync({ code: s.stock_code, data })}
                      onDelete={(code) => deleteMut.mutate(code)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Tab 3: Trigger prices */}
      {activeTab === 'triggers' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <span style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>实时市值 + 买卖阈值 (亿元)</span>
            <button
              onClick={() => qc.invalidateQueries({ queryKey: ['portfolio-mgmt-triggers'] })}
              style={{ padding: '7px 14px', fontSize: '12px', background: 'var(--bg-panel)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)', borderRadius: '6px', cursor: 'pointer' }}
            >
              Refresh
            </button>
          </div>
          {triggersQ.isLoading && <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Loading...</div>}
          {triggersQ.data && (
            <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)', borderRadius: '8px', overflow: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                    {['公司', '当前市值', 'TGT27', '2027E回报', '强买', '加仓', '减仓', '清仓', '信号'].map(h => (
                      <th key={h} style={{ padding: '8px 10px', fontSize: '11px', color: 'var(--text-muted)', textAlign: 'left', whiteSpace: 'nowrap', fontWeight: 600 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {triggersQ.data.data.map(row => (
                    <tr key={row.stock_code} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <td style={{ padding: '8px 10px', fontSize: '12px' }}>
                        <div style={{ fontWeight: 500, color: 'var(--text-primary)' }}>{row.stock_code}</div>
                        <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{row.stock_name}</div>
                      </td>
                      <td style={{ padding: '8px 10px', fontSize: '12px', color: 'var(--text-secondary)' }}>{row.market_cap != null ? row.market_cap.toFixed(0) : '-'}</td>
                      <td style={{ padding: '8px 10px', fontSize: '12px', color: 'var(--text-secondary)' }}>{row.tgt_27 != null ? row.tgt_27.toFixed(0) : '-'}</td>
                      <td style={{ padding: '8px 10px', fontSize: '12px', color: row.return_27 != null && row.return_27 > 0 ? '#16a34a' : '#ef4444' }}>{pct(row.return_27)}</td>
                      <td style={{ padding: '8px 10px', fontSize: '12px', color: '#16a34a' }}>{row.strong_buy != null ? row.strong_buy.toFixed(0) : '-'}</td>
                      <td style={{ padding: '8px 10px', fontSize: '12px', color: '#22c55e' }}>{row.add != null ? row.add.toFixed(0) : '-'}</td>
                      <td style={{ padding: '8px 10px', fontSize: '12px', color: '#f59e0b' }}>{row.reduce != null ? row.reduce.toFixed(0) : '-'}</td>
                      <td style={{ padding: '8px 10px', fontSize: '12px', color: '#ef4444' }}>{row.clear != null ? row.clear.toFixed(0) : '-'}</td>
                      <td style={{ padding: '8px 10px' }}>
                        <span style={{
                          padding: '3px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 600,
                          background: SIGNAL_COLORS[row.signal] + '22',
                          color: SIGNAL_COLORS[row.signal],
                        }}>
                          {row.signal_label}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Tab 4: Smart rebalance */}
      {activeTab === 'optimize' && (
        <div>
          {/* Assumptions summary */}
          <div style={{ marginBottom: '16px' }}>
            <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '8px' }}>估值假设汇总 (只读，可在持仓明细中编辑)</div>
            {stocksQ.isLoading && <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>Loading...</div>}
            {stocksQ.data && (
              <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)', borderRadius: '8px', overflow: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      {['代码', '名称', '仓位%', '2027E利润', '2027E PE', '分红率', '研究深度', 'TGT27', '2027E回报'].map(h => (
                        <th key={h} style={{ padding: '7px 10px', fontSize: '11px', color: 'var(--text-muted)', textAlign: 'left', fontWeight: 600, whiteSpace: 'nowrap' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {stocksQ.data.data.map(s => (
                      <tr key={s.stock_code} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                        <td style={{ padding: '7px 10px', fontSize: '12px', fontWeight: 500, color: 'var(--text-primary)' }}>{s.stock_code}</td>
                        <td style={{ padding: '7px 10px', fontSize: '12px', color: 'var(--text-secondary)' }}>{s.stock_name}</td>
                        <td style={{ padding: '7px 10px', fontSize: '12px', color: 'var(--text-muted)' }}>{s.position_pct.toFixed(1)}%</td>
                        <td style={{ padding: '7px 10px', fontSize: '12px', color: 'var(--text-muted)' }}>{s.profit_27 != null ? s.profit_27.toFixed(0) : '-'}</td>
                        <td style={{ padding: '7px 10px', fontSize: '12px', color: 'var(--text-muted)' }}>{s.pe_27 != null ? s.pe_27.toFixed(1) : '-'}</td>
                        <td style={{ padding: '7px 10px', fontSize: '12px', color: 'var(--text-muted)' }}>{(s.payout_ratio * 100).toFixed(0)}%</td>
                        <td style={{ padding: '7px 10px', fontSize: '12px', color: 'var(--text-muted)' }}>{s.research_depth}</td>
                        <td style={{ padding: '7px 10px', fontSize: '12px', color: 'var(--text-muted)' }}>{s.tgt_27 != null ? s.tgt_27.toFixed(0) : '-'}</td>
                        <td style={{ padding: '7px 10px', fontSize: '12px', color: s.return_27 != null && s.return_27 > 0 ? '#16a34a' : '#ef4444' }}>{pct(s.return_27)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Optimize button */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
            <button
              onClick={() => optimizeMut.mutate()}
              disabled={optimizeMut.isPending}
              style={{ padding: '9px 20px', fontSize: '13px', background: 'var(--accent)', color: 'white', border: 'none', borderRadius: '7px', cursor: 'pointer', fontWeight: 600 }}
            >
              {optimizeMut.isPending ? 'Optimizing...' : 'Generate Optimal Portfolio'}
            </button>
            {optimizeError && <span style={{ fontSize: '12px', color: '#ef4444' }}>{optimizeError}</span>}
          </div>

          {/* Optimizer result */}
          {optimizeResult && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
              {/* Metrics */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '10px' }}>
                <MetricCard label="选股数" value={String(optimizeResult.metrics.stock_count)} />
                <MetricCard label="2027E加权回报" value={pct(optimizeResult.metrics.weighted_return_27)} />
                <MetricCard label="加权PE" value={num(optimizeResult.metrics.weighted_pe_27, 1) + 'x'} />
                <MetricCard label="Far Ahead" value={`${optimizeResult.metrics.yy_pct.toFixed(0)}%`} />
                <MetricCard label="现金" value={`${optimizeResult.metrics.cash_pct.toFixed(0)}%`}
                  sub={optimizeResult.metrics.constraints_met ? '[OK] All constraints met' : '[WARN] Constraints violated'} />
              </div>

              {/* Violations */}
              {optimizeResult.metrics.constraint_violations.length > 0 && (
                <div style={{ background: '#fef9c3', border: '1px solid #fbbf24', borderRadius: '6px', padding: '10px 14px' }}>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: '#92400e', marginBottom: '4px' }}>[WARN] Constraint Violations</div>
                  {optimizeResult.metrics.constraint_violations.map((v, i) => (
                    <div key={i} style={{ fontSize: '11px', color: '#78350f' }}>{v}</div>
                  ))}
                </div>
              )}

              {/* Detail table */}
              <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)', borderRadius: '8px', overflow: 'auto' }}>
                <div style={{ padding: '10px 14px', fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)', borderBottom: '1px solid var(--border-subtle)' }}>
                  Recommended Portfolio (Run #{optimizeResult.run_id})
                </div>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      {['公司', '建议仓位', '2027E回报', '年化增速', '股息率', '估值偏离'].map(h => (
                        <th key={h} style={{ padding: '8px 10px', fontSize: '11px', color: 'var(--text-muted)', textAlign: 'left', fontWeight: 600 }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {optimizeResult.detail.map(row => (
                      <tr key={row.stock_code} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                        <td style={{ padding: '8px 10px' }}>
                          <div style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-primary)' }}>{row.stock_code}</div>
                          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{row.stock_name} | {row.industry}</div>
                        </td>
                        <td style={{ padding: '8px 10px', fontSize: '13px', fontWeight: 600, color: 'var(--accent)' }}>{row.suggested_pct}%</td>
                        <td style={{ padding: '8px 10px', fontSize: '12px', color: row.return_27 != null && row.return_27 > 0 ? '#16a34a' : '#ef4444' }}>{pct(row.return_27)}</td>
                        <td style={{ padding: '8px 10px', fontSize: '12px', color: 'var(--text-secondary)' }}>{row.growth_27 != null ? `${row.growth_27.toFixed(1)}%` : '-'}</td>
                        <td style={{ padding: '8px 10px', fontSize: '12px', color: 'var(--text-muted)' }}>{row.div_yield != null ? pct(row.div_yield) : '-'}</td>
                        <td style={{ padding: '8px 10px', fontSize: '12px', color: row.valuation_gap != null && row.valuation_gap > 0 ? '#16a34a' : '#ef4444' }}>
                          {row.valuation_gap != null ? pct(row.valuation_gap) : '-'}
                        </td>
                      </tr>
                    ))}
                    {optimizeResult.metrics.cash_pct > 0 && (
                      <tr>
                        <td colSpan={2} style={{ padding: '8px 10px', fontSize: '12px', color: 'var(--text-muted)', fontStyle: 'italic' }}>
                          CASH: {optimizeResult.metrics.cash_pct.toFixed(0)}%
                        </td>
                        <td colSpan={4} />
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </AppShell>
  );
}
