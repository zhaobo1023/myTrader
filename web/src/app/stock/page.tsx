'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import AppShell from '@/components/layout/AppShell';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type StockTab = 'comprehensive' | 'technical' | 'fundamental' | 'news';

interface StockOption {
  stock_code: string;
  stock_name: string | null;
}

interface StockCard {
  stock_code: string;
  stock_name: string;
  latest_date: string;
  score: number;
  score_label: string;
  max_severity: string;
  summary: string;
  market_cap: number | null;      // 亿元
  circ_market_cap: number | null;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

const TAB_CONFIG: { key: StockTab; label: string }[] = [
  { key: 'comprehensive', label: '综合分析' },
  { key: 'technical',     label: '技术面分析' },
  { key: 'fundamental',   label: '基本面分析' },
  { key: 'news',          label: '个股动态' },
];

type MarketFilter = 'all' | 'sh' | 'sz';
type CapFilter    = 'all' | 'large' | 'mid' | 'small';

const MARKET_LABELS: Record<MarketFilter, string> = { all: '全部', sh: '沪市', sz: '深市' };
const CAP_LABELS:    Record<CapFilter, string>    = { all: '全部市值', large: '大盘(≥500亿)', mid: '中盘(100-500亿)', small: '小盘(<100亿)' };

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const severityColor = (s: string) => {
  if (s === 'RED')    return '#e5534b';
  if (s === 'YELLOW') return '#c69026';
  if (s === 'GREEN')  return '#27a644';
  return 'var(--text-muted)';
};

const scoreColor = (score: number) =>
  score >= 20 ? '#27a644' : score <= -20 ? '#e5534b' : '#c69026';

function ScoreBadge({ score, label }: { score: number; label: string }) {
  const c = scoreColor(score);
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '5px',
      padding: '2px 9px', borderRadius: '12px', fontSize: '12px', fontWeight: 510,
      color: c, background: `${c}15`, border: `1px solid ${c}40`,
    }}>
      {score > 0 ? '+' : ''}{score} {label}
    </span>
  );
}

function capCategory(market_cap: number | null): CapFilter {
  if (market_cap == null) return 'all';
  if (market_cap >= 500) return 'large';
  if (market_cap >= 100) return 'mid';
  return 'small';
}

function marketCategory(code: string): MarketFilter {
  if (code.endsWith('.SH')) return 'sh';
  if (code.endsWith('.SZ')) return 'sz';
  return 'all';
}

async function mdToHtml(md: string): Promise<string> {
  const { marked } = await import('marked');
  marked.setOptions({ breaks: true });
  return await marked(md);
}

// ---------------------------------------------------------------------------
// Stock search box
// ---------------------------------------------------------------------------

