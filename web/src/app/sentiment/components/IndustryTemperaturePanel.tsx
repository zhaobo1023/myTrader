'use client';

import React, { useState, useEffect } from 'react';
import apiClient from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || '';

// ---------------------------------------------------------------------------
// Collapsible section wrapper
// ---------------------------------------------------------------------------

function CollapsibleSection({
  title,
  subtitle,
  defaultOpen = false,
  headerRight,
  children,
}: {
  title: string;
  subtitle?: string;
  defaultOpen?: boolean;
  headerRight?: React.ReactNode;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border-subtle)',
      borderRadius: '10px',
      overflow: 'hidden',
    }}>
      <div
        onClick={() => setOpen(o => !o)}
        style={{
          padding: '16px 20px',
          borderBottom: open ? '1px solid var(--border-subtle)' : 'none',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '16px',
          cursor: 'pointer', userSelect: 'none',
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '15px', fontWeight: 590, color: 'var(--text-primary)' }}>{title}</span>
            {subtitle && <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{subtitle}</span>}
          </div>
        </div>
        <div style={{ display: 'flex', gap: '8px', flexShrink: 0, alignItems: 'center' }}>
          {headerRight}
          <span style={{ fontSize: '16px', color: 'var(--text-muted)', lineHeight: 1 }}>
            {open ? '\u25B2' : '\u25BC'}
          </span>
        </div>
      </div>
      {open && children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Industry valuation heatmap
// ---------------------------------------------------------------------------

interface ValuationItem {
  name: string;
  pe_ttm: number | null;
  pe_ttm_med: number | null;
  pb: number | null;
  pe_pct_5y: number | null;
  pb_pct_5y: number | null;
  valuation_score: number | null;
  valuation_label: string;
}

interface ValuationTemperatureResponse {
  date: string;
  items: ValuationItem[];
}

interface IndustryHistoryPoint {
  date: string;
  value: number | null;
}

interface IndustryHistoryResponse {
  industry: string;
  metric: string;
  current: { date: string; value: number | null; valuation_score: number | null; valuation_label: string };
  history: IndustryHistoryPoint[];
  percentile_bands: { p20: number; p50: number; p80: number };
}

function scoreColor(score: number | null): string {
  if (score === null) return 'var(--text-muted)';
  if (score < 30) return '#27a644';
  if (score > 70) return '#e5534b';
  return '#c69026';
}

function scoreBg(score: number | null): string {
  if (score === null) return 'var(--bg-card)';
  if (score < 30) return 'rgba(39,166,68,0.10)';
  if (score > 70) return 'rgba(229,83,75,0.10)';
  return 'rgba(198,144,38,0.10)';
}

function PctBar({ pct }: { pct: number | null }) {
  if (pct === null) return <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>-</span>;
  const pctColor = pct < 0.3 ? '#27a644' : pct > 0.7 ? '#e5534b' : '#c69026';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
      <div style={{ width: '44px', height: '5px', background: 'var(--bg-tag)', borderRadius: '3px', overflow: 'hidden' }}>
        <div style={{ width: `${Math.round(pct * 100)}%`, height: '100%', background: pctColor, borderRadius: '3px' }} />
      </div>
      <span style={{ fontSize: '11px', color: pctColor, fontVariantNumeric: 'tabular-nums' }}>{Math.round(pct * 100)}%</span>
    </div>
  );
}

