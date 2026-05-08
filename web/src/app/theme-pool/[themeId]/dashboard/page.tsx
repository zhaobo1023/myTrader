'use client';

import React, { useState, useMemo } from 'react';
import { useParams, useRouter } from 'next/navigation';
import AppShell from '@/components/layout/AppShell';
import { useQuery } from '@tanstack/react-query';
import { themePoolApi } from '@/lib/api-client';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const COLOR_UP = '#ef4444';
const COLOR_DOWN = '#16a34a';

function pct(v: number | null | undefined): string {
  if (v == null) return '-';
  return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;
}

function returnColor(v: number | null | undefined): string {
  if (v == null) return 'var(--text-muted)';
  return v >= 0 ? COLOR_UP : COLOR_DOWN;
}

function scoreStr(v: number | null | undefined): string {
  if (v == null) return '-';
  return v.toFixed(0);
}

const MARKET_LABELS: Record<string, { label: string; bg: string; text: string }> = {
  A: { label: 'A股', bg: '#dbeafe', text: '#2563eb' },
  HK: { label: '港股', bg: '#fef3c7', text: '#d97706' },
  US: { label: '美股', bg: '#ede9fe', text: '#7c3aed' },
};

function MarketBadge({ market }: { market: string }) {
  const m = MARKET_LABELS[market] || MARKET_LABELS.A;
  return (
    <span style={{
      display: 'inline-block', padding: '1px 6px', borderRadius: '3px',
      fontSize: '10px', fontWeight: 600, background: m.bg, color: m.text,
    }}>
      {m.label}
    </span>
  );
}

function getMarket(code: string): string {
  if (code.endsWith('.HK')) return 'HK';
  if (!code.includes('.')) return 'US';
  return 'A';
}

// ---------------------------------------------------------------------------
// Mapping Comparison Card
// ---------------------------------------------------------------------------

