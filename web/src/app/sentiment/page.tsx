'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import AppShell from '@/components/layout/AppShell';
import DashboardView from './components/DashboardView';
import OverviewCards from './components/OverviewCards';
import FearIndexPanel from './components/FearIndexPanel';
import NewsSentimentPanel from './components/NewsSentimentPanel';
import EventSignalPanel from './components/EventSignalPanel';
import PolymarketPanel from './components/PolymarketPanel';

type MainTab = 'dashboard' | 'sentiment';
type SentimentTab = 'fear' | 'news' | 'events' | 'polymarket';

const MAIN_TABS: { key: MainTab; label: string }[] = [
  { key: 'dashboard',  label: '大盘总览' },
  { key: 'sentiment',  label: '舆情详情' },
];

const SENTIMENT_TABS: { key: SentimentTab; label: string }[] = [
  { key: 'fear',        label: '恐慌指数' },
  { key: 'news',        label: '新闻舆情' },
  { key: 'events',      label: '事件信号' },
  { key: 'polymarket',  label: '预测市场' },
];

export default function SentimentPage() {
  const [mainTab, setMainTab] = useState<MainTab>('dashboard');
  const [sentimentTab, setSentimentTab] = useState<SentimentTab>('fear');

  const { data: overview, isLoading } = useQuery({
    queryKey: ['sentiment-overview'],
    queryFn: async () => {
      const res = await fetch('/api/sentiment/overview');
      if (!res.ok) throw new Error('Failed to fetch overview');
      return res.json();
    },
    refetchInterval: 60000,
    enabled: mainTab === 'sentiment',
  });

  return (
    <AppShell>
      {/* Page header */}
      <div style={{ marginBottom: '20px' }}>
        <h1 style={{ fontSize: '20px', fontWeight: 590, color: 'var(--text-primary)', letterSpacing: '-0.3px', marginBottom: '4px' }}>
          {mainTab === 'dashboard' ? '大盘总览' : '舆情监控'}
        </h1>
        <p style={{ fontSize: '13px', color: 'var(--text-tertiary)' }}>
          {mainTab === 'dashboard'
            ? '一屏掌握市场全貌: 温度、趋势、情绪、风格、股债、宏观'
            : '实时监控市场情绪、新闻事件和预测市场'}
        </p>
      </div>

      {/* Main tab switcher */}
      <div
        style={{
          display: 'flex',
          gap: '2px',
          borderBottom: '1px solid var(--border-subtle)',
          marginBottom: '20px',
        }}
      >
        {MAIN_TABS.map((tab) => {
          const active = mainTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setMainTab(tab.key)}
              style={{
                padding: '8px 20px',
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

      {/* Content */}
      {mainTab === 'dashboard' && <DashboardView />}

      {mainTab === 'sentiment' && (
        <>
          <OverviewCards data={overview} isLoading={isLoading} />

          {/* Sentiment sub-tabs */}
          <div
            style={{
              display: 'flex',
              gap: '2px',
              borderBottom: '1px solid var(--border-subtle)',
              marginBottom: '24px',
            }}
          >
            {SENTIMENT_TABS.map((tab) => {
              const active = sentimentTab === tab.key;
              return (
                <button
                  key={tab.key}
                  onClick={() => setSentimentTab(tab.key)}
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
            {sentimentTab === 'fear'       && <FearIndexPanel />}
            {sentimentTab === 'news'       && <NewsSentimentPanel />}
            {sentimentTab === 'events'     && <EventSignalPanel />}
            {sentimentTab === 'polymarket' && <PolymarketPanel />}
          </div>
        </>
      )}
    </AppShell>
  );
}
