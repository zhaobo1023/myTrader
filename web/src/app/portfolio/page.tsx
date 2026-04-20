'use client';

import React, { Suspense, useState, useEffect } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import AppShell from '@/components/layout/AppShell';
import PositionsContent from '@/app/positions/PositionsContent';
import SimPoolContent from '@/app/sim-pool/SimPoolContent';
import CandidatePoolContent from '@/app/candidate-pool/CandidatePoolContent';
import TradeLogContent from '@/app/trade-log/TradeLogContent';
import StockSearchInput from '@/components/stock/StockSearchInput';
import { StockSearchResult } from '@/lib/api-client';
import { useAddToPositions, useAddToCandidate } from '@/hooks/useStockAdd';

type Tab = 'positions' | 'sim' | 'candidate' | 'log';
type AddTarget = 'positions' | 'candidate';

const TABS: { key: Tab; label: string }[] = [
  { key: 'positions', label: '实盘持仓' },
  { key: 'sim', label: '模拟池' },
  { key: 'candidate', label: '候选观察' },
  { key: 'log', label: '调仓日志' },
];

// ---------------------------------------------------------------------------
// Inline add form shown after selecting a stock from search
// ---------------------------------------------------------------------------
function AddStockForm({
  stock,
  target,
  onChangeTarget,
  onDone,
  onCancel,
}: {
  stock: StockSearchResult;
  target: AddTarget;
  onChangeTarget: (t: AddTarget) => void;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [level, setLevel] = useState('L2');
  const [memo, setMemo] = useState('');
  const addPos = useAddToPositions();
  const addCand = useAddToCandidate();

  const isPending = addPos.isPending || addCand.isPending;

  async function submit() {
    try {
      if (target === 'positions') {
        await addPos.mutateAsync({ stock_code: stock.stock_code, stock_name: stock.stock_name, level });
      } else {
        await addCand.mutateAsync({
          stock_code: stock.stock_code,
          stock_name: stock.stock_name,
          source_type: 'manual',
          memo: memo || null,
        });
      }
      onDone();
    } catch {
      // mutation error handled internally
    }
  }

  const segBtnStyle = (active: boolean): React.CSSProperties => ({
    fontSize: '12px', padding: '4px 14px', borderRadius: '4px',
    border: active ? '1px solid var(--accent)' : '1px solid var(--border-subtle)',
    background: active ? 'rgba(94,106,210,0.12)' : 'transparent',
    color: active ? 'var(--accent)' : 'var(--text-muted)',
    cursor: 'pointer', fontWeight: active ? 510 : 400,
  });

  return (
    <div style={{
      background: 'var(--bg-card)', border: '1px solid var(--border-std)', borderRadius: '8px',
      padding: '14px 16px', marginBottom: '16px',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '13px', fontWeight: 510, color: 'var(--text-primary)' }}>
          {stock.stock_name}
        </span>
        <span style={{ fontSize: '12px', fontFamily: 'var(--font-geist-mono)', color: 'var(--text-muted)' }}>
          {stock.stock_code}
        </span>
        {stock.industry && <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>{stock.industry}</span>}
        <div style={{ flex: 1 }} />
        <button onClick={onCancel} style={{ fontSize: '12px', color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer' }}>
          取消
        </button>
      </div>

      {/* Target selector */}
      <div style={{ display: 'flex', gap: '6px', alignItems: 'center', marginBottom: '10px' }}>
        <span style={{ fontSize: '12px', color: 'var(--text-muted)', marginRight: '4px' }}>目标：</span>
        <button onClick={() => onChangeTarget('positions')} style={segBtnStyle(target === 'positions')}>实盘持仓</button>
        <button onClick={() => onChangeTarget('candidate')} style={segBtnStyle(target === 'candidate')}>候选观察</button>
      </div>

      {/* Target-specific fields */}
      {target === 'positions' && (
        <div style={{ display: 'flex', gap: '6px', alignItems: 'center', marginBottom: '10px' }}>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>级别：</span>
          {['L1', 'L2', 'L3'].map(lv => (
            <button key={lv} onClick={() => setLevel(lv)} style={segBtnStyle(level === lv)}>{lv}</button>
          ))}
        </div>
      )}

      {target === 'candidate' && (
        <input
          value={memo}
          onChange={e => setMemo(e.target.value)}
          placeholder="备注 (选填)"
          style={{
            width: '100%', fontSize: '12px', padding: '6px 10px', borderRadius: '5px',
            border: '1px solid var(--border-subtle)', background: 'var(--bg-input)',
            color: 'var(--text-primary)', marginBottom: '10px', boxSizing: 'border-box',
          }}
        />
      )}

      <button onClick={submit} disabled={isPending} style={{
        fontSize: '12px', padding: '6px 18px', borderRadius: '6px',
        background: isPending ? 'var(--bg-card-hover)' : 'var(--accent)',
        color: isPending ? 'var(--text-muted)' : '#fff',
        border: 'none', cursor: isPending ? 'default' : 'pointer', fontWeight: 510,
      }}>
        {isPending ? '添加中...' : '确认添加'}
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// PortfolioInner
// ---------------------------------------------------------------------------
function PortfolioInner() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const tabParam = searchParams.get('tab');
  const [activeTab, setActiveTab] = useState<Tab>(
    tabParam === 'sim' ? 'sim' : 'positions'
  );
  const [selectedStock, setSelectedStock] = useState<StockSearchResult | null>(null);
  const [addTarget, setAddTarget] = useState<AddTarget>('positions');

  useEffect(() => {
    const t = searchParams.get('tab');
    if (t === 'sim') setActiveTab('sim');
    else if (t === 'candidate') setActiveTab('candidate');
    else if (t === 'log') setActiveTab('log');
    else setActiveTab('positions');
  }, [searchParams]);

  function switchTab(tab: Tab) {
    setActiveTab(tab);
    const url = tab === 'positions' ? '/portfolio' : `/portfolio?tab=${tab}`;
    router.replace(url, { scroll: false });
  }

  function handleSelectStock(stock: StockSearchResult) {
    setSelectedStock(stock);
    // Default target matches active tab
    if (activeTab === 'candidate') setAddTarget('candidate');
    else setAddTarget('positions');
  }

  function handleAddDone() {
    setSelectedStock(null);
    // Switch to the target tab if different
    if (addTarget === 'positions' && activeTab !== 'positions') switchTab('positions');
    else if (addTarget === 'candidate' && activeTab !== 'candidate') switchTab('candidate');
  }

  const tabBtnStyle = (active: boolean): React.CSSProperties => ({
    padding: '8px 20px',
    fontSize: '13px',
    fontWeight: active ? 510 : 400,
    cursor: 'pointer',
    border: 'none',
    borderBottom: active ? '2px solid var(--accent)' : '2px solid transparent',
    background: 'transparent',
    color: active ? 'var(--text-primary)' : 'var(--text-tertiary)',
    transition: 'all 0.12s',
  });

  return (
    <>
      {/* Search bar */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px', flexWrap: 'wrap',
      }}>
        <StockSearchInput
          onSelect={handleSelectStock}
          placeholder="搜索添加股票..."
          width="280px"
        />
        <span style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
          搜索股票代码或名称，快速添加到实盘持仓或候选观察
        </span>
      </div>

      {/* Inline add form */}
      {selectedStock && (
        <AddStockForm
          stock={selectedStock}
          target={addTarget}
          onChangeTarget={setAddTarget}
          onDone={handleAddDone}
          onCancel={() => setSelectedStock(null)}
        />
      )}

      {/* Tabs */}
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: '20px', borderBottom: '1px solid var(--border-subtle)' }}>
        {TABS.map((t) => (
          <button key={t.key} style={tabBtnStyle(activeTab === t.key)} onClick={() => switchTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {activeTab === 'positions' && <PositionsContent />}
      {activeTab === 'sim' && <SimPoolContent />}
      {activeTab === 'candidate' && <CandidatePoolContent />}
      {activeTab === 'log' && <TradeLogContent />}
    </>
  );
}

export default function PortfolioPage() {
  return (
    <AppShell>
      <Suspense fallback={null}>
        <PortfolioInner />
      </Suspense>
    </AppShell>
  );
}
