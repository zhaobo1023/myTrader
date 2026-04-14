'use client';

import { useState, useRef, useEffect } from 'react';
import AppShell from '@/components/layout/AppShell';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ReportType = 'comprehensive' | 'fundamental' | 'technical';

interface StockSearchItem {
  stock_code: string;
  stock_name: string | null;
}

interface StepProgress {
  step: string;
  name: string;
  status: 'pending' | 'running' | 'done';
  content?: string;
}

interface ReportListItem {
  report_id: string;
  stock_code: string;
  stock_name: string;
  report_type: string;
  created_at: string;
  char_count: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8000';

async function searchStocks(keyword: string): Promise<StockSearchItem[]> {
  if (!keyword.trim()) return [];
  const res = await fetch(`${API_BASE}/api/market/search?keyword=${encodeURIComponent(keyword)}&limit=10`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.data || [];
}

// Simple Markdown -> HTML converter using marked (loaded lazily)
async function mdToHtml(md: string): Promise<string> {
  const { marked } = await import('marked');
  marked.setOptions({ breaks: true });
  return await marked(md);
}

// ---------------------------------------------------------------------------
// Stock Search Box
// ---------------------------------------------------------------------------

function StockSearchBox({ onSelect }: { onSelect: (s: StockSearchItem) => void }) {
  const [kw, setKw] = useState('');
  const [results, setResults] = useState<StockSearchItem[]>([]);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!kw.trim()) { setResults([]); return; }
    const t = setTimeout(() => {
      searchStocks(kw).then(setResults);
    }, 200);
    return () => clearTimeout(t);
  }, [kw]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  function handleSelect(item: StockSearchItem) {
    setKw(`${item.stock_code} ${item.stock_name || ''}`);
    setOpen(false);
    onSelect(item);
  }

