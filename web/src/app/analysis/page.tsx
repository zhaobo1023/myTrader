'use client';

import { useState, useEffect, useRef } from 'react';
import AppShell from '@/components/layout/AppShell';
import apiClient from '@/lib/api-client';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface StockOption {
  code: string;
  name: string;
}

interface StockSearchItem {
  stock_code: string;
  stock_name: string | null;
  industry?: string | null;
}

interface TechReportCard {
  id: number;
  stock_code: string;
  stock_name: string;
  trade_date: string;
  score: number;
  score_label: string;
  ma_pattern?: string;
  max_severity: string;
  summary: string;
  signal_count: number;
  created_at: string;
  signals: SignalItem[];
  indicators: Record<string, number | null>;
  has_html?: boolean;
}

interface SignalItem {
  name: string;
  level: string;
  description: string;
  severity?: string;
  tag?: string;
}

interface GenerateResponse {
  generated: boolean;
  quota_used: number;
  quota_limit: number;
  report: TechReportCard;
}

interface ListResponse {
  total: number;
  items: TechReportCard[];
}

interface RagReport {
  id: number;
  stock_code: string;
  stock_name: string;
  report_type: string;
  report_date: string;
  content: string;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Style helpers
// ---------------------------------------------------------------------------

const severityColor = (s: string) => {
  if (s === 'RED') return '#e5534b';
  if (s === 'YELLOW') return '#c69026';
  if (s === 'GREEN') return '#27a644';
  return 'var(--text-muted)';
};

const scoreBadgeStyle = (score: number): React.CSSProperties => {
  const color = score >= 20 ? '#27a644' : score <= -20 ? '#e5534b' : '#c69026';
  return {
    display: 'inline-block', padding: '2px 8px', borderRadius: '12px',
    fontSize: '12px', fontWeight: 510, color,
    background: `${color}18`, border: `1px solid ${color}40`,
  };
};

const signalLevelStyle = (level: string): React.CSSProperties => {
  if (level === 'RED')    return { color: '#e5534b', background: 'rgba(229,83,75,0.1)',   padding: '1px 6px', borderRadius: '3px', fontSize: '11px' };
  if (level === 'YELLOW') return { color: '#c69026', background: 'rgba(198,144,38,0.1)',  padding: '1px 6px', borderRadius: '3px', fontSize: '11px' };
  if (level === 'GREEN')  return { color: '#27a644', background: 'rgba(39,166,68,0.1)',   padding: '1px 6px', borderRadius: '3px', fontSize: '11px' };
  return                         { color: 'var(--text-muted)', background: 'var(--bg-tag)', padding: '1px 6px', borderRadius: '3px', fontSize: '11px' };
};

// ---------------------------------------------------------------------------
// Report detail panel
// ---------------------------------------------------------------------------

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || '';

function ReportDetail({ report }: { report: TechReportCard }) {
  const indKeys = Object.keys(report.indicators || {}).slice(0, 20);

  return (
    <div style={{ marginTop: '16px', padding: '16px', background: 'var(--bg-elevated)', borderRadius: '8px', border: '1px solid var(--border-subtle)' }}>
      {/* Summary */}
      <div style={{ marginBottom: '14px' }}>
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '6px', flexWrap: 'wrap' }}>
          <span style={scoreBadgeStyle(report.score)}>{report.score > 0 ? '+' : ''}{report.score}</span>
          <span style={{ fontSize: '12px', color: 'var(--text-secondary)', background: 'var(--bg-card)', padding: '1px 6px', borderRadius: '4px' }}>{report.score_label}</span>
          {report.ma_pattern && (
            <span style={{ fontSize: '11px', color: 'var(--text-secondary)', background: 'var(--bg-card)', padding: '1px 6px', borderRadius: '4px' }}>
              {report.ma_pattern}
            </span>
          )}
          {report.max_severity !== 'NONE' && (
            <span style={{ fontSize: '11px', color: severityColor(report.max_severity), background: `${severityColor(report.max_severity)}15`, padding: '1px 6px', borderRadius: '4px' }}>
              {report.max_severity}
            </span>
          )}
          <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginLeft: 'auto' }}>
            {report.signal_count} 个信号 · {report.trade_date}
          </span>
          {report.has_html && (
            <a
              href={`${API_BASE}/api/analysis/report-html/${report.id}`}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                padding: '2px 10px', fontSize: '11px', borderRadius: '4px',
                background: 'var(--accent)', color: '#fff',
                border: '1px solid var(--accent)',
                textDecoration: 'none', display: 'inline-block',
              }}
            >
              完整报告
            </a>
          )}
        </div>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', margin: 0, lineHeight: '1.6' }}>{report.summary}</p>
      </div>

      {/* Signals */}
      {report.signals && report.signals.length > 0 && (
        <div style={{ marginBottom: '14px' }}>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 510, marginBottom: '8px' }}>信号列表</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {report.signals.map((sig, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '5px 8px', background: 'var(--bg-card)', borderRadius: '5px', fontSize: '12px' }}>
                <span style={signalLevelStyle(sig.level)}>{sig.level}</span>
                <span style={{ color: 'var(--text-primary)', fontWeight: 510, minWidth: '80px' }}>{sig.name}</span>
                <span style={{ color: 'var(--text-secondary)', flex: 1 }}>{sig.description}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Key indicators */}
      {indKeys.length > 0 && (
        <div>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 510, marginBottom: '8px' }}>关键指标</div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '6px' }}>
            {indKeys.map((k) => (
              <div key={k} style={{ background: 'var(--bg-card)', padding: '6px 8px', borderRadius: '5px' }}>
                <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '2px' }}>{k}</div>
                <div style={{ fontSize: '12px', color: 'var(--text-primary)', fontWeight: 510 }}>
                  {report.indicators[k] != null ? Number(report.indicators[k]).toFixed(3) : '--'}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Comprehensive report panel (five-step RAG)
// ---------------------------------------------------------------------------

// Simple markdown-to-html: bold, heading, paragraph, horizontal rule
function renderMarkdown(md: string): string {
  return md
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .split('\n\n')
    .map((block) => {
      const trimmed = block.trim();
      if (!trimmed) return '';
      if (trimmed.startsWith('### ')) return `<h3 style="font-size:14px;font-weight:600;margin:16px 0 6px;color:var(--text-primary)">${trimmed.slice(4)}</h3>`;
      if (trimmed.startsWith('## '))  return `<h2 style="font-size:16px;font-weight:650;margin:20px 0 8px;color:var(--text-primary)">${trimmed.slice(3)}</h2>`;
      if (trimmed.startsWith('# '))   return `<h1 style="font-size:18px;font-weight:700;margin:24px 0 10px;color:var(--text-primary)">${trimmed.slice(2)}</h1>`;
      if (trimmed === '---') return '<hr style="border:none;border-top:1px solid var(--border-subtle);margin:16px 0"/>';
      // inline bold
      const inlined = trimmed.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
      if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
        const items = inlined.split('\n').map(l => l.replace(/^[-*] /, '')).map(l => `<li>${l}</li>`).join('');
        return `<ul style="margin:4px 0 8px 20px;padding:0;color:var(--text-secondary);font-size:13px;line-height:1.7">${items}</ul>`;
      }
      return `<p style="margin:0 0 8px;color:var(--text-secondary);font-size:13px;line-height:1.7">${inlined}</p>`;
    })
    .join('\n');
}

