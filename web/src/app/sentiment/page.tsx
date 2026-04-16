'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import ReactMarkdown from 'react-markdown';
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

const mdComponents: React.ComponentProps<typeof ReactMarkdown>['components'] = {
  h1: ({ children }) => (
    <div style={{ fontWeight: 700, color: 'var(--text-primary)', fontSize: '14px', margin: '16px 0 6px', paddingLeft: '8px', borderLeft: '3px solid var(--accent)' }}>
      {children}
    </div>
  ),
  h2: ({ children }) => (
    <div style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '13px', margin: '14px 0 5px', paddingLeft: '8px', borderLeft: '3px solid var(--accent)' }}>
      {children}
    </div>
  ),
  h3: ({ children }) => (
    <div style={{ fontWeight: 600, color: 'var(--text-secondary)', fontSize: '12px', margin: '10px 0 4px' }}>
      {children}
    </div>
  ),
  p: ({ children }) => (
    <p style={{ margin: '4px 0', fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.8 }}>
      {children}
    </p>
  ),
  strong: ({ children }) => (
    <strong style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{children}</strong>
  ),
  ul: ({ children }) => (
    <ul style={{ margin: '4px 0', paddingLeft: '18px', fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.8 }}>
      {children}
    </ul>
  ),
  ol: ({ children }) => (
    <ol style={{ margin: '4px 0', paddingLeft: '18px', fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.8 }}>
      {children}
    </ol>
  ),
  li: ({ children }) => (
    <li style={{ margin: '2px 0' }}>{children}</li>
  ),
  hr: () => (
    <hr style={{ border: 'none', borderTop: '1px solid var(--border-subtle)', margin: '10px 0' }} />
  ),
  blockquote: ({ children }) => (
    <blockquote style={{
      margin: '8px 0', padding: '8px 12px',
      borderLeft: '3px solid var(--border-subtle)',
      background: 'var(--bg-elevated)', borderRadius: '0 4px 4px 0',
      fontSize: '12px', color: 'var(--text-muted)',
    }}>
      {children}
    </blockquote>
  ),
  code: ({ children }) => (
    <code style={{
      fontSize: '11px', fontFamily: 'monospace',
      background: 'var(--bg-elevated)', padding: '1px 5px',
      borderRadius: '3px', color: 'var(--accent)',
    }}>
      {children}
    </code>
  ),
};

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

  const isAborted = briefing?.content?.startsWith('[速递中止]') || briefing?.content?.startsWith('[briefing aborted]');
  const hasContent = briefing?.content && !isLoading && !isAborted;
  const sessionLabel = session === 'morning' ? '盘前速递' : '收盘复盘';

  return (
    <div style={{
      background: 'linear-gradient(135deg, var(--bg-card), var(--bg-elevated))',
      border: '1px solid var(--border-subtle)',
      borderRadius: '12px',
      padding: '18px 22px',
      marginBottom: '20px',
      boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
    }}>
      {/* Header row */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{
            fontSize: '11px', fontWeight: 700, letterSpacing: '0.8px',
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
                  padding: '3px 10px', fontSize: '10px', borderRadius: '10px',
                  border: session === s ? '1px solid var(--accent)' : '1px solid transparent',
                  background: session === s ? 'var(--accent)12' : 'transparent',
                  color: session === s ? 'var(--accent)' : 'var(--text-muted)',
                  cursor: 'pointer', fontWeight: 520, transition: 'all 0.15s',
                }}
              >
                {s === 'morning' ? '08:30 盘前' : '18:00 盘后'}
              </button>
            ))}
          </div>
          {briefing?.date && !isLoading && (
            <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{briefing.date}</span>
          )}
          {briefing?.cached && hasContent && (
            <span style={{
              fontSize: '9px', fontWeight: 500, padding: '1px 6px',
              borderRadius: '8px', background: 'rgba(34,197,94,0.1)',
              color: '#22c55e',
            }}>
              cached
            </span>
          )}
        </div>
        <button
          onClick={() => refetch()}
          disabled={isLoading}
          style={{
            fontSize: '11px', padding: '4px 14px', borderRadius: '6px',
            border: '1px solid var(--accent)40',
            background: isLoading ? 'var(--bg-card)' : 'var(--accent)10',
            color: 'var(--accent)', cursor: isLoading ? 'wait' : 'pointer',
            fontWeight: 520, opacity: isLoading ? 0.6 : 1,
            transition: 'all 0.15s',
          }}
        >
          {isLoading ? 'AI 分析中...' : hasContent ? '重新生成' : '生成解读'}
        </button>
      </div>

      {/* Content */}
      {isLoading && (
        <div style={{
          fontSize: '12px', color: 'var(--text-muted)', padding: '16px 0 4px',
          fontStyle: 'italic', display: 'flex', alignItems: 'center', gap: '8px',
        }}>
          <span style={{
            display: 'inline-block', width: '12px', height: '12px',
            border: '2px solid var(--border-subtle)', borderTopColor: 'var(--accent)',
            borderRadius: '50%', animation: 'spin 0.8s linear infinite',
          }} />
          正在综合分析 A 股大盘信号 + 全球资产数据...
        </div>
      )}
      {error && !isLoading && !hasContent && !isAborted && (
        <div style={{ fontSize: '12px', color: 'var(--text-muted)', padding: '8px 0 0' }}>
          点击「生成解读」获取 AI 分析
        </div>
      )}
      {isAborted && !isLoading && (
        <div style={{
          marginTop: '12px', padding: '10px 14px',
          background: 'rgba(198,144,38,0.08)', border: '1px solid rgba(198,144,38,0.25)',
          borderRadius: '8px', display: 'flex', alignItems: 'flex-start', gap: '8px',
        }}>
          <span style={{ fontSize: '14px', flexShrink: 0 }}>-</span>
          <div>
            <div style={{ fontSize: '12px', fontWeight: 510, color: '#c69026', marginBottom: '2px' }}>数据暂不充足，无法生成速递</div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
              {briefing.content.replace('[速递中止] ', '').replace('[briefing aborted] ', '')}
            </div>
          </div>
        </div>
      )}
      {hasContent && (
        <div style={{ marginTop: '14px' }}>
          <div
            style={{
              fontSize: '13px', color: 'var(--text-secondary)', lineHeight: 1.85,
              maxHeight: expanded ? 'none' : '160px',
              overflow: 'hidden',
              position: 'relative',
            }}
          >
            <ReactMarkdown components={mdComponents}>{briefing.content}</ReactMarkdown>
            {!expanded && (
              <div style={{
                position: 'absolute', bottom: 0, left: 0, right: 0, height: '50px',
                background: 'linear-gradient(transparent, var(--bg-card) 70%)',
                pointerEvents: 'none',
              }} />
            )}
          </div>
          <button
            onClick={() => setExpanded(!expanded)}
            style={{
              marginTop: '4px', fontSize: '11px', color: 'var(--accent)',
              background: 'none', border: 'none', cursor: 'pointer', padding: '4px 0',
              fontWeight: 520,
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
              data-track="tab_switch"
              data-track-tab={tab.key}
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
