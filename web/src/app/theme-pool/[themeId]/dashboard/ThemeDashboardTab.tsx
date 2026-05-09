'use client';

import React, { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { themePoolApi } from '@/lib/api-client';

const COLOR_UP = '#ef4444';
const COLOR_DOWN = '#16a34a';
const CN_LINE_COLOR = '#ef4444';
const US_LINE_COLORS = ['#3b82f6', '#8b5cf6'];

function pct(v: number | null | undefined): string {
  if (v == null) return '-';
  return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;
}

function returnColor(v: number | null | undefined): string {
  if (v == null) return 'var(--text-muted)';
  return v >= 0 ? COLOR_UP : COLOR_DOWN;
}

const MARKET_BADGE: Record<string, { label: string; bg: string; text: string }> = {
  A: { label: 'A股', bg: '#dbeafe', text: '#2563eb' },
  HK: { label: '港股', bg: '#fef3c7', text: '#d97706' },
};

// ---------------------------------------------------------------------------
// Dual-line SVG chart: CN stock + US peer normalized to 100
// ---------------------------------------------------------------------------

function ComparisonChart({ cnData, usPeers }: {
  cnData: { date: string; value: number | null }[];
  usPeers: { code: string; name: string; data: { date: string; value: number | null }[] }[];
}) {
  // Merge all series
  const series: { label: string; data: { date: string; value: number | null }[]; color: string }[] = [];

  if (cnData.length > 0) {
    series.push({ label: 'CN', data: cnData, color: CN_LINE_COLOR });
  }
  usPeers.forEach((p, i) => {
    if (p.data.length > 0) {
      series.push({ label: p.code, data: p.data, color: US_LINE_COLORS[i % US_LINE_COLORS.length] });
    }
  });

  if (series.length === 0) return null;

  const w = 520;
  const h = 180;
  const pad = { top: 10, right: 10, bottom: 20, left: 40 };
  const chartW = w - pad.left - pad.right;
  const chartH = h - pad.top - pad.bottom;

  // Find date range and value range across all series
  let minV = 90, maxV = 110;
  const allDates = new Set<string>();
  series.forEach(s => {
    s.data.forEach(d => {
      if (d.value != null) {
        minV = Math.min(minV, d.value);
        maxV = Math.max(maxV, d.value);
        allDates.add(d.date);
      }
    });
  });

  const dates = [...allDates].sort();
  const dateIdx = new Map(dates.map((d, i) => [d, i]));
  const numPoints = Math.max(dates.length, 10);
  const range = maxV - minV || 1;
  const toX = (i: number) => pad.left + (i / Math.max(numPoints - 1, 1)) * chartW;
  const toY = (v: number) => pad.top + (1 - (v - minV) / range) * chartH;

  // Y-axis labels
  const yLabels = [minV, (minV + maxV) / 2, maxV];

  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: 'block' }}>
      {/* Grid lines */}
      {yLabels.map((v, i) => (
        <g key={i}>
          <line x1={pad.left} y1={toY(v)} x2={w - pad.right} y2={toY(v)}
            stroke="var(--border-subtle)" strokeWidth="0.5" />
          <text x={pad.left - 4} y={toY(v) + 3} textAnchor="end" fontSize="9" fill="var(--text-muted)">
            {v.toFixed(0)}
          </text>
        </g>
      ))}
      {/* 100 baseline */}
      {minV < 100 && maxV > 100 && (
        <line x1={pad.left} y1={toY(100)} x2={w - pad.right} y2={toY(100)}
          stroke="var(--text-muted)" strokeWidth="0.5" strokeDasharray="4,3" opacity="0.5" />
      )}
      {/* Lines */}
      {series.map((s, si) => {
        const pts = dates.map((date, i) => {
          const d = s.data.find(dd => dd.date === date);
          if (d && d.value != null) return `${toX(i)},${toY(d.value)}`;
          return null;
        }).filter(Boolean).join(' ');
        return pts ? (
          <polyline key={si} points={pts} fill="none" stroke={s.color}
            strokeWidth="1.8" strokeLinejoin="round" />
        ) : null;
      })}
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Big Mapping Card
// ---------------------------------------------------------------------------

