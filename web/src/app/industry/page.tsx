'use client';

import { useState, useEffect } from 'react';
import AppShell from '@/components/layout/AppShell';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface RunSummary {
  id: number;
  run_date: string;
  week_label: string | null;
  week_number: number | null;
  week_year: number | null;
  status: string;
  industry_count: number;
  hot_count: number;
  rising_count: number;
  startup_count: number;
  retreat_count: number;
  triggered_at: string;
  finished_at: string | null;
  error_msg: string | null;
}

interface IndustryScore {
  [key: string]: string | number | boolean | null;
}

interface RunDetail extends RunSummary {
  scores: IndustryScore[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const STATUS_LABEL: Record<string, string> = {
  done: '已完成', failed: '失败', running: '执行中', pending: '等待中',
};

const STATUS_COLOR: Record<string, string> = {
  done: '#27a644',
  failed: '#e5534b',
  running: '#c69026',
  pending: '#6e7681',
};

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '-';
  return iso.split('T')[0];
}

function SignalBadge({ label, count, color }: { label: string; count: number; color: string }) {
  if (!count) return null;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '4px',
      padding: '2px 8px', borderRadius: '12px', fontSize: '11px', fontWeight: 510,
      color, background: `${color}18`, border: `1px solid ${color}40`,
      marginRight: '6px',
    }}>
      {label} {count}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Score table for expanded row
// ---------------------------------------------------------------------------

// Signal definition: label, bg color, text color, tooltip
const SIGNAL_DEFS: Record<string, { label: string; bg: string; color: string; tip: string }> = {
  '过热':   { label: '过热',     bg: '#e5534b', color: '#fff', tip: '长期分位>85，年线历史极高位，注意止盈' },
  '降温':   { label: '高位降温', bg: '#e67e22', color: '#fff', tip: '上周过热，本周跌破阈值，趋势可能反转' },
  '长强短弱': { label: '高位退潮', bg: '#c69026', color: '#fff', tip: '年线强但月线动能已失，减仓信号' },
  '连续上升': { label: '持续上升', bg: '#2980b9', color: '#fff', tip: '近3周连续上升≥5分位，趋势跟随' },
  '短强长弱': { label: '趋势启动', bg: '#27a644', color: '#fff', tip: '短期突然发力但历史低位，可能是趋势初期' },
};

function SignalTag({ name }: { name: string }) {
  const def = SIGNAL_DEFS[name];
  if (!def) return null;
  return (
    <span title={def.tip} style={{
      display: 'inline-block',
      padding: '2px 7px',
      borderRadius: '4px',
      fontSize: '11px',
      fontWeight: 600,
      color: def.color,
      background: def.bg,
      marginRight: '4px',
      letterSpacing: '0.2px',
      whiteSpace: 'nowrap',
    }}>
      {def.label}
    </span>
  );
}