function MappingCard({ mapping }: { mapping: any }) {
  const cn = mapping.cn_stock;
  const peers = mapping.us_peers || [];

  // Build normalized comparison lines
  const cnNorm = cn.normalized || [];
  const allSeries: { label: string; data: { date: string; value: number | null }[]; color: string }[] = [];
  if (cnNorm.length > 0) {
    allSeries.push({ label: cn.name, data: cnNorm, color: '#ef4444' });
  }
  const peerColors = ['#3b82f6', '#8b5cf6'];
  peers.forEach((p: any, i: number) => {
    const pNorm = p.normalized || [];
    if (pNorm.length > 0) {
      allSeries.push({ label: p.name || p.code, data: pNorm, color: peerColors[i % peerColors.length] });
    }
  });

  // SVG chart dimensions
  const w = 240;
  const h = 80;
  const pad = { top: 5, right: 5, bottom: 5, left: 5 };
  const chartW = w - pad.left - pad.right;
  const chartH = h - pad.top - pad.bottom;

  // Compute ranges across all series
  let minV = 90;
  let maxV = 110;
  const numPoints = Math.max(10, ...allSeries.map(s => s.data.length));

  allSeries.forEach(s => {
    s.data.forEach(d => {
      if (d.value != null) {
        minV = Math.min(minV, d.value);
        maxV = Math.max(maxV, d.value);
      }
    });
  });
  const range = maxV - minV || 1;
  const toX = (i: number, total: number) => pad.left + (i / Math.max(total - 1, 1)) * chartW;
  const toY = (v: number) => pad.top + (1 - (v - minV) / range) * chartH;

  return (
    <div style={{
      background: 'var(--bg-panel)',
      border: '1px solid var(--border-subtle)',
      borderRadius: '8px',
      padding: '16px',
      display: 'flex',
      flexDirection: 'column',
      gap: '10px',
    }}>
      {/* Header: CN stock info */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <MarketBadge market={cn.market} />
            <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
              {cn.name}
            </span>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{cn.code}</span>
          </div>
          <div style={{ display: 'flex', gap: '12px', marginTop: '4px', fontSize: '12px' }}>
            <span style={{ color: 'var(--text-muted)' }}>最新: <span style={{ color: 'var(--text-primary)' }}>{cn.latest_close?.toFixed(2) || '-'}</span></span>
            <span style={{ color: returnColor(cn.return_5d) }}>5日: {pct(cn.return_5d)}</span>
            <span style={{ color: returnColor(cn.return_20d) }}>20日: {pct(cn.return_20d)}</span>
          </div>
        </div>
      </div>

      {/* Comparison mini chart */}
      {allSeries.length > 0 && (
        <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: 'block' }}>
          {/* 100 baseline */}
          {minV < 100 && maxV > 100 && (
            <line x1={pad.left} y1={toY(100)} x2={w - pad.right} y2={toY(100)}
              stroke="var(--text-muted)" strokeWidth="0.5" strokeDasharray="3,2" opacity="0.4" />
          )}
          {/* Lines */}
          {allSeries.map((s, si) => {
            const pts = s.data
              .map((d, i) => d.value != null ? `${toX(i, s.data.length)},${toY(d.value)}` : null)
              .filter(Boolean)
              .join(' ');
            return pts ? (
              <polyline key={si} points={pts} fill="none" stroke={s.color} strokeWidth="1.5" strokeLinejoin="round" />
            ) : null;
          })}
        </svg>
      )}

      {/* US peers */}
      <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '8px' }}>
        <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '6px' }}>美股映射</div>
        {peers.map((p: any, i: number) => (
          <div key={p.code} style={{
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            padding: '3px 0', fontSize: '12px',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span style={{ width: '8px', height: '2px', background: peerColors[i % peerColors.length], display: 'inline-block' }} />
              <span style={{ color: 'var(--text-primary)' }}>{p.name}</span>
              <span style={{ color: 'var(--text-muted)', fontSize: '10px' }}>{p.code}</span>
            </div>
            <div style={{ display: 'flex', gap: '10px' }}>
              <span style={{ color: 'var(--text-muted)' }}>{p.latest_close?.toFixed(2) || '-'}</span>
              <span style={{ color: returnColor(p.return_5d), minWidth: '48px' }}>{pct(p.return_5d)}</span>
              <span style={{ color: returnColor(p.return_20d), minWidth: '48px' }}>{pct(p.return_20d)}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Full Stock Table
// ---------------------------------------------------------------------------

function StockTable({ stocks, onStockClick }: { stocks: any[]; onStockClick: (code: string, market: string) => void }) {
  const [sortKey, setSortKey] = useState('total_score');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDir(d => d === 'desc' ? 'asc' : 'desc');
    } else {
      setSortKey(key);
      setSortDir('desc');
    }
  };

  const sorted = useMemo(() => {
    const arr = [...stocks];
    arr.sort((a, b) => {
      let va: any, vb: any;
      if (['return_5d', 'return_10d', 'return_20d', 'return_60d', 'rps_20', 'rps_60', 'rps_250',
        'tech_score', 'fundamental_score', 'total_score'].includes(sortKey)) {
        va = a.latest_score?.[sortKey];
        vb = b.latest_score?.[sortKey];
      } else if (sortKey === 'market') {
        va = a.market;
        vb = b.market;
      } else if (sortKey === 'stock_name') {
        va = a.stock_name;
        vb = b.stock_name;
      } else {
        va = a[sortKey];
        vb = b[sortKey];
      }
      if (va == null) return 1;
      if (vb == null) return -1;
      const cmp = typeof va === 'string' ? va.localeCompare(vb) : va - vb;
      return sortDir === 'desc' ? -cmp : cmp;
    });
    return arr;
  }, [stocks, sortKey, sortDir]);

  const SortHeader = ({ label, field, width }: { label: string; field: string; width?: number }) => (
    <th
      onClick={() => handleSort(field)}
      style={{
        padding: '8px 6px', fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)',
        cursor: 'pointer', userSelect: 'none', textAlign: 'right', whiteSpace: 'nowrap',
        borderBottom: sortKey === field ? '2px solid var(--accent)' : '1px solid var(--border-subtle)',
        width,
      }}
    >
      {label} {sortKey === field ? (sortDir === 'desc' ? ' ' : ' ') : ''}
    </th>
  );

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
        <thead>
          <tr>
            <th style={{ padding: '8px 6px', fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', textAlign: 'left', borderBottom: '1px solid var(--border-subtle)' }}>
              标的
            </th>
            <SortHeader label="市场" field="market" width={50} />
            <SortHeader label="RPS20" field="rps_20" width={60} />
            <SortHeader label="RPS60" field="rps_60" width={60} />
            <SortHeader label="技术分" field="tech_score" width={55} />
            <SortHeader label="基本面" field="fundamental_score" width={55} />
            <SortHeader label="总分" field="total_score" width={50} />
            <SortHeader label="5日" field="return_5d" width={55} />
            <SortHeader label="20日" field="return_20d" width={55} />
            <SortHeader label="60日" field="return_60d" width={55} />
            <th style={{ padding: '8px 6px', fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', textAlign: 'center', borderBottom: '1px solid var(--border-subtle)' }}>
              走势
            </th>
            <th style={{ padding: '8px 6px', fontSize: '11px', fontWeight: 600, color: 'var(--text-secondary)', textAlign: 'center', borderBottom: '1px solid var(--border-subtle)', width: 60 }}>
              操作
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((s: any) => {
            const sc = s.latest_score || {};
            const market = s.market || getMarket(s.stock_code);
            const isClickable = market === 'A';
            return (
              <tr
                key={s.stock_code}
                onClick={() => isClickable && onStockClick(s.stock_code, market)}
                style={{
                  cursor: isClickable ? 'pointer' : 'default',
                  borderBottom: '1px solid var(--border-subtle)',
                  background: 'transparent',
                  transition: 'background 0.15s',
                }}
                onMouseEnter={e => { if (isClickable) (e.currentTarget as HTMLElement).style.background = 'var(--bg-elevated)'; }}
                onMouseLeave={e => { (e.currentTarget as HTMLElement).style.background = 'transparent'; }}
              >
                <td style={{ padding: '8px 6px', textAlign: 'left' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <span style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-primary)' }}>{s.stock_name}</span>
                  </div>
                  <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '1px' }}>{s.stock_code}</div>
                </td>
                <td style={{ padding: '8px 6px', textAlign: 'right' }}><MarketBadge market={market} /></td>
                <td style={{ padding: '8px 6px', textAlign: 'right', color: 'var(--text-primary)' }}>{scoreStr(sc.rps_20)}</td>
                <td style={{ padding: '8px 6px', textAlign: 'right', color: 'var(--text-primary)' }}>{scoreStr(sc.rps_60)}</td>
                <td style={{ padding: '8px 6px', textAlign: 'right', color: 'var(--text-primary)' }}>{scoreStr(sc.tech_score)}</td>
                <td style={{ padding: '8px 6px', textAlign: 'right', color: 'var(--text-primary)' }}>{scoreStr(sc.fundamental_score)}</td>
                <td style={{ padding: '8px 6px', textAlign: 'right', fontWeight: 600, color: sc.total_score != null && sc.total_score >= 60 ? COLOR_UP : 'var(--text-primary)' }}>
                  {scoreStr(sc.total_score)}
                </td>
                <td style={{ padding: '8px 6px', textAlign: 'right', color: returnColor(sc.return_5d) }}>{pct(sc.return_5d)}</td>
                <td style={{ padding: '8px 6px', textAlign: 'right', color: returnColor(sc.return_20d) }}>{pct(sc.return_20d)}</td>
                <td style={{ padding: '8px 6px', textAlign: 'right', color: returnColor(sc.return_60d) }}>{pct(sc.return_60d)}</td>
                <td style={{ padding: '8px 6px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '11px' }}>
                  {sc.return_20d != null ? (sc.return_20d >= 0 ? '/' : '\\') : '-'}
                </td>
                <td style={{ padding: '8px 6px', textAlign: 'center' }}>
                  {isClickable ? (
                    <span style={{ fontSize: '11px', color: 'var(--accent)', cursor: 'pointer' }}>详情</span>
                  ) : (
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>-</span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
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
      padding: '16px',
      minWidth: '140px',
    }}>
      <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>{label}</div>
      <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)' }}>{value}</div>
      {sub && <div style={{ fontSize: '11px', color: 'var(--text-secondary)', marginTop: '2px' }}>{sub}</div>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ThemeDashboardPage() {
  const params = useParams();
  const router = useRouter();
  const themeId = Number(params.themeId);

  const { data, isLoading, error } = useQuery({
    queryKey: ['theme-dashboard', themeId],
    queryFn: () => themePoolApi.getDashboard(themeId).then(r => r.data),
    staleTime: 5 * 60 * 1000,
  });

  const handleStockClick = (code: string, market: string) => {
    if (market === 'A') {
      router.push(`/stock?code=${code}`);
    }
  };

  if (isLoading) {
    return (
      <AppShell>
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
          <div style={{ color: 'var(--text-muted)', fontSize: '14px' }}>加载中...</div>
        </div>
      </AppShell>
    );
  }

  if (error || !data) {
    return (
      <AppShell>
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '60vh' }}>
          <div style={{ color: 'var(--text-muted)', fontSize: '14px' }}>
            加载失败，请稍后重试
          </div>
        </div>
      </AppShell>
    );
  }

  const { theme, summary, mappings, stocks } = data;

  return (
    <AppShell>
      <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '24px 16px' }}>

        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
              <button
                onClick={() => router.push(`/theme-pool/${themeId}`)}
                style={{
                  background: 'transparent', border: 'none', color: 'var(--text-muted)',
                  cursor: 'pointer', fontSize: '14px', padding: '4px 8px',
                }}
              >
                &larr; 返回
              </button>
              <h1 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)', margin: 0 }}>
                {theme.name} - 主题大盘
              </h1>
            </div>
            {theme.description && (
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px', maxWidth: '800px', lineHeight: '1.5' }}>
                {theme.description.split('\n')[0]}
              </div>
            )}
          </div>
        </div>

        {/* Summary Cards */}
        <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginBottom: '24px' }}>
          <SummaryCard label="总标的" value={`${summary.total_stocks}`} sub={`A股${summary.a_share_count} / 港股${summary.hk_count} / 美股${summary.us_count}`} />
          <SummaryCard label="平均5日收益" value={pct(summary.avg_return_5d)}
            sub={`A股: ${pct(summary.a_share_avg_return_5d)} | 美股: ${pct(summary.us_avg_return_5d)}`} />
          <SummaryCard label="平均20日收益" value={pct(summary.avg_return_20d)}
            sub={`A股: ${pct(summary.a_share_avg_return_20d)} | 美股: ${pct(summary.us_avg_return_20d)}`} />
        </div>

        {/* Market Split Bar */}
        <div style={{
          display: 'flex', gap: '2px', borderRadius: '4px', overflow: 'hidden',
          height: '6px', marginBottom: '24px',
        }}>
          <div style={{ flex: summary.a_share_count, background: '#3b82f6' }} title={`A股 ${summary.a_share_count}`} />
          <div style={{ flex: summary.hk_count, background: '#f59e0b' }} title={`港股 ${summary.hk_count}`} />
          <div style={{ flex: summary.us_count, background: '#8b5cf6' }} title={`美股 ${summary.us_count}`} />
        </div>

        {/* Section 2: Mapping Cards */}
        {mappings.length > 0 && (
          <div style={{ marginBottom: '32px' }}>
            <h2 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '12px' }}>
              A股/港股 vs 美股映射对比
            </h2>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
              gap: '12px',
            }}>
              {mappings.map((m: any) => (
                <MappingCard key={m.cn_stock.code} mapping={m} />
              ))}
            </div>
          </div>
        )}

        {/* Section 3: Full Stock Table */}
        <div>
          <h2 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '12px' }}>
            全量标的一览
          </h2>
          <div style={{
            background: 'var(--bg-panel)',
            border: '1px solid var(--border-subtle)',
            borderRadius: '8px',
            overflow: 'hidden',
          }}>
            <StockTable stocks={stocks} onStockClick={handleStockClick} />
          </div>
        </div>

      </div>
    </AppShell>
  );
}
