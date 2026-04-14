'use client';

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

function statusDot(status: HealthItem['status']) {
  const map = {
    ok: 'bg-green-500',
    warn: 'bg-yellow-400',
    error: 'bg-red-500',
    unknown: 'bg-gray-300',
  };
  return <span className={`inline-block w-2 h-2 rounded-full ${map[status] ?? map.unknown}`} />;
}

function dayLabel(days: number | null) {
  if (days === null) return <span className="text-gray-300">-</span>;
  if (days === 0) return <span className="text-green-600 font-medium">今天</span>;
  if (days === 1) return <span className="text-green-600">昨天</span>;
  if (days <= 3) return <span className="text-yellow-600">{days}天前</span>;
  return <span className="text-red-500 font-medium">{days}天前</span>;
}

export default function DataHealthPage() {
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
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h1 className="text-base font-semibold text-gray-800">数据完备度</h1>
            {data && <p className="text-xs text-gray-400 mt-0.5">检查时间: {data.checked_at}</p>}
          </div>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="text-xs px-2.5 py-1 rounded border border-gray-200 bg-white text-gray-500 hover:bg-gray-50 disabled:opacity-50"
          >
            {isFetching ? '刷新中...' : '刷新'}
          </button>
        </div>

        {data && (
          <div className="flex gap-3 mb-5 text-xs">
            <span className="flex items-center gap-1.5 text-green-600">
              <span className="inline-block w-2 h-2 rounded-full bg-green-500" /> 正常 {data.summary.ok}
            </span>
            <span className="flex items-center gap-1.5 text-yellow-600">
              <span className="inline-block w-2 h-2 rounded-full bg-yellow-400" /> 偏旧 {data.summary.warn}
            </span>
            <span className="flex items-center gap-1.5 text-red-500">
              <span className="inline-block w-2 h-2 rounded-full bg-red-500" /> 异常 {data.summary.error}
            </span>
          </div>
        )}

        {isLoading && <div className="text-sm text-gray-400 py-8 text-center">加载中...</div>}
        {error && (
          <div className="text-sm text-red-500 py-4 text-center">
            加载失败，请确认已登录管理员账号
          </div>
        )}

        {data && (
          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-50 text-gray-400 border-b border-gray-100">
                  <th className="text-left px-3 py-2 font-medium w-6"></th>
                  <th className="text-left px-3 py-2 font-medium">数据类型</th>
                  <th className="text-center px-3 py-2 font-medium">最新日期</th>
                  <th className="text-center px-3 py-2 font-medium">距今</th>
                  <th className="text-right px-3 py-2 font-medium">数量</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {Object.entries(grouped).map(([group, items]) => (
                  <>
                    <tr key={`g-${group}`} className="bg-gray-50/60">
                      <td colSpan={5} className="px-3 py-1.5 text-gray-400 font-medium text-xs">
                        {group}
                      </td>
                    </tr>
                    {items.map((item) => (
                      <tr key={item.key} className="hover:bg-gray-50/50">
                        <td className="px-3 py-2 text-center">{statusDot(item.status)}</td>
                        <td className="px-3 py-2 text-gray-700">{item.label}</td>
                        <td className="px-3 py-2 text-center font-mono text-gray-500">
                          {item.latest_date ?? <span className="text-gray-300">-</span>}
                        </td>
                        <td className="px-3 py-2 text-center">{dayLabel(item.days_behind)}</td>
                        <td className="px-3 py-2 text-right text-gray-500">
                          {item.count !== null ? (
                            <span title={item.count_label}>{item.count.toLocaleString()}</span>
                          ) : (
                            <span className="text-gray-300">-</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
