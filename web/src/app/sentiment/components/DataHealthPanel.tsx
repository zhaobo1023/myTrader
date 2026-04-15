'use client';

import React from 'react';
import { useQuery } from '@tanstack/react-query';
import apiClient from '@/lib/api-client';

interface HealthItem {
  key: string;
  label: string;
  group: string;
  count_label: string;
  latest_date: string | null;
  count: number | null;
  days_behind: number | null;
  status: 'ok' | 'warn' | 'error' | 'unknown';
  error?: string;
}

interface HealthData {
  checked_at: string;
  summary: { ok: number; warn: number; error: number; total: number };
  items: HealthItem[];
}

function statusColor(status: HealthItem['status']) {
  const map = { ok: '#27a644', warn: '#c69026', error: '#e5534b', unknown: 'var(--text-muted)' };
  return map[status] ?? map.unknown;
}

function dayLabel(days: number | null) {
  if (days === null) return '--';
  if (days === 0) return '今天';
  if (days === 1) return '昨天';
  return `${days}天前`;
}

function dayColor(days: number | null) {
  if (days === null) return 'var(--text-muted)';
  if (days <= 1) return '#27a644';
  if (days <= 3) return '#c69026';
  return '#e5534b';
}

export default function DataHealthPanel() {
  const { data, isLoading, error, refetch, isFetching } = useQuery<HealthData>({
    queryKey: ['data-health'],
    queryFn: async () => {
      const res = await apiClient.get('/api/admin/data-health');
      return res.data;
    },
    refetchInterval: 120000,
  });

  const grouped = data
    ? data.items.reduce<Record<string, HealthItem[]>>((acc, item) => {
        const g = item.group || '其他';
        if (!acc[g]) acc[g] = [];
        acc[g].push(item);
        return acc;
      }, {})
    : {};

  return (
    <div>
      {/* Header with summary */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        {data && (
          <div style={{ display: 'flex', gap: '16px', fontSize: '12px' }}>
            <span style={{ color: '#27a644' }}>
              <span style={{ display: 'inline-block', width: '6px', height: '6px', borderRadius: '50%', background: '#27a644', marginRight: '4px' }} />
              正常 {data.summary.ok}
            </span>
            <span style={{ color: '#c69026' }}>
              <span style={{ display: 'inline-block', width: '6px', height: '6px', borderRadius: '50%', background: '#c69026', marginRight: '4px' }} />
              偏旧 {data.summary.warn}
            </span>
            <span style={{ color: '#e5534b' }}>
              <span style={{ display: 'inline-block', width: '6px', height: '6px', borderRadius: '50%', background: '#e5534b', marginRight: '4px' }} />
              异常 {data.summary.error}
            </span>
          </div>
        )}
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          style={{
            fontSize: '11px', padding: '3px 10px', borderRadius: '4px',
            border: '1px solid var(--border-subtle)', background: 'var(--bg-card)',
            color: 'var(--text-muted)', cursor: isFetching ? 'not-allowed' : 'pointer',
            opacity: isFetching ? 0.5 : 1,
          }}
        >
          {isFetching ? '...' : '刷新'}
        </button>
      </div>

      {isLoading && <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px', paddingTop: '48px' }}>加载中...</div>}
      {error && <div style={{ textAlign: 'center', color: '#e5534b', fontSize: '13px', paddingTop: '32px' }}>加载失败</div>}

      {data && (
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--border-subtle)',
          borderRadius: '8px', overflow: 'hidden',
        }}>
          <table style={{ width: '100%', fontSize: '12px', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                <th style={{ width: '24px', padding: '6px 8px' }}></th>
                <th style={{ textAlign: 'left', padding: '6px 8px', color: 'var(--text-muted)', fontWeight: 400 }}>数据类型</th>
                <th style={{ textAlign: 'center', padding: '6px 8px', color: 'var(--text-muted)', fontWeight: 400 }}>最新日期</th>
                <th style={{ textAlign: 'center', padding: '6px 8px', color: 'var(--text-muted)', fontWeight: 400 }}>距今</th>
                <th style={{ textAlign: 'right', padding: '6px 8px', color: 'var(--text-muted)', fontWeight: 400 }}>数量</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(grouped).map(([group, items]) => (
                <React.Fragment key={`g-${group}`}>
                  <tr style={{ background: 'var(--bg-nav-hover)' }}>
                    <td colSpan={5} style={{ padding: '4px 8px', fontSize: '11px', color: 'var(--text-muted)', fontWeight: 510 }}>
                      {group}
                    </td>
                  </tr>
                  {items.map((item) => (
                    <tr key={item.key} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <td style={{ textAlign: 'center', padding: '5px 8px' }}>
                        <span style={{
                          display: 'inline-block', width: '6px', height: '6px',
                          borderRadius: '50%', background: statusColor(item.status),
                        }} />
                      </td>
                      <td style={{ padding: '5px 8px', color: 'var(--text-secondary)' }}>{item.label}</td>
                      <td style={{ textAlign: 'center', padding: '5px 8px', color: 'var(--text-muted)', fontFamily: 'monospace', fontSize: '11px' }}>
                        {item.latest_date ?? '--'}
                      </td>
                      <td style={{ textAlign: 'center', padding: '5px 8px', color: dayColor(item.days_behind), fontSize: '11px' }}>
                        {dayLabel(item.days_behind)}
                      </td>
                      <td style={{ textAlign: 'right', padding: '5px 8px', color: 'var(--text-muted)' }}>
                        {item.count != null ? item.count.toLocaleString() : '--'}
                      </td>
                    </tr>
                  ))}
                </React.Fragment>
              ))}
            </tbody>
          </table>
          <div style={{ padding: '8px', fontSize: '11px', color: 'var(--text-muted)', borderTop: '1px solid var(--border-subtle)' }}>
            检查时间: {data.checked_at}
          </div>
        </div>
      )}
    </div>
  );
}
