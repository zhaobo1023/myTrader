'use client';

import React, { useState, useEffect, useCallback } from 'react';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || '';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SimPool {
  id: number;
  strategy_type: string;
  signal_date: string;
  status: 'pending' | 'active' | 'closed';
  initial_cash: number;
  current_value: number | null;
  total_return: number | null;
  max_drawdown: number | null;
  sharpe_ratio: number | null;
  created_at: string;
  closed_at: string | null;
}

interface CreatePoolFormData {
  strategy_type: string;
  signal_date: string;
  max_positions: number;
  initial_cash: number;
  stop_loss_pct: number;
  take_profit_pct: number;
  max_hold_days: number;
  strategy_params: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtPct(v: number | null | undefined): string {
  if (v == null) return '--';
  const sign = v >= 0 ? '+' : '';
  return `${sign}${(v * 100).toFixed(2)}%`;
}

function fmtMoney(v: number | null | undefined): string {
  if (v == null) return '--';
  return v >= 10000 ? `${(v / 10000).toFixed(2)}万` : v.toFixed(0);
}

function statusLabel(s: string): { text: string; color: string } {
  const map: Record<string, { text: string; color: string }> = {
    pending: { text: '待买入', color: '#f59e0b' },
    active:  { text: '运行中', color: '#3b82f6' },
    closed:  { text: '已关闭', color: '#6b7280' },
  };
  return map[s] || { text: s, color: '#6b7280' };
}

function strategyLabel(s: string): string {
  const map: Record<string, string> = {
    momentum:  '动量反转',
    industry:  '行业轮动',
    micro_cap: '微盘股',
  };
  return map[s] || s;
}

// ---------------------------------------------------------------------------
// CreatePoolModal
// ---------------------------------------------------------------------------

function CreatePoolModal({ onClose, onCreated }: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const today = new Date().toISOString().split('T')[0];

  const [form, setForm] = useState<CreatePoolFormData>({
    strategy_type: 'momentum',
    signal_date: today,
    max_positions: 10,
    initial_cash: 1000000,
    stop_loss_pct: 0.08,
    take_profit_pct: 0.20,
    max_hold_days: 30,
    strategy_params: {},
  });

  const [loading, setLoading] = useState(false);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState<string>('');
  const [error, setError] = useState('');

  const handleSubmit = async () => {
    setLoading(true);
    setError('');
    try {
      const payload = {
        strategy_type: form.strategy_type,
        signal_date: form.signal_date,
        config: {
          max_positions: form.max_positions,
          initial_cash: form.initial_cash,
          stop_loss_pct: form.stop_loss_pct,
          take_profit_pct: form.take_profit_pct,
          max_hold_days: form.max_hold_days,
          strategy_params: form.strategy_params,
        },
      };
      const res = await fetch(`${API_BASE}/api/sim-pool`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Create failed');
      setTaskId(data.task_id);
      setTaskStatus('PENDING');
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  // Poll task status
  useEffect(() => {
    if (!taskId) return;
    let done = false;
    const poll = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/sim-pool/tasks/${taskId}`);
        const data = await res.json();
        setTaskStatus(data.status);
        if (data.status === 'SUCCESS') {
          done = true;
          setTimeout(() => { onCreated(); onClose(); }, 1000);
        } else if (data.status === 'FAILURE') {
          done = true;
          setError('Task failed');
        }
      } catch {}
    };
    const interval = setInterval(() => { if (!done) poll(); }, 2000);
    poll();
    return () => clearInterval(interval);
  }, [taskId, onCreated, onClose]);

  const setField = (key: keyof CreatePoolFormData, value: unknown) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const inputStyle: React.CSSProperties = {
    width: '100%', padding: '6px 10px', borderRadius: '6px', fontSize: '13px',
    border: '1px solid var(--border-subtle)', background: 'var(--bg-canvas)',
    color: 'var(--text-primary)', boxSizing: 'border-box',
  };
  const labelStyle: React.CSSProperties = {
    display: 'block', fontSize: '12px', color: 'var(--text-tertiary)', marginBottom: '4px',
  };
  const fieldStyle: React.CSSProperties = { marginBottom: '14px' };

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 100,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }} onClick={onClose}>
      <div style={{
        background: 'var(--bg-panel)', borderRadius: '10px', padding: '24px',
        width: '460px', maxWidth: '95vw', maxHeight: '90vh', overflowY: 'auto',
      }} onClick={(e) => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '20px' }}>
          <span style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
            创建模拟池
          </span>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', fontSize: '18px' }}>&times;</button>
        </div>

        {/* Strategy type */}
        <div style={fieldStyle}>
          <label style={labelStyle}>策略类型</label>
          <select value={form.strategy_type} onChange={(e) => setField('strategy_type', e.target.value)} style={inputStyle}>
            <option value="momentum">动量反转 (Momentum)</option>
            <option value="industry">行业轮动 (Industry)</option>
            <option value="micro_cap">微盘股 (Micro Cap)</option>
          </select>
        </div>

        {/* Signal date */}
        <div style={fieldStyle}>
          <label style={labelStyle}>选股日期</label>
          <input type="date" value={form.signal_date} onChange={(e) => setField('signal_date', e.target.value)} style={inputStyle} />
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
          <div style={fieldStyle}>
            <label style={labelStyle}>初始资金 (元)</label>
            <input type="number" value={form.initial_cash} onChange={(e) => setField('initial_cash', Number(e.target.value))} style={inputStyle} />
          </div>
          <div style={fieldStyle}>
            <label style={labelStyle}>最大持仓数</label>
            <input type="number" min={1} max={50} value={form.max_positions} onChange={(e) => setField('max_positions', Number(e.target.value))} style={inputStyle} />
          </div>
          <div style={fieldStyle}>
            <label style={labelStyle}>止损 (%)</label>
            <input type="number" step={0.01} min={0.01} max={0.5} value={form.stop_loss_pct} onChange={(e) => setField('stop_loss_pct', Number(e.target.value))} style={inputStyle} />
          </div>
          <div style={fieldStyle}>
            <label style={labelStyle}>止盈 (%)</label>
            <input type="number" step={0.01} min={0.01} max={1} value={form.take_profit_pct} onChange={(e) => setField('take_profit_pct', Number(e.target.value))} style={inputStyle} />
          </div>
          <div style={fieldStyle}>
            <label style={labelStyle}>最大持有天数</label>
            <input type="number" min={1} max={365} value={form.max_hold_days} onChange={(e) => setField('max_hold_days', Number(e.target.value))} style={inputStyle} />
          </div>
        </div>

        {error && (
          <div style={{ color: '#ef4444', fontSize: '12px', marginBottom: '12px' }}>{error}</div>
        )}

        {taskId && (
          <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginBottom: '12px' }}>
            任务状态: <strong style={{ color: taskStatus === 'SUCCESS' ? '#10b981' : 'var(--text-primary)' }}>{taskStatus}</strong>
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
          <button onClick={onClose} style={{ padding: '7px 16px', borderRadius: '6px', border: '1px solid var(--border-subtle)', background: 'transparent', cursor: 'pointer', fontSize: '13px', color: 'var(--text-secondary)' }}>
            取消
          </button>
          <button onClick={handleSubmit} disabled={loading || !!taskId} style={{ padding: '7px 16px', borderRadius: '6px', border: 'none', background: '#3b82f6', color: '#fff', cursor: loading || !!taskId ? 'not-allowed' : 'pointer', fontSize: '13px', opacity: loading || !!taskId ? 0.7 : 1 }}>
            {loading ? '提交中...' : taskId ? '已提交' : '创建'}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// MetricsCard
// ---------------------------------------------------------------------------

interface DetailMetrics {
  annual_return?: number | null;
  win_rate?: number | null;
  profit_loss_ratio?: number | null;
  avg_hold_days?: number | null;
  excess_return?: number | null;
  total_trades?: number | null;
}

function MetricsCard({ pool, detail }: { pool: SimPool; detail?: DetailMetrics }) {
  const ret = pool.total_return;
  const retColor = (v: number | null | undefined) =>
    v == null ? 'var(--text-secondary)' : v >= 0 ? '#10b981' : '#ef4444';

  const metrics = [
    { label: '总收益率', value: fmtPct(ret), color: retColor(ret) },
    { label: '年化收益', value: fmtPct(detail?.annual_return), color: retColor(detail?.annual_return) },
    { label: '超额收益', value: fmtPct(detail?.excess_return), color: retColor(detail?.excess_return) },
    { label: '最大回撤', value: pool.max_drawdown != null ? fmtPct(-pool.max_drawdown) : '--', color: pool.max_drawdown != null ? '#ef4444' : 'var(--text-secondary)' },
    { label: 'Sharpe', value: pool.sharpe_ratio != null ? pool.sharpe_ratio.toFixed(2) : '--', color: 'var(--text-primary)' },
    { label: '胜率', value: fmtPct(detail?.win_rate), color: retColor(detail?.win_rate) },
    { label: '盈亏比', value: detail?.profit_loss_ratio != null ? detail.profit_loss_ratio.toFixed(2) : '--', color: 'var(--text-primary)' },
    { label: '均持天数', value: detail?.avg_hold_days != null ? `${Math.round(detail.avg_hold_days)}天` : '--', color: 'var(--text-primary)' },
  ];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '10px', marginTop: '12px' }}>
      {metrics.map((m) => (
        <div key={m.label} style={{ padding: '10px 12px', background: 'var(--bg-canvas)', borderRadius: '6px', border: '1px solid var(--border-subtle)' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>{m.label}</div>
          <div style={{ fontSize: '15px', fontWeight: 600, color: m.color }}>{m.value}</div>
        </div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// PoolCard
// ---------------------------------------------------------------------------

function PoolCard({ pool, onClick }: { pool: SimPool; onClick: () => void }) {
  const st = statusLabel(pool.status);

  return (
    <div
      onClick={onClick}
      style={{
        background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)',
        borderRadius: '8px', padding: '16px', cursor: 'pointer',
        transition: 'border-color 0.15s',
      }}
      onMouseEnter={(e) => (e.currentTarget.style.borderColor = '#3b82f6')}
      onMouseLeave={(e) => (e.currentTarget.style.borderColor = 'var(--border-subtle)')}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
            {strategyLabel(pool.strategy_type)} #{pool.id}
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
            选股日期: {pool.signal_date}
          </div>
        </div>
        <span style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '10px', background: `${st.color}22`, color: st.color, fontWeight: 500 }}>
          {st.text}
        </span>
      </div>
      <MetricsCard pool={pool} />
      <div style={{ marginTop: '10px', fontSize: '11px', color: 'var(--text-muted)' }}>
        初始资金 {fmtMoney(pool.initial_cash)} &nbsp;|&nbsp; 创建 {pool.created_at?.slice(0, 10)}
        {pool.closed_at && ` | 关闭 ${pool.closed_at.slice(0, 10)}`}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SimPoolDetail
// ---------------------------------------------------------------------------

interface Position {
  id: number;
  stock_code: string;
  stock_name: string;
  status: 'open' | 'exited';
  entry_price: number | null;
  current_price: number | null;
  shares: number;
  net_return: number | null;
  exit_reason: string | null;
  entry_date: string | null;
  exit_date: string | null;
  hold_days: number | null;
}

interface NavPoint {
  nav_date: string;
  total_value?: number;
  nav: number;
  benchmark_nav?: number | null;
}

interface TradeLog {
  id: number;
  stock_code: string;
  trade_date: string;
  action: 'buy' | 'sell';
  price: number;
  shares: number;
  amount: number;
  commission: number;
  stamp_tax: number;
  net_amount: number;
  trigger: string;
}

interface Report {
  id: number;
  report_date: string;
  report_type: string;
  metrics: Record<string, unknown> | null;
  created_at: string;
}

type DetailTab = 'overview' | 'positions' | 'reports' | 'trades';

function SimPoolDetail({ poolId, onBack }: { poolId: number; onBack: () => void }) {
  const [pool, setPool] = useState<SimPool | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [navSeries, setNavSeries] = useState<NavPoint[]>([]);
  const [trades, setTrades] = useState<TradeLog[]>([]);
  const [reports, setReports] = useState<Report[]>([]);
  const [expandedReport, setExpandedReport] = useState<number | null>(null);
  const [posFilter, setPosFilter] = useState<'open' | 'exited' | 'all'>('open');
  const [activeTab, setActiveTab] = useState<DetailTab>('overview');
  const [loading, setLoading] = useState(true);
  const [closing, setClosing] = useState(false);

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const [poolRes, posRes, navRes, tradeRes, reportRes] = await Promise.all([
          fetch(`${API_BASE}/api/sim-pool/${poolId}`),
          fetch(`${API_BASE}/api/sim-pool/${poolId}/positions`),
          fetch(`${API_BASE}/api/sim-pool/${poolId}/nav`),
          fetch(`${API_BASE}/api/sim-pool/${poolId}/trades`),
          fetch(`${API_BASE}/api/sim-pool/${poolId}/reports`),
        ]);
        if (poolRes.ok) setPool(await poolRes.json());
        if (posRes.ok) { const d = await posRes.json(); setPositions(d.positions || []); }
        if (navRes.ok) { const d = await navRes.json(); setNavSeries(d.nav || []); }
        if (tradeRes.ok) { const d = await tradeRes.json(); setTrades(d.trades || []); }
        if (reportRes.ok) { const d = await reportRes.json(); setReports(d.reports || []); }
      } catch {}
      setLoading(false);
    };
    load();
  }, [poolId]);

  const finalReport = reports.find((r) => r.report_type === 'final');
  const detailMetrics: DetailMetrics = finalReport?.metrics
    ? {
        annual_return: finalReport.metrics.annual_return as number,
        win_rate: finalReport.metrics.win_rate as number,
        profit_loss_ratio: finalReport.metrics.profit_loss_ratio as number,
        avg_hold_days: finalReport.metrics.avg_hold_days as number,
        excess_return: finalReport.metrics.excess_return as number,
      }
    : {};

  const handleForceClose = async () => {
    if (!confirm('确认强制关闭该模拟池？所有持仓将以当前价格平仓。')) return;
    setClosing(true);
    try {
      const res = await fetch(`${API_BASE}/api/sim-pool/${poolId}/close`, { method: 'POST' });
      if (res.ok) {
        const d = await res.json();
        setPool((prev) => prev ? { ...prev, status: d.status } : prev);
      }
    } catch {}
    setClosing(false);
  };

  const filteredPositions = positions.filter((p) =>
    posFilter === 'all' ? true : p.status === posFilter
  );

  const tabBtnStyle = (active: boolean): React.CSSProperties => ({
    padding: '7px 16px', fontSize: '13px', cursor: 'pointer',
    border: 'none', borderBottom: active ? '2px solid #3b82f6' : '2px solid transparent',
    background: 'transparent',
    color: active ? '#3b82f6' : 'var(--text-tertiary)',
    fontWeight: active ? 510 : 400,
  });

  if (loading) return (
    <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-muted)', fontSize: '13px' }}>加载中...</div>
  );

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
      {/* Back + header */}
      <button onClick={onBack} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-tertiary)', fontSize: '13px', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '4px', padding: 0 }}>
        &larr; 返回列表
      </button>

      {pool && (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
          <div>
            <h2 style={{ fontSize: '17px', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
              {strategyLabel(pool.strategy_type)} #{pool.id}
            </h2>
            <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
              选股日期: {pool.signal_date} &nbsp;|&nbsp;
              <span style={{ color: statusLabel(pool.status).color }}>{statusLabel(pool.status).text}</span>
              {pool.closed_at && ` &nbsp;|&nbsp; 关闭: ${pool.closed_at.slice(0, 10)}`}
            </div>
          </div>
          {pool.status !== 'closed' && (
            <button
              onClick={handleForceClose}
              disabled={closing}
              style={{ padding: '6px 14px', borderRadius: '6px', border: '1px solid #ef4444', background: 'transparent', color: '#ef4444', cursor: closing ? 'not-allowed' : 'pointer', fontSize: '12px', opacity: closing ? 0.6 : 1 }}
            >
              {closing ? '关闭中...' : '强制关闭'}
            </button>
          )}
        </div>
      )}

      {/* Tab navigation */}
      <div style={{ display: 'flex', borderBottom: '1px solid var(--border-subtle)', marginBottom: '16px' }}>
        {([
          { key: 'overview', label: '概览' },
          { key: 'positions', label: `持仓 (${positions.length})` },
          { key: 'reports', label: `报告 (${reports.length})` },
          { key: 'trades', label: `交易记录 (${trades.length})` },
        ] as { key: DetailTab; label: string }[]).map((t) => (
          <button key={t.key} style={tabBtnStyle(activeTab === t.key)} onClick={() => setActiveTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab 1: Overview */}
      {activeTab === 'overview' && pool && (
        <>
          <MetricsCard pool={pool} detail={detailMetrics} />
          {navSeries.length > 0 && (
            <div style={{ marginTop: '16px', background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '16px' }}>
              <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)', marginBottom: '12px' }}>净值走势</div>
              <NavSparkline data={navSeries} />
            </div>
          )}
        </>
      )}

      {/* Tab 2: Positions */}
      {activeTab === 'positions' && (
        <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)', borderRadius: '8px', overflow: 'hidden' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '12px 16px', borderBottom: '1px solid var(--border-subtle)' }}>
            <span style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary)', flex: 1 }}>持仓明细</span>
            {(['open', 'exited', 'all'] as const).map((t) => (
              <button key={t} onClick={() => setPosFilter(t)} style={{
                padding: '4px 10px', borderRadius: '5px', fontSize: '12px', cursor: 'pointer',
                border: '1px solid var(--border-subtle)',
                background: posFilter === t ? '#3b82f6' : 'transparent',
                color: posFilter === t ? '#fff' : 'var(--text-secondary)',
              }}>
                {{ open: '持仓中', exited: '已退出', all: '全部' }[t]}
              </button>
            ))}
          </div>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
              <thead>
                <tr style={{ background: 'var(--bg-canvas)' }}>
                  {['代码', '名称', '状态', '买入价', '当前/退出价', '股数', '净收益率', '退出原因', '买入日', '退出日'].map((h) => (
                    <th key={h} style={{ padding: '8px 12px', textAlign: 'left', color: 'var(--text-muted)', fontWeight: 500, whiteSpace: 'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filteredPositions.length === 0 ? (
                  <tr><td colSpan={10} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>暂无数据</td></tr>
                ) : filteredPositions.map((p) => {
                  const rc = p.net_return == null ? 'var(--text-secondary)' : p.net_return >= 0 ? '#10b981' : '#ef4444';
                  const exitReasonColor: Record<string, string> = {
                    stop_loss: '#ef4444', take_profit: '#10b981',
                    max_hold: '#6b7280', strategy: '#f59e0b',
                  };
                  return (
                    <tr key={p.id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                      <td style={{ padding: '8px 12px', color: 'var(--text-primary)', fontWeight: 500 }}>{p.stock_code}</td>
                      <td style={{ padding: '8px 12px', color: 'var(--text-primary)' }}>{p.stock_name}</td>
                      <td style={{ padding: '8px 12px' }}>
                        <span style={{ fontSize: '11px', padding: '1px 6px', borderRadius: '8px', background: p.status === 'open' ? '#3b82f622' : '#6b728022', color: p.status === 'open' ? '#3b82f6' : '#6b7280' }}>
                          {p.status === 'open' ? '持仓中' : '已退出'}
                        </span>
                      </td>
                      <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>{p.entry_price?.toFixed(2) ?? '--'}</td>
                      <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>{p.current_price?.toFixed(2) ?? '--'}</td>
                      <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>{p.shares?.toLocaleString() ?? '--'}</td>
                      <td style={{ padding: '8px 12px', color: rc, fontWeight: 600 }}>{fmtPct(p.net_return)}</td>
                      <td style={{ padding: '8px 12px' }}>
                        {p.exit_reason ? (
                          <span style={{ fontSize: '11px', color: exitReasonColor[p.exit_reason] || 'var(--text-muted)' }}>
                            {{ stop_loss: '止损', take_profit: '止盈', max_hold: '到期', strategy: '停牌' }[p.exit_reason] || p.exit_reason}
                          </span>
                        ) : '--'}
                      </td>
                      <td style={{ padding: '8px 12px', color: 'var(--text-muted)' }}>{p.entry_date?.slice(0, 10) ?? '--'}</td>
                      <td style={{ padding: '8px 12px', color: 'var(--text-muted)' }}>{p.exit_date?.slice(0, 10) ?? '--'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab 3: Reports */}
      {activeTab === 'reports' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {reports.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-muted)', fontSize: '13px' }}>暂无报告</div>
          ) : reports.map((r) => {
            const typeMap: Record<string, string> = { daily: '日报', weekly: '周报', final: '终报' };
            const isExpanded = expandedReport === r.id;
            return (
              <div key={r.id} style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)', borderRadius: '8px', overflow: 'hidden' }}>
                <div
                  onClick={() => setExpandedReport(isExpanded ? null : r.id)}
                  style={{ display: 'flex', alignItems: 'center', padding: '12px 16px', cursor: 'pointer', gap: '12px' }}
                >
                  <span style={{ fontSize: '11px', padding: '1px 8px', borderRadius: '8px', background: r.report_type === 'final' ? '#10b98122' : '#3b82f622', color: r.report_type === 'final' ? '#10b981' : '#3b82f6' }}>
                    {typeMap[r.report_type] || r.report_type}
                  </span>
                  <span style={{ fontSize: '13px', color: 'var(--text-primary)', flex: 1 }}>{r.report_date}</span>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{isExpanded ? '收起' : '展开'}</span>
                </div>
                {isExpanded && r.metrics && (
                  <div style={{ padding: '0 16px 16px', borderTop: '1px solid var(--border-subtle)' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px', marginTop: '12px' }}>
                      {Object.entries(r.metrics)
                        .filter(([, v]) => typeof v === 'number')
                        .map(([k, v]) => {
                          const isPct = k.includes('return') || k.includes('drawdown') || k.includes('rate');
                          const val = isPct ? fmtPct(v as number) : typeof v === 'number' ? v.toFixed(3) : String(v);
                          const color = isPct && typeof v === 'number' ? (v >= 0 ? '#10b981' : '#ef4444') : 'var(--text-primary)';
                          return (
                            <div key={k} style={{ padding: '8px 10px', background: 'var(--bg-canvas)', borderRadius: '5px' }}>
                              <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '2px' }}>{k}</div>
                              <div style={{ fontSize: '13px', fontWeight: 500, color }}>{val}</div>
                            </div>
                          );
                        })}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Tab 4: Trade log */}
      {activeTab === 'trades' && (
        <div style={{ background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)', borderRadius: '8px', overflow: 'hidden' }}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
              <thead>
                <tr style={{ background: 'var(--bg-canvas)' }}>
                  {['日期', '代码', '操作', '价格', '股数', '成交额', '手续费', '印花税', '净金额', '触发原因'].map((h) => (
                    <th key={h} style={{ padding: '8px 12px', textAlign: 'left', color: 'var(--text-muted)', fontWeight: 500, whiteSpace: 'nowrap' }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {trades.length === 0 ? (
                  <tr><td colSpan={10} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-muted)' }}>暂无交易记录</td></tr>
                ) : trades.map((t) => (
                  <tr key={t.id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                    <td style={{ padding: '8px 12px', color: 'var(--text-muted)' }}>{String(t.trade_date).slice(0, 10)}</td>
                    <td style={{ padding: '8px 12px', color: 'var(--text-primary)', fontWeight: 500 }}>{t.stock_code}</td>
                    <td style={{ padding: '8px 12px' }}>
                      <span style={{ fontSize: '11px', padding: '1px 6px', borderRadius: '8px', background: t.action === 'buy' ? '#3b82f622' : '#ef444422', color: t.action === 'buy' ? '#3b82f6' : '#ef4444' }}>
                        {t.action === 'buy' ? '买入' : '卖出'}
                      </span>
                    </td>
                    <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>{Number(t.price).toFixed(2)}</td>
                    <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>{Number(t.shares).toLocaleString()}</td>
                    <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>{fmtMoney(t.amount)}</td>
                    <td style={{ padding: '8px 12px', color: 'var(--text-muted)' }}>{Number(t.commission).toFixed(2)}</td>
                    <td style={{ padding: '8px 12px', color: 'var(--text-muted)' }}>{Number(t.stamp_tax).toFixed(2)}</td>
                    <td style={{ padding: '8px 12px', color: t.action === 'buy' ? '#ef4444' : '#10b981', fontWeight: 500 }}>
                      {t.action === 'buy' ? '-' : '+'}{fmtMoney(Math.abs(t.net_amount))}
                    </td>
                    <td style={{ padding: '8px 12px', color: 'var(--text-muted)' }}>{t.trigger ?? '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// NavSparkline
// ---------------------------------------------------------------------------

function NavSparkline({ data }: { data: NavPoint[] }) {
  if (data.length < 2) return null;

  const W = 800, H = 120, PADDING = { top: 8, bottom: 24, left: 40, right: 16 };
  const innerW = W - PADDING.left - PADDING.right;
  const innerH = H - PADDING.top - PADDING.bottom;

  const navValues = data.map((d) => d.nav ?? 1.0);
  const minV = Math.min(...navValues);
  const maxV = Math.max(...navValues);
  const range = maxV - minV || 0.01;

  const points = navValues.map((v, i) => ({
    x: PADDING.left + (i / (data.length - 1)) * innerW,
    y: PADDING.top + (1 - (v - minV) / range) * innerH,
  }));

  const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
  const lastNav = navValues[navValues.length - 1];
  const firstNav = navValues[0];
  const color = lastNav >= firstNav ? '#10b981' : '#ef4444';

  const tickDates = [0, Math.floor(data.length / 2), data.length - 1].map((i) => ({
    x: points[i].x,
    label: data[i].nav_date?.slice(5),
  }));

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto' }}>
      <text x={PADDING.left - 4} y={PADDING.top + 4} textAnchor="end" fontSize="9" fill="var(--text-muted)">{maxV.toFixed(3)}</text>
      <text x={PADDING.left - 4} y={PADDING.top + innerH} textAnchor="end" fontSize="9" fill="var(--text-muted)">{minV.toFixed(3)}</text>
      {minV <= 1 && maxV >= 1 && (
        <line
          x1={PADDING.left} y1={PADDING.top + (1 - (1 - minV) / range) * innerH}
          x2={PADDING.left + innerW} y2={PADDING.top + (1 - (1 - minV) / range) * innerH}
          stroke="var(--border-subtle)" strokeDasharray="4,3" strokeWidth={0.8}
        />
      )}
      <path d={pathD} fill="none" stroke={color} strokeWidth={1.5} />
      {tickDates.map((t) => (
        <text key={t.label} x={t.x} y={H - 4} textAnchor="middle" fontSize="9" fill="var(--text-muted)">{t.label}</text>
      ))}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Main Content (exported)
// ---------------------------------------------------------------------------

export default function SimPoolContent() {
  const [pools, setPools] = useState<SimPool[]>([]);
  const [loading, setLoading] = useState(false);
  const [filterStatus, setFilterStatus] = useState<string>('');
  const [filterStrategy, setFilterStrategy] = useState<string>('');
  const [showCreate, setShowCreate] = useState(false);
  const [selectedPoolId, setSelectedPoolId] = useState<number | null>(null);

  const fetchPools = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (filterStatus) params.set('status', filterStatus);
      if (filterStrategy) params.set('strategy_type', filterStrategy);
      const res = await fetch(`${API_BASE}/api/sim-pool?${params}`);
      const data = await res.json();
      setPools(data.pools || []);
    } catch {
      setPools([]);
    } finally {
      setLoading(false);
    }
  }, [filterStatus, filterStrategy]);

  useEffect(() => { fetchPools(); }, [fetchPools]);

  const filterBtnStyle = (active: boolean): React.CSSProperties => ({
    padding: '5px 12px', borderRadius: '6px', fontSize: '12px', cursor: 'pointer',
    border: '1px solid var(--border-subtle)',
    background: active ? '#3b82f6' : 'transparent',
    color: active ? '#fff' : 'var(--text-secondary)',
  });

  return (
    <>
      {showCreate && (
        <CreatePoolModal
          onClose={() => setShowCreate(false)}
          onCreated={fetchPools}
        />
      )}

      {selectedPoolId && (
        <SimPoolDetail
          poolId={selectedPoolId}
          onBack={() => setSelectedPoolId(null)}
        />
      )}

      {!selectedPoolId && (
        <div style={{ maxWidth: '900px', margin: '0 auto' }}>
          {/* Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
            <div>
              <h2 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>
                策略模拟池
              </h2>
              <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: '4px 0 0' }}>
                自动运行的策略回测，无人工干预
              </p>
            </div>
            <button
              onClick={() => setShowCreate(true)}
              style={{ padding: '8px 16px', borderRadius: '6px', border: 'none', background: '#3b82f6', color: '#fff', cursor: 'pointer', fontSize: '13px', fontWeight: 500 }}
            >
              + 创建模拟池
            </button>
          </div>

          {/* Filters */}
          <div style={{ display: 'flex', gap: '6px', marginBottom: '16px', flexWrap: 'wrap' }}>
            {[
              { value: '', label: '全部状态' },
              { value: 'pending', label: '待买入' },
              { value: 'active', label: '运行中' },
              { value: 'closed', label: '已关闭' },
            ].map((f) => (
              <button key={f.value} style={filterBtnStyle(filterStatus === f.value)} onClick={() => setFilterStatus(f.value)}>
                {f.label}
              </button>
            ))}
            <div style={{ width: '1px', background: 'var(--border-subtle)', margin: '0 4px' }} />
            {[
              { value: '', label: '全部策略' },
              { value: 'momentum', label: '动量反转' },
              { value: 'industry', label: '行业轮动' },
              { value: 'micro_cap', label: '微盘股' },
            ].map((f) => (
              <button key={f.value} style={filterBtnStyle(filterStrategy === f.value)} onClick={() => setFilterStrategy(f.value)}>
                {f.label}
              </button>
            ))}
            <button
              onClick={fetchPools}
              style={{ marginLeft: 'auto', padding: '5px 12px', borderRadius: '6px', fontSize: '12px', cursor: 'pointer', border: '1px solid var(--border-subtle)', background: 'transparent', color: 'var(--text-secondary)' }}
            >
              刷新
            </button>
          </div>

          {/* Pool list */}
          {loading ? (
            <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-muted)', fontSize: '13px' }}>加载中...</div>
          ) : pools.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-muted)', fontSize: '13px' }}>
              暂无模拟池，点击右上角创建
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {pools.map((pool) => (
                <PoolCard key={pool.id} pool={pool} onClick={() => setSelectedPoolId(pool.id)} />
              ))}
            </div>
          )}
        </div>
      )}
    </>
  );
}
