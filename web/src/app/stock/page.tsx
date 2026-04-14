'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import AppShell from '@/components/layout/AppShell';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type StockTab = 'one-pager' | 'comprehensive' | 'technical' | 'fundamental' | 'news';

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
  market_cap: number | null;
  circ_market_cap: number | null;
}

// Task status from /api/analysis/report/status or /report/latest
interface ReportTask {
  task_id?: string;
  status: 'pending' | 'running' | 'done' | 'failed' | 'cached' | null;
  report_id?: number | null;
  report_type?: string;
  error_msg?: string | null;
  report_date?: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || '';

const TAB_CONFIG: { key: StockTab; label: string }[] = [
  { key: 'one-pager',     label: '一页纸研究' },
  { key: 'comprehensive', label: '综合分析' },
  { key: 'technical',     label: '技术面分析' },
  { key: 'fundamental',   label: '基本面分析' },
  { key: 'news',          label: '个股动态' },
];

// Map tab -> report_type used by the unified API
const TAB_REPORT_TYPE: Record<StockTab, string> = {
  'one-pager':     'one_pager',
  'comprehensive': 'five_section',
  'technical':     'technical_report',
  'fundamental':   'fundamental',
  'news':          '',
};

type MarketFilter = 'all' | 'sh' | 'sz';
type CapFilter    = 'all' | 'large' | 'mid' | 'small';

const MARKET_LABELS: Record<MarketFilter, string> = { all: '全部', sh: '沪市', sz: '深市' };
const CAP_LABELS:    Record<CapFilter, string>    = { all: '全部市值', large: '大盘(>=500亿)', mid: '中盘(100-500亿)', small: '小盘(<100亿)' };

const POLL_INTERVAL_MS = 5000;

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
// Unified report task hook
// Handles submit -> pending/running poll -> done/failed
// ---------------------------------------------------------------------------

function useReportTask(stock: StockOption, reportType: string) {
  const [task, setTask] = useState<ReportTask>({ status: null });
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPoll = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
  };