function ScoreTable({ scores }: { scores: IndustryScore[] }) {
  if (!scores || scores.length === 0) {
    return <div style={{ padding: '16px', color: 'var(--text-muted)', fontSize: '13px' }}>暂无数据</div>;
  }

  // signal priority order: most severe first
  const signalOrder = ['过热', '降温', '长强短弱', '连续上升', '短强长弱'];

  const sorted = [...scores].sort((a, b) => {
    const lA = Number(a['长期分位'] ?? 0);
    const lB = Number(b['长期分位'] ?? 0);
    return lB - lA;
  });

  function rowBg(row: IndustryScore): string {
    const l = Number(row['长期分位'] ?? 0);
    if (l >= 85) return 'rgba(229,83,75,0.06)';
    if (l >= 50) return 'rgba(39,166,68,0.04)';
    return 'transparent';
  }

  function pctColor(val: number, threshHigh = 85, threshMid = 50): string {
    if (val >= threshHigh) return '#e5534b';
    if (val >= threshMid)  return '#27a644';
    if (val <= 15)          return '#6e7681';
    return 'var(--text-secondary)';
  }

  return (
    <div className="table-scroll">
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', minWidth: '500px' }}>
        <thead>
          <tr style={{ background: 'var(--bg-panel)' }}>
            {['行业', '短期分位', '长期分位', '截面分位', '动量斜率', '信号'].map(c => (
              <th key={c} style={{
                padding: '8px 12px', textAlign: 'left', fontWeight: 510,
                color: 'var(--text-secondary)', borderBottom: '2px solid var(--border-subtle)',
                whiteSpace: 'nowrap',
              }}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => {
            const activeSignals = signalOrder.filter(k => row[k]);
            const longPct  = Number(row['长期分位'] ?? 0);
            const shortPct = Number(row['短期分位'] ?? 0);
            return (
              <tr key={i} style={{ background: rowBg(row) }}>
                <td style={{
                  padding: '8px 12px', fontWeight: 510,
                  color: activeSignals.length ? 'var(--text-primary)' : 'var(--text-secondary)',
                  borderBottom: '1px solid var(--border-subtle)',
                }}>
                  {String(row['行业'] ?? '')}
                </td>
                <td style={{
                  padding: '8px 12px', fontWeight: activeSignals.length ? 510 : 400,
                  color: pctColor(shortPct),
                  borderBottom: '1px solid var(--border-subtle)',
                }}>
                  {row['短期分位'] != null ? Number(row['短期分位']).toFixed(1) : '-'}
                </td>
                <td style={{
                  padding: '8px 12px', fontWeight: 600,
                  color: pctColor(longPct),
                  borderBottom: '1px solid var(--border-subtle)',
                }}>
                  {row['长期分位'] != null ? Number(row['长期分位']).toFixed(1) : '-'}
                </td>
                <td style={{
                  padding: '8px 12px', color: 'var(--text-secondary)',
                  borderBottom: '1px solid var(--border-subtle)',
                }}>
                  {row['截面分位'] != null ? Number(row['截面分位']).toFixed(1) : '-'}
                </td>
                <td style={{
                  padding: '8px 12px', color: 'var(--text-secondary)',
                  borderBottom: '1px solid var(--border-subtle)',
                }}>
                  {row['动量斜率'] != null ? Number(row['动量斜率']).toFixed(2) : '-'}
                </td>
                <td style={{ padding: '8px 12px', borderBottom: '1px solid var(--border-subtle)' }}>
                  {activeSignals.length
                    ? activeSignals.map(k => <SignalTag key={k} name={k} />)
                    : <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>-</span>
                  }
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {/* Legend */}
      <div style={{
        padding: '10px 12px', background: 'var(--bg-panel)',
        borderTop: '1px solid var(--border-subtle)',
        display: 'flex', flexWrap: 'wrap', gap: '12px',
      }}>
        {Object.entries(SIGNAL_DEFS).map(([, def]) => (
          <span key={def.label} style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '11px', color: 'var(--text-muted)' }}>
            <span style={{ display: 'inline-block', padding: '1px 6px', borderRadius: '4px', background: def.bg, color: def.color, fontWeight: 600, fontSize: '10px' }}>{def.label}</span>
            {def.tip}
          </span>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ETF Log Bias card
// ---------------------------------------------------------------------------

interface EtfRow {
  ts_code: string;
  name: string;
  trade_date: string;
  close: number | null;
  log_bias: number | null;
  signal_state: string;
  prev_state: string;
}

interface LogBiasRunStatus {
  id?: number;
  run_date?: string;
  status?: string;
  etf_count?: number;
  triggered_at?: string;
  finished_at?: string | null;
  error_msg?: string | null;
}

const SIGNAL_META: Record<string, { label: string; color: string; bg: string; tip: string }> = {
  overheat: { label: '过热',   color: '#e5534b', bg: 'rgba(229,83,75,0.12)',   tip: 'log_bias > 15，严重高估，注意止盈' },
  breakout: { label: '突破',   color: '#27a644', bg: 'rgba(39,166,68,0.12)',   tip: 'log_bias >= 5，上升突破，可跟进' },
  pullback: { label: '回调',   color: '#2980b9', bg: 'rgba(41,128,185,0.12)',  tip: '突破后 log_bias 回落至 0-5，整理阶段' },
  stall:    { label: '急跌',   color: '#c69026', bg: 'rgba(198,144,38,0.12)',  tip: 'log_bias < -5，急速下跌，冷却期中' },
  normal:   { label: '正常',   color: 'var(--text-muted)', bg: 'var(--bg-tag)', tip: '无明显信号' },
};

function SignalPill({ state }: { state: string }) {
  const meta = SIGNAL_META[state] ?? SIGNAL_META.normal;
  return (
    <span title={meta.tip} style={{
      display: 'inline-block',
      padding: '2px 8px',
      borderRadius: '4px',
      fontSize: '11px',
      fontWeight: 600,
      color: meta.color,
      background: meta.bg,
    }}>
      {meta.label}
    </span>
  );
}

function biasFmt(v: number | null): string {
  if (v == null) return '--';
  return (v >= 0 ? '+' : '') + v.toFixed(2);
}

function biasColor(v: number | null): string {
  if (v == null) return 'var(--text-muted)';
  if (v >= 15) return '#e5534b';
  if (v >= 5)  return '#27a644';
  if (v <= -5) return '#c69026';
  return 'var(--text-secondary)';
}

interface HistoryRow {
  trade_date: string;
  close: number | null;
  log_bias: number | null;
  signal_state: string;
}

// Tiny SVG sparkline for log_bias history
function LogBiasSparkline({ data }: { data: HistoryRow[] }) {
  if (data.length < 2) return <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>数据不足</span>;

  const W = 480;
  const H = 80;
  const PAD = 4;

  const values = data.map(d => d.log_bias ?? 0);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  const toX = (i: number) => PAD + (i / (data.length - 1)) * (W - PAD * 2);
  const toY = (v: number) => PAD + (1 - (v - min) / range) * (H - PAD * 2);

  const zeroY = toY(0);

  // Build polyline points
  const points = data.map((d, i) => `${toX(i)},${toY(d.log_bias ?? 0)}`).join(' ');

  // Signal dots
  const dots = data.filter(d => d.signal_state !== 'normal').map((d, _, arr) => {
    const idx = data.indexOf(d);
    const meta = SIGNAL_META[d.signal_state] ?? SIGNAL_META.normal;
    return { x: toX(idx), y: toY(d.log_bias ?? 0), color: meta.color, label: meta.label, date: d.trade_date };
  });

  // Reference lines at ±5, ±15
  const refLines = [5, 15, -5, -15].map(v => ({ v, y: toY(v), dashed: Math.abs(v) === 15 }));

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: 'block', overflow: 'visible' }}>
        {/* reference lines */}
        {refLines.map(({ v, y, dashed }) => (
          <g key={v}>
            <line x1={PAD} y1={y} x2={W - PAD} y2={y}
              stroke={v > 0 ? '#27a644' : '#e5534b'}
              strokeWidth={0.8}
              strokeDasharray={dashed ? '4 3' : '2 2'}
              opacity={0.5} />
            <text x={W - PAD + 2} y={y + 3} fontSize={8} fill={v > 0 ? '#27a644' : '#e5534b'} opacity={0.7}>{v}</text>
          </g>
        ))}
        {/* zero line */}
        {zeroY >= PAD && zeroY <= H - PAD && (
          <line x1={PAD} y1={zeroY} x2={W - PAD} y2={zeroY}
            stroke="var(--border-subtle)" strokeWidth={1} />
        )}
        {/* log_bias line */}
        <polyline points={points} fill="none" stroke="var(--accent)" strokeWidth={1.5} />
        {/* signal dots */}
        {dots.map((d, i) => (
          <circle key={i} cx={d.x} cy={d.y} r={3} fill={d.color} stroke="#fff" strokeWidth={1}>
            <title>{d.date} {d.label}</title>
          </circle>
        ))}
      </svg>
      <div style={{ display: 'flex', gap: '16px', marginTop: '6px', flexWrap: 'wrap' }}>
        {refLines.map(({ v }) => (
          <span key={v} style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
            {v > 0 ? `+${v}` : v} = {v === 5 ? '突破线' : v === 15 ? '过热线' : v === -5 ? '急跌线' : '深度急跌'}
          </span>
        ))}
      </div>
    </div>
  );
}

function LogBiasCard() {
  const [etfs, setEtfs] = useState<EtfRow[]>([]);
  const [runStatus, setRunStatus] = useState<LogBiasRunStatus>({});
  const [loading, setLoading] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  // collapsed by default
  const [expanded, setExpanded] = useState(false);
  const [expandedEtf, setExpandedEtf] = useState<string | null>(null);
  const [historyData, setHistoryData] = useState<HistoryRow[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  async function loadData() {
    setLoading(true);
    try {
      const [dataRes, statusRes] = await Promise.all([
        fetch(`${API_BASE}/api/industry/log-bias/latest`),
        fetch(`${API_BASE}/api/industry/log-bias/run-status`),
      ]);
      const dataJson = await dataRes.json();
      const statusJson = await statusRes.json();
      setEtfs(dataJson.data || []);
      setRunStatus(statusJson || {});
    } catch {
      // ignore
    } finally {
      setLoading(false);
      setLoaded(true);
    }
  }

  useEffect(() => { loadData(); }, []);

  useEffect(() => {
    if (!runStatus.status || !['pending', 'running'].includes(runStatus.status)) return;
    const timer = setInterval(loadData, 8000);
    return () => clearInterval(timer);
  }, [runStatus.status]);

  async function toggleEtfHistory(tsCode: string) {
    if (expandedEtf === tsCode) {
      setExpandedEtf(null);
      setHistoryData([]);
      return;
    }
    setExpandedEtf(tsCode);
    setHistoryLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/industry/log-bias/history/${tsCode}?days=120`);
      const j = await res.json();
      setHistoryData(j.data || []);
    } finally {
      setHistoryLoading(false);
    }
  }

  async function handleTrigger() {
    setTriggering(true);
    setErrorMsg(null);
    try {
      const res = await fetch(`${API_BASE}/api/industry/log-bias/trigger`, { method: 'POST' });
      if (!res.ok) {
        const j = await res.json();
        setErrorMsg(j.detail || '触发失败');
      } else {
        await loadData();
      }
    } finally {
      setTriggering(false);
    }
  }

  const status = runStatus.status;
  const today = new Date().toISOString().split('T')[0];
  const isToday = runStatus.run_date === today;

  let btnLabel = '触发计算';
  let btnDisabled = triggering;
  let btnColor = 'var(--accent)';
  if (status && isToday) {
    if (status === 'done') {
      btnLabel = '今日已完成'; btnColor = '#27a644'; btnDisabled = true;
    } else if (status === 'running' || status === 'pending') {
      btnLabel = '计算中...'; btnColor = 'var(--text-muted)'; btnDisabled = true;
    } else if (status === 'failed') {
      btnLabel = '重新触发'; btnColor = '#c69026';
    }
  }

  const signalOrder = ['overheat', 'breakout', 'pullback', 'stall', 'normal'];
  const sorted = [...etfs].sort((a, b) => {
    const oa = signalOrder.indexOf(a.signal_state);
    const ob = signalOrder.indexOf(b.signal_state);
    if (oa !== ob) return oa - ob;
    return Math.abs(b.log_bias ?? 0) - Math.abs(a.log_bias ?? 0);
  });

  const tradeDate = etfs[0]?.trade_date ?? '';

  // Summary badges for header
  const signalCounts = sorted.reduce((acc, e) => {
    if (e.signal_state !== 'normal') acc[e.signal_state] = (acc[e.signal_state] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border-subtle)',
      borderRadius: '10px',
      overflow: 'hidden',
    }}>
      {/* Header - always visible, clickable to expand */}
      <div
        onClick={() => setExpanded(e => !e)}
        style={{
          padding: '16px 20px',
          borderBottom: expanded && etfs.length > 0 ? '1px solid var(--border-subtle)' : 'none',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px',
          cursor: 'pointer', userSelect: 'none',
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '15px', fontWeight: 590, color: 'var(--text-primary)' }}>
              ETF 对数乖离率
            </span>
            {tradeDate && (
              <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{tradeDate}</span>
            )}
            {/* signal summary badges */}
            {Object.entries(signalCounts).map(([sig, cnt]) => {
              const m = SIGNAL_META[sig];
              return m ? (
                <span key={sig} style={{
                  fontSize: '11px', padding: '1px 7px', borderRadius: '10px',
                  color: m.color, background: m.bg, fontWeight: 600,
                }}>{m.label} {cnt}</span>
              ) : null;
            })}
            {loaded && etfs.length > 0 && Object.keys(signalCounts).length === 0 && (
              <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>全部正常</span>
            )}
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            12 只行业 ETF 乖离率监控，每日收盘后计算
          </div>
        </div>
        <div style={{ display: 'flex', gap: '8px', flexShrink: 0, alignItems: 'center' }}>
          <button
            onClick={e => { e.stopPropagation(); handleTrigger(); }}
            disabled={btnDisabled}
            style={{
              padding: '5px 14px', borderRadius: '6px', fontSize: '12px', fontWeight: 510,
              background: btnDisabled ? 'transparent' : btnColor,
              border: `1px solid ${btnColor}`,
              color: btnDisabled ? btnColor : '#fff',
              cursor: btnDisabled ? 'not-allowed' : 'pointer',
            }}
          >
            {triggering ? '触发中...' : btnLabel}
          </button>
          <span style={{ fontSize: '16px', color: 'var(--text-muted)', lineHeight: 1 }}>
            {expanded ? '▲' : '▼'}
          </span>
        </div>
      </div>

      {errorMsg && expanded && (
        <div style={{
          margin: '0 20px 12px', padding: '8px 12px', borderRadius: '6px',
          background: 'rgba(229,83,75,0.06)', border: '1px solid rgba(229,83,75,0.2)',
          fontSize: '12px', color: '#e5534b',
        }}>
          {errorMsg}
        </div>
      )}

      {/* Expanded content */}
      {expanded && (
        <>
          {sorted.length > 0 ? (
            <div className="table-scroll">
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', minWidth: '400px' }}>
                <thead>
                  <tr style={{ background: 'var(--bg-panel)' }}>
                    {['ETF', '代码', '收盘', '乖离率', '信号', ''].map((h, i) => (
                      <th key={i} style={{
                        padding: '8px 14px', textAlign: 'left', fontWeight: 510,
                        color: 'var(--text-secondary)',
                        borderBottom: '1px solid var(--border-subtle)',
                        whiteSpace: 'nowrap',
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sorted.map(row => (
                    <React.Fragment key={row.ts_code}>
                      <tr
                        onClick={() => toggleEtfHistory(row.ts_code)}
                        style={{
                          borderBottom: expandedEtf === row.ts_code ? 'none' : '1px solid var(--border-subtle)',
                          cursor: 'pointer',
                          background: expandedEtf === row.ts_code ? 'var(--bg-card-hover)' : 'transparent',
                        }}
                        onMouseEnter={e => { if (expandedEtf !== row.ts_code) (e.currentTarget as HTMLTableRowElement).style.background = 'var(--bg-card-hover)'; }}
                        onMouseLeave={e => { if (expandedEtf !== row.ts_code) (e.currentTarget as HTMLTableRowElement).style.background = 'transparent'; }}
                      >
                        <td style={{ padding: '8px 14px', color: 'var(--text-primary)', fontWeight: 510 }}>
                          {row.name}
                        </td>
                        <td style={{ padding: '8px 14px', color: 'var(--text-muted)', fontFamily: 'var(--font-geist-mono)', fontSize: '11px' }}>
                          {row.ts_code}
                        </td>
                        <td style={{ padding: '8px 14px', color: 'var(--text-secondary)' }}>
                          {row.close != null ? row.close.toFixed(3) : '--'}
                        </td>
                        <td style={{ padding: '8px 14px', fontWeight: 600, color: biasColor(row.log_bias), fontFamily: 'var(--font-geist-mono)' }}>
                          {biasFmt(row.log_bias)}
                        </td>
                        <td style={{ padding: '8px 14px' }}>
                          <SignalPill state={row.signal_state} />
                        </td>
                        <td style={{ padding: '8px 14px', color: 'var(--accent)', fontSize: '11px' }}>
                          {expandedEtf === row.ts_code ? '收起' : '走势'}
                        </td>
                      </tr>
                      {expandedEtf === row.ts_code && (
                        <tr>
                          <td colSpan={6} style={{ padding: '16px 20px', background: 'var(--bg-elevated)', borderBottom: '1px solid var(--border-subtle)' }}>
                            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px', fontWeight: 510 }}>
                              {row.name} · 近120日 log_bias 走势
                            </div>
                            {historyLoading ? (
                              <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>加载中...</div>
                            ) : (
                              <LogBiasSparkline data={historyData} />
                            )}
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  ))}
                </tbody>
              </table>
              {/* Legend */}
              <div style={{
                padding: '10px 14px', background: 'var(--bg-panel)',
                borderTop: '1px solid var(--border-subtle)',
                display: 'flex', flexWrap: 'wrap', gap: '14px',
              }}>
                {Object.entries(SIGNAL_META).filter(([k]) => k !== 'normal').map(([, m]) => (
                  <span key={m.label} style={{ display: 'flex', alignItems: 'center', gap: '5px', fontSize: '11px', color: 'var(--text-muted)' }}>
                    <span style={{ display: 'inline-block', padding: '1px 6px', borderRadius: '4px', background: m.bg, color: m.color, fontWeight: 600, fontSize: '10px' }}>{m.label}</span>
                    {m.tip}
                  </span>
                ))}
              </div>
            </div>
          ) : (
            loaded && (
              <div style={{ padding: '24px', color: 'var(--text-muted)', fontSize: '13px', textAlign: 'center' }}>
                暂无数据，点击「触发计算」生成今日 ETF 乖离率
              </div>
            )
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SW Rotation card
// ---------------------------------------------------------------------------

function SwRotationCard() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  async function loadRuns() {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/industry/sw-rotation/runs?limit=5`);
      const json = await res.json();
      setRuns(json.data || []);
    } catch {
      // ignore
    } finally {
      setLoading(false);
      setLoaded(true);
    }
  }

  // Load on first render
  if (!loaded && !loading) {
    loadRuns();
  }

  async function handleTrigger() {
    setTriggering(true);
    setErrorMsg(null);
    try {
      const res = await fetch(`${API_BASE}/api/industry/sw-rotation/trigger`, { method: 'POST' });
      if (!res.ok) {
        const j = await res.json();
        setErrorMsg(j.detail || '触发失败');
      } else {
        await loadRuns();
        // start polling
        const poll = setInterval(async () => {
          const r2 = await fetch(`${API_BASE}/api/industry/sw-rotation/runs?limit=5`);
          const j2 = await r2.json();
          const latest = (j2.data || [])[0];
          setRuns(j2.data || []);
          if (latest && !['pending', 'running'].includes(latest.status)) {
            clearInterval(poll);
          }
        }, 10000);
      }
    } finally {
      setTriggering(false);
    }
  }

  async function toggleExpand(run: RunSummary) {
    if (expandedId === run.id) {
      setExpandedId(null);
      setDetail(null);
      return;
    }
    setExpandedId(run.id);
    setDetail(null);
    setDetailLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/industry/sw-rotation/runs/${run.id}`);
      const j = await res.json();
      setDetail(j);
    } finally {
      setDetailLoading(false);
    }
  }

  // Derive trigger button state
  const latestRun = runs[0];
  const todayFriday = (() => {
    const d = new Date();
    const daysAhead = (5 - d.getDay() + 7) % 7;
    const fri = new Date(d);
    fri.setDate(d.getDate() + (daysAhead === 0 ? 0 : daysAhead));
    return fri.toISOString().split('T')[0];
  })();
  const isThisWeek = latestRun && latestRun.run_date === todayFriday;

  let btnLabel = '触发执行';
  let btnColor = 'var(--accent)';
  let btnDisabled = triggering;

  if (latestRun) {
    if (!isThisWeek) {
      // last run is from a different week
      btnLabel = triggering ? '触发中...' : '触发本周执行';
    } else if (latestRun.status === 'done') {
      btnLabel = '本周已完成';
      btnColor = '#27a644';
      btnDisabled = true;
    } else if (latestRun.status === 'running' || latestRun.status === 'pending') {
      btnLabel = '执行中...';
      btnColor = 'var(--text-muted)';
      btnDisabled = true;
    } else if (latestRun.status === 'failed') {
      btnLabel = '重新触发';
      btnColor = '#c69026';
    }
  } else {
    btnLabel = triggering ? '触发中...' : '触发执行';
  }

  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border-subtle)',
      borderRadius: '10px',
      overflow: 'hidden',
    }}>
      {/* Card header */}
      <div style={{
        padding: '18px 20px',
        borderBottom: runs.length > 0 ? '1px solid var(--border-subtle)' : 'none',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '16px',
      }}>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '6px' }}>
            <span style={{ fontSize: '15px', fontWeight: 590, color: 'var(--text-primary)' }}>
              每周横截面排名
            </span>
            {latestRun && (
              <span style={{
                fontSize: '11px', padding: '2px 7px', borderRadius: '10px',
                color: STATUS_COLOR[latestRun.status] ?? 'var(--text-muted)',
                background: `${STATUS_COLOR[latestRun.status] ?? '#888'}18`,
                border: `1px solid ${STATUS_COLOR[latestRun.status] ?? '#888'}40`,
              }}>
                {STATUS_LABEL[latestRun.status] ?? latestRun.status}
              </span>
            )}
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            申万31行业 20日/250日历史分位 + 截面排名，每周五收盘后生成
          </div>
          {latestRun?.status === 'done' && latestRun.industry_count > 0 && (
            <div style={{ marginTop: '8px', display: 'flex', flexWrap: 'wrap' }}>
              <SignalBadge label="过热" count={latestRun.hot_count} color="#e5534b" />
              <SignalBadge label="上升" count={latestRun.rising_count} color="#2980b9" />
              <SignalBadge label="启动候选" count={latestRun.startup_count} color="#27a644" />
              <SignalBadge label="退潮" count={latestRun.retreat_count} color="#c69026" />
            </div>
          )}
          {latestRun?.status === 'failed' && latestRun.error_msg && (
            <div style={{
              marginTop: '8px', padding: '8px 12px', borderRadius: '6px',
              background: '#fff1f0', border: '1px solid #e5534b40', fontSize: '12px', color: '#e5534b',
            }}>
              执行失败：{latestRun.error_msg.slice(0, 120)}
              {latestRun.error_msg.length > 120 ? '...' : ''}
              &nbsp;如有问题请联系管理员 zhaobo_1023@163.com
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: '8px', flexShrink: 0, alignItems: 'flex-start' }}>
          <button
            onClick={loadRuns}
            disabled={loading}
            style={{
              padding: '6px 12px', borderRadius: '6px', fontSize: '12px',
              background: 'transparent', border: '1px solid var(--border-subtle)',
              color: 'var(--text-secondary)', cursor: loading ? 'default' : 'pointer',
            }}
          >
            {loading ? '刷新中' : '刷新'}
          </button>
          <button
            onClick={handleTrigger}
            disabled={btnDisabled}
            style={{
              padding: '6px 16px', borderRadius: '6px', fontSize: '12px', fontWeight: 510,
              background: btnDisabled ? 'transparent' : btnColor,
              border: `1px solid ${btnColor}`,
              color: btnDisabled ? btnColor : '#fff',
              cursor: btnDisabled ? 'not-allowed' : 'pointer',
              opacity: btnDisabled && !['本周已完成', '执行中...'].includes(btnLabel) ? 0.6 : 1,
            }}
          >
            {btnLabel}
          </button>
        </div>
      </div>

      {errorMsg && (
        <div style={{
          margin: '0 20px 0', padding: '8px 12px',
          background: '#fff1f0', border: '1px solid #e5534b40',
          borderRadius: '6px', fontSize: '12px', color: '#e5534b',
        }}>
          {errorMsg}
        </div>
      )}

      {/* Run history table */}
      {runs.length > 0 && (
        <div className="table-scroll">
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', minWidth: '520px' }}>
            <thead>
              <tr style={{ background: 'var(--bg-panel)' }}>
                {['日期', '状态', '行业数', '过热', '上升', '启动候选', '退潮', '操作'].map(h => (
                  <th key={h} style={{
                    padding: '7px 14px', textAlign: 'left', fontWeight: 510,
                    color: 'var(--text-secondary)',
                    borderBottom: '1px solid var(--border-subtle)',
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <React.Fragment key={run.id}>
                  <tr style={{ background: expandedId === run.id ? 'var(--bg-panel)' : 'transparent' }}>
                    <td style={{ padding: '7px 14px', color: 'var(--text-secondary)',
                      borderBottom: '1px solid var(--border-subtle)' }}>
                      {run.week_label || fmtDate(run.run_date)}
                    </td>
                    <td style={{ padding: '7px 14px', borderBottom: '1px solid var(--border-subtle)' }}>
                      <span style={{
                        fontSize: '11px', padding: '1px 7px', borderRadius: '10px',
                        color: STATUS_COLOR[run.status] ?? 'var(--text-muted)',
                        background: `${STATUS_COLOR[run.status] ?? '#888'}18`,
                        border: `1px solid ${STATUS_COLOR[run.status] ?? '#888'}40`,
                      }}>
                        {STATUS_LABEL[run.status] ?? run.status}
                      </span>
                    </td>
                    <td style={{ padding: '7px 14px', color: 'var(--text-secondary)',
                      borderBottom: '1px solid var(--border-subtle)' }}>
                      {run.status === 'done' ? run.industry_count : '-'}
                    </td>
                    <td style={{ padding: '7px 14px', color: '#e5534b',
                      borderBottom: '1px solid var(--border-subtle)' }}>
                      {run.status === 'done' ? run.hot_count : '-'}
                    </td>
                    <td style={{ padding: '7px 14px', color: '#2980b9',
                      borderBottom: '1px solid var(--border-subtle)' }}>
                      {run.status === 'done' ? run.rising_count : '-'}
                    </td>
                    <td style={{ padding: '7px 14px', color: '#27a644',
                      borderBottom: '1px solid var(--border-subtle)' }}>
                      {run.status === 'done' ? run.startup_count : '-'}
                    </td>
                    <td style={{ padding: '7px 14px', color: '#c69026',
                      borderBottom: '1px solid var(--border-subtle)' }}>
                      {run.status === 'done' ? run.retreat_count : '-'}
                    </td>
                    <td style={{ padding: '7px 14px', borderBottom: '1px solid var(--border-subtle)' }}>
                      {run.status === 'done' && (
                        <button
                          onClick={() => toggleExpand(run)}
                          style={{
                            fontSize: '11px', color: 'var(--accent)', background: 'none',
                            border: 'none', cursor: 'pointer', padding: '2px 6px',
                          }}
                        >
                          {expandedId === run.id ? '收起' : '展开'}
                        </button>
                      )}
                    </td>
                  </tr>
                  {expandedId === run.id && (
                    <tr>
                      <td colSpan={8} style={{ padding: 0, background: 'var(--bg-canvas)' }}>
                        {detailLoading ? (
                          <div style={{ padding: '16px', color: 'var(--text-muted)', fontSize: '13px' }}>
                            加载中...
                          </div>
                        ) : detail ? (
                          <ScoreTable scores={detail.scores} />
                        ) : null}
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {loaded && runs.length === 0 && (
        <div style={{ padding: '24px', color: 'var(--text-muted)', fontSize: '13px', textAlign: 'center' }}>
          暂无执行记录，点击「触发执行」开始生成本周行业排名
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Industry Stock Screener Card
// ---------------------------------------------------------------------------

interface IndustryStock {
  stock_code: string;
  stock_name: string;
  close: number | null;
  rps_250: number | null;
  rps_120: number | null;
  rps_20: number | null;
  rps_slope: number | null;
  in_pool: boolean;
  trade_date: string;
}

function rpsColor(v: number | null): string {
  if (v == null) return 'var(--text-muted)';
  if (v >= 90) return '#27a644';
  if (v >= 70) return '#5e6ad2';
  if (v < 40)  return '#e5534b';
  return 'var(--text-secondary)';
}

function IndustryStockScreener({ onIndustrySelect }: { onIndustrySelect?: (name: string) => void }) {
  const [industries, setIndustries] = useState<string[]>([]);
  const [selectedIndustry, setSelectedIndustry] = useState('');
  const [minRps, setMinRps] = useState('60');
  const [sortBy, setSortBy] = useState('rps_250');
  const [stocks, setStocks] = useState<IndustryStock[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingIndustries, setLoadingIndustries] = useState(false);
  const [addingCode, setAddingCode] = useState<string | null>(null);
  const [addedCodes, setAddedCodes] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function loadIndustries() {
    if (industries.length > 0) return;
    setLoadingIndustries(true);
    try {
      const res = await fetch(`${API_BASE}/api/candidate-pool/industries`);
      const j = await res.json();
      setIndustries(j.data || []);
    } catch {
      // ignore
    } finally {
      setLoadingIndustries(false);
    }
  }

  async function search() {
    if (!selectedIndustry) return;
    setLoading(true);
    setMsg(null);
    try {
      const params = new URLSearchParams({ industry_name: selectedIndustry, sort_by: sortBy });
      if (minRps) params.set('min_rps', minRps);
      const res = await fetch(`${API_BASE}/api/candidate-pool/industry-stocks?${params}`);
      const j = await res.json();
      setStocks(j.data || []);
      // collect in-pool codes
      const inPool = new Set<string>((j.data || []).filter((s: IndustryStock) => s.in_pool).map((s: IndustryStock) => s.stock_code));
      setAddedCodes(inPool);
    } catch {
      setMsg('查询失败');
    } finally {
      setLoading(false);
    }
  }

  async function addToPool(stock: IndustryStock) {
    setAddingCode(stock.stock_code);
    setMsg(null);
    try {
      const snapshot = {
        rps_250: stock.rps_250,
        rps_120: stock.rps_120,
        close: stock.close,
        industry_name: selectedIndustry,
      };
      const res = await fetch(`${API_BASE}/api/candidate-pool/stocks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          stock_code: stock.stock_code,
          stock_name: stock.stock_name,
          source_type: 'industry',
          source_detail: selectedIndustry,
          entry_snapshot: snapshot,
        }),
      });
      if (res.ok) {
        setAddedCodes(prev => new Set([...prev, stock.stock_code]));
        setMsg(`${stock.stock_name} 已加入候选池`);
      }
    } catch {
      setMsg('加入失败');
    } finally {
      setAddingCode(null);
    }
  }

  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border-subtle)',
      borderRadius: '10px',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div
        onClick={() => { setExpanded(e => !e); if (!expanded) loadIndustries(); }}
        style={{
          padding: '16px 20px', cursor: 'pointer', userSelect: 'none',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px',
        }}
      >
        <div>
          <div style={{ fontSize: '15px', fontWeight: 590, color: 'var(--text-primary)', marginBottom: '3px' }}>
            行业选股
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            选择行业，按 RPS 筛选个股，一键加入候选池
          </div>
        </div>
        <span style={{ fontSize: '16px', color: 'var(--text-muted)' }}>{expanded ? '▲' : '▼'}</span>
      </div>

      {expanded && (
        <>
          {/* Filters */}
          <div style={{
            padding: '12px 20px', borderTop: '1px solid var(--border-subtle)',
            display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'flex-end',
          }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>行业</label>
              <select
                value={selectedIndustry}
                onChange={e => setSelectedIndustry(e.target.value)}
                style={{
                  fontSize: '12px', padding: '6px 10px', borderRadius: '6px',
                  border: '1px solid var(--border-std)', background: 'var(--bg-input)',
                  color: 'var(--text-primary)', minWidth: '120px',
                }}
              >
                <option value=''>选择行业...</option>
                {loadingIndustries && <option disabled>加载中...</option>}
                {industries.map(ind => (
                  <option key={ind} value={ind}>{ind}</option>
                ))}
              </select>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>RPS250 最低</label>
              <input
                type='number'
                value={minRps}
                onChange={e => setMinRps(e.target.value)}
                min={0} max={100} step={5}
                style={{
                  fontSize: '12px', padding: '6px 10px', borderRadius: '6px', width: '80px',
                  border: '1px solid var(--border-std)', background: 'var(--bg-input)',
                  color: 'var(--text-primary)',
                }}
              />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>排序</label>
              <select
                value={sortBy}
                onChange={e => setSortBy(e.target.value)}
                style={{
                  fontSize: '12px', padding: '6px 10px', borderRadius: '6px',
                  border: '1px solid var(--border-std)', background: 'var(--bg-input)',
                  color: 'var(--text-primary)',
                }}
              >
                <option value='rps_250'>RPS250</option>
                <option value='rps_120'>RPS120</option>
                <option value='rps_20'>RPS20</option>
                <option value='rps_slope'>RPS斜率</option>
              </select>
            </div>
            <button
              onClick={search}
              disabled={!selectedIndustry || loading}
              style={{
                fontSize: '12px', padding: '7px 18px', borderRadius: '6px', fontWeight: 510,
                background: !selectedIndustry || loading ? 'transparent' : 'var(--accent)',
                border: `1px solid ${!selectedIndustry || loading ? 'var(--border-subtle)' : 'var(--accent)'}`,
                color: !selectedIndustry || loading ? 'var(--text-muted)' : '#fff',
                cursor: !selectedIndustry || loading ? 'default' : 'pointer',
              }}
            >
              {loading ? '查询中...' : '查询'}
            </button>
          </div>

          {msg && (
            <div style={{ padding: '6px 20px', fontSize: '12px', color: 'var(--accent)' }}>{msg}</div>
          )}

          {/* Results */}
          {stocks.length > 0 && (
            <div className="table-scroll" style={{ borderTop: '1px solid var(--border-subtle)' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', minWidth: '520px' }}>
                <thead>
                  <tr style={{ background: 'var(--bg-panel)' }}>
                    {['代码', '名称', '收盘', 'RPS250', 'RPS120', 'RPS20', 'RPS斜率', '操作'].map(h => (
                      <th key={h} style={{
                        padding: '8px 12px', textAlign: 'left', fontWeight: 510,
                        color: 'var(--text-muted)', fontSize: '11px',
                        borderBottom: '1px solid var(--border-subtle)', whiteSpace: 'nowrap',
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {stocks.map((stock, i) => {
                    const inPool = addedCodes.has(stock.stock_code);
                    const isAdding = addingCode === stock.stock_code;
                    return (
                      <tr
                        key={stock.stock_code}
                        style={{ background: i % 2 === 0 ? 'transparent' : 'var(--bg-card)', borderBottom: '1px solid var(--border-subtle)' }}
                        onMouseEnter={e => { (e.currentTarget as HTMLTableRowElement).style.background = 'var(--bg-card-hover)'; }}
                        onMouseLeave={e => { (e.currentTarget as HTMLTableRowElement).style.background = i % 2 === 0 ? 'transparent' : 'var(--bg-card)'; }}
                      >
                        <td style={{ padding: '8px 12px', fontFamily: 'var(--font-geist-mono)', color: 'var(--text-muted)', fontSize: '11px' }}>{stock.stock_code}</td>
                        <td style={{ padding: '8px 12px', fontWeight: 510, color: 'var(--text-primary)' }}>{stock.stock_name}</td>
                        <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>
                          {stock.close != null ? stock.close.toFixed(2) : '--'}
                        </td>
                        <td style={{ padding: '8px 12px', fontWeight: 600, color: rpsColor(stock.rps_250) }}>
                          {stock.rps_250 != null ? stock.rps_250.toFixed(1) : '--'}
                        </td>
                        <td style={{ padding: '8px 12px', color: rpsColor(stock.rps_120) }}>
                          {stock.rps_120 != null ? stock.rps_120.toFixed(1) : '--'}
                        </td>
                        <td style={{ padding: '8px 12px', color: rpsColor(stock.rps_20) }}>
                          {stock.rps_20 != null ? stock.rps_20.toFixed(1) : '--'}
                        </td>
                        <td style={{ padding: '8px 12px', color: (stock.rps_slope ?? 0) > 0 ? '#27a644' : '#e5534b' }}>
                          {stock.rps_slope != null ? (stock.rps_slope > 0 ? '+' : '') + stock.rps_slope.toFixed(2) : '--'}
                        </td>
                        <td style={{ padding: '8px 12px' }}>
                          {inPool ? (
                            <span style={{ fontSize: '11px', color: '#27a644', fontWeight: 510 }}>已在池</span>
                          ) : (
                            <button
                              onClick={() => addToPool(stock)}
                              disabled={isAdding}
                              style={{
                                fontSize: '11px', padding: '3px 10px', borderRadius: '4px',
                                background: isAdding ? 'transparent' : 'rgba(94,106,210,0.1)',
                                border: '1px solid rgba(94,106,210,0.3)',
                                color: isAdding ? 'var(--text-muted)' : 'var(--accent)',
                                cursor: isAdding ? 'default' : 'pointer', fontWeight: 510,
                              }}
                            >
                              {isAdding ? '加入中...' : '+ 候选池'}
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <div style={{ padding: '8px 12px', background: 'var(--bg-panel)', borderTop: '1px solid var(--border-subtle)', fontSize: '11px', color: 'var(--text-muted)' }}>
                {selectedIndustry} · 共 {stocks.length} 只  · {stocks[0]?.trade_date || ''}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

import React from 'react';

export default function IndustryPage() {
  return (
    <AppShell>
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ fontSize: '20px', fontWeight: 590, color: 'var(--text-primary)',
          letterSpacing: '-0.3px', margin: 0 }}>
          行业
        </h1>
        <p style={{ fontSize: '13px', color: 'var(--text-muted)', margin: '6px 0 0' }}>
          申万一级行业 ETF 走势、每周横截面强弱排名
        </p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {/* ETF log bias card */}
        <LogBiasCard />

        {/* Weekly rotation card */}
        <SwRotationCard />

        {/* Industry stock screener */}
        <IndustryStockScreener />
      </div>
    </AppShell>
  );
}
