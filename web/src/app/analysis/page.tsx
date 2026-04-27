'use client';

import { useRouter } from 'next/navigation';
import AppShell from '@/components/layout/AppShell';
import apiClient from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TechReportCard {
  id: number;
  stock_code: string;
  stock_name: string;
  trade_date: string;
  score: number;
  score_label: string;
  max_severity: string;
  summary: string;
  signal_count: number;
  created_at: string;
  has_html?: boolean;
}

interface ListResponse {
  total: number;
  items: TechReportCard[];
}

// ---------------------------------------------------------------------------
// Style helpers
// ---------------------------------------------------------------------------

const severityColor = (s: string) => {
  if (s === 'RED') return '#e5534b';
  if (s === 'YELLOW') return '#c69026';
  if (s === 'GREEN') return '#27a644';
  return 'var(--text-muted)';
};

const scoreBadgeStyle = (score: number): React.CSSProperties => {
  const color = score >= 20 ? '#27a644' : score <= -20 ? '#e5534b' : '#c69026';
  return {
    display: 'inline-block', padding: '2px 8px', borderRadius: '12px',
    fontSize: '12px', fontWeight: 510, color,
    background: `${color}18`, border: `1px solid ${color}40`,
  };
};

// ---------------------------------------------------------------------------
// Page: Report Browser (slimmed from original analysis page)
// All stock-specific analysis features moved to /stock page.
// ---------------------------------------------------------------------------

export default function AnalysisPage() {
  const router = useRouter();

  const { data: listData } = useQuery<ListResponse>({
    queryKey: ['tech-reports'],
    queryFn: () => apiClient.get('/api/analysis/reports').then((r) => r.data),
    staleTime: 60000,
  });

  const handleCardClick = (card: TechReportCard) => {
    router.push(`/stock?code=${encodeURIComponent(card.stock_code)}&tab=kline-tech`);
  };

  return (
    <AppShell>
      <div style={{ display: 'flex', alignItems: 'center', gap: '16px', marginBottom: '24px', flexWrap: 'wrap' }}>
        <h1 style={{ fontSize: '20px', fontWeight: 590, color: 'var(--text-primary)', letterSpacing: '-0.3px', margin: 0 }}>
          报告浏览
        </h1>
        {listData && (
          <span style={{ fontSize: '12px', color: 'var(--text-muted)', marginLeft: 'auto' }}>
            共 {listData.total} 份报告
          </span>
        )}
      </div>

      <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '14px' }}>
        最近生成的技术面报告（点击卡片跳转到个股分析）
      </div>

      {!listData?.items?.length ? (
        <div style={{ padding: '60px 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: '14px' }}>
          暂无报告记录
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '14px' }}>
          {listData.items.map((card) => (
            <div
              key={card.id}
              onClick={() => handleCardClick(card)}
              style={{
                background: 'var(--bg-panel)',
                border: '1px solid var(--border-subtle)',
                borderLeft: `3px solid ${severityColor(card.max_severity)}`,
                borderRadius: '8px',
                padding: '14px 16px',
                cursor: 'pointer',
                transition: 'background 0.12s',
              }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-card)'; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-panel)'; }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                <div>
                  <div style={{ fontSize: '14px', fontWeight: 510, color: 'var(--text-primary)' }}>
                    {card.stock_name || card.stock_code}
                  </div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '1px' }}>
                    {card.stock_code} &nbsp;&middot;&nbsp; {card.trade_date}
                  </div>
                </div>
                <span style={scoreBadgeStyle(card.score)}>{card.score > 0 ? '+' : ''}{card.score}</span>
              </div>
              <div style={{ display: 'flex', gap: '6px', marginBottom: '8px' }}>
                <span style={{ fontSize: '11px', color: 'var(--text-secondary)', background: 'var(--bg-card)', padding: '1px 6px', borderRadius: '4px' }}>
                  {card.score_label}
                </span>
                {card.max_severity !== 'NONE' && (
                  <span style={{ fontSize: '11px', color: severityColor(card.max_severity), background: `${severityColor(card.max_severity)}15`, padding: '1px 6px', borderRadius: '4px' }}>
                    {card.max_severity}
                  </span>
                )}
              </div>
              <div style={{
                fontSize: '12px', color: 'var(--text-secondary)', lineHeight: '1.5',
                display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
                marginBottom: '8px',
              }}>
                {card.summary}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{card.signal_count} 个信号</div>
            </div>
          ))}
        </div>
      )}
    </AppShell>
  );
}
