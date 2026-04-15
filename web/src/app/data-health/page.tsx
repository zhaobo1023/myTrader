'use client';

import { useState, Fragment } from 'react';
import { useQuery } from '@tanstack/react-query';
import apiClient from '@/lib/api-client';
import AppShell from '@/components/layout/AppShell';

// ============================================================
// Types
// ============================================================

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

interface TaskRun {
  status: string;
  duration_ms: number | null;
  record_count: number | null;
  error_msg: string | null;
}

interface TaskRow {
  task_name: string;
  task_group: string;
  label: string;
  runs: Record<string, TaskRun>;
}

interface TaskRunData {
  dates: string[];
  tasks: TaskRow[];
  summary: Record<string, { success: number; failed: number; running: number; skipped: number; total: number }>;
}

// ============================================================
// Helpers
// ============================================================

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

function runStatusCell(run: TaskRun | undefined) {
  if (!run) {
    return (
      <div className="flex items-center justify-center" title="未运行">
        <span className="inline-block w-2.5 h-2.5 rounded-full bg-gray-200" />
      </div>
    );
  }
  const colorMap: Record<string, string> = {
    success: 'bg-green-500',
    failed: 'bg-red-500',
    running: 'bg-yellow-400 animate-pulse',
    skipped: 'bg-gray-400',
  };
  const dur = run.duration_ms !== null ? `${(run.duration_ms / 1000).toFixed(1)}s` : '';
  const title = [
    run.status,
    dur && `耗时${dur}`,
    run.record_count !== null && `${run.record_count}条`,
    run.error_msg,
  ].filter(Boolean).join(' | ');

  return (
    <div className="flex items-center justify-center" title={title}>
      <span className={`inline-block w-2.5 h-2.5 rounded-full ${colorMap[run.status] ?? 'bg-gray-300'}`} />
    </div>
  );
}

// ============================================================
// Tab 1: Data Completeness
// ============================================================

