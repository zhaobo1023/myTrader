'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useQuery } from '@tanstack/react-query';
import { themePoolApi, ThemePoolItem } from '@/lib/api-client';
import { useAddToPositions, useAddToCandidate, useAddToTheme } from '@/hooks/useStockAdd';

type Target = 'positions' | 'candidate' | 'theme';

interface QuickAddMenuProps {
  stockCode: string;
  stockName: string;
  sourceType?: 'strategy' | 'industry' | 'manual';
  sourceDetail?: string;
  snapshot?: Record<string, unknown>;
  /** Limit which targets are shown. Default: all three. */
  targets?: Target[];
}

// ---------------------------------------------------------------------------
// Dropdown rendered via Portal to avoid overflow:hidden clipping
// ---------------------------------------------------------------------------
function DropdownPortal({
  anchorRef,
  children,
}: {
  anchorRef: React.RefObject<HTMLDivElement | null>;
  children: React.ReactNode;
}) {
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  useEffect(() => {
    function update() {
      const el = anchorRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      setPos({
        top: rect.bottom + 4,
        left: rect.right - 180, // align right edge with button right edge
      });
    }
    update();
    window.addEventListener('scroll', update, true);
    window.addEventListener('resize', update);
    return () => {
      window.removeEventListener('scroll', update, true);
      window.removeEventListener('resize', update);
    };
  }, [anchorRef]);

  if (!pos) return null;

  // Clamp left to avoid going off-screen
  const clampedLeft = Math.max(8, pos.left);

  return createPortal(
    <div style={{
      position: 'fixed', top: pos.top, left: clampedLeft,
      zIndex: 9999,
    }}>
      {children}
    </div>,
    document.body,
  );
}

