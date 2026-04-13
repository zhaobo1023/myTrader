'use client';

import type { SignalLogEntry } from '@/lib/api-client';

/**
 * SignalLog - displays recent signal change events as a timeline.
 */

interface SignalLogProps {
  entries: SignalLogEntry[];
}

const SECTION_LABELS: Record<string, string> = {
  temperature: '市场温度',
  trend: '趋势方向',
  sentiment: '情绪恐贪',
  style: '风格轮动',
  'style.scale': '大小盘',
  'style.growth_value': '成长价值',
  stock_bond: '股债关系',
  macro: '宏观背景',
};

const SECTION_COLORS: Record<string, string> = {
  temperature: '#f97316',
  trend: '#3b82f6',
  sentiment: '#8b5cf6',
  style: '#06b6d4',
  'style.scale': '#06b6d4',
  'style.growth_value': '#06b6d4',
  stock_bond: '#10b981',
  macro: '#64748b',
};

export default function SignalLog({ entries }: SignalLogProps) {
  if (!entries || entries.length === 0) {
    return (
      <div
        style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '10px',
          padding: '16px 18px',
        }}
      >
        <div style={{ fontSize: '13px', fontWeight: 510, color: 'var(--text-secondary)', marginBottom: '8px' }}>
          信号变化日志
        </div>
        <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
          最近 7 天无信号翻转记录
        </div>
      </div>
    );
  }

  return (
    <div
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border-subtle)',
        borderRadius: '10px',
        padding: '16px 18px',
      }}
    >
      <div style={{ fontSize: '13px', fontWeight: 510, color: 'var(--text-secondary)', marginBottom: '12px' }}>
        信号变化日志
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {entries.map((entry, i) => {
          const sectionColor = SECTION_COLORS[entry.section] || '#8a8f98';
          return (
            <div
              key={i}
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '10px',
                fontSize: '12px',
              }}
            >
              <span
                style={{
                  color: 'var(--text-muted)',
                  fontFamily: 'var(--font-geist-mono)',
                  flexShrink: 0,
                  width: '52px',
                }}
              >
                {entry.date.slice(5)}
              </span>
              <span
                style={{
                  color: sectionColor,
                  background: `${sectionColor}15`,
                  padding: '1px 8px',
                  borderRadius: '4px',
                  fontSize: '11px',
                  flexShrink: 0,
                  fontWeight: 510,
                }}
              >
                {SECTION_LABELS[entry.section] || entry.section}
              </span>
              <span style={{ color: 'var(--text-tertiary)' }}>
                {entry.from} {'->'} {entry.to}
              </span>
              {entry.detail && (
                <span style={{ color: 'var(--text-muted)', flex: 1 }}>
                  {entry.detail}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