function MiniLineChart({ history, bands }: { history: IndustryHistoryPoint[]; bands: { p20: number; p50: number; p80: number } }) {
  const vals = history.map(h => h.value).filter((v): v is number => v !== null);
  if (vals.length < 2) return <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>--</div>;

  const W = 320, H = 90;
  const min = Math.min(...vals, bands.p20) * 0.95;
  const max = Math.max(...vals, bands.p80) * 1.05;
  const toY = (v: number) => H - ((v - min) / (max - min)) * H;
  const toX = (i: number) => (i / (history.length - 1)) * W;

  const points = history
    .map((h, i) => h.value !== null ? `${toX(i).toFixed(1)},${toY(h.value).toFixed(1)}` : null)
    .filter(Boolean).join(' ');

  const lineY20 = toY(bands.p20).toFixed(1);
  const lineY50 = toY(bands.p50).toFixed(1);
  const lineY80 = toY(bands.p80).toFixed(1);

  return (
    <svg width={W} height={H} style={{ display: 'block', overflow: 'visible' }}>
      <line x1="0" y1={lineY80} x2={W} y2={lineY80} stroke="#e5534b" strokeWidth="1" strokeDasharray="3 3" opacity="0.5" />
      <line x1="0" y1={lineY50} x2={W} y2={lineY50} stroke="var(--text-muted)" strokeWidth="1" strokeDasharray="3 3" opacity="0.4" />
      <line x1="0" y1={lineY20} x2={W} y2={lineY20} stroke="#27a644" strokeWidth="1" strokeDasharray="3 3" opacity="0.5" />
      <text x={W + 3} y={parseFloat(lineY80) + 4} fontSize="9" fill="#e5534b" opacity="0.7">p80</text>
      <text x={W + 3} y={parseFloat(lineY50) + 4} fontSize="9" fill="var(--text-muted)" opacity="0.7">p50</text>
      <text x={W + 3} y={parseFloat(lineY20) + 4} fontSize="9" fill="#27a644" opacity="0.7">p20</text>
      <polyline points={points} fill="none" stroke="var(--accent)" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function IndustryValuationHeatmapContent() {
  const [expanded, setExpanded] = useState(false);
  const [selectedIndustry, setSelectedIndustry] = useState<string | null>(null);
  const [triggeringValuation, setTriggeringValuation] = useState(false);
  const [triggerMsg, setTriggerMsg] = useState<string | null>(null);

  const { data, isLoading, refetch } = useQuery<ValuationTemperatureResponse>({
    queryKey: ['valuation-temperature'],
    queryFn: () => apiClient.get('/api/analysis/valuation/temperature').then(r => r.data),
    staleTime: 300000,
  });

  const { data: histData, isLoading: histLoading } = useQuery<IndustryHistoryResponse>({
    queryKey: ['valuation-industry-history', selectedIndustry],
    queryFn: () => apiClient.get(`/api/analysis/valuation/industry/${encodeURIComponent(selectedIndustry!)}/history`, { params: { metric: 'pe_ttm', years: 2 } }).then(r => r.data),
    enabled: !!selectedIndustry,
    staleTime: 300000,
  });

  const displayItems = data?.items ?? [];
  const visibleItems = expanded ? displayItems : displayItems.slice(0, 10);

  return (
    <div style={{ padding: '0 20px 18px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px', paddingTop: '4px' }}>
        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>按 5年PE分位 升序，绿=低估 红=高估</span>
        <button
          disabled={triggeringValuation}
          onClick={async () => {
            setTriggeringValuation(true);
            setTriggerMsg(null);
            try {
              const res = await fetch(`${API_BASE}/api/analysis/valuation/trigger`, { method: 'POST' });
              const j = await res.json();
              if (!res.ok) { setTriggerMsg(j.detail || '触发失败'); return; }
              setTriggerMsg(j.message || '计算完成');
              refetch();
            } catch { setTriggerMsg('请求失败'); }
            finally { setTriggeringValuation(false); }
          }}
          style={{
            padding: '4px 10px', borderRadius: '6px', fontSize: '11px', fontWeight: 510,
            background: 'var(--accent)', color: '#fff', border: 'none',
            cursor: triggeringValuation ? 'wait' : 'pointer', opacity: triggeringValuation ? 0.6 : 1,
            marginLeft: 'auto',
          }}
        >
          {triggeringValuation ? '计算中...' : '手动计算'}
        </button>
        {triggerMsg && <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{triggerMsg}</span>}
      </div>

      {isLoading && <div style={{ color: 'var(--text-muted)', fontSize: '13px', padding: '16px 0' }}>加载中...</div>}

      {!isLoading && displayItems.length > 0 && (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '6px' }}>
            {visibleItems.map((item) => (
              <div
                key={item.name}
                onClick={() => setSelectedIndustry(selectedIndustry === item.name ? null : item.name)}
                style={{
                  padding: '9px 10px',
                  borderRadius: '7px',
                  background: scoreBg(item.valuation_score),
                  border: `1px solid ${selectedIndustry === item.name ? scoreColor(item.valuation_score) : 'transparent'}`,
                  cursor: 'pointer',
                  transition: 'all 0.12s',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                  <span style={{ fontSize: '12px', fontWeight: 510, color: 'var(--text-primary)' }}>{item.name}</span>
                  <span style={{ fontSize: '11px', fontWeight: 590, color: scoreColor(item.valuation_score) }}>
                    {item.valuation_score !== null ? item.valuation_score.toFixed(0) : '-'}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>PE {item.pe_ttm !== null ? item.pe_ttm.toFixed(1) : '-'}</span>
                  <PctBar pct={item.pe_pct_5y} />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '2px' }}>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>PB {item.pb !== null ? item.pb.toFixed(2) : '-'}</span>
                  <PctBar pct={item.pb_pct_5y} />
                </div>
              </div>
            ))}
          </div>

          {displayItems.length > 10 && (
            <button
              onClick={() => setExpanded(!expanded)}
              style={{ marginTop: '8px', fontSize: '12px', color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer', padding: '4px 0' }}
            >
              {expanded ? '收起' : `展开全部 ${displayItems.length} 个行业`}
            </button>
          )}

          {selectedIndustry && (
            <div style={{ marginTop: '14px', padding: '14px 16px', background: 'var(--bg-elevated)', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
                <span style={{ fontSize: '13px', fontWeight: 510, color: 'var(--text-primary)' }}>{selectedIndustry} -- PE-TTM 历史（近 2 年）</span>
                {histData?.current && (
                  <span style={{ fontSize: '12px', color: scoreColor(histData.current.valuation_score), background: scoreBg(histData.current.valuation_score), padding: '1px 8px', borderRadius: '10px' }}>
                    {histData.current.valuation_label} · {histData.current.value?.toFixed(1)}x
                  </span>
                )}
                <button onClick={() => setSelectedIndustry(null)} style={{ marginLeft: 'auto', background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '14px' }}>x</button>
              </div>
              {histLoading && <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>加载中...</div>}
              {histData && !histLoading && (
                <div style={{ overflowX: 'auto' }}>
                  <MiniLineChart history={histData.history} bands={histData.percentile_bands} />
                  <div style={{ display: 'flex', gap: '16px', marginTop: '8px', fontSize: '11px', color: 'var(--text-muted)' }}>
                    <span><span style={{ color: '#27a644' }}>p20</span> {histData.percentile_bands.p20?.toFixed(1)}x</span>
                    <span><span style={{ color: 'var(--text-secondary)' }}>p50</span> {histData.percentile_bands.p50?.toFixed(1)}x</span>
                    <span><span style={{ color: '#e5534b' }}>p80</span> {histData.percentile_bands.p80?.toFixed(1)}x</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// SW Rotation types & helpers
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

const SIGNAL_DEFS: Record<string, { label: string; bg: string; color: string; tip: string }> = {
  '过热':   { label: '过热',     bg: '#e5534b', color: '#fff', tip: '长期(250日)分位>=85 且 短期(20日)分位>=60，处于历史极高位且当前仍强势，注意止盈' },
  '降温':   { label: '高位降温', bg: '#e67e22', color: '#fff', tip: '上周长期分位>=85(过热)，本周跌破阈值，趋势可能反转' },
  '长强短弱': { label: '高位退潮', bg: '#c69026', color: '#fff', tip: '长期(250日)分位>=70 但 短期(20日)分位<=35，长期高位但近期动能衰竭，减仓信号' },
  '连续上升': { label: '持续上升', bg: '#2980b9', color: '#fff', tip: '近3周周度分位持续递增且累计升幅>=5个分位点，趋势跟随信号' },
  '短强长弱': { label: '趋势启动', bg: '#27a644', color: '#fff', tip: '短期(20日)分位>=60 但 长期(250日)分位<=40，短期突然发力但历史低位，可能是趋势初期' },
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
    return <div style={{ padding: '16px', color: 'var(--text-muted)', fontSize: '13px' }}>--</div>;
  }

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
    </div>
  );
}

// ---------------------------------------------------------------------------
// SW Rotation Card (content only, wrapped in CollapsibleSection externally)
// ---------------------------------------------------------------------------

function SwRotationCardContent() {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [forceTriggering, setForceTriggering] = useState(false);
  const [showForceConfirm, setShowForceConfirm] = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [showSignalHelp, setShowSignalHelp] = useState(false);

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

  async function handleForceTrigger() {
    setShowForceConfirm(false);
    setForceTriggering(true);
    setErrorMsg(null);
    try {
      const res = await fetch(`${API_BASE}/api/industry/sw-rotation/force-trigger`, { method: 'POST' });
      if (!res.ok) {
        const j = await res.json();
        setErrorMsg(j.detail || '强制触发失败');
      } else {
        await loadRuns();
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
      setForceTriggering(false);
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
    <div>
      {/* Sub-header with description & buttons */}
      <div style={{
        padding: '12px 20px',
        borderBottom: runs.length > 0 ? '1px solid var(--border-subtle)' : 'none',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '16px',
      }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            申万31行业 20日/250日历史分位 + 截面排名，每周五收盘后生成
          </div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px', lineHeight: 1.7 }}>
            <b style={{ color: 'var(--text-secondary)' }}>短期分位</b>: 行业近20日涨跌幅在过去250日中的排名位置 &nbsp;
            <b style={{ color: 'var(--text-secondary)' }}>长期分位</b>: 近250日涨跌幅在过去3年中的排名位置 &nbsp;
            <b style={{ color: 'var(--text-secondary)' }}>截面分位</b>: 当日行业在31个行业中的相对强弱排名
          </div>
          {latestRun?.status === 'done' && latestRun.industry_count > 0 && (
            <div style={{ marginTop: '8px', display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
              <SignalBadge label="过热" count={latestRun.hot_count} color="#e5534b" />
              <SignalBadge label="上升" count={latestRun.rising_count} color="#2980b9" />
              <SignalBadge label="启动候选" count={latestRun.startup_count} color="#27a644" />
              <SignalBadge label="退潮" count={latestRun.retreat_count} color="#c69026" />
            </div>
          )}
          {/* Signal explanation - collapsible */}
          <div style={{ marginTop: '8px' }}>
            <button
              onClick={() => setShowSignalHelp(s => !s)}
              style={{
                background: 'none', border: 'none', cursor: 'pointer', padding: '2px 0',
                fontSize: '11px', color: 'var(--accent)',
              }}
            >
              {showSignalHelp ? '收起信号说明' : '[信号说明]'}
            </button>
            {showSignalHelp && (
              <div style={{
                marginTop: '6px', padding: '10px 14px', borderRadius: '6px',
                background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)',
                display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '6px 16px',
                fontSize: '11px', color: 'var(--text-muted)', lineHeight: 1.6,
              }}>
                {Object.entries(SIGNAL_DEFS).map(([, def]) => (
                  <div key={def.label} style={{ display: 'flex', alignItems: 'baseline', gap: '6px' }}>
                    <span style={{
                      display: 'inline-block', padding: '1px 6px', borderRadius: '4px',
                      background: def.bg, color: def.color, fontWeight: 600, fontSize: '10px',
                      flexShrink: 0,
                    }}>{def.label}</span>
                    <span>{def.tip}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
          {latestRun?.status === 'failed' && latestRun.error_msg && (
            <div style={{
              marginTop: '8px', padding: '8px 12px', borderRadius: '6px',
              background: '#fff1f0', border: '1px solid #e5534b40', fontSize: '12px', color: '#e5534b',
            }}>
              执行失败：{latestRun.error_msg.slice(0, 120)}
              {latestRun.error_msg.length > 120 ? '...' : ''}
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
// CSI Index Log Bias multi-day table card
// ---------------------------------------------------------------------------

interface LogBiasTableRow {
  code: string;
  name: string;
  values: (number | null)[];
  signal_state: string;
}

interface LogBiasTableData {
  dates: string[];
  rows: LogBiasTableRow[];
}

interface HistoryRow {
  trade_date: string;
  close: number | null;
  log_bias: number | null;
  signal_state: string;
}

const SIGNAL_META: Record<string, { label: string; color: string; bg: string; tip: string }> = {
  overheat: { label: '过热',   color: '#e5534b', bg: 'rgba(229,83,75,0.12)',   tip: 'log_bias > 15，严重高估，注意止盈' },
  breakout: { label: '突破',   color: '#27a644', bg: 'rgba(39,166,68,0.12)',   tip: 'log_bias >= 5，上升突破，可跟进' },
  pullback: { label: '回调',   color: '#2980b9', bg: 'rgba(41,128,185,0.12)',  tip: '突破后 log_bias 回落至 0-5，整理阶段' },
  stall:    { label: '急跌',   color: '#c69026', bg: 'rgba(198,144,38,0.12)',  tip: 'log_bias < -5，急速下跌，冷却期中' },
  normal:   { label: '正常',   color: 'var(--text-muted)', bg: 'var(--bg-tag)', tip: '无明显信号' },
};

/** Color a log_bias cell: blue for positive (stronger = deeper), red for negative */
function biasCellBg(v: number | null): string {
  if (v == null) return 'transparent';
  if (v >= 15)  return 'rgba(229,83,75,0.28)';
  if (v >= 10)  return 'rgba(41,128,185,0.25)';
  if (v >= 5)   return 'rgba(41,128,185,0.18)';
  if (v >= 2)   return 'rgba(41,128,185,0.10)';
  if (v > 0)    return 'rgba(41,128,185,0.05)';
  if (v <= -10) return 'rgba(229,83,75,0.22)';
  if (v <= -5)  return 'rgba(229,83,75,0.14)';
  if (v <= -2)  return 'rgba(229,83,75,0.08)';
  if (v < 0)    return 'rgba(229,83,75,0.04)';
  return 'transparent';
}

function biasCellColor(v: number | null): string {
  if (v == null) return 'var(--text-muted)';
  if (v >= 15)  return '#e5534b';
  if (v >= 5)   return '#2563eb';
  if (v <= -5)  return '#e5534b';
  return 'var(--text-secondary)';
}

function biasFmt(v: number | null): string {
  if (v == null) return '--';
  return (v >= 0 ? '+' : '') + v.toFixed(1);
}

// Tiny SVG sparkline for log_bias history
function LogBiasSparkline({ data }: { data: HistoryRow[] }) {
  if (data.length < 2) return <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>数据不足</span>;

  const W = 480;
  const H = 100;
  const PAD_TOP = 4;
  const PAD_BOTTOM = 18;
  const PAD_X = 4;

  const values = data.map(d => d.log_bias ?? 0);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  const toX = (i: number) => PAD_X + (i / (data.length - 1)) * (W - PAD_X * 2);
  const toY = (v: number) => PAD_TOP + (1 - (v - min) / range) * (H - PAD_TOP - PAD_BOTTOM);

  const zeroY = toY(0);
  const chartBottom = H - PAD_BOTTOM;

  const points = data.map((d, i) => `${toX(i)},${toY(d.log_bias ?? 0)}`).join(' ');

  const allDots = data.map((d, i) => ({
    x: toX(i), y: toY(d.log_bias ?? 0),
    date: d.trade_date, value: d.log_bias ?? 0,
    signal: d.signal_state,
  }));

  const signalDots = allDots.filter(d => d.signal !== 'normal').map(d => ({
    ...d, color: (SIGNAL_META[d.signal] ?? SIGNAL_META.normal).color,
    label: (SIGNAL_META[d.signal] ?? SIGNAL_META.normal).label,
  }));

  const refLines = [5, 15, -5, -15].map(v => ({ v, y: toY(v), dashed: Math.abs(v) === 15 }));

  const fmtDt = (d: string) => d.slice(5);
  const dateTicks = [
    { i: 0, label: fmtDt(data[0].trade_date) },
    { i: Math.floor(data.length / 2), label: fmtDt(data[Math.floor(data.length / 2)].trade_date) },
    { i: data.length - 1, label: fmtDt(data[data.length - 1].trade_date) },
  ];

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${W} ${H}`} style={{ display: 'block', overflow: 'visible' }}>
        {refLines.map(({ v, y, dashed }) => (
          <g key={v}>
            <line x1={PAD_X} y1={y} x2={W - PAD_X} y2={y}
              stroke={v > 0 ? '#27a644' : '#e5534b'}
              strokeWidth={0.8}
              strokeDasharray={dashed ? '4 3' : '2 2'}
              opacity={0.5} />
            <text x={W - PAD_X + 2} y={y + 3} fontSize={8} fill={v > 0 ? '#27a644' : '#e5534b'} opacity={0.7}>{v}</text>
          </g>
        ))}
        {zeroY >= PAD_TOP && zeroY <= chartBottom && (
          <line x1={PAD_X} y1={zeroY} x2={W - PAD_X} y2={zeroY}
            stroke="var(--border-subtle)" strokeWidth={1} />
        )}
        <polyline points={points} fill="none" stroke="var(--accent)" strokeWidth={1.5} />
        {allDots.map((d, i) => (
          <circle key={`h-${i}`} cx={d.x} cy={d.y} r={6} fill="transparent" stroke="none">
            <title>{d.date}  {d.value.toFixed(2)}</title>
          </circle>
        ))}
        {signalDots.map((d, i) => (
          <circle key={i} cx={d.x} cy={d.y} r={3} fill={d.color} stroke="#fff" strokeWidth={1}>
            <title>{d.date}  {d.value.toFixed(2)}  {d.label}</title>
          </circle>
        ))}
        {dateTicks.map(({ i, label }) => (
          <text key={i} x={toX(i)} y={H - 2} fontSize={9} fill="var(--text-muted)"
            textAnchor={i === 0 ? 'start' : i === data.length - 1 ? 'end' : 'middle'}>
            {label}
          </text>
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

function LogBiasCardContent() {
  const [tableData, setTableData] = useState<LogBiasTableData | null>(null);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [triggeringEtf, setTriggeringEtf] = useState(false);
  const [triggeringIndex, setTriggeringIndex] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [expandedCode, setExpandedCode] = useState<string | null>(null);
  const [historyData, setHistoryData] = useState<HistoryRow[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);

  async function loadTable() {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/industry/log-bias/table?days=10`);
      const j = await res.json();
      setTableData(j);
    } catch {
      // ignore
    } finally {
      setLoading(false);
      setLoaded(true);
    }
  }

  useEffect(() => { loadTable(); }, []);

  async function handleTriggerEtf() {
    setTriggeringEtf(true);
    setErrorMsg(null);
    try {
      const res = await fetch(`${API_BASE}/api/industry/log-bias/trigger`, { method: 'POST' });
      if (!res.ok) {
        const j = await res.json();
        setErrorMsg(j.detail || 'ETF 触发失败');
      } else {
        setTimeout(loadTable, 3000);
      }
    } finally {
      setTriggeringEtf(false);
    }
  }

  async function handleTriggerIndex() {
    setTriggeringIndex(true);
    setErrorMsg(null);
    try {
      const res = await fetch(`${API_BASE}/api/industry/log-bias/trigger-indices`, { method: 'POST' });
      if (!res.ok) {
        const j = await res.json();
        setErrorMsg(j.detail || '指数触发失败');
      } else {
        setTimeout(loadTable, 5000);
      }
    } finally {
      setTriggeringIndex(false);
    }
  }

  async function toggleHistory(code: string) {
    if (expandedCode === code) {
      setExpandedCode(null);
      setHistoryData([]);
      return;
    }
    setExpandedCode(code);
    setHistoryLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/industry/log-bias/history/${code}?days=120`);
      const j = await res.json();
      setHistoryData(j.data || []);
    } finally {
      setHistoryLoading(false);
    }
  }

  const dates = tableData?.dates ?? [];
  const rows = tableData?.rows ?? [];

  return (
    <div>
      {/* Action bar */}
      <div style={{
        padding: '10px 20px',
        display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap',
        borderBottom: '1px solid var(--border-subtle)',
      }}>
        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
          (ln(close) - EMA(ln(close), 20)) * 100 | 正值蓝(偏强) 负值红(偏弱)
        </span>
        <span style={{ flex: 1 }} />
        <button
          onClick={loadTable}
          disabled={loading}
          style={{
            padding: '4px 10px', borderRadius: '6px', fontSize: '11px',
            background: 'transparent', border: '1px solid var(--border-subtle)',
            color: 'var(--text-secondary)', cursor: loading ? 'default' : 'pointer',
          }}
        >
          {loading ? '刷新中' : '刷新'}
        </button>
        <button
          onClick={handleTriggerEtf}
          disabled={triggeringEtf}
          style={{
            padding: '4px 10px', borderRadius: '6px', fontSize: '11px', fontWeight: 510,
            background: 'var(--accent)', color: '#fff', border: 'none',
            cursor: triggeringEtf ? 'wait' : 'pointer', opacity: triggeringEtf ? 0.6 : 1,
          }}
        >
          {triggeringEtf ? '计算中...' : '更新 ETF'}
        </button>
        <button
          onClick={handleTriggerIndex}
          disabled={triggeringIndex}
          style={{
            padding: '4px 10px', borderRadius: '6px', fontSize: '11px', fontWeight: 510,
            background: '#2563eb', color: '#fff', border: 'none',
            cursor: triggeringIndex ? 'wait' : 'pointer', opacity: triggeringIndex ? 0.6 : 1,
          }}
        >
          {triggeringIndex ? '计算中...' : '更新指数'}
        </button>
      </div>

      {errorMsg && (
        <div style={{
          margin: '8px 20px', padding: '8px 12px', borderRadius: '6px',
          background: 'rgba(229,83,75,0.06)', border: '1px solid rgba(229,83,75,0.2)',
          fontSize: '12px', color: '#e5534b',
        }}>
          {errorMsg}
        </div>
      )}

      {loading && !loaded && (
        <div style={{ padding: '24px', color: 'var(--text-muted)', fontSize: '13px', textAlign: 'center' }}>加载中...</div>
      )}

      {loaded && rows.length === 0 && (
        <div style={{ padding: '24px', color: 'var(--text-muted)', fontSize: '13px', textAlign: 'center' }}>
          暂无数据，点击「更新指数」生成行业对数乖离率
        </div>
      )}

      {rows.length > 0 && (
        <div className="table-scroll">
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', minWidth: `${200 + dates.length * 64}px` }}>
            <thead>
              <tr style={{ background: 'var(--bg-panel)' }}>
                <th style={{
                  padding: '7px 12px', textAlign: 'left', fontWeight: 510,
                  color: 'var(--text-secondary)', borderBottom: '2px solid var(--border-subtle)',
                  position: 'sticky', left: 0, background: 'var(--bg-panel)', zIndex: 1,
                  minWidth: '80px',
                }}>
                  行业
                </th>
                <th style={{
                  padding: '7px 8px', textAlign: 'center', fontWeight: 510,
                  color: 'var(--text-secondary)', borderBottom: '2px solid var(--border-subtle)',
                  minWidth: '44px',
                }}>
                  信号
                </th>
                {dates.map((d, i) => (
                  <th key={i} style={{
                    padding: '7px 4px', textAlign: 'center', fontWeight: 510,
                    color: i === dates.length - 1 ? 'var(--text-primary)' : 'var(--text-muted)',
                    borderBottom: '2px solid var(--border-subtle)',
                    fontSize: '11px', minWidth: '52px',
                  }}>
                    {d}
                  </th>
                ))}
                <th style={{
                  padding: '7px 8px', textAlign: 'center', fontWeight: 510,
                  color: 'var(--text-secondary)', borderBottom: '2px solid var(--border-subtle)',
                  minWidth: '36px',
                }} />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const meta = SIGNAL_META[row.signal_state] ?? SIGNAL_META.normal;
                return (
                  <React.Fragment key={row.code}>
                    <tr>
                      <td style={{
                        padding: '6px 12px', fontWeight: 510, color: 'var(--text-primary)',
                        borderBottom: '1px solid var(--border-subtle)',
                        position: 'sticky', left: 0, background: 'var(--bg-card)', zIndex: 1,
                        whiteSpace: 'nowrap',
                      }}>
                        {row.name}
                      </td>
                      <td style={{
                        padding: '6px 4px', textAlign: 'center',
                        borderBottom: '1px solid var(--border-subtle)',
                      }}>
                        {row.signal_state !== 'normal' && (
                          <span title={meta.tip} style={{
                            display: 'inline-block', padding: '1px 6px', borderRadius: '4px',
                            fontSize: '10px', fontWeight: 600, color: meta.color, background: meta.bg,
                          }}>
                            {meta.label}
                          </span>
                        )}
                      </td>
                      {row.values.map((v, i) => (
                        <td key={i} style={{
                          padding: '6px 4px', textAlign: 'center',
                          borderBottom: '1px solid var(--border-subtle)',
                          background: biasCellBg(v),
                          color: biasCellColor(v),
                          fontWeight: i === dates.length - 1 ? 600 : 400,
                          fontFamily: 'var(--font-geist-mono)',
                          fontSize: '11px',
                        }}>
                          {biasFmt(v)}
                        </td>
                      ))}
                      <td style={{
                        padding: '6px 8px', textAlign: 'center',
                        borderBottom: '1px solid var(--border-subtle)',
                      }}>
                        <button
                          onClick={() => toggleHistory(row.code)}
                          style={{
                            fontSize: '11px', color: 'var(--accent)', background: 'none',
                            border: 'none', cursor: 'pointer', padding: '2px 4px',
                          }}
                        >
                          {expandedCode === row.code ? '收起' : '走势'}
                        </button>
                      </td>
                    </tr>
                    {expandedCode === row.code && (
                      <tr>
                        <td colSpan={dates.length + 3} style={{
                          padding: '16px 20px', background: 'var(--bg-elevated)',
                          borderBottom: '1px solid var(--border-subtle)',
                        }}>
                          <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '8px', fontWeight: 510 }}>
                            {row.name} ({row.code}) -- 近120日 log_bias 走势
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
                );
              })}
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
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Composed panel
// ---------------------------------------------------------------------------

export default function IndustryTemperaturePanel() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <CollapsibleSection title="行业估值温度" defaultOpen={false}>
        <IndustryValuationHeatmapContent />
      </CollapsibleSection>

      <CollapsibleSection
        title="每周横截面排名"
        subtitle="申万31行业"
        defaultOpen={false}
      >
        <SwRotationCardContent />
      </CollapsibleSection>

      <CollapsibleSection
        title="行业对数乖离率"
        subtitle="20EMA 减法版 | 30+ 中证行业主题指数"
        defaultOpen={false}
      >
        <LogBiasCardContent />
      </CollapsibleSection>
    </div>
  );
}
