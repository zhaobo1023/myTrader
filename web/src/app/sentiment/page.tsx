'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import AppShell from '@/components/layout/AppShell';
import OverviewCards from './components/OverviewCards';
import FearIndexPanel from './components/FearIndexPanel';
import NewsSentimentPanel from './components/NewsSentimentPanel';
import EventSignalPanel from './components/EventSignalPanel';
import PolymarketPanel from './components/PolymarketPanel';

type SentimentTab = 'fear' | 'news' | 'events' | 'polymarket';

const TABS: { key: SentimentTab; label: string }[] = [
  { key: 'fear',        label: '恐慌指数' },
  { key: 'news',        label: '新闻舆情' },
  { key: 'events',      label: '事件信号' },
  { key: 'polymarket',  label: '预测市场' },
];

export default function SentimentPage() {
  const [activeTab, setActiveTab] = useState<SentimentTab>('fear');

  const { data: overview, isLoading } = useQuery({
    queryKey: ['sentiment-overview'],
    queryFn: async () => {
      const res = await fetch('/api/sentiment/overview');
      if (!res.ok) throw new Error('Failed to fetch overview');
      return res.json();
    },
    refetchInterval: 60000,
  });

  return (
    <AppShell>
      <div style={{ marginBottom: '24px' }}>
        <h1 style={{ fontSize: '20px', fontWeight: 590, color: 'var(--text-primary)', letterSpacing: '-0.3px', marginBottom: '4px' }}>
          舆情监控
        </h1>
        <p style={{ fontSize: '13px', color: 'var(--text-tertiary)' }}>
          实时监控市场情绪、新闻事件和预测市场
        </p>
      </div>

      <OverviewCards data={overview} isLoading={isLoading} />

      <div
        style={{
          display: 'flex',
          gap: '2px',
          borderBottom: '1px solid var(--border-subtle)',
          marginBottom: '24px',
        }}
      >
        {TABS.map((tab) => {
          const active = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={{
                padding: '8px 16px',
                fontSize: '13px',
                fontWeight: active ? 510 : 400,
                color: active ? 'var(--text-primary)' : 'var(--text-tertiary)',
                background: 'none',
                border: 'none',
                borderBottom: active ? '2px solid var(--accent)' : '2px solid transparent',
                cursor: 'pointer',
                marginBottom: '-1px',
                transition: 'color 0.12s',
              }}
              onMouseEnter={(e) => { if (!active) (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-secondary)'; }}
              onMouseLeave={(e) => { if (!active) (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-tertiary)'; }}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      <div>
        {activeTab === 'fear'       && <FearIndexPanel />}
        {activeTab === 'news'       && <NewsSentimentPanel />}
        {activeTab === 'events'     && <EventSignalPanel />}
        {activeTab === 'polymarket' && <PolymarketPanel />}
      </div>
    </AppShell>
  );
}
