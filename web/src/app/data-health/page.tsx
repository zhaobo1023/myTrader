'use client';

import { useEffect } from 'react';
import Navbar from '@/components/layout/Navbar';
import apiClient from '@/lib/api-client';
import { useAuthStore } from '@/lib/store';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';

interface HealthItem {
  key: string;
  label: string;
  desc: string;
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

function StatusBadge({ status }: { status: HealthItem['status'] }) {
  const map = {
    ok: { label: '正常', cls: 'bg-green-100 text-green-800' },
    warn: { label: '偏旧', cls: 'bg-yellow-100 text-yellow-800' },
    error: { label: '异常', cls: 'bg-red-100 text-red-800' },
    unknown: { label: '未知', cls: 'bg-gray-100 text-gray-600' },
  };
  const { label, cls } = map[status] ?? map.unknown;
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${cls}`}>
      {label}
    </span>
  );
}

function DaysBehind({ days }: { days: number | null }) {
  if (days === null) return <span className="text-gray-400">-</span>;
  if (days === 0) return <span className="text-green-600">今天</span>;
  if (days === 1) return <span className="text-green-600">昨天</span>;
  const cls = days <= 3 ? 'text-yellow-600' : 'text-red-600';
  return <span className={cls}>{days} 天前</span>;
}

export default function DataHealthPage() {
  const router = useRouter();
  const { user } = useAuthStore();

  useEffect(() => {
    if (user !== undefined && (!user || user.role !== 'admin')) {
      router.push('/dashboard');
    }
  }, [user, router]);

  const { data, isLoading, error, refetch } = useQuery<HealthData>({
    queryKey: ['data-health'],
    queryFn: async () => {
      const res = await apiClient.get('/api/admin/data-health');
      return res.data;
    },
    refetchInterval: 60000,
  });

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <div className="max-w-4xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-xl font-semibold text-gray-900">数据完备度</h1>
            {data && (
              <p className="text-sm text-gray-500 mt-0.5">
                检查时间: {data.checked_at}
              </p>
            )}
          </div>
          <button
            onClick={() => refetch()}
            className="text-sm px-3 py-1.5 rounded bg-white border border-gray-200 text-gray-600 hover:bg-gray-50"
          >
            刷新
          </button>
        </div>

        {isLoading && (
          <div className="text-center py-12 text-gray-500">加载中...</div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 rounded p-4 text-red-700 text-sm">
            加载失败，请确认已登录管理员账号
          </div>
        )}

        {data && (
          <>
            <div className="grid grid-cols-3 gap-4 mb-6">
              <div className="bg-white rounded-lg border border-gray-200 p-4 text-center">
                <div className="text-2xl font-semibold text-green-600">{data.summary.ok}</div>
                <div className="text-sm text-gray-500 mt-1">正常</div>
              </div>
              <div className="bg-white rounded-lg border border-gray-200 p-4 text-center">
                <div className="text-2xl font-semibold text-yellow-600">{data.summary.warn}</div>
                <div className="text-sm text-gray-500 mt-1">偏旧</div>
              </div>
              <div className="bg-white rounded-lg border border-gray-200 p-4 text-center">
                <div className="text-2xl font-semibold text-red-600">{data.summary.error}</div>
                <div className="text-sm text-gray-500 mt-1">异常</div>
              </div>
            </div>

            <div className="bg-white rounded-lg border border-gray-200 divide-y divide-gray-100">
              {data.items.map((item) => (
                <div key={item.key} className="px-5 py-4 flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <span className="font-medium text-gray-900 text-sm">{item.label}</span>
                      <StatusBadge status={item.status} />
                    </div>
                    <p className="text-xs text-gray-500">{item.desc}</p>
                    {item.error && (
                      <p className="text-xs text-red-500 mt-1">{item.error}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-6 text-sm shrink-0">
                    <div className="text-right">
                      <div className="text-gray-400 text-xs mb-0.5">最新数据</div>
                      <div className="text-gray-800 font-mono text-xs">
                        {item.latest_date ?? '-'}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-gray-400 text-xs mb-0.5">距今</div>
                      <div className="text-xs">
                        <DaysBehind days={item.days_behind} />
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-gray-400 text-xs mb-0.5">{item.count_label}</div>
                      <div className="text-gray-800 text-xs">
                        {item.count !== null ? item.count.toLocaleString() : '-'}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            <p className="text-xs text-gray-400 mt-4 text-center">
              偏旧 = 数据超过正常更新周期；异常 = 数据严重滞后或表不存在
            </p>
          </>
        )}
      </div>
    </div>
  );
}
