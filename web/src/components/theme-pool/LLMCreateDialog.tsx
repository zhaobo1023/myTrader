'use client';

import { useState, useRef, useCallback } from 'react';
import { useSSEFetch } from '@/hooks/useSSEFetch';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CandidateStock {
  stock_code: string;
  stock_name: string;
  source: 'akshare' | 'llm';
  boards: string[];
  relevance: 'high' | 'medium';
  reason: string;
  selected: boolean;
}

type Phase =
  | 'idle'
  | 'concept_mapping'
  | 'fetching'
  | 'filtering'
  | 'review'
  | 'creating'
  | 'done'
  | 'error';

interface SSEEvent {
  type?: string;
  [key: string]: unknown;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: (themeName: string, stocks: CandidateStock[]) => Promise<void>;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const phaseLabel: Record<string, string> = {
  concept_mapping: 'AI 扩展概念关键词...',
  fetching: '从东方财富拉取成分股...',
  filtering: 'AI 过滤精选候选股...',
};

function relevanceColor(r: string) {
  return r === 'high' ? '#27a644' : '#c69026';
}

function relevanceBg(r: string) {
  return r === 'high' ? 'rgba(39,166,68,0.1)' : 'rgba(198,144,38,0.1)';
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function LLMCreateDialog({ open, onClose, onCreated }: Props) {
  const [themeName, setThemeName] = useState('');
  const [phase, setPhase] = useState<Phase>('idle');
  const [logs, setLogs] = useState<string[]>([]);
  const [concepts, setConcepts] = useState<string[]>([]);
  const [candidates, setCandidates] = useState<CandidateStock[]>([]);
  const [summary, setSummary] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const [creating, setCreating] = useState(false);
  const [extraCode, setExtraCode] = useState('');

  const abortRef = useRef<AbortController | null>(null);
  const { stream } = useSSEFetch();

  const addLog = useCallback((msg: string) => {
    setLogs(prev => [...prev, msg]);
  }, []);

  const handleStart = async () => {
    if (!themeName.trim()) return;
    setPhase('concept_mapping');
    setLogs([]);
    setConcepts([]);
    setCandidates([]);
    setSummary('');
    setErrorMsg('');

    abortRef.current = new AbortController();

    try {
      await stream(
        '/api/theme-pool/llm/create',
        { theme_name: themeName.trim(), max_candidates: 40 },
        (event: SSEEvent) => {
          switch (event.type ?? '') {
            case 'start':
              addLog(String(event.message ?? ''));
              break;

            case 'phase':
              addLog(String(event.message ?? ''));
              if (event.phase === 'fetching') setPhase('fetching');
              break;

            case 'concept_mapping': {
              const c = (event.concepts as string[]) ?? [];
              setConcepts(c);
              addLog(`AI 识别到 ${c.length} 个相关概念：${c.join('、')}`);
              break;
            }

            case 'boards_matched':
              addLog(`匹配到 ${event.total} 个东财概念板块`);
              break;

            case 'fetching':
              if (event.status === 'done') {
                addLog(`  板块「${event.board}」: ${event.count} 只成分股`);
              }
              break;

            case 'raw_pool':
              addLog(`原始候选池: ${event.total} 只 -> 有效 ${event.valid} 只`);
              setPhase('filtering');
              break;

            case 'filtering_start':
              addLog(`AI 正在分析 ${event.total_candidates} 只候选股...`);
              break;

            case 'filter_done':
              addLog(`AI 精选完成: 保留 ${event.selected} 只`);
              break;

            case 'candidate_list': {
              const stocks = ((event.stocks as CandidateStock[]) ?? []).map(s => ({
                ...s,
                selected: true,
              }));
              setCandidates(stocks);
              setPhase('review');
              break;
            }

            case 'done':
              setSummary(String(event.summary ?? ''));
              break;

            case 'error':
              setErrorMsg(String(event.message ?? '发生未知错误'));
              setPhase('error');
              break;
          }
        },
        abortRef.current.signal,
      );
    } catch (err: unknown) {
      if ((err as Error)?.name !== 'AbortError') {
        setErrorMsg(String(err));
        setPhase('error');
      }
    }
  };

  const handleCancel = () => {
    abortRef.current?.abort();
    setPhase('idle');
  };

  const toggleStock = (code: string) => {
    setCandidates(prev =>
      prev.map(s => s.stock_code === code ? { ...s, selected: !s.selected } : s)
    );
  };

  const toggleAll = (val: boolean) => {
    setCandidates(prev => prev.map(s => ({ ...s, selected: val })));
  };

  const handleAddExtra = () => {
    const raw = extraCode.trim().replace(/\./g, '');
    if (!raw || raw.length !== 6) return;
    const code = raw.startsWith('0') || raw.startsWith('3')
      ? `${raw}.SZ`
      : raw.startsWith('6') || raw.startsWith('9')
      ? `${raw}.SH`
      : `${raw}.BJ`;
    if (candidates.find(s => s.stock_code === code)) {
      setExtraCode('');
      return;
    }
    setCandidates(prev => [
      ...prev,
      { stock_code: code, stock_name: '待确认', source: 'llm', boards: [], relevance: 'medium', reason: '手动添加', selected: true },
    ]);
    setExtraCode('');
  };

  const handleConfirm = async () => {
    const selected = candidates.filter(s => s.selected);
    if (!selected.length) return;
    setCreating(true);
    try {
      await onCreated(themeName.trim(), selected);
      setPhase('done');
    } catch (e) {
      setErrorMsg(String(e));
      setPhase('error');
    } finally {
      setCreating(false);
    }
  };

  const handleClose = () => {
    abortRef.current?.abort();
    setPhase('idle');
    setThemeName('');
    setLogs([]);
    setCandidates([]);
    setSummary('');
    setErrorMsg('');
    onClose();
  };

  if (!open) return null;

  const selectedCount = candidates.filter(s => s.selected).length;
  const highCount = candidates.filter(s => s.selected && s.relevance === 'high').length;

  return (
    <div
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={handleClose}
    >
      <div
        style={{ background: 'var(--bg-panel)', borderRadius: '12px', width: '780px', maxWidth: '95vw', maxHeight: '88vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ padding: '18px 24px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>AI 创建主题票池</div>
            <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>输入主题名，AI 自动匹配东财概念板块并精选候选股</div>
          </div>
          <button onClick={handleClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', fontSize: '18px' }}>×</button>
        </div>

        {/* Input row */}
        <div style={{ padding: '16px 24px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', gap: '10px', alignItems: 'center' }}>
          <input
            value={themeName}
            onChange={e => setThemeName(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && phase === 'idle') handleStart(); }}
            placeholder="输入主题名，如：电网设备、国产替代、消费复苏"
            disabled={phase !== 'idle' && phase !== 'error'}
            style={{ flex: 1, padding: '8px 12px', borderRadius: '6px', fontSize: '13px', border: '1px solid var(--border-subtle)', background: 'var(--bg-canvas)', color: 'var(--text-primary)', outline: 'none' }}
          />
          {phase === 'idle' || phase === 'error' ? (
            <button
              onClick={handleStart}
              disabled={!themeName.trim()}
              style={{ padding: '8px 20px', borderRadius: '6px', fontSize: '13px', fontWeight: 500, background: themeName.trim() ? 'var(--accent)' : 'var(--bg-tag)', color: themeName.trim() ? '#fff' : 'var(--text-muted)', border: 'none', cursor: themeName.trim() ? 'pointer' : 'not-allowed' }}
            >
              开始分析
            </button>
          ) : phase === 'review' || phase === 'done' ? null : (
            <button
              onClick={handleCancel}
              style={{ padding: '8px 16px', borderRadius: '6px', fontSize: '13px', border: '1px solid var(--border-subtle)', background: 'transparent', color: 'var(--text-secondary)', cursor: 'pointer' }}
            >
              取消
            </button>
          )}
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>

          {/* Concepts row */}
          {concepts.length > 0 && (
            <div style={{ padding: '10px 24px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', gap: '6px', flexWrap: 'wrap', alignItems: 'center' }}>
              <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginRight: '4px' }}>AI 扩展概念:</span>
              {concepts.map(c => (
                <span key={c} style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '10px', background: 'var(--bg-elevated)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)' }}>{c}</span>
              ))}
            </div>
          )}

          {/* Progress logs (shown during processing) */}
          {phase !== 'idle' && phase !== 'review' && phase !== 'done' && (
            <div style={{ flex: 1, overflow: 'auto', padding: '16px 24px' }}>
              {phaseLabel[phase] && (
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                  <div style={{ width: '16px', height: '16px', border: '2px solid var(--accent)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
                  <span style={{ fontSize: '13px', color: 'var(--text-primary)' }}>{phaseLabel[phase]}</span>
                </div>
              )}
              {phase === 'error' && (
                <div style={{ padding: '10px 14px', borderRadius: '8px', background: 'rgba(229,83,75,0.08)', border: '1px solid rgba(229,83,75,0.2)', color: '#e5534b', fontSize: '13px', marginBottom: '12px' }}>
                  {errorMsg}
                </div>
              )}
              <div style={{ fontFamily: 'var(--font-geist-mono)', fontSize: '11px', color: 'var(--text-secondary)', lineHeight: '1.8' }}>
                {logs.map((log, i) => <div key={i}>{log}</div>)}
              </div>
            </div>
          )}

          {/* Candidate list (review phase) */}
          {(phase === 'review' || phase === 'done') && (
            <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
              {/* Summary bar */}
              <div style={{ padding: '10px 24px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
                {summary && <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{summary}</span>}
                <span style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '10px', background: 'rgba(39,166,68,0.1)', color: '#27a644' }}>已选 {selectedCount} 只</span>
                {highCount > 0 && <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>其中高相关 {highCount} 只</span>}
                <div style={{ marginLeft: 'auto', display: 'flex', gap: '8px' }}>
                  <button onClick={() => toggleAll(true)} style={{ fontSize: '11px', color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer' }}>全选</button>
                  <button onClick={() => toggleAll(false)} style={{ fontSize: '11px', color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer' }}>全不选</button>
                </div>
              </div>

              {/* Stock list */}
              <div style={{ flex: 1, overflowY: 'auto', padding: '8px 24px' }}>
                {/* AKShare group */}
                {candidates.filter(s => s.source === 'akshare').length > 0 && (
                  <div style={{ marginBottom: '8px' }}>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)', padding: '8px 0 4px', fontWeight: 500 }}>
                      东财概念板块 ({candidates.filter(s => s.source === 'akshare').length} 只)
                    </div>
                    {candidates.filter(s => s.source === 'akshare').map(s => (
                      <StockRow key={s.stock_code} stock={s} onToggle={() => toggleStock(s.stock_code)} />
                    ))}
                  </div>
                )}
                {/* LLM supplement group */}
                {candidates.filter(s => s.source === 'llm').length > 0 && (
                  <div style={{ marginBottom: '8px' }}>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)', padding: '8px 0 4px', fontWeight: 500 }}>
                      AI 补充标的 ({candidates.filter(s => s.source === 'llm').length} 只)
                    </div>
                    {candidates.filter(s => s.source === 'llm').map(s => (
                      <StockRow key={s.stock_code} stock={s} onToggle={() => toggleStock(s.stock_code)} />
                    ))}
                  </div>
                )}

                {/* Manual add */}
                <div style={{ padding: '10px 0', borderTop: '1px solid var(--border-subtle)', marginTop: '8px', display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)', flexShrink: 0 }}>手动添加:</span>
                  <input
                    value={extraCode}
                    onChange={e => setExtraCode(e.target.value)}
                    onKeyDown={e => { if (e.key === 'Enter') handleAddExtra(); }}
                    placeholder="输入 6 位代码，如 000001"
                    style={{ flex: 1, padding: '5px 8px', borderRadius: '5px', fontSize: '12px', border: '1px solid var(--border-subtle)', background: 'var(--bg-canvas)', color: 'var(--text-primary)', outline: 'none' }}
                  />
                  <button onClick={handleAddExtra} style={{ padding: '5px 12px', borderRadius: '5px', fontSize: '12px', border: '1px solid var(--border-subtle)', background: 'transparent', color: 'var(--text-secondary)', cursor: 'pointer' }}>
                    添加
                  </button>
                </div>
              </div>

              {/* Confirm footer */}
              <div style={{ padding: '14px 24px', borderTop: '1px solid var(--border-subtle)', display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
                <button onClick={handleClose} style={{ padding: '8px 16px', borderRadius: '6px', fontSize: '13px', border: '1px solid var(--border-subtle)', background: 'transparent', color: 'var(--text-secondary)', cursor: 'pointer' }}>
                  取消
                </button>
                <button
                  onClick={handleConfirm}
                  disabled={selectedCount === 0 || creating}
                  style={{ padding: '8px 20px', borderRadius: '6px', fontSize: '13px', fontWeight: 500, border: 'none', background: selectedCount > 0 ? 'var(--accent)' : 'var(--bg-tag)', color: selectedCount > 0 ? '#fff' : 'var(--text-muted)', cursor: selectedCount > 0 && !creating ? 'pointer' : 'not-allowed' }}
                >
                  {creating ? '创建中...' : `确认创建（写入 ${selectedCount} 只股票）`}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stock row sub-component
// ---------------------------------------------------------------------------

function StockRow({ stock, onToggle }: { stock: CandidateStock; onToggle: () => void }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', padding: '7px 0', borderBottom: '1px solid var(--border-subtle)' }}
    >
      <input
        type="checkbox"
        checked={stock.selected}
        onChange={onToggle}
        style={{ marginTop: '2px', flexShrink: 0, cursor: 'pointer' }}
      />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '13px', fontWeight: 510, color: 'var(--text-primary)' }}>{stock.stock_name}</span>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'var(--font-geist-mono)' }}>{stock.stock_code}</span>
          <span style={{ fontSize: '10px', padding: '1px 6px', borderRadius: '8px', background: relevanceBg(stock.relevance), color: relevanceColor(stock.relevance), fontWeight: 500 }}>
            {stock.relevance === 'high' ? '高相关' : '中相关'}
          </span>
          {stock.source === 'llm' && (
            <span style={{ fontSize: '10px', padding: '1px 6px', borderRadius: '8px', background: 'rgba(94,106,210,0.1)', color: 'var(--accent)' }}>AI 推荐</span>
          )}
          {stock.boards.length > 0 && (
            <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{stock.boards.slice(0, 2).join(' · ')}</span>
          )}
        </div>
        {stock.reason && (
          <div
            onClick={() => setExpanded(v => !v)}
            style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '3px', cursor: 'pointer', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: expanded ? 'normal' : 'nowrap' }}
          >
            {stock.reason}
          </div>
        )}
      </div>
    </div>
  );
}
