'use client';

import { useQuery } from '@tanstack/react-query';
import { marketOverviewApi } from '@/lib/api-client';
import type {
  MarketDashboardData,
  TemperatureSection,
  TrendSection,
  SentimentSection,
  StyleSection,
  StockBondSection,
  MacroSection,
} from '@/lib/api-client';
import SignalCard from './SignalCard';
import SignalLog from './SignalLog';

/**
 * DashboardView - the main 6-section market overview dashboard.
 *
 * Layout: 3-column grid (top row + bottom row) + signal log below.
 */

// ---------------------------------------------------------------------------
// Helper: extract sparkline values from series
// ---------------------------------------------------------------------------
function seriesValues(series: Array<{ value?: number }> | undefined): number[] {
  if (!series) return [];
  return series.map((p) => p.value).filter((v): v is number => v !== null && v !== undefined);
}

// ---------------------------------------------------------------------------
// Section renderers
// ---------------------------------------------------------------------------

function renderTemperature(data: TemperatureSection) {
  if (!data?.available) return <SignalCard title="市场温度" unavailable indicators={[]} />;

  const ind = data.indicators || {};
  const vol = ind.volume as Record<string, unknown> | undefined;
  const vr = ind.volume_ratio_ma20 as Record<string, unknown> | undefined;
  const tp = ind.turnover_pct_rank as Record<string, unknown> | undefined;
  const ad = ind.advance_decline as Record<string, unknown> | undefined;
  const lu = ind.limit_up_down as Record<string, unknown> | undefined;
  const mc = ind.margin_change_5d as Record<string, unknown> | undefined;

  const indicators = [
    {
      label: '成交额',
      value: vol?.value != null ? `${vol.value}亿` : null,
      sub: vol?.change as string | undefined,
      changeDir: (vol?.change as string)?.startsWith('+') ? 'up' as const : (vol?.change as string)?.startsWith('-') ? 'down' as const : undefined,
    },
    {
      label: '量/MA20',
      value: vr?.value != null ? String(vr.value) : null,
      signal: vr?.signal as string | undefined,
    },
    {
      label: '换手分位',
      value: tp?.value != null ? `${tp.value}%` : null,
      signal: tp?.signal as string | undefined,
    },
    {
      label: '涨/跌家数',
      value: ad?.advance != null ? `${ad.advance}/${ad.decline}` : null,
      sub: ad?.ratio != null ? `(${ad.ratio})` : undefined,
      signal: ad?.signal as string | undefined,
    },
    {
      label: '涨停/跌停',
      value: lu?.up != null ? `${lu.up}/${lu.down}` : null,
    },
    {
      label: '融资5日变化',
      value: mc?.value != null ? `${mc.value}%` : null,
      signal: mc?.signal as string | undefined,
    },
  ];

  return (
    <SignalCard
      title="市场温度"
      level={data.level}
      levelLabel={data.level_label}
      indicators={indicators}
      sparklineData={seriesValues(data.volume_series)}
      sparklineLabel="近20日成交额"
      sparklineColor="auto"
    />
  );
}