function StockSearchBox({ onSelect, compact }: { onSelect: (s: StockOption) => void; compact?: boolean }) {
  const [kw, setKw] = useState('');
  const [results, setResults] = useState<StockOption[]>([]);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!kw.trim()) { setResults([]); return; }
    const t = setTimeout(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/market/search?keyword=${encodeURIComponent(kw)}&limit=10`);
        const data = await res.json();
        setResults(data.data || []);
      } catch { setResults([]); }
    }, 200);
    return () => clearTimeout(t);
  }, [kw]);

  useEffect(() => {
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);

  return (
    <div ref={ref} style={{ position: 'relative', width: compact ? '220px' : '280px' }}>
      <input
        value={kw}
        onChange={(e) => { setKw(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        placeholder="搜索股票代码或名称"
        style={{
          width: '100%', boxSizing: 'border-box',
          padding: compact ? '6px 10px' : '8px 12px',
          background: 'var(--bg-input)', border: '1px solid var(--border-subtle)',
          borderRadius: '6px', fontSize: '13px', color: 'var(--text-primary)', outline: 'none',
        }}
      />
      {open && results.length > 0 && (
        <div style={{
          position: 'absolute', top: compact ? '32px' : '38px', left: 0, right: 0, zIndex: 300,
          background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)',
          borderRadius: '6px', boxShadow: '0 4px 16px rgba(0,0,0,0.25)',
          maxHeight: '220px', overflowY: 'auto',
        }}>
          {results.map((item) => (
            <div
              key={item.stock_code}
              onClick={() => {
                setKw(`${item.stock_code} ${item.stock_name || ''}`);
                setOpen(false);
                onSelect(item);
              }}
              style={{
                padding: '8px 12px', cursor: 'pointer', fontSize: '13px',
                display: 'flex', justifyContent: 'space-between',
                borderBottom: '1px solid var(--border-subtle)',
              }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-nav-hover)'; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'transparent'; }}
            >
              <span style={{ color: 'var(--text-primary)' }}>{item.stock_name || item.stock_code}</span>
              <span style={{ color: 'var(--text-muted)', fontSize: '12px' }}>{item.stock_code}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stock card grid (home view)
// ---------------------------------------------------------------------------

function StockCardGrid({ onSelect }: { onSelect: (s: StockOption) => void }) {
  const [cards, setCards] = useState<StockCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [marketFilter, setMarketFilter] = useState<MarketFilter>('all');
  const [capFilter, setCapFilter] = useState<CapFilter>('all');

  useEffect(() => {
    fetch(`${API_BASE}/api/analysis/analyzed-stocks`)
      .then((r) => r.json())
      .then((d) => setCards(d.data || []))
      .catch(() => setCards([]))
      .finally(() => setLoading(false));
  }, []);

  const filtered = cards.filter((c) => {
    if (marketFilter !== 'all' && marketCategory(c.stock_code) !== marketFilter) return false;
    if (capFilter !== 'all' && capCategory(c.market_cap) !== capFilter) return false;
    return true;
  });

  return (
    <div>
      {/* Filter bar */}
      <div style={{ display: 'flex', gap: '20px', alignItems: 'center', marginBottom: '18px', flexWrap: 'wrap' }}>
        <FilterPills
          label="市场"
          options={Object.entries(MARKET_LABELS) as [MarketFilter, string][]}
          value={marketFilter}
          onChange={setMarketFilter}
        />
        <FilterPills
          label="市值"
          options={Object.entries(CAP_LABELS) as [CapFilter, string][]}
          value={capFilter}
          onChange={setCapFilter}
        />
        <span style={{ fontSize: '12px', color: 'var(--text-muted)', marginLeft: 'auto' }}>
          {filtered.length} 只股票
        </span>
      </div>

      {loading && (
        <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
          加载中...
        </div>
      )}

      {!loading && filtered.length === 0 && (
        <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
          暂无分析记录，搜索股票开始分析
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: '12px' }}>
        {filtered.map((card) => (
          <div
            key={card.stock_code}
            onClick={() => onSelect({ stock_code: card.stock_code, stock_name: card.stock_name })}
            style={{
              background: 'var(--bg-card)',
              border: `1px solid var(--border-subtle)`,
              borderLeft: `3px solid ${severityColor(card.max_severity)}`,
              borderRadius: '8px', padding: '14px 16px',
              cursor: 'pointer', transition: 'all 0.12s',
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-nav-hover)';
              (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--accent)40';
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-card)';
              (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--border-subtle)';
            }}
          >
            {/* Stock name + code */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
              <div>
                <div style={{ fontSize: '14px', fontWeight: 590, color: 'var(--text-primary)' }}>
                  {card.stock_name}
                </div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>
                  {card.stock_code}
                </div>
              </div>
              <ScoreBadge score={card.score} label={card.score_label} />
            </div>

            {/* Market cap + date */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px', color: 'var(--text-muted)' }}>
              <span>
                {card.market_cap != null ? `${card.market_cap.toFixed(0)}亿` : '-'}
                {' · '}
                {marketCategory(card.stock_code) === 'sh' ? '沪市' : '深市'}
              </span>
              <span>{card.latest_date}</span>
            </div>

            {/* Summary snippet */}
            {card.summary && (
              <div style={{
                marginTop: '8px', fontSize: '12px', color: 'var(--text-muted)',
                overflow: 'hidden', display: '-webkit-box',
                WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
              }}>
                {card.summary}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function FilterPills<T extends string>({
  label, options, value, onChange,
}: {
  label: string;
  options: [T, string][];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
      <span style={{ fontSize: '12px', color: 'var(--text-muted)', flexShrink: 0 }}>{label}</span>
      <div style={{ display: 'flex', gap: '4px' }}>
        {options.map(([v, lbl]) => (
          <button
            key={v}
            onClick={() => onChange(v)}
            style={{
              padding: '3px 10px', borderRadius: '20px', fontSize: '12px', cursor: 'pointer',
              border: `1px solid ${value === v ? 'var(--accent)' : 'var(--border-subtle)'}`,
              background: value === v ? 'rgba(113,112,255,0.1)' : 'transparent',
              color: value === v ? 'var(--accent)' : 'var(--text-secondary)',
              fontWeight: value === v ? 510 : 400,
              transition: 'all 0.1s',
            }}
          >
            {lbl}
          </button>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tab content components
// ---------------------------------------------------------------------------

interface StepItem { step: string; name: string; status: 'pending' | 'running' | 'done'; }

function ReportViewer({ markdown }: { markdown: string }) {
  const [html, setHtml] = useState('');
  useEffect(() => { mdToHtml(markdown).then(setHtml); }, [markdown]);
  return (
    <>
      <style>{`
        .md-body { font-size: 14px; line-height: 1.8; color: var(--text-primary); }
        .md-body h1 { font-size: 18px; font-weight: 650; margin: 20px 0 10px; border-bottom: 1px solid var(--border-subtle); padding-bottom: 6px; }
        .md-body h2 { font-size: 15px; font-weight: 590; margin: 16px 0 8px; }
        .md-body h3 { font-size: 13px; font-weight: 560; margin: 12px 0 5px; color: var(--text-secondary); }
        .md-body p  { margin: 5px 0; color: var(--text-secondary); }
        .md-body ul, .md-body ol { margin: 5px 0 5px 20px; color: var(--text-secondary); }
        .md-body li { margin: 3px 0; }
        .md-body table { width: 100%; border-collapse: collapse; margin: 10px 0; font-size: 13px; }
        .md-body th { background: var(--bg-elevated); padding: 6px 10px; text-align: left; color: var(--text-muted); font-weight: 510; border-bottom: 1px solid var(--border-subtle); }
        .md-body td { padding: 6px 10px; border-bottom: 1px solid var(--border-subtle); color: var(--text-secondary); }
        .md-body blockquote { border-left: 3px solid var(--accent); padding: 6px 12px; margin: 10px 0; background: var(--bg-elevated); color: var(--text-muted); }
        .md-body code { background: var(--bg-elevated); padding: 1px 4px; border-radius: 3px; font-size: 12px; }
        .md-body hr { border: none; border-top: 1px solid var(--border-subtle); margin: 16px 0; }
        .md-body strong { color: var(--text-primary); }
      `}</style>
      <div className="md-body" dangerouslySetInnerHTML={{ __html: html }} />
    </>
  );
}

function ComprehensiveTab({ stock }: { stock: StockOption }) {
  const [generating, setGenerating] = useState(false);
  const [reportId, setReportId] = useState<number | null>(null);
  const [reportDate, setReportDate] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  // Check DB cache on mount / stock change
  useEffect(() => {
    setReportId(null); setReportDate(''); setError('');
    setLoading(true);
    fetch(`${API_BASE}/api/analysis/five-section/today?code=${stock.stock_code}`)
      .then((r) => r.json())
      .then((d) => {
        if (d.exists && d.report) {
          setReportId(d.report.id);
          setReportDate(d.report.report_date || '');
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [stock.stock_code]);

  async function generate() {
    if (generating) return;
    setError('');
    setGenerating(true);
    try {
      const res = await fetch(`${API_BASE}/api/analysis/five-section/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          stock_code: stock.stock_code,
          stock_name: stock.stock_name || stock.stock_code,
        }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || '生成失败'); return; }
      setReportId(data.report_id);
      setReportDate(data.report_date || new Date().toISOString().slice(0, 10));
    } catch (e) { setError(String(e)); }
    finally { setGenerating(false); }
  }

  const hasCached = reportId != null && !generating;
  const reportUrl = reportId ? `${API_BASE}/api/analysis/rag-report-html/${reportId}` : '';

  if (loading) {
    return <div style={{ fontSize: '13px', color: 'var(--text-muted)', padding: '40px 0', textAlign: 'center' }}>加载中...</div>;
  }

  return (
    <div>
      {/* Not yet generated: show generate button */}
      {!hasCached && !generating && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
          <button
            onClick={generate}
            style={{
              padding: '8px 24px', borderRadius: '6px', fontSize: '13px', fontWeight: 510,
              background: 'var(--accent)', color: '#fff', border: 'none', cursor: 'pointer',
            }}
          >
            生成五截面分析报告
          </button>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            技术面 / 资金面 / 基本面 / 情绪面 / 资本周期
          </span>
        </div>
      )}

      {/* Generating */}
      {generating && (
        <div style={{ marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span style={{ fontSize: '13px', color: 'var(--accent)', fontWeight: 510 }}>正在生成五截面分析报告，请稍候...</span>
        </div>
      )}

      {error && (
        <div style={{ marginBottom: '12px', fontSize: '12px', color: '#e5534b', padding: '8px 12px', background: 'rgba(229,83,75,0.08)', borderRadius: '6px' }}>
          {error}
        </div>
      )}

      {/* Report ready: show link + iframe */}
      {hasCached && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              生成日期: {reportDate}
            </span>
            <a
              href={reportUrl}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                padding: '3px 12px', fontSize: '12px', borderRadius: '5px', cursor: 'pointer',
                background: 'var(--accent)', color: '#fff', border: 'none', textDecoration: 'none',
              }}
            >
              在新标签页打开
            </a>
          </div>
          <div style={{
            background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: '8px',
            overflow: 'hidden',
          }}>
            <iframe
              src={reportUrl}
              title="五截面分析报告"
              style={{
                width: '100%', height: '80vh', border: 'none',
                display: 'block',
              }}
            />
          </div>
        </div>
      )}

      {/* Placeholder */}
      {!hasCached && !generating && !error && (
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: '8px',
          padding: '60px 24px', textAlign: 'center',
        }}>
          <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            今日尚未生成五截面分析报告，点击上方按钮开始分析
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Technical tab
// ---------------------------------------------------------------------------

