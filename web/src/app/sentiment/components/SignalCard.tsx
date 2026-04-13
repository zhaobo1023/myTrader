'use client';

import Sparkline from './Sparkline';

/**
 * SignalCard - reusable card for each dashboard section.
 *
 * Layout:
 *   [Section title]  [Level badge]
 *   [Indicator rows with direction arrows]
 *   [Sparkline at bottom]
 */

interface IndicatorRow {
  label: string;
  value: string | null;
  sub?: string;
  signal?: string; // maps to color
  changeDir?: 'up' | 'down' | 'flat';
}

interface SignalCardProps {
  title: string;
  level?: string;
  levelLabel?: string;
  levelColor?: string;
  indicators: IndicatorRow[];
  sparklineData?: number[];
  sparklineLabel?: string;
  sparklineColor?: string;
  unavailable?: boolean;
  children?: React.ReactNode;
}

const LEVEL_COLORS: Record<string, string> = {
  // Temperature
  freezing: '#3b82f6',
  cold: '#60a5fa',
  normal: '#8a8f98',
  active: '#f97316',
  overheated: '#ef4444',
  // Trend
  strong_up: '#16a34a',
  mild_up: '#4ade80',
  consolidating: '#8a8f98',
  weak_down: '#f97316',
  panic_drop: '#ef4444',
  // Sentiment (inverted: fear=green=opportunity)
  extreme_fear: '#16a34a',
  fear: '#4ade80',
  neutral: '#8a8f98',
  greed: '#f97316',
  extreme_greed: '#ef4444',
  // Stock-bond
  stock_attractive: '#16a34a',
  bond_preferred: '#3b82f6',
  // Macro
  tailwind: '#16a34a',
  headwind: '#ef4444',
  // Unknown
  unknown: '#8a8f98',
};

const SIGNAL_COLORS: Record<string, string> = {
  positive: 'var(--green)',
  bullish: 'var(--green)',
  strong: 'var(--green)',
  extreme_strong: 'var(--green)',
  active: '#f97316',
  expanding: 'var(--green)',
  expanding_fast: 'var(--green)',
  inflow: 'var(--green)',
  chasing: '#f97316',
  normal: 'var(--text-tertiary)',
  balanced: 'var(--text-tertiary)',
  stable: 'var(--text-tertiary)',
  neutral: 'var(--text-tertiary)',
  unknown: 'var(--text-muted)',
  negative: 'var(--red)',
  bearish: 'var(--red)',
  weak: 'var(--red)',
  extreme_weak: 'var(--red)',
  contracting: 'var(--red)',
  contracting_fast: 'var(--red)',
  outflow: 'var(--red)',
  hesitant: 'var(--red)',
  cold: '#60a5fa',
  freezing: '#3b82f6',
  overheated: '#ef4444',
  complacent: 'var(--green)',
  anxious: '#f97316',
  panic: 'var(--red)',
};

const DIR_ARROWS: Record<string, string> = {
  up: '[^]',
  down: '[v]',
  flat: '[-]',
};

export default function SignalCard({
  title,
  level,
  levelLabel,
  levelColor,
  indicators,
  sparklineData,
  sparklineLabel,
  sparklineColor,
  unavailable,
  children,
}: SignalCardProps) {
  const resolvedLevelColor = levelColor || LEVEL_COLORS[level || ''] || '#8a8f98';

  return (
    <div
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border-subtle)',
        borderRadius: '10px',
        padding: '16px 18px',
        display: 'flex',
        flexDirection: 'column',
        gap: '12px',
        minHeight: '200px',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '13px', fontWeight: 510, color: 'var(--text-secondary)' }}>
          {title}
        </span>
        {levelLabel && (
          <span
            style={{
              fontSize: '12px',
              fontWeight: 510,
              color: resolvedLevelColor,
              background: `${resolvedLevelColor}18`,
              padding: '2px 10px',
              borderRadius: '10px',
              letterSpacing: '0.3px',
            }}
          >
            {levelLabel}
          </span>
        )}
      </div>

      {unavailable ? (
        <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '8px' }}>
          暂无数据
        </div>
      ) : (
        <>
          {/* Indicator rows */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', flex: 1 }}>
            {indicators.map((ind, i) => (
              <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                <span style={{ fontSize: '12px', color: 'var(--text-muted)', flexShrink: 0 }}>
                  {ind.label}
                </span>
                <div style={{ display: 'flex', alignItems: 'baseline', gap: '4px' }}>
                  <span
                    style={{
                      fontSize: '13px',
                      fontWeight: 510,
                      color: SIGNAL_COLORS[ind.signal || ''] || 'var(--text-primary)',
                      fontFamily: ind.value && /[\d.]/.test(ind.value) ? 'var(--font-geist-mono)' : undefined,
                    }}
                  >
                    {ind.value ?? '--'}
                  </span>
                  {ind.sub && (
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                      {ind.sub}
                    </span>
                  )}
                  {ind.changeDir && (
                    <span
                      style={{
                        fontSize: '10px',
                        color: ind.changeDir === 'up' ? 'var(--green)' : ind.changeDir === 'down' ? 'var(--red)' : 'var(--text-muted)',
                      }}
                    >
                      {DIR_ARROWS[ind.changeDir]}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>

          {/* Custom children (e.g. style compass) */}
          {children}

          {/* Sparkline */}
          {sparklineData && sparklineData.length > 1 && (
            <div>
              {sparklineLabel && (
                <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '4px' }}>
                  {sparklineLabel}
                </div>
              )}
              <Sparkline
                data={sparklineData}
                width={200}
                height={28}
                color={sparklineColor || 'auto'}
              />
            </div>
          )}
        </>
      )}
    </div>
  );
}