  const pollStatus = useCallback(async (taskId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/analysis/report/status?task_id=${taskId}`);
      if (!res.ok) return;
      const data = await res.json();
      setTask(data);
      if (data.status === 'done' || data.status === 'failed') stopPoll();
    } catch { /* ignore */ }
  }, []);

  const startPoll = useCallback((taskId: string) => {
    stopPoll();
    pollRef.current = setInterval(() => pollStatus(taskId), POLL_INTERVAL_MS);
  }, [pollStatus]);

  // On mount / stock change: check latest report/task
  useEffect(() => {
    if (!reportType) { setLoading(false); return; }
    stopPoll();
    setTask({ status: null });
    setLoading(true);

    fetch(`${API_BASE}/api/analysis/report/latest?code=${stock.stock_code}&report_type=${reportType}`)
      .then((r) => r.json())
      .then((d) => {
        if (d.cached) {
          setTask({ status: 'cached', report_id: d.report_id, report_date: d.report_date, report_type: reportType });
        } else if (d.task_id) {
          setTask({ status: d.status, task_id: d.task_id, report_id: d.report_id, report_type: reportType });
          if (d.status === 'pending' || d.status === 'running') startPoll(d.task_id);
        } else {
          setTask({ status: null });
        }
      })
      .catch(() => setTask({ status: null }))
      .finally(() => setLoading(false));

    return stopPoll;
  }, [stock.stock_code, reportType, startPoll]);

  const submit = useCallback(async () => {
    if (submitting) return;
    setSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/api/analysis/report/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          stock_code: stock.stock_code,
          stock_name: stock.stock_name || stock.stock_code,
          report_type: reportType,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setTask({ status: 'failed', error_msg: data.detail || '提交失败' });
        return;
      }
      if (data.status === 'cached') {
        setTask({ status: 'cached', report_id: data.report_id, report_type: reportType });
      } else {
        setTask({ status: data.status, task_id: data.task_id, report_type: reportType });
        if (data.task_id && (data.status === 'submitted' || data.status === 'pending' || data.status === 'running')) {
          // treat submitted same as pending for polling
          setTask((prev) => ({ ...prev, status: 'pending' }));
          startPoll(data.task_id);
        }
      }
    } catch (e) {
      setTask({ status: 'failed', error_msg: String(e) });
    } finally {
      setSubmitting(false);
    }
  }, [stock, reportType, submitting, startPoll]);

  return { task, loading, submitting, submit };
}

// ---------------------------------------------------------------------------
// Shared report status banner
// ---------------------------------------------------------------------------

function ReportStatusBanner({
  task,
  submitting,
  onSubmit,
  submitLabel,
  resubmitLabel,
}: {
  task: ReportTask;
  submitting: boolean;
  onSubmit: () => void;
  submitLabel: string;
  resubmitLabel: string;
}) {
  const isPending = task.status === 'pending' || task.status === 'running';
  const isDone = task.status === 'done' || task.status === 'cached';
  const isFailed = task.status === 'failed';

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px', flexWrap: 'wrap' }}>
      {!isPending && (
        <button
          onClick={onSubmit}
          disabled={submitting}
          style={{
            padding: '7px 20px', borderRadius: '6px', fontSize: '13px', fontWeight: 510,
            background: submitting ? 'var(--bg-elevated)' : 'var(--accent)',
            color: submitting ? 'var(--text-muted)' : '#fff',
            border: 'none', cursor: submitting ? 'not-allowed' : 'pointer',
          }}
        >
          {submitting ? '提交中...' : (isDone ? resubmitLabel : submitLabel)}
        </button>
      )}

      {isPending && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '7px 14px', background: 'rgba(113,112,255,0.08)', borderRadius: '6px', border: '1px solid rgba(113,112,255,0.2)' }}>
          <span style={{ fontSize: '13px', color: 'var(--accent)', fontWeight: 510 }}>
            报告生成中，请稍后刷新查看
          </span>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>（每5秒自动检查）</span>
        </div>
      )}

      {isFailed && task.error_msg && (
        <div style={{ fontSize: '12px', color: '#e5534b', padding: '6px 12px', background: 'rgba(229,83,75,0.08)', borderRadius: '6px' }}>
          生成失败: {task.error_msg.slice(0, 120)}
        </div>
      )}

      {isDone && (
        <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
          {task.report_date ? `生成日期: ${task.report_date}` : '已生成'}
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ReportViewer (markdown -> HTML)
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Markdown report tab (one-pager, fundamental, comprehensive text)
// ---------------------------------------------------------------------------

function MarkdownReportTab({
  stock,
  reportType,
  submitLabel,
  resubmitLabel,
  placeholder,
  showHistory,
}: {
  stock: StockOption;
  reportType: string;
  submitLabel: string;
  resubmitLabel: string;
  placeholder: string;
  showHistory?: boolean;
}) {
  const { task, loading, submitting, submit } = useReportTask(stock, reportType);
  const [content, setContent] = useState('');
  const [history, setHistory] = useState<{ id: number; report_date: string }[]>([]);
  const [viewingId, setViewingId] = useState<number | null>(null);
  const [viewingContent, setViewingContent] = useState('');

  // Fetch report content when task is done/cached
  useEffect(() => {
    const rid = task.report_id;
    if ((task.status === 'done' || task.status === 'cached') && rid) {
      fetch(`${API_BASE}/api/analysis/rag-report/${rid}`)
        .then((r) => r.json())
        .then((d) => setContent(d.content || ''))
        .catch(() => setContent(''));
    } else if (task.status !== 'done' && task.status !== 'cached') {
      setContent('');
    }
  }, [task.status, task.report_id]);

  // Load history for one-pager
  useEffect(() => {
    if (!showHistory) return;
    fetch(`${API_BASE}/api/analysis/one-pager/history?code=${stock.stock_code}&limit=10`)
      .then((r) => r.json())
      .then((d) => setHistory(Array.isArray(d) ? d : []))
      .catch(() => setHistory([]));
  }, [stock.stock_code, showHistory]);

  function loadHistoryItem(id: number) {
    setViewingId(id);
    fetch(`${API_BASE}/api/analysis/rag-report/${id}`)
      .then((r) => r.json())
      .then((d) => setViewingContent(d.content || ''))
      .catch(() => setViewingContent('[加载失败]'));
  }

  const displayContent = viewingId ? viewingContent : content;

  if (loading) {
    return <div style={{ padding: '40px 0', textAlign: 'center', fontSize: '13px', color: 'var(--text-muted)' }}>加载中...</div>;
  }

  return (
    <div>
      <ReportStatusBanner
        task={task}
        submitting={submitting}
        onSubmit={submit}
        submitLabel={submitLabel}
        resubmitLabel={resubmitLabel}
      />

      {showHistory && history.length > 0 && (
        <div style={{ marginBottom: '14px' }}>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '6px' }}>历史报告</div>
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
            {history.map((h) => (
              <button
                key={h.id}
                onClick={() => {
                  if (viewingId === h.id) { setViewingId(null); setViewingContent(''); }
                  else loadHistoryItem(h.id);
                }}
                style={{
                  padding: '3px 10px', fontSize: '11px', borderRadius: '4px', cursor: 'pointer',
                  border: `1px solid ${viewingId === h.id ? 'var(--accent)' : 'var(--border-subtle)'}`,
                  background: viewingId === h.id ? 'rgba(113,112,255,0.1)' : 'var(--bg-card)',
                  color: viewingId === h.id ? 'var(--accent)' : 'var(--text-secondary)',
                }}
              >
                {h.report_date}
              </button>
            ))}
          </div>
        </div>
      )}

      {displayContent ? (
        <div style={{
          padding: '20px 24px', background: 'var(--bg-card)',
          border: '1px solid var(--border-subtle)', borderRadius: '8px',
          lineHeight: '1.7', maxHeight: '70vh', overflowY: 'auto',
        }}>
          <ReportViewer markdown={displayContent} />
        </div>
      ) : (task.status === null || task.status === 'failed') ? (
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--border-subtle)',
          borderRadius: '8px', padding: '60px 24px', textAlign: 'center',
        }}>
          <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>{placeholder}</div>
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// HTML report tab (five-section, iframe)
// ---------------------------------------------------------------------------

function HtmlReportTab({
  stock,
  reportType,
  submitLabel,
  resubmitLabel,
  placeholder,
  iframeTitle,
}: {
  stock: StockOption;
  reportType: string;
  submitLabel: string;
  resubmitLabel: string;
  placeholder: string;
  iframeTitle: string;
}) {
  const { task, loading, submitting, submit } = useReportTask(stock, reportType);

  const reportUrl = task.report_id
    ? `${API_BASE}/api/analysis/rag-report-html/${task.report_id}`
    : '';

  if (loading) {
    return <div style={{ padding: '40px 0', textAlign: 'center', fontSize: '13px', color: 'var(--text-muted)' }}>加载中...</div>;
  }

  const isDone = task.status === 'done' || task.status === 'cached';

  return (
    <div>
      <ReportStatusBanner
        task={task}
        submitting={submitting}
        onSubmit={submit}
        submitLabel={submitLabel}
        resubmitLabel={resubmitLabel}
      />

      {isDone && reportUrl ? (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
            <a
              href={reportUrl}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                padding: '3px 12px', fontSize: '12px', borderRadius: '5px',
                background: 'var(--accent)', color: '#fff', textDecoration: 'none',
              }}
            >
              在新标签页打开
            </a>
          </div>
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: '8px', overflow: 'hidden' }}>
            <iframe
              src={reportUrl}
              title={iframeTitle}
              style={{ width: '100%', height: '80vh', border: 'none', display: 'block' }}
            />
          </div>
        </div>
      ) : (task.status === null || task.status === 'failed') ? (
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--border-subtle)',
          borderRadius: '8px', padding: '60px 24px', textAlign: 'center',
        }}>
          <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>{placeholder}</div>
        </div>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Technical tab (keeps list view, uses task queue for generate)
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
                      padding: '2px 10px', fontSize: '11px', borderRadius: '4px',
                      background: 'var(--accent)', color: '#fff',
                      border: '1px solid var(--accent)', textDecoration: 'none',
                    }}
                  >
                    完整报告
                  </a>
                )}
                <span style={{ fontSize: '11px', color: 'var(--accent)' }}>{isExpanded ? '收起' : '展开'}</span>
              </div>
            </div>
            <div style={{ padding: '0 16px 10px', fontSize: '12px', color: 'var(--text-muted)' }}>{rep.summary}</div>
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
            {isExpanded && rep.indicators && Object.keys(rep.indicators).length > 0 && (
              <div style={{ padding: '0 16px 16px' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontWeight: 510, marginBottom: '6px' }}>关键指标</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(90px, 1fr))', gap: '6px' }}>
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
  const { task, loading: taskLoading, submitting, submit } = useReportTask(stock, 'technical_report');
  const [reports, setReports] = useState<TechReport[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [latestDate, setLatestDate] = useState('');

  useEffect(() => {
    setReports([]); setListLoading(true);
    Promise.all([
      fetch(`${API_BASE}/api/analysis/reports/by-stock?code=${stock.stock_code}&days=3`).then((r) => r.json()),
      fetch(`${API_BASE}/api/market/latest-date`).then((r) => r.json()),
    ]).then(([reps, ld]) => {
      setReports(Array.isArray(reps) ? reps : []);
      setLatestDate(ld.latest_date || '');
    }).catch(() => {}).finally(() => setListLoading(false));
  }, [stock.stock_code]);

  // When task completes, reload list
  useEffect(() => {
    if (task.status === 'done') {
      fetch(`${API_BASE}/api/analysis/reports/by-stock?code=${stock.stock_code}&days=3`)
        .then((r) => r.json())
        .then((reps) => setReports(Array.isArray(reps) ? reps : []))
        .catch(() => {});
    }
  }, [task.status, stock.stock_code]);

  const hasLatest = reports.some((r) => r.trade_date === latestDate);

  if (listLoading || taskLoading) {
    return <div style={{ fontSize: '13px', color: 'var(--text-muted)', padding: '30px 0' }}>加载中...</div>;
  }

  return (
    <div>
      {latestDate && !hasLatest && (
        <ReportStatusBanner
          task={task}
          submitting={submitting}
          onSubmit={submit}
          submitLabel={`生成 ${latestDate} 报告`}
          resubmitLabel={`重新生成 ${latestDate} 报告`}
        />
      )}
      {reports.length === 0 ? (
        <div style={{ fontSize: '13px', color: 'var(--text-muted)', padding: '20px 0' }}>
          近3天暂无报告{latestDate && !hasLatest ? '，点击上方按钮生成' : ''}
        </div>
      ) : (
        <TechReportList reports={reports} latestDate={latestDate} />
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
              onClick={() => { setKw(`${item.stock_code} ${item.stock_name || ''}`); setOpen(false); onSelect(item); }}
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
// Stock card grid
// ---------------------------------------------------------------------------

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
        <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>加载中...</div>
      )}
      {!loading && filtered.length === 0 && (
        <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>暂无分析记录，搜索股票开始分析</div>
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
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
              <div>
                <div style={{ fontSize: '14px', fontWeight: 590, color: 'var(--text-primary)' }}>{card.stock_name}</div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>{card.stock_code}</div>
              </div>
              <ScoreBadge score={card.score} label={card.score_label} />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '11px', color: 'var(--text-muted)' }}>
              <span>
                {card.market_cap != null ? `${card.market_cap.toFixed(0)}亿` : '-'}
                {' · '}
                {marketCategory(card.stock_code) === 'sh' ? '沪市' : '深市'}
              </span>
              <span>{card.latest_date}</span>
            </div>
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

// ---------------------------------------------------------------------------
// Stock detail view
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

      <div style={{
        display: 'flex', gap: '0', background: 'var(--bg-card)',
        border: '1px solid var(--border-subtle)', borderRadius: '8px',
        padding: '4px', marginBottom: '20px',
        overflowX: 'auto', WebkitOverflowScrolling: 'touch',
      }}>
        {TAB_CONFIG.map((t) => (
          <button
            key={t.key}
            onClick={() => onTabChange(t.key)}
            style={{
              padding: '6px 14px', fontSize: '13px', borderRadius: '6px', border: 'none',
              fontWeight: activeTab === t.key ? 510 : 400,
              color: activeTab === t.key ? 'var(--text-primary)' : 'var(--text-tertiary)',
              background: activeTab === t.key ? 'var(--bg-nav-active)' : 'none',
              cursor: 'pointer', transition: 'all 0.12s', whiteSpace: 'nowrap', flexShrink: 0,
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div key={stock.stock_code}>
        {activeTab === 'one-pager' && (
          <MarkdownReportTab
            stock={stock}
            reportType="one_pager"
            submitLabel="生成一页纸研究"
            resubmitLabel="重新生成"
            placeholder="点击生成一页纸研究开始深度分析"
            showHistory
          />
        )}
        {activeTab === 'comprehensive' && (
          <HtmlReportTab
            stock={stock}
            reportType="five_section"
            submitLabel="生成五截面分析报告"
            resubmitLabel="重新生成"
            placeholder="今日尚未生成五截面分析报告，点击上方按钮开始"
            iframeTitle="五截面分析报告"
          />
        )}
        {activeTab === 'technical' && <TechnicalTab stock={stock} />}
        {activeTab === 'fundamental' && (
          <MarkdownReportTab
            stock={stock}
            reportType="fundamental"
            submitLabel="生成基本面研报"
            resubmitLabel="重新生成"
            placeholder="今日尚未生成基本面研报，点击上方按钮开始分析"
          />
        )}
        {activeTab === 'news' && <NewsTab stock={stock} />}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

function useTriggerAnnualReportIngest(stock: StockOption | null) {
  useEffect(() => {
    if (!stock) return;
    const bare = stock.stock_code.includes('.') ? stock.stock_code.split('.')[0] : stock.stock_code;
    // Fire-and-forget: silently trigger background ingest, don't block UI
    fetch(`${API_BASE}/api/analysis/annual-report/ingest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stock_code: bare, stock_name: stock.stock_name || bare, years: 3 }),
    }).catch(() => {/* ignore errors, this is best-effort */});
  }, [stock?.stock_code]);
}

export default function StockPage() {
  const [selectedStock, setSelectedStock] = useState<StockOption | null>(null);
  const [activeTab, setActiveTab] = useState<StockTab>('one-pager');

  useTriggerAnnualReportIngest(selectedStock);

  const handleSelect = useCallback((s: StockOption) => {
    setSelectedStock(s);
    setActiveTab('one-pager');
  }, []);

  const handleBack = useCallback(() => {
    setSelectedStock(null);
  }, []);

  return (
    <AppShell>
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
