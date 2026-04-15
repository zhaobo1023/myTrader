'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import apiClient from '@/lib/api-client';
import AppShell from '@/components/layout/AppShell';
import DashboardView from './components/DashboardView';
import OverviewCards from './components/OverviewCards';
import FearIndexPanel from './components/FearIndexPanel';
import NewsSentimentPanel from './components/NewsSentimentPanel';
import EventSignalPanel from './components/EventSignalPanel';
import PolymarketPanel from './components/PolymarketPanel';
import GlobalAssetsPanel from './components/GlobalAssetsPanel';

type MainTab = 'dashboard' | 'global' | 'sentiment';
type SentimentTab = 'fear' | 'news' | 'events' | 'polymarket';

const MAIN_TABS: { key: MainTab; label: string }[] = [
  { key: 'dashboard',  label: '大盘总览' },
  { key: 'global',     label: '全球资产' },
  { key: 'sentiment',  label: '舆情详情' },
];

const SENTIMENT_TABS: { key: SentimentTab; label: string }[] = [
  { key: 'fear',        label: '恐慌指数' },
  { key: 'news',        label: '新闻舆情' },
  { key: 'events',      label: '事件信号' },
  { key: 'polymarket',  label: '预测市场' },
];

// ---------------------------------------------------------------------------
// AI Briefing Card (shown above tabs)
// ---------------------------------------------------------------------------

function AIBriefingCard() {
  const [session, setSession] = useState<'morning' | 'evening'>(() => {
    return new Date().getHours() < 15 ? 'morning' : 'evening';
  });
  const [expanded, setExpanded] = useState(false);

  const { data: briefing, isLoading, error, refetch } = useQuery({
    queryKey: ['globalBriefing', session],
    queryFn: () => apiClient.get('/api/market/global-briefing', { params: { session }, timeout: 60000 }).then((r) => r.data),
    staleTime: 10 * 60 * 1000,
    retry: 1,
    enabled: false,
  });

  const hasContent = briefing?.content && !isLoading;
  const sessionLabel = session === 'morning' ? '盘前速递' : '收盘复盘';

  return (
    <div style={{
      background: 'linear-gradient(135deg, var(--bg-card), var(--bg-elevated))',
      border: '1px solid var(--border-subtle)',
      borderRadius: '10px',
      padding: '16px 20px',
      marginBottom: '20px',
    }}>
      {/* Header row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{
            fontSize: '11px', fontWeight: 600, letterSpacing: '0.5px',
            color: 'var(--accent)', textTransform: 'uppercase',
          }}>
            AI {sessionLabel}
          </span>
          <div style={{ display: 'flex', gap: '2px' }}>
            {(['morning', 'evening'] as const).map((s) => (
              <button
                key={s}
                onClick={() => setSession(s)}
                style={{
                  padding: '2px 8px', fontSize: '10px', borderRadius: '10px',
                  border: session === s ? '1px solid var(--accent)' : '1px solid transparent',
                  background: session === s ? 'var(--accent)10' : 'transparent',
                  color: session === s ? 'var(--accent)' : 'var(--text-muted)',
                  cursor: 'pointer', fontWeight: 510,
                }}
              >
                {s === 'morning' ? '08:30 盘前' : '18:00 盘后'}
              </button>
            ))}
          </div>
          {briefing?.date && !isLoading && (
            <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{briefing.date}</span>
          )}
        </div>
        <button
          onClick={() => refetch()}
          disabled={isLoading}
          style={{
            fontSize: '11px', padding: '4px 12px', borderRadius: '6px',
            border: '1px solid var(--accent)40',
            background: isLoading ? 'var(--bg-card)' : 'var(--accent)10',
            color: 'var(--accent)', cursor: isLoading ? 'wait' : 'pointer',
            fontWeight: 510, opacity: isLoading ? 0.6 : 1,
          }}
        >
          {isLoading ? 'AI 分析中...' : hasContent ? '重新生成' : '生成解读'}
        </button>
      </div>

      {/* Content */}
      {isLoading && (
        <div style={{ fontSize: '12px', color: 'var(--text-muted)', padding: '12px 0 4px', fontStyle: 'italic' }}>
          正在综合分析A股大盘信号 + 全球资产数据...
        </div>
      )}
      {error && !isLoading && !hasContent && (
        <div style={{ fontSize: '12px', color: 'var(--text-muted)', padding: '8px 0 0' }}>
          点击「生成解读」获取 AI 分析
        </div>
      )}
      {hasContent && (
        <div style={{ marginTop: '12px' }}>
          <div
            style={{
              fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.8,
              maxHeight: expanded ? 'none' : '120px',
              overflow: 'hidden',
              position: 'relative',
            }}
          >
            {briefing.content.split('\n').map((line: string, i: number) => {
              if (line.startsWith('###') || line.startsWith('##')) {
                return <div key={i} style={{ fontWeight: 590, color: 'var(--text-primary)', margin: '10px 0 4px', fontSize: '13px' }}>{line.replace(/^#+\s*/, '')}</div>;
              }
              if (line.startsWith('**') && line.endsWith('**')) {
                return <div key={i} style={{ fontWeight: 510, color: 'var(--text-primary)', margin: '8px 0 2px' }}>{line.replace(/\*\*/g, '')}</div>;
              }
              if (line.startsWith('---')) return <hr key={i} style={{ border: 'none', borderTop: '1px solid var(--border-subtle)', margin: '8px 0' }} />;
              if (!line.trim()) return null;
              // Inline bold
              const parts = line.split(/(\*\*[^*]+\*\*)/g);
              return (
                <div key={i} style={{ margin: '2px 0' }}>
                  {parts.map((p, j) =>
                    p.startsWith('**') && p.endsWith('**')
                      ? <strong key={j} style={{ color: 'var(--text-primary)', fontWeight: 510 }}>{p.replace(/\*\*/g, '')}</strong>
                      : <span key={j}>{p}</span>
                  )}
                </div>
              );
            })}
            {!expanded && (
              <div style={{
                position: 'absolute', bottom: 0, left: 0, right: 0, height: '40px',
                background: 'linear-gradient(transparent, var(--bg-card))',
              }} />
            )}
          </div>
          <button
            onClick={() => setExpanded(!expanded)}
            style={{
              marginTop: '4px', fontSize: '11px', color: 'var(--accent)',
              background: 'none', border: 'none', cursor: 'pointer', padding: '4px 0',
            }}
          >
            {expanded ? '收起' : '展开全文'}
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------

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
      <div style={{ marginBottom: '16px' }}>
        <h1 style={{ fontSize: '20px', fontWeight: 590, color: 'var(--text-primary)', letterSpacing: '-0.3px' }}>
          大盘
        </h1>
      </div>

      {/* AI Briefing — above all tabs */}
      <AIBriefingCard />

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
      {mainTab === 'global' && <GlobalAssetsPanel />}

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
