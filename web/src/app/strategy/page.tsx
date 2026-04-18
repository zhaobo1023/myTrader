'use client';

import { Suspense, useState, useEffect } from 'react';
import { useSearchParams, useRouter } from 'next/navigation';
import AppShell from '@/components/layout/AppShell';
import StrategyContent from './StrategyContent';
import ThemePoolContent from '@/app/theme-pool/ThemePoolContent';
import IndustryStockScreener from './components/IndustryStockScreener';

type Tab = 'preset' | 'theme' | 'industry';

const TABS: { key: Tab; label: string }[] = [
  { key: 'preset', label: '预设策略' },
  { key: 'theme', label: '主题选股' },
  { key: 'industry', label: '行业选股' },
];

function StrategyInner() {
  const searchParams = useSearchParams();
  const router = useRouter();

  const tabParam = searchParams.get('tab');
  const [activeTab, setActiveTab] = useState<Tab>(
    tabParam === 'theme' ? 'theme' : 'preset'
  );

  useEffect(() => {
    const t = searchParams.get('tab');
    if (t === 'theme') setActiveTab('theme');
    else if (t === 'industry') setActiveTab('industry');
    else setActiveTab('preset');
  }, [searchParams]);

  function switchTab(tab: Tab) {
    setActiveTab(tab);
    const url = tab === 'preset' ? '/strategy' : `/strategy?tab=${tab}`;
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

      {activeTab === 'preset' && <StrategyContent />}
      {activeTab === 'theme' && <ThemePoolContent />}
      {activeTab === 'industry' && <IndustryStockScreener />}
    </>
  );
}

export default function StrategyPage() {
  return (
    <AppShell>
      <Suspense fallback={null}>
        <StrategyInner />
      </Suspense>
    </AppShell>
  );
}