function DataCompletenessTab() {
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
      <div className="flex items-center justify-between mb-4">
        <div>
          {data && <p className="text-xs text-gray-400">检查时间: {data.checked_at}</p>}
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
                <Fragment key={`g-${group}`}>
                  <tr className="bg-gray-50/60">
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
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ============================================================
// Tab 2: Task Run Status
// ============================================================

function TaskRunStatusTab() {
  const [selectedCell, setSelectedCell] = useState<{ task: string; date: string; run: TaskRun } | null>(null);

  const { data, isLoading, error, refetch, isFetching } = useQuery<TaskRunData>({
    queryKey: ['task-runs'],
    queryFn: async () => {
      const res = await apiClient.get('/api/admin/task-runs', { params: { days: 7 } });
      return res.data;
    },
    refetchInterval: 120000,
  });

  // Group tasks by task_group
  const grouped = data
    ? data.tasks.reduce<Record<string, TaskRow[]>>((acc, t) => {
        const g = t.task_group || '其他';
        if (!acc[g]) acc[g] = [];
        acc[g].push(t);
        return acc;
      }, {})
    : {};

  const groupOrder = ['data_fetch', 'factor', 'indicator', 'strategy', 'report', 'sentiment'];
  const groupLabels: Record<string, string> = {
    data_fetch: '数据拉取',
    factor: '因子计算',
    indicator: '技术指标',
    strategy: '策略',
    report: '报告',
    sentiment: '情绪',
  };

  const sortedGroups = Object.keys(grouped).sort(
    (a, b) => (groupOrder.indexOf(a) === -1 ? 99 : groupOrder.indexOf(a))
            - (groupOrder.indexOf(b) === -1 ? 99 : groupOrder.indexOf(b))
  );

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          {data && (
            <div className="flex gap-3 text-xs">
              {data.dates[0] && data.summary[data.dates[0]] && (
                <>
                  <span className="text-green-600">成功 {data.summary[data.dates[0]].success}</span>
                  <span className="text-red-500">失败 {data.summary[data.dates[0]].failed}</span>
                  <span className="text-yellow-600">运行中 {data.summary[data.dates[0]].running}</span>
                </>
              )}
            </div>
          )}
        </div>
        <button
          onClick={() => refetch()}
          disabled={isFetching}
          className="text-xs px-2.5 py-1 rounded border border-gray-200 bg-white text-gray-500 hover:bg-gray-50 disabled:opacity-50"
        >
          {isFetching ? '刷新中...' : '刷新'}
        </button>
      </div>

      {isLoading && <div className="text-sm text-gray-400 py-8 text-center">加载中...</div>}
      {error && (
        <div className="text-sm text-red-500 py-4 text-center">
          加载失败
        </div>
      )}

      {data && data.dates.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-50 text-gray-400 border-b border-gray-100">
                <th className="text-left px-3 py-2 font-medium min-w-[140px] sticky left-0 bg-gray-50">任务</th>
                {data.dates.map((d) => (
                  <th key={d} className="text-center px-2 py-2 font-medium whitespace-nowrap font-mono">
                    {d.slice(5)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {sortedGroups.map((group) => (
                <Fragment key={`tg-${group}`}>
                  <tr className="bg-gray-50/60">
                    <td colSpan={data.dates.length + 1} className="px-3 py-1.5 text-gray-400 font-medium text-xs">
                      {groupLabels[group] || group}
                    </td>
                  </tr>
                  {grouped[group].map((task) => (
                    <tr key={task.task_name} className="hover:bg-gray-50/50">
                      <td className="px-3 py-2 text-gray-700 sticky left-0 bg-white">{task.label}</td>
                      {data.dates.map((d) => {
                        const run = task.runs[d];
                        return (
                          <td
                            key={d}
                            className="px-2 py-2 cursor-pointer"
                            onClick={() => run && setSelectedCell({ task: task.label, date: d, run })}
                          >
                            {runStatusCell(run)}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && data.tasks.length === 0 && (
        <div className="text-sm text-gray-400 py-8 text-center">暂无任务运行记录</div>
      )}

      {/* Detail popover */}
      {selectedCell && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/20" onClick={() => setSelectedCell(null)}>
          <div className="bg-white rounded-lg shadow-lg p-4 max-w-sm w-full mx-4" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-medium text-gray-800">{selectedCell.task}</h3>
              <span className="text-xs text-gray-400 font-mono">{selectedCell.date}</span>
            </div>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-gray-500">状态</span>
                <span className={
                  selectedCell.run.status === 'success' ? 'text-green-600' :
                  selectedCell.run.status === 'failed' ? 'text-red-500' :
                  'text-yellow-600'
                }>{selectedCell.run.status}</span>
              </div>
              {selectedCell.run.duration_ms !== null && (
                <div className="flex justify-between">
                  <span className="text-gray-500">耗时</span>
                  <span className="text-gray-700">{(selectedCell.run.duration_ms / 1000).toFixed(1)}s</span>
                </div>
              )}
              {selectedCell.run.record_count !== null && (
                <div className="flex justify-between">
                  <span className="text-gray-500">记录数</span>
                  <span className="text-gray-700">{selectedCell.run.record_count.toLocaleString()}</span>
                </div>
              )}
              {selectedCell.run.error_msg && (
                <div>
                  <span className="text-gray-500">错误</span>
                  <p className="mt-1 text-red-500 bg-red-50 rounded p-2 break-all">{selectedCell.run.error_msg}</p>
                </div>
              )}
            </div>
            <button
              onClick={() => setSelectedCell(null)}
              className="mt-4 w-full text-xs py-1.5 rounded border border-gray-200 text-gray-500 hover:bg-gray-50"
            >
              关闭
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ============================================================
// Main Page
// ============================================================

export default function DataHealthPage() {
  const [tab, setTab] = useState<'completeness' | 'task-runs'>('completeness');

  return (
    <AppShell>
      <div>
        <div className="flex items-center justify-between mb-4">
          <h1 style={{ fontSize: '20px', fontWeight: 590, color: 'var(--text-primary)', letterSpacing: '-0.3px' }}>
            数据健康
          </h1>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-5 border-b border-gray-200">
          <button
            onClick={() => setTab('completeness')}
            className={`px-3 py-2 text-xs font-medium border-b-2 -mb-px transition-colors ${
              tab === 'completeness'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-400 hover:text-gray-600'
            }`}
          >
            数据完备度
          </button>
          <button
            onClick={() => setTab('task-runs')}
            className={`px-3 py-2 text-xs font-medium border-b-2 -mb-px transition-colors ${
              tab === 'task-runs'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-400 hover:text-gray-600'
            }`}
          >
            任务运行状态
          </button>
        </div>

        {tab === 'completeness' && <DataCompletenessTab />}
        {tab === 'task-runs' && <TaskRunStatusTab />}
      </div>
    </AppShell>
  );
}