function MappingCard({ mapping }: { mapping: any }) {
  const cn = mapping.cn_stock;
  const peers = mapping.us_peers || [];

  const cnNorm = cn.normalized || [];
  const usPeerData = peers.map((p: any) => ({
    code: p.code,
    name: p.name || p.code,
    data: p.normalized || [],
  }));

  const hasChartData = cnNorm.length > 0 || usPeerData.some((p: { data: any[] }) => p.data.length > 0);

  // Compute period return display
  const cnLatest = cn.latest_close;
  const cn5d = cn.return_5d;
  const cn20d = cn.return_20d;

  return (
    <div style={{
      background: 'var(--bg-panel)',
      border: '1px solid var(--border-subtle)',
      borderRadius: '10px',
      padding: '20px',
      display: 'flex',
      flexDirection: 'column',
      gap: '14px',
    }}>
      {/* Row 1: CN stock header + US peers header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        {/* CN stock */}
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
            {MARKET_BADGE[cn.market] && (
              <span style={{
                padding: '2px 8px', borderRadius: '4px', fontSize: '10px', fontWeight: 600,
                background: MARKET_BADGE[cn.market].bg, color: MARKET_BADGE[cn.market].text,
              }}>
                {MARKET_BADGE[cn.market].label}
              </span>
            )}
            <span style={{ fontSize: '16px', fontWeight: 700, color: 'var(--text-primary)' }}>
              {cn.name}
            </span>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{cn.code}</span>
          </div>
          <div style={{ display: 'flex', gap: '16px', fontSize: '13px' }}>
            <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>
              {cnLatest?.toFixed(2) || '-'}
            </span>
            <span style={{ color: returnColor(cn5d) }}>
              5日 {pct(cn5d)}
            </span>
            <span style={{ color: returnColor(cn20d) }}>
              20日 {pct(cn20d)}
            </span>
          </div>
        </div>

        {/* US peers */}
        <div style={{ flex: 1, textAlign: 'right' }}>
          <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            美股映射
          </div>
          {peers.map((p: any, i: number) => (
            <div key={p.code} style={{
              display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: '8px',
              padding: '3px 0', fontSize: '13px',
            }}>
              <span style={{ fontSize: '12px', color: 'var(--text-primary)', fontWeight: 500 }}>{p.name}</span>
              <span style={{
                padding: '1px 6px', borderRadius: '3px', fontSize: '10px', fontWeight: 600,
                background: '#ede9fe', color: '#7c3aed',
              }}>
                {p.code}
              </span>
              <span style={{ color: 'var(--text-primary)', fontWeight: 600, minWidth: '56px', textAlign: 'right' }}>
                {p.latest_close?.toFixed(2) || '-'}
              </span>
              <span style={{ color: returnColor(p.return_5d), minWidth: '52px', textAlign: 'right' }}>
                {pct(p.return_5d)}
              </span>
              <span style={{ color: returnColor(p.return_20d), minWidth: '52px', textAlign: 'right' }}>
                {pct(p.return_20d)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Chart */}
      {hasChartData && (
        <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '12px' }}>
          <ComparisonChart cnData={cnNorm} usPeers={usPeerData} />
          {/* Legend */}
          <div style={{ display: 'flex', gap: '16px', marginTop: '6px', justifyContent: 'center' }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: CN_LINE_COLOR }}>
              <span style={{ width: '12px', height: '2px', background: CN_LINE_COLOR, display: 'inline-block' }} />
              {cn.name}
            </span>
            {peers.map((p: any, i: number) => (
              <span key={p.code} style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '11px', color: US_LINE_COLORS[i % US_LINE_COLORS.length] }}>
                <span style={{ width: '12px', height: '2px', background: US_LINE_COLORS[i % US_LINE_COLORS.length], display: 'inline-block' }} />
                {p.name} ({p.code})
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Summary Card
// ---------------------------------------------------------------------------

function SummaryCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div style={{
      background: 'var(--bg-panel)',
      border: '1px solid var(--border-subtle)',
      borderRadius: '8px',
      padding: '14px 16px',
      minWidth: '130px',
    }}>
      <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginBottom: '2px' }}>{label}</div>
      <div style={{ fontSize: '18px', fontWeight: 700, color: 'var(--text-primary)' }}>{value}</div>
      {sub && <div style={{ fontSize: '10px', color: 'var(--text-secondary)', marginTop: '1px' }}>{sub}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export default function ThemeDashboardTab({ themeId, onStockClick }: { themeId: number; onStockClick: (code: string) => void }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['theme-dashboard', themeId],
    queryFn: () => themePoolApi.getDashboard(themeId).then(r => r.data),
    staleTime: 5 * 60 * 1000,
  });

  if (isLoading) {
    return <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>加载专题跟踪数据...</div>;
  }

  if (error || !data) {
    return <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>加载失败，请稍后重试</div>;
  }

  const { summary, mappings } = data;

  return (
    <div>
      {/* Summary */}
      <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '16px' }}>
        <SummaryCard label="A股/港股" value={`${summary.a_share_count + summary.hk_count}只`} sub={`A股${summary.a_share_count} / 港股${summary.hk_count}`} />
        <SummaryCard label="美股映射" value={`${summary.us_count}只`} sub="可比公司" />
        <SummaryCard label="A股平均5日" value={pct(summary.a_share_avg_return_5d)} />
        <SummaryCard label="A股平均20日" value={pct(summary.a_share_avg_return_20d)} />
        <SummaryCard label="美股平均5日" value={pct(summary.us_avg_return_5d)} />
        <SummaryCard label="美股平均20日" value={pct(summary.us_avg_return_20d)} />
      </div>

      {/* Mapping Cards - full width stacked */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        {mappings.map((m: any) => (
          <MappingCard key={m.cn_stock.code} mapping={m} />
        ))}
      </div>
    </div>
  );
}