  return (
    <div ref={ref} style={{ position: 'relative', flex: 1, maxWidth: '320px' }}>
      <input
        value={kw}
        onChange={(e) => { setKw(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        placeholder="搜索股票代码或名称"
        style={{
          width: '100%', boxSizing: 'border-box', padding: '7px 12px',
          background: 'var(--bg-input)', border: '1px solid var(--border-subtle)',
          borderRadius: '6px', fontSize: '13px', color: 'var(--text-primary)', outline: 'none',
        }}
      />
      {open && results.length > 0 && (
        <div style={{
          position: 'absolute', top: '36px', left: 0, right: 0, zIndex: 200,
          background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)',
          borderRadius: '6px', boxShadow: '0 4px 16px rgba(0,0,0,0.25)',
          maxHeight: '220px', overflowY: 'auto',
        }}>
          {results.map((item) => (
            <div
              key={item.stock_code}
              onClick={() => handleSelect(item)}
              style={{
                padding: '8px 12px', cursor: 'pointer', fontSize: '13px',
                display: 'flex', justifyContent: 'space-between',
                borderBottom: '1px solid var(--border-subtle)',
              }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-card-hover)'; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'transparent'; }}
            >
              <span style={{ color: 'var(--text-primary)' }}>{item.stock_name || item.stock_code}</span>
              <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-geist-mono)', fontSize: '12px' }}>{item.stock_code}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Markdown Report Viewer
// ---------------------------------------------------------------------------

function ReportViewer({ markdown }: { markdown: string }) {
  const [html, setHtml] = useState('');

  useEffect(() => {
    mdToHtml(markdown).then(setHtml);
  }, [markdown]);

  return (
    <>
      <style>{`
        .md-report { font-size: 14px; line-height: 1.8; color: var(--text-primary); }
        .md-report h1 { font-size: 20px; font-weight: 650; margin: 24px 0 12px; color: var(--text-primary); border-bottom: 1px solid var(--border-subtle); padding-bottom: 8px; }
        .md-report h2 { font-size: 16px; font-weight: 590; margin: 20px 0 8px; color: var(--text-primary); }
        .md-report h3 { font-size: 14px; font-weight: 560; margin: 16px 0 6px; color: var(--text-secondary); }
        .md-report p  { margin: 8px 0; color: var(--text-secondary); }
        .md-report ul, .md-report ol { margin: 8px 0 8px 20px; color: var(--text-secondary); }
        .md-report li { margin: 4px 0; }
        .md-report table { width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 13px; }
        .md-report th { background: var(--bg-card-hover); padding: 7px 10px; text-align: left; color: var(--text-muted); font-weight: 510; border-bottom: 1px solid var(--border-subtle); }
        .md-report td { padding: 7px 10px; border-bottom: 1px solid var(--border-subtle); color: var(--text-secondary); }
        .md-report blockquote { border-left: 3px solid var(--accent); padding: 8px 14px; margin: 12px 0; background: var(--bg-elevated); color: var(--text-muted); font-style: italic; }
        .md-report code { background: var(--bg-elevated); padding: 1px 5px; border-radius: 3px; font-size: 12px; font-family: var(--font-geist-mono); }
        .md-report pre { background: var(--bg-elevated); padding: 12px; border-radius: 6px; overflow-x: auto; margin: 10px 0; }
        .md-report hr { border: none; border-top: 1px solid var(--border-subtle); margin: 20px 0; }
        .md-report strong { color: var(--text-primary); }
      `}</style>
      <div
        className="md-report"
        dangerouslySetInnerHTML={{ __html: html }}
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

export default function RAGPage() {
  const [tab, setTab] = useState<'generate' | 'history'>('generate');

  // Generate form state
  const [selectedStock, setSelectedStock] = useState<StockSearchItem | null>(null);
  const [reportType, setReportType] = useState<ReportType>('comprehensive');

  // Generation progress
  const [steps, setSteps] = useState<StepProgress[]>([]);
  const [generating, setGenerating] = useState(false);
  const [reportContent, setReportContent] = useState('');
  const [reportId, setReportId] = useState('');
  const [error, setError] = useState('');

  // History
  const [historyList, setHistoryList] = useState<ReportListItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [viewingReport, setViewingReport] = useState<{ id: string; content: string } | null>(null);

  async function loadHistory(code?: string) {
    setHistoryLoading(true);
    try {
      const url = code
        ? `${API_BASE}/api/rag/report/list?stock_code=${encodeURIComponent(code)}&limit=30`
        : `${API_BASE}/api/rag/report/list?limit=30`;
      const res = await fetch(url);
      const data = await res.json();
      setHistoryList(data.reports || []);
    } catch {
      setHistoryList([]);
    } finally {
      setHistoryLoading(false);
    }
  }

  useEffect(() => {
    if (tab === 'history') loadHistory();
  }, [tab]);

  async function handleGenerate() {
    if (!selectedStock || generating) return;
    setError('');
    setReportContent('');
    setReportId('');
    setSteps([]);
    setGenerating(true);

    try {
      const res = await fetch(`${API_BASE}/api/rag/report/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          stock_code: selectedStock.stock_code,
          stock_name: selectedStock.stock_name || selectedStock.stock_code,
          report_type: reportType,
          collection: 'reports',
        }),
      });

      if (!res.ok || !res.body) {
        setError(`请求失败: ${res.status}`);
        setGenerating(false);
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const event = JSON.parse(line.slice(6));

            if (event.type === 'plan') {
              setSteps((event.sections as string[]).map((name: string, i: number) => ({
                step: `step${i + 1}`,
                name,
                status: 'pending',
              })));
            } else if (event.type === 'step_start') {
              setSteps((prev) => prev.map((s) =>
                s.name === event.name ? { ...s, status: 'running' } : s
              ));
            } else if (event.type === 'step_done') {
              setSteps((prev) => prev.map((s) =>
                s.name === event.name ? { ...s, status: 'done', content: event.content } : s
              ));
            } else if (event.type === 'done') {
              setReportContent(event.content || '');
              setReportId(event.report_id || '');
              setSteps((prev) => prev.map((s) => ({ ...s, status: 'done' })));
            } else if (event.type === 'error') {
              setError(event.message || '生成失败');
            }
          } catch { /* skip malformed */ }
        }
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setGenerating(false);
    }
  }

  async function viewHistoryReport(id: string) {
    if (viewingReport?.id === id) { setViewingReport(null); return; }
    try {
      const res = await fetch(`${API_BASE}/api/rag/report/${id}`);
      const text = await res.text();
      setViewingReport({ id, content: text });
    } catch {
      setViewingReport(null);
    }
  }

  const REPORT_TYPE_OPTIONS: { value: ReportType; label: string; desc: string }[] = [
    { value: 'comprehensive', label: '综合研报', desc: '五步法基本面 + 技术面' },
    { value: 'fundamental', label: '基本面', desc: '五步法深度分析' },
    { value: 'technical', label: '技术面', desc: '纯技术指标分析' },
  ];

  return (
    <AppShell>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
        <h1 style={{ fontSize: '20px', fontWeight: 590, color: 'var(--text-primary)', letterSpacing: '-0.3px', margin: 0 }}>
          智能研报
        </h1>
        <div style={{ display: 'flex', gap: '2px', background: 'var(--bg-card-hover)', borderRadius: '8px', padding: '3px' }}>
          {(['generate', 'history'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              style={{
                padding: '5px 14px', fontSize: '13px', fontWeight: tab === t ? 510 : 400,
                color: tab === t ? 'var(--text-primary)' : 'var(--text-tertiary)',
                background: tab === t ? 'var(--bg-nav-active)' : 'none',
                border: 'none', borderRadius: '6px', cursor: 'pointer',
              }}
            >
              {t === 'generate' ? '生成研报' : '历史研报'}
            </button>
          ))}
        </div>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* Generate tab                                                         */}
      {/* ------------------------------------------------------------------ */}
      {tab === 'generate' && (
        <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: '20px', alignItems: 'start' }}>
          {/* Left panel: form */}
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: '10px', padding: '18px' }}>
            <div style={{ fontSize: '13px', fontWeight: 510, color: 'var(--text-muted)', marginBottom: '14px' }}>研报设置</div>

            <div style={{ marginBottom: '14px' }}>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '6px' }}>股票</div>
              <StockSearchBox onSelect={setSelectedStock} />
              {selectedStock && (
                <div style={{ marginTop: '6px', fontSize: '12px', color: 'var(--accent)' }}>
                  已选: {selectedStock.stock_name} ({selectedStock.stock_code})
                </div>
              )}
            </div>

            <div style={{ marginBottom: '18px' }}>
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '8px' }}>报告类型</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {REPORT_TYPE_OPTIONS.map((opt) => (
                  <label
                    key={opt.value}
                    style={{
                      display: 'flex', alignItems: 'center', gap: '8px', padding: '8px 10px',
                      border: `1px solid ${reportType === opt.value ? 'var(--accent)' : 'var(--border-subtle)'}`,
                      borderRadius: '6px', cursor: 'pointer',
                      background: reportType === opt.value ? 'rgba(113,112,255,0.06)' : 'transparent',
                    }}
                  >
                    <input
                      type="radio"
                      name="reportType"
                      value={opt.value}
                      checked={reportType === opt.value}
                      onChange={() => setReportType(opt.value)}
                      style={{ accentColor: 'var(--accent)' }}
                    />
                    <div>
                      <div style={{ fontSize: '13px', fontWeight: 510, color: 'var(--text-primary)' }}>{opt.label}</div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{opt.desc}</div>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            <button
              onClick={handleGenerate}
              disabled={!selectedStock || generating}
              style={{
                width: '100%', padding: '9px',
                background: !selectedStock || generating ? 'var(--bg-elevated)' : 'var(--accent-bg)',
                color: !selectedStock || generating ? 'var(--text-muted)' : '#fff',
                border: 'none', borderRadius: '6px', fontSize: '13px', fontWeight: 510,
                cursor: !selectedStock || generating ? 'not-allowed' : 'pointer',
              }}
            >
              {generating ? '生成中...' : '生成研报'}
            </button>

            {/* Step progress */}
            {steps.length > 0 && (
              <div style={{ marginTop: '16px' }}>
                <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '8px' }}>生成进度</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
                  {steps.map((s) => (
                    <div key={s.step} style={{ display: 'flex', alignItems: 'center', gap: '7px', fontSize: '12px' }}>
                      <span style={{
                        width: '16px', height: '16px', borderRadius: '50%', flexShrink: 0,
                        background: s.status === 'done' ? '#27a644' : s.status === 'running' ? 'var(--accent)' : 'var(--bg-elevated)',
                        border: `1px solid ${s.status === 'done' ? '#27a644' : s.status === 'running' ? 'var(--accent)' : 'var(--border-subtle)'}`,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: '9px', color: '#fff',
                      }}>
                        {s.status === 'done' ? '✓' : s.status === 'running' ? '…' : ''}
                      </span>
                      <span style={{ color: s.status === 'done' ? 'var(--text-primary)' : s.status === 'running' ? 'var(--accent)' : 'var(--text-muted)' }}>
                        {s.name}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {error && (
              <div style={{ marginTop: '12px', padding: '8px 10px', background: 'rgba(229,83,75,0.08)', border: '1px solid rgba(229,83,75,0.2)', borderRadius: '6px', fontSize: '12px', color: '#e5534b' }}>
                {error}
              </div>
            )}
          </div>

          {/* Right panel: report viewer */}
          <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: '10px', padding: '24px', minHeight: '500px' }}>
            {!reportContent && !generating && (
              <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px', paddingTop: '80px' }}>
                选择股票并点击「生成研报」<br />
                <span style={{ fontSize: '12px', marginTop: '6px', display: 'block' }}>综合研报包含五步法基本面分析 + 技术面，耗时约 3-5 分钟</span>
              </div>
            )}
            {generating && !reportContent && (
              <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px', paddingTop: '80px' }}>
                <div style={{ marginBottom: '12px' }}>正在生成研报，请稍候...</div>
                <div style={{ fontSize: '12px' }}>大模型逐步分析中，每个章节完成后实时显示</div>
              </div>
            )}
            {reportContent && (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                    报告ID: <span style={{ fontFamily: 'var(--font-geist-mono)' }}>{reportId}</span>
                  </div>
                  <button
                    onClick={() => {
                      const blob = new Blob([reportContent], { type: 'text/markdown;charset=utf-8' });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement('a');
                      a.href = url; a.download = `${reportId}.md`; a.click();
                      URL.revokeObjectURL(url);
                    }}
                    style={{ fontSize: '12px', color: 'var(--accent)', background: 'none', border: '1px solid var(--accent)', borderRadius: '5px', padding: '4px 10px', cursor: 'pointer' }}
                  >
                    下载 .md
                  </button>
                </div>
                <ReportViewer markdown={reportContent} />
              </>
            )}
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------------ */}
      {/* History tab                                                          */}
      {/* ------------------------------------------------------------------ */}
      {tab === 'history' && (
        <div>
          {historyLoading && (
            <div style={{ fontSize: '13px', color: 'var(--text-muted)', padding: '40px 0', textAlign: 'center' }}>加载中...</div>
          )}
          {!historyLoading && historyList.length === 0 && (
            <div style={{ fontSize: '13px', color: 'var(--text-muted)', padding: '40px 0', textAlign: 'center' }}>暂无历史研报</div>
          )}
          {!historyLoading && historyList.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {historyList.map((item) => (
                <div key={item.report_id}>
                  <div
                    style={{
                      background: 'var(--bg-card)', border: '1px solid var(--border-subtle)',
                      borderRadius: '8px', padding: '14px 18px',
                      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    }}
                  >
                    <div>
                      <div style={{ fontSize: '14px', fontWeight: 510, color: 'var(--text-primary)', marginBottom: '3px' }}>
                        {item.stock_name} <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-geist-mono)', fontSize: '12px' }}>{item.stock_code}</span>
                      </div>
                      <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                        {item.report_type} · {item.created_at?.slice(0, 16)} · {item.char_count?.toLocaleString()} 字符
                      </div>
                    </div>
                    <button
                      onClick={() => viewHistoryReport(item.report_id)}
                      style={{
                        fontSize: '12px', padding: '5px 12px',
                        background: viewingReport?.id === item.report_id ? 'var(--bg-elevated)' : 'none',
                        color: 'var(--accent)', border: '1px solid var(--accent)',
                        borderRadius: '5px', cursor: 'pointer',
                      }}
                    >
                      {viewingReport?.id === item.report_id ? '收起' : '查看'}
                    </button>
                  </div>
                  {viewingReport?.id === item.report_id && (
                    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderTop: 'none', borderRadius: '0 0 8px 8px', padding: '24px' }}>
                      <ReportViewer markdown={viewingReport.content} />
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </AppShell>
  );
}