interface TechReport {
  id: number; stock_code: string; stock_name: string; trade_date: string;
  score: number; score_label: string; max_severity: string; summary: string;
  signal_count: number; ma_pattern?: string; has_html?: boolean;
  signals: { name: string; level: string; description: string }[];
  indicators: Record<string, number | null>;
}

function TechReportList({ reports, latestDate }: { reports: TechReport[]; latestDate: string }) {
  const [expandedId, setExpandedId] = useState<number | null>(null);

  if (reports.length === 0) return null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
      {reports.map((rep) => {
        const isExpanded = expandedId === rep.id;
        return (
          <div key={rep.id} style={{
            background: 'var(--bg-card)', borderRadius: '8px', overflow: 'hidden',
            border: '1px solid var(--border-subtle)',
            borderLeft: `3px solid ${severityColor(rep.max_severity)}`,
          }}>
            {/* Header row */}
            <div
              onClick={() => setExpandedId(isExpanded ? null : rep.id)}
              style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', cursor: 'pointer' }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-nav-hover)'; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'transparent'; }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '13px', fontWeight: 510, color: 'var(--text-primary)' }}>
                  {rep.trade_date}
                  {rep.trade_date === latestDate && (
                    <span style={{ marginLeft: '6px', fontSize: '10px', color: 'var(--accent)' }}>最新</span>
                  )}
                </span>
                <ScoreBadge score={rep.score} label={rep.score_label} />
                {rep.ma_pattern && (
                  <span style={{ fontSize: '11px', color: 'var(--text-secondary)', background: 'var(--bg-elevated)', padding: '1px 6px', borderRadius: '4px' }}>
                    {rep.ma_pattern}
                  </span>
                )}
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                {rep.has_html && (
                  <a
                    href={`${API_BASE}/api/analysis/report-html/${rep.id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={(e) => e.stopPropagation()}
                    style={{
                      padding: '2px 10px', fontSize: '11px', borderRadius: '4px', cursor: 'pointer',
                      background: 'var(--accent)', color: '#fff',
                      border: '1px solid var(--accent)',
                      textDecoration: 'none', display: 'inline-block',
                    }}
                  >
                    完整报告
                  </a>
                )}
                <span style={{ fontSize: '11px', color: 'var(--accent)' }}>{isExpanded ? '收起' : '展开'}</span>
              </div>
            </div>

            {/* Summary */}
            <div style={{ padding: '0 16px 10px', fontSize: '12px', color: 'var(--text-muted)' }}>{rep.summary}</div>

            {/* Signal list */}
            {isExpanded && rep.signals && rep.signals.length > 0 && (
              <div style={{ padding: '0 16px 16px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                {rep.signals.map((sig, i) => (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'center', gap: '8px',
                    padding: '5px 8px', background: 'var(--bg-elevated)', borderRadius: '5px', fontSize: '12px',
                  }}>
                    <span style={{ padding: '1px 6px', borderRadius: '3px', fontSize: '11px', fontWeight: 600, color: severityColor(sig.level), background: `${severityColor(sig.level)}18` }}>{sig.level}</span>
                    <span style={{ fontWeight: 510, color: 'var(--text-primary)', minWidth: '80px' }}>{sig.name}</span>
                    <span style={{ color: 'var(--text-secondary)' }}>{sig.description}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Key indicators */}
            {isExpanded && rep.indicators && Object.keys(rep.indicators).length > 0 && (
              <div style={{ padding: '0 16px 16px' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 510, marginBottom: '6px' }}>关键指标</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '6px' }}>
                  {Object.entries(rep.indicators).slice(0, 16).map(([k, v]) => (
                    <div key={k} style={{ background: 'var(--bg-elevated)', padding: '5px 8px', borderRadius: '5px' }}>
                      <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '2px' }}>{k}</div>
                      <div style={{ fontSize: '12px', color: 'var(--text-primary)', fontWeight: 510 }}>
                        {v != null ? Number(v).toFixed(3) : '--'}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function TechnicalTab({ stock }: { stock: StockOption }) {
  const [reports, setReports] = useState<TechReport[]>([]);
  const [loading, setLoading] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [latestDate, setLatestDate] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    setReports([]); setError(''); setLoading(true);
    Promise.all([
      fetch(`${API_BASE}/api/analysis/reports/by-stock?code=${stock.stock_code}&days=3`).then((r) => r.json()),
      fetch(`${API_BASE}/api/market/latest-date`).then((r) => r.json()),
    ]).then(([reps, ld]) => {
      setReports(Array.isArray(reps) ? reps : []);
      setLatestDate(ld.latest_date || '');
    }).catch(() => setError('加载失败')).finally(() => setLoading(false));
  }, [stock.stock_code]);

  const hasLatest = reports.some((r) => r.trade_date === latestDate);

  async function generate() {
    setGenerating(true); setError('');
    try {
      const res = await fetch(`${API_BASE}/api/analysis/reports/generate`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stock_code: stock.stock_code, stock_name: stock.stock_name || '' }),
      });
      const data = await res.json();
      if (!res.ok) { setError(data.detail || '生成失败'); return; }
      setReports((p) => [data.report, ...p.filter((r) => r.trade_date !== data.report.trade_date)]);
    } catch (e) { setError(String(e)); }
    finally { setGenerating(false); }
  }

  if (loading) return <div style={{ fontSize: '13px', color: 'var(--text-muted)', padding: '30px 0' }}>加载中...</div>;

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
        {latestDate && !hasLatest && (
          <button onClick={generate} disabled={generating} style={{
            padding: '6px 16px', fontSize: '12px', fontWeight: 510, borderRadius: '6px', border: 'none',
            background: generating ? 'transparent' : 'var(--accent)',
            color: generating ? 'var(--text-muted)' : '#fff',
            cursor: generating ? 'not-allowed' : 'pointer',
          }}>
            {generating ? '生成中...' : `生成 ${latestDate} 报告`}
          </button>
        )}
        {error && <span style={{ fontSize: '12px', color: '#e5534b' }}>{error}</span>}
      </div>

      {reports.length === 0 && !generating && (
        <div style={{ fontSize: '13px', color: 'var(--text-muted)', padding: '20px 0' }}>
          近3天暂无报告{latestDate && !hasLatest ? '，点击上方按钮生成' : ''}
        </div>
      )}

      <TechReportList reports={reports} latestDate={latestDate} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Fundamental tab (five-step fundamental report, mirrors ComprehensiveTab)
// ---------------------------------------------------------------------------

function FundamentalTab({ stock }: { stock: StockOption }) {
  const [steps, setSteps] = useState<StepItem[]>([]);
  const [generating, setGenerating] = useState(false);
  const [reportContent, setReportContent] = useState('');
  const [reportDate, setReportDate] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  // Check DB cache on mount / stock change
  useEffect(() => {
    setReportContent(''); setReportDate(''); setError(''); setSteps([]);
    setLoading(true);
    fetch(`${API_BASE}/api/analysis/comprehensive/today?code=${stock.stock_code}&report_type=fundamental`)
      .then((r) => r.json())
      .then((d) => {
        if (d.exists && d.report) {
          setReportContent(d.report.content || '');
          setReportDate(d.report.report_date || '');
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [stock.stock_code]);

  async function generate() {
    if (generating) return;
    setError(''); setSteps([]);
    setGenerating(true);
    try {
      const res = await fetch(`${API_BASE}/api/analysis/comprehensive/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          stock_code: stock.stock_code,
          stock_name: stock.stock_name || stock.stock_code,
          report_type: 'fundamental',
        }),
      });
      if (!res.ok || !res.body) { setError(`请求失败: ${res.status}`); setGenerating(false); return; }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() || '';
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const ev = JSON.parse(line.slice(6));
            if (ev.type === 'cached') {
              setReportContent(ev.report?.content || '');
              setReportDate(ev.report?.report_date || '');
            } else if (ev.type === 'plan') {
              setSteps((ev.sections as string[]).map((name: string, i: number) => ({ step: `s${i}`, name, status: 'pending' })));
            } else if (ev.type === 'step_start') {
              setSteps((p) => p.map((s) => s.name === ev.name ? { ...s, status: 'running' } : s));
            } else if (ev.type === 'step_done') {
              setSteps((p) => p.map((s) => s.name === ev.name ? { ...s, status: 'done' } : s));
            } else if (ev.type === 'done') {
              setReportContent(ev.content || '');
              setReportDate(new Date().toISOString().slice(0, 10));
            } else if (ev.type === 'error') {
              setError(ev.message || '生成失败');
            }
          } catch { /* skip */ }
        }
      }
    } catch (e) { setError(String(e)); }
    finally { setGenerating(false); }
  }

  const hasCached = !!reportContent && !generating;

  if (loading) {
    return <div style={{ fontSize: '13px', color: 'var(--text-muted)', padding: '40px 0', textAlign: 'center' }}>加载中...</div>;
  }

  return (
    <div>
      {/* Not yet generated: show generate button */}
      {!hasCached && !generating && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
          <button
            onClick={generate}
            style={{
              padding: '8px 24px', borderRadius: '6px', fontSize: '13px', fontWeight: 510,
              background: 'var(--accent)', color: '#fff', border: 'none', cursor: 'pointer',
            }}
          >
            生成基本面研报
          </button>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            五步法深度分析: 财报发现 / 驱动逻辑 / 估值偏差 / 催化剂 / 风险建议
          </span>
        </div>
      )}

      {/* Generating: show step progress */}
      {generating && (
        <div style={{ marginBottom: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
            <span style={{ fontSize: '13px', color: 'var(--accent)', fontWeight: 510 }}>正在生成...</span>
          </div>
          {steps.length > 0 && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
              {steps.map((s) => (
                <span key={s.step} style={{
                  fontSize: '11px', padding: '3px 10px', borderRadius: '10px',
                  color: s.status === 'done' ? '#27a644' : s.status === 'running' ? 'var(--accent)' : 'var(--text-muted)',
                  background: s.status === 'done' ? 'rgba(39,166,68,0.1)' : s.status === 'running' ? 'rgba(113,112,255,0.1)' : 'var(--bg-elevated)',
                  border: `1px solid ${s.status === 'done' ? 'rgba(39,166,68,0.3)' : s.status === 'running' ? 'rgba(113,112,255,0.3)' : 'var(--border-subtle)'}`,
                  fontWeight: s.status === 'running' ? 510 : 400,
                }}>
                  {s.status === 'done' ? 'v ' : s.status === 'running' ? '... ' : ''}{s.name}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {error && (
        <div style={{ marginBottom: '12px', fontSize: '12px', color: '#e5534b', padding: '8px 12px', background: 'rgba(229,83,75,0.08)', borderRadius: '6px' }}>
          {error}
        </div>
      )}

      {/* Report content */}
      {hasCached && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
              生成日期: {reportDate}
            </span>
            <button
              onClick={() => {
                const b = new Blob([reportContent], { type: 'text/markdown' });
                const u = URL.createObjectURL(b);
                const a = document.createElement('a');
                a.href = u; a.download = `${stock.stock_code}_fundamental_${reportDate}.md`; a.click();
                URL.revokeObjectURL(u);
              }}
              style={{ fontSize: '12px', color: 'var(--accent)', background: 'none', border: '1px solid var(--accent)', borderRadius: '5px', padding: '3px 10px', cursor: 'pointer' }}
            >
              下载 .md
            </button>
          </div>
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '24px' }}>
            <ReportViewer markdown={reportContent} />
          </div>
        </div>
      )}

      {/* Placeholder when not generated and not generating */}
      {!hasCached && !generating && !error && (
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: '8px',
          padding: '60px 24px', textAlign: 'center',
        }}>
          <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
            今日尚未生成基本面研报，点击上方按钮开始分析
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// News tab (placeholder)
// ---------------------------------------------------------------------------

function NewsTab({ stock }: { stock: StockOption }) {
  return (
    <div style={{
      background: 'var(--bg-card)', border: '1px solid var(--border-subtle)',
      borderRadius: '8px', padding: '40px 24px', textAlign: 'center',
    }}>
      <div style={{ fontSize: '14px', fontWeight: 510, color: 'var(--text-secondary)', marginBottom: '8px' }}>
        {stock.stock_name} 个股动态
      </div>
      <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
        公司公告、重大事件抓取即将上线
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stock detail view (after selecting a stock)
// ---------------------------------------------------------------------------

function StockDetail({
  stock, activeTab, onTabChange, onBack,
}: {
  stock: StockOption;
  activeTab: StockTab;
  onTabChange: (t: StockTab) => void;
  onBack: () => void;
}) {
  return (
    <div>
      {/* Stock header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '20px', flexWrap: 'wrap' }}>
        <button
          onClick={onBack}
          style={{
            padding: '4px 10px', fontSize: '12px', borderRadius: '5px',
            background: 'transparent', border: '1px solid var(--border-subtle)',
            color: 'var(--text-secondary)', cursor: 'pointer',
          }}
        >
          &larr; 返回
        </button>
        <div>
          <span style={{ fontSize: '17px', fontWeight: 590, color: 'var(--text-primary)' }}>
            {stock.stock_name}
          </span>
          <span style={{ fontSize: '13px', color: 'var(--text-muted)', marginLeft: '8px' }}>
            {stock.stock_code}
          </span>
        </div>
      </div>

      {/* Tab bar */}
      <div style={{
        display: 'flex', gap: '0', background: 'var(--bg-card)',
        border: '1px solid var(--border-subtle)', borderRadius: '8px',
        padding: '4px', width: 'fit-content', marginBottom: '20px',
      }}>
        {TAB_CONFIG.map((t) => (
          <button
            key={t.key}
            onClick={() => onTabChange(t.key)}
            style={{
              padding: '6px 18px', fontSize: '13px', borderRadius: '6px', border: 'none',
              fontWeight: activeTab === t.key ? 510 : 400,
              color: activeTab === t.key ? 'var(--text-primary)' : 'var(--text-tertiary)',
              background: activeTab === t.key ? 'var(--bg-nav-active)' : 'none',
              cursor: 'pointer', transition: 'all 0.12s',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div key={stock.stock_code}>
        {activeTab === 'comprehensive' && <ComprehensiveTab stock={stock} />}
        {activeTab === 'technical'     && <TechnicalTab     stock={stock} />}
        {activeTab === 'fundamental'   && <FundamentalTab   stock={stock} />}
        {activeTab === 'news'          && <NewsTab           stock={stock} />}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function StockPage() {
  const [selectedStock, setSelectedStock] = useState<StockOption | null>(null);
  const [activeTab, setActiveTab] = useState<StockTab>('comprehensive');

  const handleSelect = useCallback((s: StockOption) => {
    setSelectedStock(s);
    setActiveTab('comprehensive');
  }, []);

  const handleBack = useCallback(() => {
    setSelectedStock(null);
  }, []);

  return (
    <AppShell>
      {/* Page header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px', flexWrap: 'wrap' }}>
        <h1 style={{ fontSize: '20px', fontWeight: 590, color: 'var(--text-primary)', letterSpacing: '-0.3px', margin: 0 }}>
          {selectedStock ? '个股分析' : '个股'}
        </h1>
        <StockSearchBox onSelect={handleSelect} compact={!!selectedStock} />
      </div>

      {selectedStock ? (
        <StockDetail
          stock={selectedStock}
          activeTab={activeTab}
          onTabChange={setActiveTab}
          onBack={handleBack}
        />
      ) : (
        <StockCardGrid onSelect={handleSelect} />
      )}
    </AppShell>
  );
}
