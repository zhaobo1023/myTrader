'use client';

import React, { useState, useCallback } from 'react';
import apiClient from '@/lib/api-client';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || '';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface StrategyWarning {
  type: 'danger' | 'warning' | 'info';
  title: string;
  body: string;
}

interface PresetStrategyMeta {
  key: string;
  name: string;
  description: string;
  params_desc: string;
  warnings: StrategyWarning[];
}

interface PresetRunSummary {
  id: number;
  run_date: string;
  status: string;
  signal_count: number;
  momentum_count: number;
  reversal_count: number;
  market_status: string;
  market_message: string;
  triggered_at: string;
  finished_at: string | null;
  error_msg: string | null;
}

interface SignalRow {
  stock_code: string;
  stock_name: string;
  signal_type: string;
  rps?: number | null;
  close?: number | null;
  ma20?: number | null;
  ma250?: number | null;
  volume_ratio?: number | null;
  recent_occurrences?: number;
  total_mv?: number | null;
  circ_mv?: number | null;
  pe_ttm?: number | null;
  pb?: number | null;
}

interface PresetRunDetail extends PresetRunSummary {
  signals: SignalRow[];
}

interface PresetStrategyCard {
  meta: PresetStrategyMeta;
  today_run: PresetRunSummary | null;
  recent_runs: PresetRunSummary[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TIMEOUT_HOURS = 3;

function isTimedOut(run: PresetRunSummary): boolean {
  if (run.status !== 'failed' && run.status !== 'running') return false;
  const triggered = new Date(run.triggered_at).getTime();
  return Date.now() - triggered > TIMEOUT_HOURS * 3600 * 1000;
}

const STATUS_LABEL: Record<string, string> = {
  done: '已完成', failed: '失败', running: '执行中', pending: '等待中',
};

function statusBadge(status: string): React.CSSProperties {
  if (status === 'done')    return { color: '#27a644', background: 'rgba(39,166,68,0.1)', padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 510 };
  if (status === 'failed')  return { color: '#e5534b', background: 'rgba(229,83,75,0.1)', padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 510 };
  if (status === 'running') return { color: 'var(--accent)', background: 'rgba(113,112,255,0.1)', padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 510 };
  return { color: 'var(--text-muted)', background: 'var(--bg-tag)', padding: '2px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 510 };
}

function warningBannerStyle(type: string): { container: React.CSSProperties; title: React.CSSProperties; body: React.CSSProperties } {
  if (type === 'danger') return {
    container: { background: 'rgba(229,83,75,0.07)', border: '1px solid rgba(229,83,75,0.25)', borderRadius: '7px', padding: '10px 14px', marginBottom: '8px' },
    title: { color: '#e5534b', fontWeight: 600, fontSize: '12px', marginBottom: '3px' },
    body: { color: 'rgba(229,83,75,0.85)', fontSize: '12px', lineHeight: '1.5' },
  };
  if (type === 'warning') return {
    container: { background: 'rgba(210,161,28,0.08)', border: '1px solid rgba(210,161,28,0.28)', borderRadius: '7px', padding: '10px 14px', marginBottom: '8px' },
    title: { color: '#c79a14', fontWeight: 600, fontSize: '12px', marginBottom: '3px' },
    body: { color: 'rgba(182,142,20,0.9)', fontSize: '12px', lineHeight: '1.5' },
  };
  return {
    container: { background: 'rgba(113,112,255,0.06)', border: '1px solid rgba(113,112,255,0.2)', borderRadius: '7px', padding: '10px 14px', marginBottom: '8px' },
    title: { color: 'var(--accent)', fontWeight: 600, fontSize: '12px', marginBottom: '3px' },
    body: { color: 'rgba(113,112,255,0.8)', fontSize: '12px', lineHeight: '1.5' },
  };
}

function marketBadge(ms: string): React.CSSProperties {
  if (ms === 'bullish') return { color: '#27a644', background: 'rgba(39,166,68,0.1)', padding: '2px 8px', borderRadius: '4px', fontSize: '11px' };
  if (ms === 'bearish') return { color: '#e5534b', background: 'rgba(229,83,75,0.1)', padding: '2px 8px', borderRadius: '4px', fontSize: '11px' };
  if (ms === 'neutral') return { color: '#d2a11c', background: 'rgba(210,161,28,0.1)', padding: '2px 8px', borderRadius: '4px', fontSize: '11px' };
  return { color: 'var(--text-muted)', padding: '2px 8px', fontSize: '11px' };
}

function fmt(v: number | null | undefined, digits = 2): string {
  if (v == null) return '--';
  return v.toFixed(digits);
}

// ---------------------------------------------------------------------------
// Add-to-pool button
// ---------------------------------------------------------------------------

function AddToPoolButton({ sig, strategyName }: { sig: SignalRow; strategyName: string }) {
  const [state, setState] = useState<'idle' | 'confirm' | 'adding' | 'done' | 'error'>('idle');
  const [memo, setMemo] = useState('');

  const doAdd = useCallback(async () => {
    setState('adding');
    try {
      const snapshot: Record<string, unknown> = {
        strategy_name: strategyName,
        close: sig.close,
        rps_250: sig.rps,
        ma20: sig.ma20,
        ma250: sig.ma250,
        volume_ratio: sig.volume_ratio,
        signal_type: sig.signal_type,
      };
      if (sig.total_mv != null) snapshot.total_mv = sig.total_mv;

      await fetch(`${API_BASE}/api/candidate-pool/stocks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          stock_code: sig.stock_code,
          stock_name: sig.stock_name || sig.stock_code,
          source_type: 'strategy',
          source_detail: strategyName,
          entry_snapshot: snapshot,
          memo: memo || null,
        }),
      });
      setState('done');
    } catch {
      setState('error');
    }
  }, [sig, strategyName, memo]);

  if (state === 'done') {
    return <span style={{ fontSize: '11px', color: '#27a644', fontWeight: 510 }}>已加入</span>;
  }
  if (state === 'error') {
    return <span style={{ fontSize: '11px', color: '#e5534b' }}>失败</span>;
  }
  if (state === 'confirm') {
    return (
      <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }} onClick={e => e.stopPropagation()}>
        <input
          value={memo}
          onChange={e => setMemo(e.target.value)}
          placeholder='备注(选填)'
          style={{
            fontSize: '11px', padding: '2px 6px', borderRadius: '4px', width: '100px',
            border: '1px solid var(--border-std)', background: 'var(--bg-input)',
            color: 'var(--text-primary)',
          }}
        />
        <button
          onClick={doAdd}
          style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '4px', background: 'var(--accent)', color: '#fff', border: 'none', cursor: 'pointer' }}
        >
          确认
        </button>
        <button
          onClick={() => setState('idle')}
          style={{ fontSize: '11px', padding: '2px 6px', borderRadius: '4px', background: 'none', border: '1px solid var(--border-subtle)', color: 'var(--text-muted)', cursor: 'pointer' }}
        >
          取消
        </button>
      </div>
    );
  }
  return (
    <button
      onClick={e => { e.stopPropagation(); setState('confirm'); }}
      disabled={state === 'adding'}
      style={{
        fontSize: '11px', padding: '2px 8px', borderRadius: '4px',
        background: 'rgba(94,106,210,0.1)', border: '1px solid rgba(94,106,210,0.3)',
        color: 'var(--accent)', cursor: 'pointer', fontWeight: 510, whiteSpace: 'nowrap',
      }}
    >
      {state === 'adding' ? '加入中...' : '+ 候选池'}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Strategy Card Component
// ---------------------------------------------------------------------------

function StrategyCard({ card }: { card: PresetStrategyCard }) {
  const queryClient = useQueryClient();
  const [expandedRunId, setExpandedRunId] = useState<number | null>(null);
  const [runDetail, setRunDetail] = useState<PresetRunDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [warningsExpanded, setWarningsExpanded] = useState(false);

  const today = new Date().toISOString().split('T')[0];
  const todayRun = card.today_run;

  const triggerMutation = useMutation({
    mutationFn: ({ force = false, runDate }: { force?: boolean; runDate?: string } = {}): Promise<any> => {
      const params = new URLSearchParams();
      if (force) params.set('force', 'true');
      if (runDate) params.set('run_date', runDate);
      return apiClient.post(`/api/strategy/preset/${card.meta.key}/trigger?${params}`).then((r) => r.data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['preset-strategies'] });
    },
    onError: (err: { response?: { data?: { detail?: string } } }) => {
      const msg = err?.response?.data?.detail || '触发失败';
      alert(msg);
    },
  });

  async function toggleExpand(runId: number) {
    if (expandedRunId === runId) {
      setExpandedRunId(null);
      setRunDetail(null);
      return;
    }
    setExpandedRunId(runId);
    setLoadingDetail(true);
    try {
      const res = await apiClient.get(`/api/strategy/preset/${card.meta.key}/runs/${runId}`);
      setRunDetail(res.data);
    } catch {
      setRunDetail(null);
    } finally {
      setLoadingDetail(false);
    }
  }

  function renderTriggerButton() {
    const isPending = triggerMutation.isPending;

    if (isPending) {
      return (
        <button disabled style={btnStyle('gray')}>
          提交中...
        </button>
      );
    }

    if (!todayRun) {
      return (
        <button data-track="strategy_trigger" onClick={() => triggerMutation.mutate({})} style={btnStyle('accent')}>
          触发执行
        </button>
      );
    }

    const { status } = todayRun;

    if (status === 'done') {
      return (
        <div style={{ display: 'flex', gap: '8px' }}>
          <button disabled style={btnStyle('green')}>
            今日已完成
          </button>
          <button
            data-track="strategy_force_trigger"
            onClick={() => triggerMutation.mutate({ force: true })}
            style={{
              ...btnStyle('gray'),
              fontSize: '12px',
              padding: '6px 12px',
            }}
            title="强制重新运行今日任务（即使已完成）"
          >
            强制重新触发
          </button>
        </div>
      );
    }

    if (status === 'pending' || status === 'running') {
      return (
        <button disabled style={btnStyle('gray')}>
          <span style={{ display: 'inline-block', animation: 'spin 1s linear infinite', marginRight: '5px' }}>&#9696;</span>
          执行中...
        </button>
      );
    }

    if (status === 'failed') {
      return (
        <button onClick={() => triggerMutation.mutate({})} style={btnStyle('orange')}>
          重新触发
        </button>
      );
    }

    return null;
  }

  return (
    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: '10px', marginBottom: '20px', overflow: 'hidden' }}>
      {/* Card Header */}
      <div style={{ padding: '18px 20px', borderBottom: '1px solid var(--border-subtle)' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <div style={{ flex: '1 1 200px', minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
              <h2 style={{ fontSize: '16px', fontWeight: 590, color: 'var(--text-primary)', margin: 0 }}>
                {card.meta.name}
              </h2>
              {todayRun && (
                <span style={statusBadge(todayRun.status)}>{STATUS_LABEL[todayRun.status] ?? todayRun.status}</span>
              )}
            </div>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', margin: '0 0 4px' }}>
              {card.meta.description}
            </p>
            <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: 0 }}>
              参数：{card.meta.params_desc}
            </p>
          </div>
          <div style={{ flexShrink: 0 }}>
            {renderTriggerButton()}
          </div>
        </div>

        {/* Warning banners */}
        {card.meta.warnings && card.meta.warnings.length > 0 && (() => {
          const first = card.meta.warnings[0];
          const rest = card.meta.warnings.slice(1);
          const s0 = warningBannerStyle(first.type);
          return (
            <div style={{ marginTop: '14px' }}>
              <div style={{ ...s0.container, marginBottom: rest.length > 0 ? '6px' : '0' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <div style={s0.title}>{first.title}</div>
                  {rest.length > 0 && (
                    <button
                      onClick={() => setWarningsExpanded((v) => !v)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '11px', color: 'var(--text-muted)', padding: '0 2px', flexShrink: 0 }}
                    >
                      {warningsExpanded ? '收起' : '查看更多风险提示'}
                    </button>
                  )}
                </div>
                <div style={s0.body}>{first.body}</div>
              </div>

              {warningsExpanded && rest.map((w, i) => {
                const s = warningBannerStyle(w.type);
                return (
                  <div key={i} style={{ ...s.container, marginBottom: i === rest.length - 1 ? '0' : '6px' }}>
                    <div style={s.title}>{w.title}</div>
                    <div style={s.body}>{w.body}</div>
                  </div>
                );
              })}
            </div>
          );
        })()}

        {/* Today run error */}
        {todayRun?.status === 'failed' && (
          <div style={{ marginTop: '10px', padding: '10px 14px', background: 'rgba(229,83,75,0.06)', border: '1px solid rgba(229,83,75,0.2)', borderRadius: '6px', fontSize: '12px' }}>
            <div style={{ color: '#e5534b', marginBottom: todayRun.error_msg ? '6px' : '0' }}>
              执行失败，可点击「重新触发」重试。
              若问题持续，请联系管理员：
              <a href="mailto:zhaobo_1023@163.com" style={{ color: '#e5534b', textDecoration: 'underline', marginLeft: '4px' }}>
                zhaobo_1023@163.com
              </a>
            </div>
            {todayRun.error_msg && (
              <div style={{ color: 'rgba(229,83,75,0.7)', fontFamily: 'var(--font-geist-mono)', fontSize: '11px', wordBreak: 'break-all', borderTop: '1px solid rgba(229,83,75,0.15)', paddingTop: '6px', marginTop: '2px' }}>
                {todayRun.error_msg}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Recent runs table */}
      {card.recent_runs.length > 0 && (
        <div style={{ padding: '0' }}>
          <div style={{ padding: '12px 20px 8px', fontSize: '12px', color: 'var(--text-muted)', fontWeight: 510 }}>
            最近执行记录
          </div>
          <div className="table-scroll">
          <table style={{ width: '100%', fontSize: '12px', borderCollapse: 'collapse', minWidth: '480px' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-subtle)', borderTop: '1px solid var(--border-subtle)' }}>
                {(card.meta.key === 'microcap_pure_mv'
                  ? ['日期', '状态', '候选数', '交易日', '操作']
                  : ['日期', '状态', '总信号', '动量', '反转', '大盘', '操作']
                ).map((h) => (
                  <th
                    key={h}
                    style={{
                      padding: '7px 12px',
                      textAlign: h === '操作' ? 'right' : 'left',
                      color: 'var(--text-muted)',
                      fontWeight: 400,
                      background: 'var(--bg-card-hover)',
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {card.recent_runs.map((run) => (
                <React.Fragment key={run.id}>
                  <tr
                    style={{
                      borderBottom: expandedRunId === run.id ? 'none' : '1px solid var(--border-subtle)',
                      background: expandedRunId === run.id ? 'var(--bg-card-hover)' : 'transparent',
                      transition: 'background 0.12s',
                    }}
                    onMouseEnter={(e) => {
                      if (expandedRunId !== run.id)
                        (e.currentTarget as HTMLTableRowElement).style.background = 'var(--bg-card-hover)';
                    }}
                    onMouseLeave={(e) => {
                      if (expandedRunId !== run.id)
                        (e.currentTarget as HTMLTableRowElement).style.background = 'transparent';
                    }}
                  >
                    <td style={{ padding: '8px 12px', color: run.run_date === today ? 'var(--text-primary)' : 'var(--text-secondary)', fontWeight: run.run_date === today ? 510 : 400 }}>
                      {run.run_date}
                      {run.run_date === today && <span style={{ marginLeft: '5px', fontSize: '10px', color: 'var(--accent)' }}>今日</span>}
                    </td>
                    <td style={{ padding: '8px 12px' }}>
                      <span style={statusBadge(run.status)}>{STATUS_LABEL[run.status] ?? run.status}</span>
                    </td>
                    <td style={{ padding: '8px 12px', color: 'var(--text-primary)', fontWeight: 510 }}>
                      {run.status === 'done' ? run.signal_count : '--'}
                    </td>
                    {card.meta.key === 'microcap_pure_mv' ? (
                      <td style={{ padding: '8px 12px', color: 'var(--text-secondary)', fontSize: '11px' }}>
                        {run.market_message ? run.market_message.replace('trade_date=', '') : '--'}
                      </td>
                    ) : (
                      <>
                        <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>
                          {run.status === 'done' ? run.momentum_count : '--'}
                        </td>
                        <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>
                          {run.status === 'done' ? run.reversal_count : '--'}
                        </td>
                        <td style={{ padding: '8px 12px' }}>
                          {run.market_status ? (
                            <span style={marketBadge(run.market_status)}>{run.market_status}</span>
                          ) : '--'}
                        </td>
                      </>
                    )}
                    <td style={{ padding: '8px 12px', textAlign: 'right' }}>
                      <div style={{ display: 'flex', gap: '6px', justifyContent: 'flex-end' }}>
                        {(run.status === 'done' || run.status === 'failed') && (
                          <button
                            onClick={() => {
                              if (run.status === 'done') {
                                if (!confirm(`确认重算 ${run.run_date} 的数据？`)) return;
                              }
                              triggerMutation.mutate({ force: true, runDate: run.run_date });
                            }}
                            disabled={triggerMutation.isPending}
                            style={{
                              fontSize: '11px',
                              color: run.status === 'failed' ? '#e5534b' : 'var(--text-muted)',
                              background: 'none',
                              border: 'none',
                              cursor: triggerMutation.isPending ? 'wait' : 'pointer',
                              padding: '2px 6px',
                              borderRadius: '4px',
                            }}
                          >
                            重算
                          </button>
                        )}
                        {run.status === 'done' && (
                          <button
                            onClick={() => toggleExpand(run.id)}
                            style={{
                              fontSize: '11px',
                              color: expandedRunId === run.id ? 'var(--text-muted)' : 'var(--accent)',
                              background: 'none',
                              border: 'none',
                              cursor: 'pointer',
                              padding: '2px 6px',
                              borderRadius: '4px',
                            }}
                          >
                            {expandedRunId === run.id ? '收起' : '展开'}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>

                  {/* Expanded signals detail */}
                  {expandedRunId === run.id && (
                    <tr key={`detail-${run.id}`}>
                      <td colSpan={card.meta.key === 'microcap_pure_mv' ? 5 : 7} style={{ padding: '0', borderBottom: '1px solid var(--border-subtle)' }}>
                        <div style={{ padding: '12px 20px', background: 'var(--bg-elevated)' }}>
                          {loadingDetail && (
                            <div style={{ fontSize: '12px', color: 'var(--text-muted)', padding: '10px 0' }}>加载中...</div>
                          )}
                          {!loadingDetail && runDetail && runDetail.id === run.id && (
                            <>
                              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '8px' }}>
                                {card.meta.key === 'microcap_pure_mv'
                                  ? `持仓候选（${runDetail.signals.length} 只）· ${runDetail.market_message || ''}`
                                  : <>信号明细（{runDetail.signals.length} 只）· 大盘：<span style={marketBadge(runDetail.market_status)}>{runDetail.market_status || '--'}</span>
                                    {runDetail.market_message && <span style={{ marginLeft: '8px', color: 'var(--text-tertiary)' }}>{runDetail.market_message}</span>}
                                  </>
                                }
                              </div>
                              {runDetail.signals.length === 0 ? (
                                <div style={{ fontSize: '12px', color: 'var(--text-muted)', padding: '8px 0' }}>无信号</div>
                              ) : card.meta.key === 'microcap_pure_mv' ? (
                                <div className="table-scroll">
                                  <table style={{ width: '100%', fontSize: '12px', borderCollapse: 'collapse', minWidth: '480px' }}>
                                    <thead>
                                      <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                                        {['#', '代码', '名称', '总市值(亿)', '流通市值(亿)', 'PE-TTM', 'PB'].map((h) => (
                                          <th key={h} style={{ padding: '5px 10px', textAlign: h === '代码' || h === '名称' ? 'left' : 'right', color: 'var(--text-muted)', fontWeight: 400 }}>
                                            {h}
                                          </th>
                                        ))}
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {runDetail.signals.map((sig, idx) => (
                                        <tr
                                          key={`${sig.stock_code}-${idx}`}
                                          style={{ borderBottom: '1px solid var(--border-subtle)' }}
                                          onMouseEnter={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = 'var(--bg-card)'; }}
                                          onMouseLeave={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = 'transparent'; }}
                                        >
                                          <td style={{ padding: '5px 10px', textAlign: 'right', color: 'var(--text-muted)', fontWeight: 400 }}>{idx + 1}</td>
                                          <td style={{ padding: '5px 10px', fontFamily: 'var(--font-geist-mono)', color: 'var(--text-secondary)' }}>{sig.stock_code}</td>
                                          <td style={{ padding: '5px 10px', color: 'var(--text-primary)' }}>{sig.stock_name || '--'}</td>
                                          <td style={{ padding: '5px 10px', textAlign: 'right', color: 'var(--text-primary)', fontWeight: 510 }}>
                                            {sig.total_mv != null ? sig.total_mv.toFixed(2) : '--'}
                                          </td>
                                          <td style={{ padding: '5px 10px', textAlign: 'right', color: 'var(--text-secondary)' }}>
                                            {sig.circ_mv != null ? sig.circ_mv.toFixed(2) : '--'}
                                          </td>
                                          <td style={{ padding: '5px 10px', textAlign: 'right', color: 'var(--text-secondary)' }}>{fmt(sig.pe_ttm, 1)}</td>
                                          <td style={{ padding: '5px 10px', textAlign: 'right', color: 'var(--text-secondary)' }}>{fmt(sig.pb, 2)}</td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              ) : (
                                <div className="table-scroll">
                                  <table style={{ width: '100%', fontSize: '12px', borderCollapse: 'collapse', minWidth: '560px' }}>
                                    <thead>
                                      <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                                        {['代码', '名称', '类型', 'RPS', '收盘', 'MA20', 'MA250', '量比', '5日出现', ''].map((h) => (
                                          <th key={h} style={{ padding: '5px 10px', textAlign: h === '代码' || h === '名称' || h === '类型' || h === '' ? 'left' : 'right', color: 'var(--text-muted)', fontWeight: 400 }}>
                                            {h}
                                          </th>
                                        ))}
                                      </tr>
                                    </thead>
                                    <tbody>
                                      {runDetail.signals.map((sig, idx) => (
                                        <tr
                                          key={`${sig.stock_code}-${idx}`}
                                          style={{ borderBottom: '1px solid var(--border-subtle)' }}
                                          onMouseEnter={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = 'var(--bg-card)'; }}
                                          onMouseLeave={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = 'transparent'; }}
                                        >
                                          <td style={{ padding: '5px 10px', fontFamily: 'var(--font-geist-mono)', color: 'var(--text-secondary)' }}>{sig.stock_code}</td>
                                          <td style={{ padding: '5px 10px', color: 'var(--text-primary)' }}>{sig.stock_name || '--'}</td>
                                          <td style={{ padding: '5px 10px' }}>
                                            <span style={{
                                              fontSize: '10px',
                                              padding: '1px 6px',
                                              borderRadius: '3px',
                                              background: sig.signal_type === 'momentum' ? 'rgba(39,166,68,0.12)' : 'rgba(113,112,255,0.12)',
                                              color: sig.signal_type === 'momentum' ? '#27a644' : 'var(--accent)',
                                            }}>
                                              {sig.signal_type === 'momentum' ? '动量' : '反转'}
                                            </span>
                                          </td>
                                          <td style={{ padding: '5px 10px', textAlign: 'right', color: 'var(--text-secondary)' }}>{fmt(sig.rps ?? null, 1)}</td>
                                          <td style={{ padding: '5px 10px', textAlign: 'right', color: 'var(--text-primary)', fontWeight: 510 }}>{fmt(sig.close ?? null)}</td>
                                          <td style={{ padding: '5px 10px', textAlign: 'right', color: 'var(--text-secondary)' }}>{fmt(sig.ma20 ?? null)}</td>
                                          <td style={{ padding: '5px 10px', textAlign: 'right', color: 'var(--text-secondary)' }}>{fmt(sig.ma250 ?? null)}</td>
                                          <td style={{ padding: '5px 10px', textAlign: 'right', color: (sig.volume_ratio ?? 0) > 1.5 ? '#27a644' : 'var(--text-secondary)' }}>{fmt(sig.volume_ratio ?? null)}</td>
                                          <td style={{ padding: '5px 10px', textAlign: 'right', color: 'var(--text-secondary)' }}>
                                            {(sig.recent_occurrences ?? 0) > 0 ? (
                                              <span style={{
                                                color: (sig.recent_occurrences ?? 0) >= 3 ? '#d0021b' : (sig.recent_occurrences ?? 0) >= 2 ? '#f5a623' : 'var(--text-secondary)',
                                                fontWeight: (sig.recent_occurrences ?? 0) >= 2 ? 600 : 400,
                                              }}>
                                                {sig.recent_occurrences ?? 0}
                                              </span>
                                            ) : '--'}
                                          </td>
                                          <td style={{ padding: '5px 10px' }}>
                                            <AddToPoolButton sig={sig} strategyName={card.meta.name} />
                                          </td>
                                        </tr>
                                      ))}
                                    </tbody>
                                  </table>
                                </div>
                              )}
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
          </div>
        </div>
      )}

      {card.recent_runs.length === 0 && (
        <div style={{ padding: '24px 20px', fontSize: '13px', color: 'var(--text-muted)', textAlign: 'center' }}>
          暂无执行记录，点击「触发执行」开始首次运行
        </div>
      )}
    </div>
  );
}

// Button style helper
function btnStyle(variant: 'accent' | 'gray' | 'green' | 'orange' | 'red'): React.CSSProperties {
  const base: React.CSSProperties = {
    padding: '7px 16px',
    fontSize: '12px',
    fontWeight: 510,
    border: 'none',
    borderRadius: '6px',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    transition: 'opacity 0.12s',
  };
  if (variant === 'accent')  return { ...base, background: 'var(--accent-bg)', color: '#fff' };
  if (variant === 'green')   return { ...base, background: 'rgba(39,166,68,0.15)', color: '#27a644', cursor: 'not-allowed', opacity: 0.8 };
  if (variant === 'orange')  return { ...base, background: 'rgba(210,161,28,0.18)', color: '#c79a14' };
  if (variant === 'red')     return { ...base, background: 'rgba(229,83,75,0.12)', color: '#e5534b', cursor: 'not-allowed', opacity: 0.8 };
  return { ...base, background: 'var(--bg-card-hover)', color: 'var(--text-muted)', cursor: 'not-allowed', opacity: 0.7 };
}

// ---------------------------------------------------------------------------
// StrategyContent (exported)
// ---------------------------------------------------------------------------

export default function StrategyContent() {
  const queryClient = useQueryClient();

  const { data: cards, isLoading, error } = useQuery<PresetStrategyCard[]>({
    queryKey: ['preset-strategies'],
    queryFn: () => apiClient.get('/api/strategy/preset').then((r) => r.data),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      const hasActive = data.some(
        (c) => c.today_run && (c.today_run.status === 'pending' || c.today_run.status === 'running')
      );
      return hasActive ? 10000 : false;
    },
  });

  return (
    <>
      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '24px' }}>
        <h2 style={{ fontSize: '16px', fontWeight: 590, color: 'var(--text-primary)', letterSpacing: '-0.3px', margin: 0 }}>
          预设策略
        </h2>
        <button
          onClick={() => queryClient.invalidateQueries({ queryKey: ['preset-strategies'] })}
          style={{ fontSize: '12px', color: 'var(--text-muted)', background: 'none', border: '1px solid var(--border-subtle)', borderRadius: '6px', padding: '5px 12px', cursor: 'pointer' }}
        >
          刷新
        </button>
      </div>

      {isLoading && (
        <div style={{ fontSize: '13px', color: 'var(--text-muted)', padding: '40px 0', textAlign: 'center' }}>
          加载中...
        </div>
      )}

      {error && (
        <div style={{ fontSize: '13px', color: '#e5534b', padding: '20px', background: 'rgba(229,83,75,0.06)', borderRadius: '8px' }}>
          加载失败，请检查 API 服务
        </div>
      )}

      {cards && cards.map((card) => (
        <StrategyCard key={card.meta.key} card={card} />
      ))}
    </>
  );
}