interface SseStep {
  step: string;
  name: string;
  content?: string;
  done: boolean;
}

function ComprehensiveReportPanel({ stock }: { stock: StockOption }) {
  const [cachedReport, setCachedReport] = useState<RagReport | null>(null);
  const [checkDone, setCheckDone] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [steps, setSteps] = useState<SseStep[]>([]);
  const [finalContent, setFinalContent] = useState<string>('');
  const [error, setError] = useState<string>('');

  // Check for today's cached report
  useEffect(() => {
    setCachedReport(null);
    setCheckDone(false);
    setSteps([]);
    setFinalContent('');
    setError('');
    setStreaming(false);

    apiClient.get('/api/analysis/comprehensive/today', { params: { code: stock.code } })
      .then((r) => {
        if (r.data.exists && r.data.report) {
          setCachedReport(r.data.report);
          setFinalContent(r.data.report.content || '');
        }
        setCheckDone(true);
      })
      .catch(() => setCheckDone(true));
  }, [stock.code]);

  function startGenerate() {
    setError('');
    setSteps([]);
    setFinalContent('');
    setStreaming(true);

    const es = new EventSource(
      `${API_BASE}/api/analysis/comprehensive/generate-sse?code=${encodeURIComponent(stock.code)}&name=${encodeURIComponent(stock.name)}&report_type=comprehensive`
    );

    es.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === 'cached') {
          setCachedReport(msg.report);
          setFinalContent(msg.report?.content || '');
          setStreaming(false);
          es.close();
        } else if (msg.type === 'plan') {
          const initial: SseStep[] = (msg.sections as string[]).map((name, i) => ({
            step: `step${i + 1}`, name, done: false,
          }));
          setSteps(initial);
        } else if (msg.type === 'step_start') {
          setSteps((prev) =>
            prev.map((s) => s.name === msg.name ? { ...s, done: false } : s)
          );
        } else if (msg.type === 'step_done') {
          setSteps((prev) =>
            prev.map((s) => s.name === msg.name ? { ...s, content: msg.content, done: true } : s)
          );
        } else if (msg.type === 'done') {
          setFinalContent(msg.content || '');
          setStreaming(false);
          es.close();
        } else if (msg.type === 'error') {
          setError(msg.message || '生成失败');
          setStreaming(false);
          es.close();
        }
      } catch {
        // ignore parse errors
      }
    };

    es.onerror = () => {
      setError('连接中断，请重试');
      setStreaming(false);
      es.close();
    };
  }

  // POST-based SSE via fetch (EventSource doesn't support POST)
  function startGeneratePost() {
    setError('');
    setSteps([]);
    setFinalContent('');
    setStreaming(true);

    fetch(`${API_BASE}/api/analysis/comprehensive/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stock_code: stock.code, stock_name: stock.name, report_type: 'comprehensive' }),
    }).then(async (res) => {
      if (!res.ok || !res.body) {
        setError('请求失败');
        setStreaming(false);
        return;
      }
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
            const msg = JSON.parse(line.slice(6));
            if (msg.type === 'cached') {
              setCachedReport(msg.report);
              setFinalContent(msg.report?.content || '');
              setStreaming(false);
            } else if (msg.type === 'plan') {
              const initial: SseStep[] = (msg.sections as string[]).map((name, i) => ({
                step: `step${i + 1}`, name, done: false,
              }));
              setSteps(initial);
            } else if (msg.type === 'step_start') {
              setSteps((prev) =>
                prev.map((s) => s.name === msg.name ? { ...s, done: false } : s)
              );
            } else if (msg.type === 'step_done') {
              setSteps((prev) =>
                prev.map((s) => s.name === msg.name ? { ...s, content: msg.content, done: true } : s)
              );
            } else if (msg.type === 'done') {
              setFinalContent(msg.content || '');
              setStreaming(false);
            } else if (msg.type === 'error') {
              setError(msg.message || '生成失败');
              setStreaming(false);
            }
          } catch {
            // ignore
          }
        }
      }
      setStreaming(false);
    }).catch((e) => {
      setError(String(e));
      setStreaming(false);
    });
  }

  if (!checkDone) {
    return <div style={{ padding: '40px 0', textAlign: 'center', fontSize: '13px', color: 'var(--text-muted)' }}>检查缓存...</div>;
  }

  return (
    <div style={{ marginTop: '8px' }}>
      {/* Header bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px', flexWrap: 'wrap' }}>
        <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
          {cachedReport
            ? `今日研报已生成 · ${cachedReport.report_date}`
            : '今日尚未生成综合研报'}
        </div>
        {!streaming && (
          <button
            onClick={startGeneratePost}
            style={{
              padding: '5px 14px', fontSize: '12px', fontWeight: 510,
              background: 'var(--accent-bg)', color: '#fff',
              border: 'none', borderRadius: '6px', cursor: 'pointer',
            }}
          >
            {cachedReport ? '重新生成' : '生成综合研报'}
          </button>
        )}
        {streaming && (
          <span style={{ fontSize: '12px', color: 'var(--accent)', animation: 'pulse 1.5s infinite' }}>
            生成中...
          </span>
        )}
      </div>

      {/* Error */}
      {error && (
        <div style={{ padding: '8px 12px', background: 'rgba(229,83,75,0.08)', border: '1px solid rgba(229,83,75,0.25)', borderRadius: '6px', fontSize: '12px', color: '#e5534b', marginBottom: '12px' }}>
          {error}
        </div>
      )}

      {/* Step progress (during streaming) */}
      {streaming && steps.length > 0 && (
        <div style={{ marginBottom: '16px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {steps.map((s) => (
            <div key={s.name} style={{
              display: 'flex', alignItems: 'center', gap: '8px',
              padding: '7px 12px', borderRadius: '6px',
              background: s.done ? 'rgba(39,166,68,0.06)' : 'var(--bg-card)',
              border: `1px solid ${s.done ? 'rgba(39,166,68,0.2)' : 'var(--border-subtle)'}`,
              fontSize: '12px',
            }}>
              <span style={{ color: s.done ? '#27a644' : 'var(--text-muted)', fontSize: '13px' }}>{s.done ? '[OK]' : '[ ]'}</span>
              <span style={{ color: s.done ? 'var(--text-primary)' : 'var(--text-muted)', fontWeight: s.done ? 510 : 400 }}>{s.name}</span>
              {s.done && s.content && (
                <span style={{ color: 'var(--text-muted)', fontSize: '11px', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {s.content.slice(0, 80)}...
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Final report content */}
      {finalContent && !streaming && (
        <div style={{
          padding: '20px 24px',
          background: 'var(--bg-card)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '8px',
          lineHeight: '1.7',
          maxHeight: '70vh',
          overflowY: 'auto',
        }}
          dangerouslySetInnerHTML={{ __html: renderMarkdown(finalContent) }}
        />
      )}

      {/* Placeholder if nothing yet */}
      {!finalContent && !streaming && !error && (
        <div style={{ padding: '40px 0', textAlign: 'center', fontSize: '13px', color: 'var(--text-muted)' }}>
          点击"生成综合研报"开始分析
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stock search box
// ---------------------------------------------------------------------------

function StockSearchBox({
  onSelect,
}: {
  onSelect: (stock: StockOption) => void;
}) {
  const [keyword, setKeyword] = useState('');
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const { data: searchResult } = useQuery<{ count: number; data: StockSearchItem[] }>({
    queryKey: ['stock-search', keyword],
    queryFn: () =>
      apiClient.get('/api/market/search', { params: { keyword, limit: 10 } }).then((r) => r.data),
    enabled: keyword.length >= 1,
    staleTime: 30000,
  });

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, []);

  function handleSelect(item: StockSearchItem) {
    const stock: StockOption = { code: item.stock_code, name: item.stock_name || item.stock_code };
    setKeyword(`${stock.code} ${stock.name}`);
    setOpen(false);
    onSelect(stock);
  }

  const items = searchResult?.data || [];

  return (
    <div ref={ref} style={{ position: 'relative', width: '320px' }}>
      <input
        type="text"
        value={keyword}
        onChange={(e) => { setKeyword(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        placeholder="搜索股票代码或名称"
        style={{
          width: '100%', boxSizing: 'border-box',
          padding: '8px 12px',
          background: 'var(--bg-input)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '6px',
          fontSize: '13px',
          color: 'var(--text-primary)',
          outline: 'none',
        }}
      />
      {open && items.length > 0 && (
        <div style={{
          position: 'absolute', top: '38px', left: 0, right: 0, zIndex: 100,
          background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)',
          borderRadius: '6px', boxShadow: '0 4px 16px rgba(0,0,0,0.3)',
          maxHeight: '240px', overflowY: 'auto',
        }}>
          {items.map((item) => (
            <div
              key={item.stock_code}
              onClick={() => handleSelect(item)}
              style={{
                padding: '8px 12px', cursor: 'pointer', fontSize: '13px',
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
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
// Stock report panel - technical tab
// ---------------------------------------------------------------------------

function TechReportTabContent({ stock }: { stock: StockOption }) {
  const queryClient = useQueryClient();
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [generatedReport, setGeneratedReport] = useState<TechReportCard | null>(null);
  const [generateError, setGenerateError] = useState<string>('');

  const { data: recentReports, isLoading } = useQuery<TechReportCard[]>({
    queryKey: ['stock-reports', stock.code],
    queryFn: () =>
      apiClient.get('/api/analysis/reports/by-stock', { params: { code: stock.code, days: 3 } }).then((r) => r.data),
  });

  const { data: latestDateData } = useQuery<{ latest_date: string }>({
    queryKey: ['latest-date'],
    queryFn: () => apiClient.get('/api/market/latest-date').then((r) => r.data),
    staleTime: 300000,
  });

  const latestTradeDate = latestDateData?.latest_date || '';
  const hasLatestReport = recentReports?.some((r) => r.trade_date === latestTradeDate);
  const showGenerateBtn = latestTradeDate && !hasLatestReport;

  const generateMutation = useMutation<GenerateResponse, { response?: { data?: { detail?: string }; status?: number } }, void>({
    mutationFn: () =>
      apiClient
        .post('/api/analysis/reports/generate', {
          stock_code: stock.code,
          stock_name: stock.name,
        })
        .then((r) => r.data),
    onSuccess: (data) => {
      setGeneratedReport(data.report);
      setExpandedId(data.report.id || -1);
      setGenerateError('');
      queryClient.invalidateQueries({ queryKey: ['stock-reports', stock.code] });
    },
    onError: (err) => {
      const detail = err?.response?.data?.detail;
      const status = err?.response?.status;
      if (status === 429) setGenerateError('今日配额已用完，明日再试');
      else setGenerateError(detail || '生成失败，请检查股票代码或数据');
    },
  });

  const allReports: TechReportCard[] = (() => {
    const base = recentReports || [];
    if (generatedReport && !base.some((r) => r.id === generatedReport.id)) {
      return [generatedReport, ...base];
    }
    return base;
  })();

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '16px' }}>
        {showGenerateBtn && (
          <button
            onClick={() => { setGenerateError(''); generateMutation.mutate(); }}
            disabled={generateMutation.isPending}
            style={{
              padding: '5px 14px', fontSize: '12px', fontWeight: 510,
              background: generateMutation.isPending ? 'var(--bg-card)' : 'var(--accent-bg)',
              color: generateMutation.isPending ? 'var(--text-muted)' : '#fff',
              border: 'none', borderRadius: '6px',
              cursor: generateMutation.isPending ? 'not-allowed' : 'pointer',
            }}
          >
            {generateMutation.isPending ? '生成中...' : `生成 ${latestTradeDate} 报告`}
          </button>
        )}
      </div>

      {generateError && (
        <div style={{ padding: '8px 12px', background: 'rgba(229,83,75,0.08)', border: '1px solid rgba(229,83,75,0.25)', borderRadius: '6px', fontSize: '12px', color: '#e5534b', marginBottom: '12px' }}>
          {generateError}
        </div>
      )}

      {isLoading && (
        <div style={{ fontSize: '13px', color: 'var(--text-muted)', padding: '20px 0' }}>加载中...</div>
      )}

      {!isLoading && allReports.length === 0 && !showGenerateBtn && (
        <div style={{ padding: '30px 0', textAlign: 'center', fontSize: '13px', color: 'var(--text-muted)' }}>
          近3天无报告记录
        </div>
      )}

      {!isLoading && allReports.length === 0 && showGenerateBtn && (
        <div style={{ padding: '20px 0', fontSize: '13px', color: 'var(--text-muted)' }}>
          近3天暂无报告，点击上方按钮生成最新交易日报告
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {allReports.map((report) => {
          const isExpanded = expandedId === report.id || (report.id === 0 && expandedId === -1);
          return (
            <div
              key={`${report.id}-${report.trade_date}`}
              style={{
                background: 'var(--bg-card)',
                border: '1px solid var(--border-subtle)',
                borderLeft: `3px solid ${severityColor(report.max_severity)}`,
                borderRadius: '8px',
                overflow: 'hidden',
              }}
            >
              <div
                onClick={() => setExpandedId(isExpanded ? null : (report.id || -1))}
                style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '12px 16px', cursor: 'pointer',
                  transition: 'background 0.12s',
                }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-card-hover)'; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'transparent'; }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span style={{ fontSize: '13px', fontWeight: 510, color: 'var(--text-primary)' }}>
                    {report.trade_date}
                    {report.trade_date === latestTradeDate && (
                      <span style={{ marginLeft: '6px', fontSize: '10px', color: 'var(--accent)' }}>最新</span>
                    )}
                  </span>
                  <span style={scoreBadgeStyle(report.score)}>{report.score > 0 ? '+' : ''}{report.score}</span>
                  <span style={{ fontSize: '11px', color: 'var(--text-secondary)', background: 'var(--bg-panel)', padding: '1px 6px', borderRadius: '4px' }}>
                    {report.score_label}
                  </span>
                  {report.max_severity !== 'NONE' && (
                    <span style={{ fontSize: '10px', color: severityColor(report.max_severity), background: `${severityColor(report.max_severity)}15`, padding: '1px 5px', borderRadius: '3px' }}>
                      {report.max_severity}
                    </span>
                  )}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{report.signal_count} 个信号</span>
                  <span style={{ fontSize: '11px', color: 'var(--accent)' }}>{isExpanded ? '收起' : '展开'}</span>
                </div>
              </div>

              <div style={{ padding: '0 16px 10px', fontSize: '12px', color: 'var(--text-muted)', lineHeight: '1.5' }}>
                {report.summary}
              </div>

              {isExpanded && (
                <div style={{ padding: '0 16px 16px' }}>
                  <ReportDetail report={report} />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// One-pager deep research panel
// ---------------------------------------------------------------------------

interface OnePagerHistory {
  id: number;
  stock_code: string;
  stock_name: string;
  report_type: string;
  report_date: string;
  created_at: string;
}

function OnePagerPanel({ stock }: { stock: StockOption }) {
  const [cachedReport, setCachedReport] = useState<RagReport | null>(null);
  const [checkDone, setCheckDone] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [steps, setSteps] = useState<SseStep[]>([]);
  const [finalContent, setFinalContent] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [history, setHistory] = useState<OnePagerHistory[]>([]);
  const [viewingHistoryId, setViewingHistoryId] = useState<number | null>(null);
  const [historyContent, setHistoryContent] = useState<string>('');
  const [loadingHistory, setLoadingHistory] = useState(false);

  // Check for today's cached report + load history
  useEffect(() => {
    setCachedReport(null);
    setCheckDone(false);
    setSteps([]);
    setFinalContent('');
    setError('');
    setStreaming(false);
    setHistory([]);
    setViewingHistoryId(null);
    setHistoryContent('');

    Promise.all([
      apiClient.get('/api/analysis/one-pager/today', { params: { code: stock.code } })
        .then((r) => {
          if (r.data.exists && r.data.report) {
            setCachedReport(r.data.report);
            setFinalContent(r.data.report.content || '');
          }
        })
        .catch(() => {}),
      apiClient.get('/api/analysis/one-pager/history', { params: { code: stock.code, limit: 10 } })
        .then((r) => setHistory(r.data || []))
        .catch(() => {}),
    ]).finally(() => setCheckDone(true));
  }, [stock.code]);

  function loadHistoryReport(id: number) {
    setViewingHistoryId(id);
    setLoadingHistory(true);
    apiClient.get(`/api/analysis/rag-report/${id}`)
      .then((r) => {
        setHistoryContent(r.data?.content || '');
        setLoadingHistory(false);
      })
      .catch(() => {
        setLoadingHistory(false);
        setHistoryContent('[加载失败]');
      });
  }

  function startGenerate() {
    setError('');
    setSteps([]);
    setFinalContent('');
    setStreaming(true);
    setViewingHistoryId(null);
    setHistoryContent('');

    fetch(`${API_BASE}/api/analysis/one-pager/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ stock_code: stock.code, stock_name: stock.name }),
    }).then(async (res) => {
      if (!res.ok || !res.body) {
        setError('请求失败');
        setStreaming(false);
        return;
      }
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
            const msg = JSON.parse(line.slice(6));
            if (msg.type === 'cached') {
              setCachedReport(msg.report);
              setFinalContent(msg.report?.content || '');
              setStreaming(false);
            } else if (msg.type === 'plan') {
              const initial: SseStep[] = (msg.sections as string[]).map((name: string, i: number) => ({
                step: `part${i + 1}`, name, done: false,
              }));
              setSteps(initial);
            } else if (msg.type === 'step_start') {
              setSteps((prev) =>
                prev.map((s) => s.name === msg.name ? { ...s, done: false } : s)
              );
            } else if (msg.type === 'step_done') {
              setSteps((prev) =>
                prev.map((s) => s.name === msg.name ? { ...s, content: msg.content, done: true } : s)
              );
            } else if (msg.type === 'done') {
              setFinalContent(msg.content || '');
              setStreaming(false);
              // Refresh history
              apiClient.get('/api/analysis/one-pager/history', { params: { code: stock.code, limit: 10 } })
                .then((r) => setHistory(r.data || []))
                .catch(() => {});
            } else if (msg.type === 'error') {
              setError(msg.message || '生成失败');
              setStreaming(false);
            }
          } catch {
            // ignore
          }
        }
      }
      setStreaming(false);
    }).catch((e) => {
      setError(String(e));
      setStreaming(false);
    });
  }

  if (!checkDone) {
    return <div style={{ padding: '40px 0', textAlign: 'center', fontSize: '13px', color: 'var(--text-muted)' }}>检查缓存...</div>;
  }

  // Determine what content to display
  const displayContent = viewingHistoryId ? historyContent : finalContent;
  const isMarkdown = !viewingHistoryId || !displayContent.startsWith('<');

  return (
    <div style={{ marginTop: '8px' }}>
      {/* Header bar */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px', flexWrap: 'wrap' }}>
        <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
          {cachedReport
            ? `今日报告已生成 · ${cachedReport.report_date}`
            : '今日尚未生成一页纸研究'}
        </div>
        {!streaming && (
          <button
            onClick={startGenerate}
            style={{
              padding: '5px 14px', fontSize: '12px', fontWeight: 510,
              background: 'var(--accent-bg)', color: '#fff',
              border: 'none', borderRadius: '6px', cursor: 'pointer',
            }}
          >
            {cachedReport ? '重新生成' : '生成一页纸研究'}
          </button>
        )}
        {streaming && (
          <span style={{ fontSize: '12px', color: 'var(--accent)', animation: 'pulse 1.5s infinite' }}>
            生成中...
          </span>
        )}
      </div>

      {/* Error */}
      {error && (
        <div style={{ padding: '8px 12px', background: 'rgba(229,83,75,0.08)', border: '1px solid rgba(229,83,75,0.25)', borderRadius: '6px', fontSize: '12px', color: '#e5534b', marginBottom: '12px' }}>
          {error}
        </div>
      )}

      {/* Step progress (during streaming) */}
      {streaming && steps.length > 0 && (
        <div style={{ marginBottom: '16px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {steps.map((s) => (
            <div key={s.name} style={{
              display: 'flex', alignItems: 'center', gap: '8px',
              padding: '7px 12px', borderRadius: '6px',
              background: s.done ? 'rgba(39,166,68,0.06)' : 'var(--bg-card)',
              border: `1px solid ${s.done ? 'rgba(39,166,68,0.2)' : 'var(--border-subtle)'}`,
              fontSize: '12px',
            }}>
              <span style={{ color: s.done ? '#27a644' : 'var(--text-muted)', fontSize: '13px' }}>{s.done ? '[OK]' : '[ ]'}</span>
              <span style={{ color: s.done ? 'var(--text-primary)' : 'var(--text-muted)', fontWeight: s.done ? 510 : 400 }}>{s.name}</span>
              {s.done && s.content && (
                <span style={{ color: 'var(--text-muted)', fontSize: '11px', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {s.content.slice(0, 80)}...
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {/* History list */}
      {history.length > 0 && !streaming && (
        <div style={{ marginBottom: '16px' }}>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', fontWeight: 510, marginBottom: '8px' }}>历史报告</div>
          <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
            {history.map((h) => (
              <button
                key={h.id}
                onClick={() => {
                  if (viewingHistoryId === h.id) {
                    // Toggle off -> show today's
                    setViewingHistoryId(null);
                    setHistoryContent('');
                  } else {
                    // Check if this is today's report
                    if (cachedReport && h.id === cachedReport.id) {
                      setViewingHistoryId(null);
                      setHistoryContent('');
                    } else {
                      loadHistoryReport(h.id);
                    }
                  }
                }}
                style={{
                  padding: '4px 10px', fontSize: '11px', borderRadius: '4px',
                  border: `1px solid ${viewingHistoryId === h.id ? 'var(--accent)' : 'var(--border-subtle)'}`,
                  background: viewingHistoryId === h.id ? 'rgba(59,130,246,0.1)' : 'var(--bg-card)',
                  color: viewingHistoryId === h.id ? 'var(--accent)' : 'var(--text-secondary)',
                  cursor: 'pointer',
                }}
              >
                {h.report_date}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Loading history content */}
      {loadingHistory && (
        <div style={{ padding: '20px 0', textAlign: 'center', fontSize: '13px', color: 'var(--text-muted)' }}>加载历史报告...</div>
      )}

      {/* Report content */}
      {displayContent && !streaming && !loadingHistory && (
        <div style={{
          padding: '20px 24px',
          background: 'var(--bg-card)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '8px',
          lineHeight: '1.7',
          maxHeight: '70vh',
          overflowY: 'auto',
        }}
          dangerouslySetInnerHTML={{
            __html: isMarkdown ? renderMarkdown(displayContent) : displayContent
          }}
        />
      )}

      {/* Placeholder if nothing yet */}
      {!displayContent && !streaming && !error && !loadingHistory && (
        <div style={{ padding: '40px 0', textAlign: 'center', fontSize: '13px', color: 'var(--text-muted)' }}>
          点击"生成一页纸研究"开始深度分析
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stock panel with tabs: 技术分析 | 综合研报 | 一页纸研究
// ---------------------------------------------------------------------------

type Tab = 'one-pager' | 'tech' | 'comprehensive';

function StockReportPanel({ stock }: { stock: StockOption }) {
  const [activeTab, setActiveTab] = useState<Tab>('one-pager');

  const tabStyle = (tab: Tab): React.CSSProperties => ({
    padding: '6px 16px',
    fontSize: '13px',
    fontWeight: activeTab === tab ? 590 : 400,
    color: activeTab === tab ? 'var(--text-primary)' : 'var(--text-muted)',
    background: 'transparent',
    border: 'none',
    borderBottom: activeTab === tab ? '2px solid var(--accent)' : '2px solid transparent',
    cursor: 'pointer',
    transition: 'all 0.12s',
  });

  return (
    <div style={{ marginTop: '24px' }}>
      {/* Stock name + tabs */}
      <div style={{ marginBottom: '16px' }}>
        <h2 style={{ fontSize: '16px', fontWeight: 590, color: 'var(--text-primary)', margin: '0 0 12px' }}>
          {stock.name}
          <span style={{ fontSize: '12px', color: 'var(--text-muted)', marginLeft: '8px', fontFamily: 'var(--font-geist-mono)', fontWeight: 400 }}>{stock.code}</span>
        </h2>
        <div style={{ display: 'flex', borderBottom: '1px solid var(--border-subtle)', gap: '4px' }}>
          <button style={tabStyle('one-pager')} onClick={() => setActiveTab('one-pager')}>一页纸研究</button>
          <button style={tabStyle('tech')} onClick={() => setActiveTab('tech')}>技术分析</button>
          <button style={tabStyle('comprehensive')} onClick={() => setActiveTab('comprehensive')}>综合研报</button>
        </div>
      </div>

      {activeTab === 'one-pager' && <OnePagerPanel stock={stock} />}
      {activeTab === 'tech' && <TechReportTabContent stock={stock} />}
      {activeTab === 'comprehensive' && <ComprehensiveReportPanel stock={stock} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function AnalysisPage() {
  const [selectedStock, setSelectedStock] = useState<StockOption | null>(null);

  const { data: listData } = useQuery<ListResponse>({
    queryKey: ['tech-reports'],
    queryFn: () => apiClient.get('/api/analysis/reports').then((r) => r.data),
    staleTime: 60000,
  });

  return (
    <AppShell>
      {/* Page title + search */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px', flexWrap: 'wrap' }}>
        <h1 style={{ fontSize: '20px', fontWeight: 590, color: 'var(--text-primary)', letterSpacing: '-0.3px', margin: 0 }}>
          个股分析
        </h1>
        <StockSearchBox onSelect={(s) => setSelectedStock(s)} />
        {listData && (
          <span style={{ fontSize: '12px', color: 'var(--text-muted)', marginLeft: 'auto' }}>
            共 {listData.total} 份报告
          </span>
        )}
      </div>

      {/* Stock-specific panel */}
      {selectedStock ? (
        <StockReportPanel key={selectedStock.code} stock={selectedStock} />
      ) : (
        /* Default: show recent reports list */
        <>
          {!listData?.items?.length ? (
            <div style={{ padding: '60px 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: '14px' }}>
              搜索股票代码或名称以查看报告
            </div>
          ) : (
            <div>
              <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '14px' }}>最近生成的报告</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '14px' }}>
                {listData.items.map((card) => (
                  <div
                    key={card.id}
                    onClick={() => setSelectedStock({ code: card.stock_code, name: card.stock_name })}
                    style={{
                      background: 'var(--bg-panel)',
                      border: '1px solid var(--border-subtle)',
                      borderLeft: `3px solid ${severityColor(card.max_severity)}`,
                      borderRadius: '8px',
                      padding: '14px 16px',
                      cursor: 'pointer',
                      transition: 'background 0.12s',
                    }}
                    onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-card)'; }}
                    onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-panel)'; }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                      <div>
                        <div style={{ fontSize: '14px', fontWeight: 510, color: 'var(--text-primary)' }}>
                          {card.stock_name || card.stock_code}
                        </div>
                        <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '1px' }}>
                          {card.stock_code} &nbsp;&middot;&nbsp; {card.trade_date}
                        </div>
                      </div>
                      <span style={scoreBadgeStyle(card.score)}>{card.score > 0 ? '+' : ''}{card.score}</span>
                    </div>
                    <div style={{ display: 'flex', gap: '6px', marginBottom: '8px' }}>
                      <span style={{ fontSize: '11px', color: 'var(--text-secondary)', background: 'var(--bg-card)', padding: '1px 6px', borderRadius: '4px' }}>
                        {card.score_label}
                      </span>
                      {card.max_severity !== 'NONE' && (
                        <span style={{ fontSize: '11px', color: severityColor(card.max_severity), background: `${severityColor(card.max_severity)}15`, padding: '1px 6px', borderRadius: '4px' }}>
                          {card.max_severity}
                        </span>
                      )}
                    </div>
                    <div style={{
                      fontSize: '12px', color: 'var(--text-secondary)', lineHeight: '1.5',
                      display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
                      marginBottom: '8px',
                    }}>
                      {card.summary}
                    </div>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{card.signal_count} 个信号</div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </AppShell>
  );
}