function renderTrend(data: TrendSection) {
  if (!data?.available) return <SignalCard title="趋势方向" unavailable indicators={[]} />;

  const indices = data.indices || {};
  const ind = data.indicators || {};
  const maPos = ind.ma_position;
  const macd = ind.macd_weekly;
  const adx = ind.adx;
  const svd = ind.svd;

  // Build index return string
  const indexEntries = Object.values(indices);
  const indexStr = indexEntries
    .filter((v) => v.change_pct != null)
    .map((v) => `${v.name} ${(v.change_pct ?? 0) >= 0 ? '+' : ''}${v.change_pct}%`)
    .join('  ');

  const maAbove = maPos?.above?.join('/') || '-';
  const maBelow = maPos?.below?.join('/') || '-';

  const macdLabels: Record<string, string> = {
    golden_cross: '金叉',
    dead_cross: '死叉',
    above_zero: '零上',
    below_zero: '零下',
    unknown: '-',
  };
  const histLabels: Record<string, string> = {
    expanding: '扩张',
    contracting: '收缩',
  };

  const indicators = [
    {
      label: '主要指数',
      value: indexStr || null,
    },
    {
      label: '均线上方',
      value: maAbove,
      signal: maPos?.above && maPos.above.length >= 3 ? 'bullish' : maPos?.above && maPos.above.length <= 1 ? 'bearish' : 'neutral',
    },
    {
      label: '均线排列',
      value: ind.ma_alignment === 'bullish' ? '多头排列' : ind.ma_alignment === 'bearish' ? '空头排列' : '缠绕',
      signal: ind.ma_alignment === 'bullish' ? 'bullish' : ind.ma_alignment === 'bearish' ? 'bearish' : 'neutral',
    },
    {
      label: 'MACD周线',
      value: macd ? `${macdLabels[macd.status] || macd.status} ${histLabels[macd.histogram || ''] || ''}` : null,
      signal: macd?.status === 'golden_cross' || macd?.status === 'above_zero' ? 'bullish' : macd?.status === 'dead_cross' || macd?.status === 'below_zero' ? 'bearish' : 'neutral',
    },
    {
      label: 'ADX趋势',
      value: adx?.value != null ? String(adx.value) : null,
      sub: adx?.signal === 'trending' ? '趋势明确' : adx?.signal === 'weak_trend' ? '弱趋势' : '震荡',
      signal: adx?.signal as string | undefined,
    },
    {
      label: 'SVD结构',
      value: svd?.state_label || null,
      sub: svd?.is_mutation ? '[突变]' : undefined,
      signal: svd?.is_mutation ? 'bearish' : 'neutral',
    },
  ];

  const sparkData = (data.trend_series || []).map((p) => (p as Record<string, number>).close).filter((v): v is number => v != null);

  return (
    <SignalCard
      title="趋势方向"
      level={data.level}
      levelLabel={data.level_label}
      indicators={indicators}
      sparklineData={sparkData}
      sparklineLabel="沪深300 近60日"
      sparklineColor="auto"
    />
  );
}

function renderSentiment(data: SentimentSection) {
  if (!data?.available) return <SignalCard title="情绪恐贪" unavailable indicators={[]} />;

  const ind = data.indicators || {};
  const qvix = ind.qvix as Record<string, unknown> | undefined;
  const north = ind.north_flow as Record<string, unknown> | undefined;
  const vix = ind.vix as Record<string, unknown> | undefined;
  const margin = ind.margin_net_buy as Record<string, unknown> | undefined;
  const nhl = ind.new_high_low as Record<string, unknown> | undefined;
  const seal = ind.seal_rate as Record<string, unknown> | undefined;

  const indicators = [
    {
      label: 'A股恐贪指数',
      value: data.score != null ? String(data.score) : null,
      signal: data.level as string | undefined,
    },
    {
      label: 'QVIX',
      value: qvix?.value != null ? String(qvix.value) : null,
      signal: qvix?.signal as string | undefined,
    },
    {
      label: '北向5日',
      value: north?.sum_5d != null ? `${north.sum_5d}亿` : null,
      signal: north?.signal as string | undefined,
    },
    {
      label: '融资净买入',
      value: margin?.today != null ? `${margin.today}亿` : null,
      sub: margin?.sum_5d != null ? `5日:${margin.sum_5d}亿` : undefined,
    },
    {
      label: '新高/新低',
      value: nhl?.high != null ? `${nhl.high}/${nhl.low}` : null,
      signal: nhl?.signal as string | undefined,
    },
    {
      label: '封板率',
      value: seal?.value != null ? `${seal.value}%` : null,
      signal: seal?.signal as string | undefined,
    },
  ];

  return (
    <SignalCard
      title="情绪恐贪"
      level={data.level}
      levelLabel={data.level_label}
      indicators={indicators}
      sparklineData={seriesValues(data.sentiment_series)}
      sparklineLabel="VIX恐贪指数 近20日"
      sparklineColor="auto"
    />
  );
}

