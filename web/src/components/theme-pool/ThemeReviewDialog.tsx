'use client';

import React, { useState, useRef, useCallback } from 'react';
import { useSSEFetch } from '@/hooks/useSSEFetch';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type ReviewVerdict = 'hold' | 'watch' | 'exit';

interface ReviewItem {
  stock_code: string;
  verdict: ReviewVerdict;
  reason: string;
}

type Phase =
  | 'idle'
  | 'loading_stocks'
  | 'reviewing'
  | 'done'
  | 'error';

const VERDICT_LABEL: Record<ReviewVerdict, string> = {
  hold: '维持',
  watch: '关注',
  exit: '建议移出',
};

const VERDICT_COLOR: Record<ReviewVerdict, { bg: string; text: string }> = {
  hold:  { bg: '#dcfce7', text: '#16a34a' },
  watch: { bg: '#fef3c7', text: '#d97706' },
  exit:  { bg: '#fee2e2', text: '#ef4444' },
};

// ---------------------------------------------------------------------------
// ThemeReviewDialog
// ---------------------------------------------------------------------------

interface Props {
  open: boolean;
  themeId: number;
  themeName: string;
  onClose: () => void;
}

export function ThemeReviewDialog({ open, themeId, themeName, onClose }: Props) {
  const [phase, setPhase] = useState<Phase>('idle');
  const [logs, setLogs] = useState<string[]>([]);
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [summary, setSummary] = useState('');
  const [errorMsg, setErrorMsg] = useState('');
  const abortRef = useRef<AbortController | null>(null);
  const { stream } = useSSEFetch();

  const addLog = (msg: string) => setLogs((prev) => [...prev, msg]);

  const startReview = useCallback(async () => {
    setPhase('loading_stocks');
    setLogs([]);
    setReviews([]);
    setSummary('');
    setErrorMsg('');

    abortRef.current = new AbortController();

    try {
      await stream(
        '/api/theme-pool/llm/stream',
        {
          skill_id: 'theme-review',
          params: { theme_id: themeId, theme_name: themeName },
        },
        (event) => {
          const type = event.type ?? '';
          switch (type) {
            case 'start':
              addLog(String(event.message ?? ''));
              break;
            case 'loading_stocks':
              setPhase('loading_stocks');
              addLog(String(event.message ?? '正在加载成分股...'));
              break;
            case 'reviewing':
              setPhase('reviewing');
              addLog(`正在让 AI 复评 ${event.total ?? ''} 只股票...`);
              break;
            case 'review_result': {
              const items = (event.reviews as ReviewItem[]) ?? [];
              setReviews(items);
              break;
            }
            case 'done':
              setPhase('done');
              setSummary(String(event.summary ?? '复评完成'));
              addLog(String(event.summary ?? ''));
              break;
            case 'error':
              setPhase('error');
              setErrorMsg(String(event.message ?? '未知错误'));
              addLog(`[错误] ${event.message ?? ''}`);
              break;
          }
        },
        abortRef.current.signal,
      );
    } catch (err: unknown) {
      if ((err as Error)?.name !== 'AbortError') {
        setPhase('error');
        const msg = (err as Error)?.message ?? '请求失败';
        setErrorMsg(msg);
        addLog(`[错误] ${msg}`);
      }
    }
  }, [themeId, themeName, stream]);

  const handleClose = () => {
    abortRef.current?.abort();
    setPhase('idle');
    setLogs([]);
    setReviews([]);
    onClose();
  };

  if (!open) return null;

  const isRunning = phase === 'loading_stocks' || phase === 'reviewing';
  const holdCount = reviews.filter((r) => r.verdict === 'hold').length;
  const watchCount = reviews.filter((r) => r.verdict === 'watch').length;
  const exitCount = reviews.filter((r) => r.verdict === 'exit').length;

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 1100,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onClick={handleClose}
    >
      <div
        style={{
          background: 'var(--bg-panel)', borderRadius: '10px', padding: '24px',
          width: '680px', maxWidth: '95vw', maxHeight: '85vh',
          display: 'flex', flexDirection: 'column', gap: '16px',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
              AI 主题复评
            </h3>
            <p style={{ margin: '2px 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
              {themeName}
            </p>
          </div>
          <button
            onClick={handleClose}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              fontSize: '18px', color: 'var(--text-muted)', lineHeight: 1, padding: '2px 6px',
            }}
          >
            x
          </button>
        </div>

        {/* Idle state: start button */}
        {phase === 'idle' && (
          <div style={{ textAlign: 'center', padding: '24px 0' }}>
            <p style={{ margin: '0 0 16px', fontSize: '13px', color: 'var(--text-secondary)' }}>
              AI 将逐一评估每只成分股的投资逻辑，给出维持 / 关注 / 建议移出 三种结论。
            </p>
            <button
              onClick={startReview}
              style={{
                padding: '9px 24px', borderRadius: '6px', fontSize: '13px', fontWeight: 500,
                border: 'none', background: 'var(--accent)', color: '#fff', cursor: 'pointer',
              }}
            >
              开始 AI 复评
            </button>
          </div>
        )}

        {/* Running state: progress log */}
        {(isRunning || (phase !== 'idle' && logs.length > 0 && phase !== 'done' && phase !== 'error')) && (
          <div>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '6px', fontWeight: 500 }}>
              {isRunning ? '正在分析中...' : ''}
            </div>
            <div style={{
              background: 'var(--bg-canvas)', borderRadius: '6px', padding: '10px 12px',
              maxHeight: '120px', overflowY: 'auto',
              fontFamily: 'monospace', fontSize: '11px', color: 'var(--text-secondary)',
            }}>
              {logs.map((l, i) => <div key={i}>{l}</div>)}
              {isRunning && <div style={{ color: 'var(--accent)' }}>...</div>}
            </div>
          </div>
        )}

        {/* Error state */}
        {phase === 'error' && (
          <div style={{
            padding: '10px 14px', borderRadius: '6px', background: '#fee2e2',
            color: '#ef4444', fontSize: '12px',
          }}>
            复评失败：{errorMsg}
          </div>
        )}

        {/* Done: summary stats */}
        {phase === 'done' && summary && (
          <div style={{
            display: 'flex', gap: '12px', padding: '10px 14px', borderRadius: '6px',
            background: 'var(--bg-canvas)',
          }}>
            {[
              { label: '维持', count: holdCount, color: '#16a34a', bg: '#dcfce7' },
              { label: '关注', count: watchCount, color: '#d97706', bg: '#fef3c7' },
              { label: '建议移出', count: exitCount, color: '#ef4444', bg: '#fee2e2' },
            ].map(({ label, count, color, bg }) => (
              <div key={label} style={{
                flex: 1, textAlign: 'center', padding: '8px 0',
                borderRadius: '6px', background: bg,
              }}>
                <div style={{ fontSize: '20px', fontWeight: 700, color }}>{count}</div>
                <div style={{ fontSize: '11px', color, marginTop: '2px' }}>{label}</div>
              </div>
            ))}
          </div>
        )}

        {/* Review results list */}
        {reviews.length > 0 && (
          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <div style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '4px' }}>
              复评结果（共 {reviews.length} 只）
            </div>
            {reviews.map((r) => {
              const vc = VERDICT_COLOR[r.verdict] || VERDICT_COLOR.hold;
              return (
                <div
                  key={r.stock_code}
                  style={{
                    display: 'flex', alignItems: 'flex-start', gap: '10px',
                    padding: '8px 10px', borderRadius: '6px',
                    border: '1px solid var(--border-subtle)',
                    background: 'var(--bg-canvas)',
                  }}
                >
                  <span style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-primary)', minWidth: '90px' }}>
                    {r.stock_code}
                  </span>
                  <span style={{
                    display: 'inline-block', padding: '1px 6px', borderRadius: '3px',
                    fontSize: '11px', fontWeight: 500, background: vc.bg, color: vc.text,
                    whiteSpace: 'nowrap', flexShrink: 0,
                  }}>
                    {VERDICT_LABEL[r.verdict]}
                  </span>
                  <span style={{ fontSize: '12px', color: 'var(--text-secondary)', flex: 1 }}>
                    {r.reason}
                  </span>
                </div>
              );
            })}
          </div>
        )}

        {/* Footer */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', paddingTop: '4px' }}>
          {(phase === 'done' || phase === 'error') && (
            <button
              onClick={() => { setPhase('idle'); setLogs([]); setReviews([]); }}
              style={{
                padding: '6px 14px', borderRadius: '6px', fontSize: '12px',
                border: '1px solid var(--border-subtle)', background: 'transparent',
                color: 'var(--text-secondary)', cursor: 'pointer',
              }}
            >
              重新复评
            </button>
          )}
          <button
            onClick={handleClose}
            style={{
              padding: '6px 14px', borderRadius: '6px', fontSize: '12px',
              border: 'none', background: 'var(--accent)', color: '#fff', cursor: 'pointer',
            }}
          >
            关闭
          </button>
        </div>
      </div>
    </div>
  );
}
