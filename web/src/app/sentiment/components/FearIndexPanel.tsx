'use client';

import { useQuery } from '@tanstack/react-query';

const cardStyle: React.CSSProperties = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border-subtle)',
  borderRadius: '8px',
  padding: '16px 20px',
};

export default function FearIndexPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ['fear-index'],
    queryFn: async () => {
      const res = await fetch('/api/sentiment/fear-index');
      if (!res.ok) throw new Error('Failed to fetch fear index');
      return res.json();
    },
    refetchInterval: 300000,
  });

  const { data: history } = useQuery({
    queryKey: ['fear-index-history'],
    queryFn: async () => {
      const res = await fetch('/api/sentiment/fear-index/history?days=7');
      if (!res.ok) throw new Error('Failed to fetch history');
      return res.json();
    },
  });

  if (isLoading) {
    return <div style={{ color: 'var(--text-tertiary)', fontSize: '13px' }}>加载中...</div>;
  }
  if (!data) return null;

  const scoreColor = (score: number) => {
    if (score <= 20) return '#e5534b';
    if (score <= 40) return '#c69026';
    if (score <= 60) return '#8a8f98';
    if (score <= 80) return '#27a644';
    return '#10b981';
  };

  const color = scoreColor(data.fear_greed_score);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* Score bar */}
      <div style={cardStyle}>
        <div style={{ fontSize: '13px', fontWeight: 510, color: 'var(--text-secondary)', marginBottom: '16px' }}>
          综合恐慌/贪婪评分
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
          <div style={{ flex: 1 }}>
            <div style={{ height: '8px', background: 'var(--bg-elevated)', borderRadius: '4px', overflow: 'hidden' }}>
              <div
                style={{
                  height: '100%',
                  width: `${data.fear_greed_score}%`,
                  background: color,
                  borderRadius: '4px',
                  transition: 'width 0.5s ease',
                }}
              />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-muted)', marginTop: '6px' }}>
              <span>极度恐慌</span>
              <span>中性</span>
              <span>极度贪婪</span>
            </div>
          </div>
          <div style={{ textAlign: 'center', flexShrink: 0 }}>
            <div style={{ fontSize: '40px', fontWeight: 590, color, letterSpacing: '-1px', lineHeight: 1 }}>
              {data.fear_greed_score}
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginTop: '4px' }}>
              {data.market_regime}
            </div>
          </div>
        </div>
      </div>

      {/* 4 indicator cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
        {[
          { label: 'VIX 恐慌指数', value: data.vix.toFixed(2), sub: data.vix_level },
          { label: 'OVX 原油波动率', value: data.ovx.toFixed(2), sub: '能源市场情绪' },
          { label: 'GVZ 黄金波动率', value: data.gvz.toFixed(2), sub: '避险情绪' },
          { label: 'US10Y 收益率', value: `${data.us10y.toFixed(2)}%`, sub: '利率水平' },
        ].map((item) => (
          <div key={item.label} style={cardStyle}>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '8px' }}>{item.label}</div>
            <div style={{ fontSize: '24px', fontWeight: 590, color: 'var(--text-primary)', letterSpacing: '-0.4px' }}>
              {item.value}
            </div>
            <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginTop: '4px' }}>{item.sub}</div>
          </div>
        ))}
      </div>

      {/* Strategy recommendation */}
      <div style={cardStyle}>
        <div style={{ fontSize: '13px', fontWeight: 510, color: 'var(--text-secondary)', marginBottom: '12px' }}>
          策略建议
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
            <div style={{ fontSize: '12px', color: 'var(--text-muted)', flexShrink: 0, paddingTop: '1px' }}>利率</div>
            <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>{data.us10y_strategy}</div>
          </div>
          {data.risk_alert && (
            <div
              style={{
                display: 'flex',
                gap: '12px',
                alignItems: 'flex-start',
                background: 'rgba(229,83,75,0.08)',
                border: '1px solid rgba(229,83,75,0.2)',
                borderRadius: '6px',
                padding: '10px 12px',
              }}
            >
              <div style={{ fontSize: '11px', color: '#e5534b', flexShrink: 0, paddingTop: '1px', fontWeight: 510 }}>
                [WARN]
              </div>
              <div style={{ fontSize: '13px', color: '#e5534b' }}>{data.risk_alert}</div>
            </div>
          )}
        </div>
      </div>

      {/* 7-day history */}
      {history && history.data && history.data.length > 0 && (
        <div style={cardStyle}>
          <div style={{ fontSize: '13px', fontWeight: 510, color: 'var(--text-secondary)', marginBottom: '12px' }}>
            7日趋势
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {history.data.slice(0, 7).map((item: Record<string, unknown>, idx: number) => {
              const sc = Number(item.fear_greed_score);
              const c = scoreColor(sc);
              return (
                <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)', width: '72px', flexShrink: 0 }}>
                    {new Date(String(item.timestamp)).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })}
                  </div>
                  <div style={{ flex: 1, height: '6px', background: 'var(--bg-elevated)', borderRadius: '3px', overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${sc}%`, background: c, borderRadius: '3px' }} />
                  </div>
                  <div style={{ fontSize: '12px', fontWeight: 510, color: c, width: '28px', textAlign: 'right', flexShrink: 0 }}>
                    {sc}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