function renderStyle(data: StyleSection) {
  if (!data?.available) return <SignalCard title="风格轮动" unavailable indicators={[]} />;

  const scale = data.scale;
  const style = data.style;
  const anchor = data.anchor_5y;

  const indicators = [
    {
      label: '大小盘',
      value: scale ? `${scale.label}${scale.strength_label ? ' ' + scale.strength_label : ''}` : null,
      signal: scale?.direction === 'large_cap' || scale?.direction === 'small_cap' ? 'active' : 'neutral',
    },
    {
      label: '成长/价值',
      value: style ? `${style.label}${style.strength_label ? ' ' + style.strength_label : ''}` : null,
      signal: style?.direction === 'growth' || style?.direction === 'value' ? 'active' : 'neutral',
    },
    {
      label: '5年锚偏离',
      value: anchor?.deviation_pct != null ? `${anchor.deviation_pct}%` : null,
      sub: anchor?.signal_text || undefined,
      signal: anchor?.signal === 'undervalued' ? 'bullish' : anchor?.signal === 'overvalued' ? 'bearish' : 'neutral',
    },
  ];

  // Style compass as children
  const compassContent = scale && style ? (
    <div
      style={{
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        padding: '8px 0',
      }}
    >
      <div
        style={{
          position: 'relative',
          width: '100px',
          height: '100px',
          border: '1px solid var(--border-subtle)',
          borderRadius: '50%',
        }}
      >
        {/* Axis labels */}
        <span style={{ position: 'absolute', top: '2px', left: '50%', transform: 'translateX(-50%)', fontSize: '9px', color: 'var(--text-muted)' }}>
          成长
        </span>
        <span style={{ position: 'absolute', bottom: '2px', left: '50%', transform: 'translateX(-50%)', fontSize: '9px', color: 'var(--text-muted)' }}>
          价值
        </span>
        <span style={{ position: 'absolute', left: '2px', top: '50%', transform: 'translateY(-50%)', fontSize: '9px', color: 'var(--text-muted)' }}>
          小盘
        </span>
        <span style={{ position: 'absolute', right: '2px', top: '50%', transform: 'translateY(-50%)', fontSize: '9px', color: 'var(--text-muted)' }}>
          大盘
        </span>

        {/* Dot position based on signals */}
        {(() => {
          // X: -1 (small) to +1 (large), Y: -1 (value) to +1 (growth)
          const x = scale.direction === 'large_cap' ? (scale.strength === 'confirmed' ? 0.6 : 0.3)
            : scale.direction === 'small_cap' ? (scale.strength === 'confirmed' ? -0.6 : -0.3) : 0;
          const y = style.direction === 'growth' ? (style.strength === 'confirmed' ? 0.6 : 0.3)
            : style.direction === 'value' ? (style.strength === 'confirmed' ? -0.6 : -0.3) : 0;
          const px = 50 + x * 35;
          const py = 50 - y * 35;
          return (
            <div
              style={{
                position: 'absolute',
                left: `${px}%`,
                top: `${py}%`,
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                background: 'var(--accent)',
                transform: 'translate(-50%, -50%)',
                boxShadow: '0 0 0 3px rgba(94,106,210,0.25)',
              }}
            />
          );
        })()}
      </div>
    </div>
  ) : null;

  return (
    <SignalCard
      title="风格轮动"
      level={undefined}
      levelLabel={undefined}
      indicators={indicators}
    >
      {compassContent}
    </SignalCard>
  );
}

