'use client';

import { useQuery } from '@tanstack/react-query';
import apiClient from '@/lib/api-client';

interface AssetItem {
  key: string;
  name: string;
  group: string;
  unit: string;
  value: number | null;
  change: number | null;
  change_pct: number | null;
  date: string | null;
  trend: number[];
}

interface AssetGroup {
  name: string;
  items: AssetItem[];
}

function TinySparkline({ data, width = 80, height = 28 }: { data: number[]; width?: number; height?: number }) {
  if (data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const pad = 2;
  const pts = data
    .map((v, i) => {
      const x = pad + (i / (data.length - 1)) * (width - pad * 2);
      const y = pad + (1 - (v - min) / range) * (height - pad * 2);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
  const last = data[data.length - 1];
  const first = data[0];
  const color = last >= first ? '#27a644' : '#e5534b';
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="1.2" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function AssetCard({ item }: { item: AssetItem }) {
  const isUp = item.change != null && item.change > 0;
  const isDown = item.change != null && item.change < 0;
  const changeColor = isUp ? '#27a644' : isDown ? '#e5534b' : 'var(--text-muted)';
  const changeSign = isUp ? '+' : '';

  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border-subtle)',
      borderRadius: '8px',
      padding: '12px 14px',
      display: 'flex',
      flexDirection: 'column',
      gap: '6px',
      minWidth: 0,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '12px', fontWeight: 510, color: 'var(--text-secondary)' }}>{item.name}</span>
        {item.unit && <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{item.unit}</span>}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
        <div>
          <div style={{ fontSize: '18px', fontWeight: 590, color: 'var(--text-primary)', letterSpacing: '-0.3px' }}>
            {item.value != null ? item.value.toLocaleString() : '--'}
          </div>
          {item.change_pct != null && (
            <div style={{ fontSize: '11px', color: changeColor, marginTop: '2px' }}>
              {changeSign}{item.change_pct.toFixed(2)}%
              {item.change != null && (
                <span style={{ marginLeft: '4px', opacity: 0.7 }}>{changeSign}{item.change}</span>
              )}
            </div>
          )}
        </div>
        {item.trend.length >= 2 && <TinySparkline data={item.trend} />}
      </div>
    </div>
  );
}

export default function GlobalAssetsPanel() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['globalAssets'],
    queryFn: () => apiClient.get('/api/market/global-assets', { params: { days: 30 } }).then((r) => r.data),
    staleTime: 5 * 60 * 1000,
  });

  if (isLoading) return <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px', paddingTop: '48px' }}>加载全球资产数据...</div>;
  if (error) return <div style={{ textAlign: 'center', color: '#e5534b', fontSize: '13px', paddingTop: '32px' }}>加载失败，请检查API或运行 macro_fetcher 拉取数据</div>;
  if (!data?.groups) return null;

  const groups: AssetGroup[] = data.groups;

  return (
    <div>
      {groups.map((group) => (
        <div key={group.name}>
          <h2 style={{ fontSize: '11px', fontWeight: 510, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.8px', margin: '24px 0 10px' }}>
            {group.name}
          </h2>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
            gap: '10px',
          }}>
            {group.items.map((item: AssetItem) => (
              <AssetCard key={item.key} item={item} />
            ))}
          </div>
        </div>
      ))}
      {data.updated && (
        <p style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '24px' }}>
          数据来源: macro_data | 更新: {data.updated}
        </p>
      )}
    </div>
  );
}