export default function QuickAddMenu({
  stockCode,
  stockName,
  sourceType = 'manual',
  sourceDetail,
  snapshot,
  targets = ['positions', 'candidate', 'theme'],
}: QuickAddMenuProps) {
  const [open, setOpen] = useState(false);
  const [step, setStep] = useState<null | 'positions' | 'candidate' | 'theme'>(null);
  const [level, setLevel] = useState('L2');
  const [memo, setMemo] = useState('');
  const [result, setResult] = useState<'ok' | 'err' | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const addPos = useAddToPositions();
  const addCand = useAddToCandidate();
  const addTheme = useAddToTheme();

  // Load active themes only when the menu is opened and theme is a target
  const { data: themesData } = useQuery({
    queryKey: ['theme-pools', 'active'],
    queryFn: () => themePoolApi.listThemes('active').then(r => r.data),
    enabled: open && targets.includes('theme'),
    staleTime: 30_000,
  });
  const themes: ThemePoolItem[] = themesData?.items || [];

  const resetState = useCallback(() => {
    setOpen(false);
    setStep(null);
    setLevel('L2');
    setMemo('');
  }, []);

  // Close on outside click (check both button container and portal dropdown)
  useEffect(() => {
    if (!open) return;
    function handler(e: MouseEvent) {
      const target = e.target as Node;
      if (
        containerRef.current && !containerRef.current.contains(target) &&
        dropdownRef.current && !dropdownRef.current.contains(target)
      ) {
        resetState();
      }
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open, resetState]);

  function showResult(ok: boolean) {
    setResult(ok ? 'ok' : 'err');
    setTimeout(() => { setResult(null); resetState(); }, 1200);
  }

  async function submitPositions() {
    try {
      await addPos.mutateAsync({ stock_code: stockCode, stock_name: stockName, level });
      showResult(true);
    } catch {
      showResult(false);
    }
  }

  async function submitCandidate() {
    try {
      await addCand.mutateAsync({
        stock_code: stockCode,
        stock_name: stockName,
        source_type: sourceType,
        source_detail: sourceDetail,
        entry_snapshot: snapshot,
        memo: memo || null,
      });
      showResult(true);
    } catch {
      showResult(false);
    }
  }

  async function submitTheme(themeId: number) {
    try {
      await addTheme.mutateAsync({ themeId, stock_code: stockCode, stock_name: stockName });
      showResult(true);
    } catch {
      showResult(false);
    }
  }

  // Result feedback
  if (result === 'ok') {
    return <span style={{ fontSize: '11px', color: '#27a644', fontWeight: 510 }}>已添加</span>;
  }
  if (result === 'err') {
    return <span style={{ fontSize: '11px', color: '#e5534b' }}>失败</span>;
  }

  const isPending = addPos.isPending || addCand.isPending || addTheme.isPending;

  return (
    <div ref={containerRef} style={{ position: 'relative', display: 'inline-block' }} onClick={e => e.stopPropagation()}>
      <button
        onClick={() => { if (!open) { setOpen(true); setStep(null); } else resetState(); }}
        disabled={isPending}
        style={{
          fontSize: '13px', width: '26px', height: '26px', lineHeight: '26px',
          borderRadius: '6px', border: '1px solid var(--border-subtle)',
          background: open ? 'var(--bg-card-hover)' : 'transparent',
          color: 'var(--accent)', cursor: 'pointer', fontWeight: 600,
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        }}
      >
        +
      </button>

      {open && (
        <DropdownPortal anchorRef={containerRef}>
          <div
            ref={dropdownRef}
            style={{
              background: 'var(--bg-panel)', border: '1px solid var(--border-std)',
              borderRadius: '8px', boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
              minWidth: '180px', overflow: 'hidden',
            }}
          >
            {/* Main menu */}
            {step === null && (
              <div>
                {targets.includes('positions') && (
                  <div
                    onClick={() => setStep('positions')}
                    style={menuItemStyle}
                    onMouseEnter={hoverIn} onMouseLeave={hoverOut}
                  >
                    加入实盘持仓
                  </div>
                )}
                {targets.includes('candidate') && (
                  <div
                    onClick={() => setStep('candidate')}
                    style={menuItemStyle}
                    onMouseEnter={hoverIn} onMouseLeave={hoverOut}
                  >
                    加入候选观察
                  </div>
                )}
                {targets.includes('theme') && (
                  <div
                    onClick={() => setStep('theme')}
                    style={menuItemStyle}
                    onMouseEnter={hoverIn} onMouseLeave={hoverOut}
                  >
                    加入主题池 &rsaquo;
                  </div>
                )}
              </div>
            )}

            {/* Positions: level selector */}
            {step === 'positions' && (
              <div style={{ padding: '10px 14px' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '8px' }}>选择持仓级别</div>
                <div style={{ display: 'flex', gap: '6px', marginBottom: '10px' }}>
                  {['L1', 'L2', 'L3'].map(lv => (
                    <button
                      key={lv}
                      onClick={() => setLevel(lv)}
                      style={{
                        fontSize: '12px', padding: '4px 12px', borderRadius: '4px',
                        border: level === lv ? '1px solid var(--accent)' : '1px solid var(--border-subtle)',
                        background: level === lv ? 'rgba(94,106,210,0.12)' : 'transparent',
                        color: level === lv ? 'var(--accent)' : 'var(--text-secondary)',
                        cursor: 'pointer', fontWeight: level === lv ? 510 : 400,
                      }}
                    >
                      {lv}
                    </button>
                  ))}
                </div>
                <div style={{ display: 'flex', gap: '6px' }}>
                  <button onClick={submitPositions} disabled={isPending} style={confirmBtnStyle}>
                    {isPending ? '添加中...' : '确认'}
                  </button>
                  <button onClick={() => setStep(null)} style={cancelBtnStyle}>返回</button>
                </div>
              </div>
            )}

            {/* Candidate: memo input */}
            {step === 'candidate' && (
              <div style={{ padding: '10px 14px' }}>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '6px' }}>备注 (选填)</div>
                <input
                  value={memo}
                  onChange={e => setMemo(e.target.value)}
                  placeholder="添加备注..."
                  style={{
                    width: '100%', fontSize: '12px', padding: '5px 8px', borderRadius: '4px',
                    border: '1px solid var(--border-std)', background: 'var(--bg-input)',
                    color: 'var(--text-primary)', marginBottom: '8px', boxSizing: 'border-box',
                  }}
                />
                <div style={{ display: 'flex', gap: '6px' }}>
                  <button onClick={submitCandidate} disabled={isPending} style={confirmBtnStyle}>
                    {isPending ? '添加中...' : '确认'}
                  </button>
                  <button onClick={() => setStep(null)} style={cancelBtnStyle}>返回</button>
                </div>
              </div>
            )}

            {/* Theme: list active themes */}
            {step === 'theme' && (
              <div>
                <div style={{ padding: '8px 14px', fontSize: '11px', color: 'var(--text-muted)', borderBottom: '1px solid var(--border-subtle)' }}>
                  选择主题池
                  <span onClick={() => setStep(null)} style={{ float: 'right', cursor: 'pointer', color: 'var(--accent)' }}>返回</span>
                </div>
                {themes.length === 0 ? (
                  <div style={{ padding: '12px 14px', fontSize: '12px', color: 'var(--text-muted)' }}>
                    暂无活跃主题池
                  </div>
                ) : (
                  <div style={{ maxHeight: '200px', overflowY: 'auto' }}>
                    {themes.map(t => (
                      <div
                        key={t.id}
                        onClick={() => submitTheme(t.id)}
                        style={{ ...menuItemStyle, fontSize: '12px' }}
                        onMouseEnter={hoverIn} onMouseLeave={hoverOut}
                      >
                        <span>{t.name}</span>
                        <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginLeft: '8px' }}>
                          {t.stock_count}只
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </DropdownPortal>
      )}
    </div>
  );
}

// Shared styles
const menuItemStyle: React.CSSProperties = {
  padding: '9px 14px', fontSize: '13px', cursor: 'pointer',
  color: 'var(--text-secondary)', borderBottom: '1px solid var(--border-subtle)',
  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
};

const confirmBtnStyle: React.CSSProperties = {
  fontSize: '12px', padding: '5px 14px', borderRadius: '5px',
  background: 'var(--accent)', color: '#fff', border: 'none', cursor: 'pointer', fontWeight: 510,
};

const cancelBtnStyle: React.CSSProperties = {
  fontSize: '12px', padding: '5px 14px', borderRadius: '5px',
  background: 'transparent', color: 'var(--text-muted)',
  border: '1px solid var(--border-subtle)', cursor: 'pointer',
};

function hoverIn(e: React.MouseEvent) {
  (e.currentTarget as HTMLElement).style.background = 'var(--bg-card-hover)';
}
function hoverOut(e: React.MouseEvent) {
  (e.currentTarget as HTMLElement).style.background = 'transparent';
}