function renderStockBond(data: StockBondSection) {
  if (!data?.available) return <SignalCard title="股债关系" unavailable indicators={[]} />;

  const sp = data.spread;
  const div = data.dividend;
  const fund = data.fund_rolling;

  const indicators = [
    {
      label: '股债利差',
      value: sp?.spread_cn != null ? `${sp.spread_cn}%` : null,
      sub: sp?.signal || undefined,
      signal: sp?.signal === 'attractive' ? 'bullish' : sp?.signal === 'expensive' ? 'bearish' : 'neutral',
    },
    {
      label: '盈利收益率',
      value: sp?.earnings_yield != null ? `${sp.earnings_yield}%` : null,
    },
    {
      label: '10Y国债',
      value: sp?.cn_bond != null ? `${sp.cn_bond}%` : null,
    },
    {
      label: '股息率利差',
      value: div?.spread != null ? `${div.spread}%` : null,
      signal: div?.signal === 'very_attractive' || div?.signal === 'attractive' ? 'bullish' : 'neutral',
    },
    {
      label: '基金3年滚动',
      value: fund?.current_pct != null ? `${fund.current_pct}%` : null,
      sub: fund?.signal_text || undefined,
      signal: fund?.signal === 'bottom' ? 'bullish' : fund?.signal === 'bubble' ? 'bearish' : 'neutral',
    },
  ];

  return (
    <SignalCard
      title="股债关系"
      level={data.level}
      levelLabel={data.level_label}
      indicators={indicators}
      sparklineData={seriesValues(data.spread_series)}
      sparklineLabel="股债利差走势"
      sparklineColor="auto"
    />
  );
}

function renderMacro(data: MacroSection) {
  if (!data?.available) return <SignalCard title="宏观背景" unavailable indicators={[]} />;

  const ind = data.indicators || {};
  const pmi = ind.pmi_mfg as Record<string, unknown> | undefined;
  const m2 = ind.m2_yoy as Record<string, unknown> | undefined;
  const ah = ind.ah_premium as Record<string, unknown> | undefined;
  const vix = ind.vix as Record<string, unknown> | undefined;
  const north = ind.north_flow as Record<string, unknown> | undefined;

  const indicators = [
    {
      label: 'PMI',
      value: pmi?.value != null ? String(pmi.value) : null,
      sub: pmi?.signal_text as string | undefined,
      signal: pmi?.signal as string | undefined,
    },
    {
      label: 'M2增速',
      value: m2?.value != null ? `${m2.value}%` : null,
    },
    {
      label: 'AH溢价',
      value: ah?.value != null ? String(ah.value) : null,
      signal: ah?.signal as string | undefined,
    },
    {
      label: 'VIX',
      value: vix?.value != null ? String(vix.value) : null,
      sub: vix?.level as string | undefined,
    },
    {
      label: '北向5日',
      value: north?.sum_5d != null ? `${north.sum_5d}亿` : null,
      signal: north?.signal as string | undefined,
    },
  ];

  return (
    <SignalCard
      title="宏观背景"
      level={data.level}
      levelLabel={data.level_label}
      indicators={indicators}
    />
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function DashboardView() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['market-dashboard'],
    queryFn: () => marketOverviewApi.dashboard().then((r) => r.data),
    refetchInterval: 300_000, // 5 min
    staleTime: 60_000,
  });

  if (isLoading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {/* Loading skeleton: responsive grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '12px' }}>
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div
              key={i}
              style={{
                background: 'var(--bg-card)',
                border: '1px solid var(--border-subtle)',
                borderRadius: '10px',
                height: '220px',
                opacity: 0.4,
              }}
            />
          ))}
        </div>
        <div
          style={{
            background: 'var(--bg-card)',
            border: '1px solid var(--border-subtle)',
            borderRadius: '10px',
            height: '80px',
            opacity: 0.4,
          }}
        />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div style={{ fontSize: '13px', color: 'var(--text-muted)', padding: '24px' }}>
        加载大盘数据失败。请检查后端服务是否运行。
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      {/* Header info */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
          数据截止: {data.updated_at}
        </div>
      </div>

      {/* 6 cards in responsive grid: 3 cols desktop, 2 tablet, 1 mobile */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
          gap: '12px',
        }}
      >
        {renderTemperature(data.temperature)}
        {renderTrend(data.trend)}
        {renderSentiment(data.sentiment)}
        {renderStyle(data.style)}
        {renderStockBond(data.stock_bond)}
        {renderMacro(data.macro)}
      </div>

      {/* Signal change log */}
      <SignalLog entries={data.signal_log || []} />
    </div>
  );
}
