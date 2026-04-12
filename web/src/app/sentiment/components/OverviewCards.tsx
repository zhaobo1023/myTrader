'use client';

interface OverviewCardsProps {
  data?: {
    fear_index: {
      fear_greed_score: number;
      market_regime: string;
      vix: number;
      us10y: number;
    };
    event_count: number;
    bullish_count: number;
    bearish_count: number;
    smart_money_count: number;
  };
  isLoading: boolean;
}

const cardStyle: React.CSSProperties = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border-subtle)',
  borderRadius: '8px',
  padding: '16px 20px',
};

const labelStyle: React.CSSProperties = {
  fontSize: '11px',
  color: 'var(--text-muted)',
  textTransform: 'uppercase',
  letterSpacing: '0.5px',
  marginBottom: '8px',
};

const valueStyle: React.CSSProperties = {
  fontSize: '28px',
  fontWeight: 590,
  color: 'var(--text-primary)',
  letterSpacing: '-0.5px',
  lineHeight: 1,
};

const subStyle: React.CSSProperties = {
  fontSize: '12px',
  color: 'var(--text-tertiary)',
  marginTop: '6px',
};

export default function OverviewCards({ data, isLoading }: OverviewCardsProps) {
  if (isLoading) {
    return (
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', marginBottom: '24px' }}>
        {[1, 2, 3, 4].map((i) => (
          <div key={i} style={{ ...cardStyle, height: '88px', opacity: 0.4 }} />
        ))}
      </div>
    );
  }

  if (!data) return null;

  const regime = data.fear_index.market_regime;
  const regimeColor =
    regime.includes('fear') ? '#e5534b' :
    regime.includes('greed') ? '#27a644' :
    'var(--text-tertiary)';

  const regimeLabel: Record<string, string> = {
    extreme_fear:  '极度恐慌',
    fear:          '恐慌',
    neutral:       '中性',
    greed:         '贪婪',
    extreme_greed: '极度贪婪',
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', marginBottom: '24px' }}>
      <div style={cardStyle}>
        <div style={labelStyle}>恐慌/贪婪指数</div>
        <div style={{ ...valueStyle, color: regimeColor }}>{data.fear_index.fear_greed_score}</div>
        <div style={subStyle}>{regimeLabel[regime] ?? regime}</div>
      </div>

      <div style={cardStyle}>
        <div style={labelStyle}>VIX 恐慌指数</div>
        <div style={valueStyle}>{data.fear_index.vix.toFixed(2)}</div>
        <div style={subStyle}>波动率指数</div>
      </div>

      <div style={cardStyle}>
        <div style={labelStyle}>US10Y 收益率</div>
        <div style={valueStyle}>{data.fear_index.us10y.toFixed(2)}%</div>
        <div style={subStyle}>10年期美债</div>
      </div>

      <div style={cardStyle}>
        <div style={labelStyle}>事件信号</div>
        <div style={valueStyle}>{data.event_count}</div>
        <div style={subStyle}>
          <span style={{ color: '#27a644' }}>+{data.bullish_count} 利多</span>
          {'  '}
          <span style={{ color: '#e5534b' }}>-{data.bearish_count} 利空</span>
        </div>
      </div>
    </div>
  );
}
