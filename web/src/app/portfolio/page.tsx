'use client';

import { Suspense, useState, useEffect } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import AppShell from '@/components/layout/AppShell';
import PositionsContent from '@/app/positions/PositionsContent';
import SimPoolContent from '@/app/sim-pool/SimPoolContent';

type Tab = 'positions' | 'sim';

const TABS: { key: Tab; label: string }[] = [
  { key: 'positions', label: '实盘持仓' },
  { key: 'sim', label: '模拟池' },
];

function PortfolioInner() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const tabParam = searchParams.get('tab');
  const [activeTab, setActiveTab] = useState<Tab>(
    tabParam === 'sim' ? 'sim' : 'positions'
  );

  useEffect(() => {
    const t = searchParams.get('tab');
    if (t === 'sim') setActiveTab('sim');
    else setActiveTab('positions');
  }, [searchParams]);

  function switchTab(tab: Tab) {
    setActiveTab(tab);
    const url = tab === 'positions' ? '/portfolio' : '/portfolio?tab=sim';
    router.replace(url, { scroll: false });
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
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: '20px', borderBottom: '1px solid var(--border-subtle)' }}>
        {TABS.map((t) => (
          <button key={t.key} style={tabBtnStyle(activeTab === t.key)} onClick={() => switchTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {activeTab === 'positions' && <PositionsContent />}
      {activeTab === 'sim' && <SimPoolContent />}
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
