'use client';

import { useState, Fragment } from 'react';
import { useQuery } from '@tanstack/react-query';
import apiClient from '@/lib/api-client';
import AppShell from '@/components/layout/AppShell';
import { ProtectedRoute } from '@/components/layout/ProtectedRoute';
import WechatSubscriptionsPanel from '@/components/wechat-subscriptions-panel';

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
  expected_count: number | null;
  completeness: number | null;
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
    staleTime: 60 * 60 * 1000, // match server-side 1h cache
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
                <th className="text-right px-3 py-2 font-medium w-24">完备度</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {Object.entries(grouped).map(([group, items]) => (
                <Fragment key={`g-${group}`}>
                  <tr className="bg-gray-50/60">
                    <td colSpan={6} className="px-3 py-1.5 text-gray-400 font-medium text-xs">
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
                      <td className="px-3 py-2">
                        {item.completeness !== null ? (
                          <div className="flex items-center gap-1.5 justify-end">
                            <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                              <div
                                className={`h-full rounded-full ${
                                  item.completeness >= 90
                                    ? 'bg-green-500'
                                    : item.completeness >= 60
                                    ? 'bg-yellow-400'
                                    : 'bg-red-400'
                                }`}
                                style={{ width: `${item.completeness}%` }}
                              />
                            </div>
                            <span className={`text-xs tabular-nums ${
                              item.completeness >= 90
                                ? 'text-green-600'
                                : item.completeness >= 60
                                ? 'text-yellow-600'
                                : 'text-red-500'
                            }`}>
                              {item.completeness}%
                            </span>
                          </div>
                        ) : (
                          <span className="text-gray-300 text-xs block text-right">-</span>
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

/** Returns true for Saturday (6) or Sunday (0) */
function isWeekend(dateStr: string) {
  const d = new Date(dateStr + 'T00:00:00');
  const day = d.getDay();
  return day === 0 || day === 6;
}

function TaskRunStatusTab() {
  const [selectedCell, setSelectedCell] = useState<{ task: string; date: string; run: TaskRun } | null>(null);

  const { data, isLoading, error, refetch, isFetching } = useQuery<TaskRunData>({
    queryKey: ['task-runs'],
    queryFn: async () => {
      const res = await apiClient.get('/api/admin/task-runs', { params: { days: 14 } });
      return res.data;
    },
    staleTime: 60 * 60 * 1000,
  });

  // Filter out weekends — show only trading-day columns
  const tradingDates = data ? data.dates.filter((d) => !isWeekend(d)) : [];

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
          {data && tradingDates[0] && (
            <div className="flex gap-3 text-xs">
              {data.summary[tradingDates[0]] && (
                <>
                  <span className="text-green-600">成功 {data.summary[tradingDates[0]].success}</span>
                  <span className="text-red-500">失败 {data.summary[tradingDates[0]].failed}</span>
                  <span className="text-yellow-600">运行中 {data.summary[tradingDates[0]].running}</span>
                </>
              )}
              <span className="text-gray-400">（已过滤周末，显示最近交易日）</span>
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

      {data && tradingDates.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-50 text-gray-400 border-b border-gray-100">
                <th className="text-left px-3 py-2 font-medium min-w-[140px] sticky left-0 bg-gray-50">任务</th>
                {tradingDates.map((d) => (
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
                    <td colSpan={tradingDates.length + 1} className="px-3 py-1.5 text-gray-400 font-medium text-xs">
                      {groupLabels[group] || group}
                    </td>
                  </tr>
                  {grouped[group].map((task) => (
                    <tr key={task.task_name} className="hover:bg-gray-50/50">
                      <td className="px-3 py-2 text-gray-700 sticky left-0 bg-white">{task.label}</td>
                      {tradingDates.map((d) => {
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
// Tab 3: Scheduler Plan
// ============================================================

interface DepDetail { id: string; status: string }

interface SchedulerTask {
  id: string;
  name: string;
  group: string;
  schedule: string;
  enabled: boolean;
  tags: string[];
  depends_on: string[];
  deps_detail: DepDetail[];
  deps_ok: boolean;
  today_status: string | null;
  latest_run: {
    status: string;
    started_at: string | null;
    finished_at: string | null;
    duration_s: number;
    error_msg: string | null;
    triggered_by: string | null;
  } | null;
  alert_on_failure: boolean;
}

/** Infer frequency badge from schedule string and tags */
function freqBadge(schedule: string, tags: string[]) {
  if (!schedule || schedule === 'manual') return null;
  // cron with day-of-week restriction (e.g. "0 8 * * 1-5") = weekly-ish or workday
  // simple HH:MM or after_gate = daily
  // cron "0 8 * * 0" or similar with specific day = weekly
  const isCron = /\d+\s+\d+\s+\*\s+\*\s+\S+/.test(schedule.trim());
  if (isCron) {
    // check if it runs every day or only specific days
    const parts = schedule.trim().split(/\s+/);
    const dow = parts[4] || '*';
    if (dow === '*' || dow === '1-5') {
      return <span className="text-xs px-1.5 py-0.5 rounded bg-blue-50 text-blue-500 border border-blue-100">日</span>;
    }
    return <span className="text-xs px-1.5 py-0.5 rounded bg-purple-50 text-purple-500 border border-purple-100">周</span>;
  }
  if (tags.includes('weekly')) {
    return <span className="text-xs px-1.5 py-0.5 rounded bg-purple-50 text-purple-500 border border-purple-100">周</span>;
  }
  // HH:MM or after_gate = daily
  return <span className="text-xs px-1.5 py-0.5 rounded bg-blue-50 text-blue-500 border border-blue-100">日</span>;
}

interface SchedulerData {
  tasks: SchedulerTask[];
  as_of: string;
}

const SCHEDULE_LABEL: Record<string, string> = {
  after_gate: '行情就绪后',
  manual: '手动',
};

function scheduleDisplay(s: string) {
  if (!s) return '-';
  if (s in SCHEDULE_LABEL) return SCHEDULE_LABEL[s];
  if (/^\d{1,2}:\d{2}$/.test(s)) return s;
  // cron
  return s;
}

function todayStatusBadge(status: string | null) {
  if (!status) return <span className="text-gray-300 text-xs">未执行</span>;
  const map: Record<string, string> = {
    success: 'text-green-600 bg-green-50 border-green-200',
    failed: 'text-red-500 bg-red-50 border-red-200',
    running: 'text-yellow-600 bg-yellow-50 border-yellow-200',
    skipped: 'text-gray-400 bg-gray-50 border-gray-200',
  };
  const labels: Record<string, string> = { success: '成功', failed: '失败', running: '运行中', skipped: '跳过' };
  return (
    <span className={`text-xs px-2 py-0.5 rounded border ${map[status] ?? 'text-gray-400'}`}>
      {labels[status] ?? status}
    </span>
  );
}

function SchedulerTab() {
  const [triggering, setTriggering] = useState<string | null>(null);
  const [triggerMsg, setTriggerMsg] = useState<Record<string, string>>({});
  const [watchdogRunning, setWatchdogRunning] = useState(false);
  const [watchdogResult, setWatchdogResult] = useState<{ missed_count: number; missed: { id: string; name: string; schedule: string; missed_by_minutes: number }[] } | null>(null);

  const { data, isLoading, error, refetch, isFetching } = useQuery<SchedulerData>({
    queryKey: ['scheduler-tasks'],
    queryFn: async () => {
      const res = await apiClient.get('/api/admin/scheduler/tasks');
      return res.data;
    },
    staleTime: 30 * 1000,
  });

  const handleTrigger = async (taskId: string, force: boolean) => {
    if (triggering) return;
    setTriggering(taskId);
    setTriggerMsg((prev) => ({ ...prev, [taskId]: '触发中...' }));
    try {
      const res = await apiClient.post('/api/admin/scheduler/trigger', { task_id: taskId, force });
      const result = res.data.result as string;
      const label = result === 'success' ? '执行成功' : result === 'failed' ? '执行失败' : result;
      setTriggerMsg((prev) => ({ ...prev, [taskId]: label }));
      setTimeout(() => {
        setTriggerMsg((prev) => { const n = { ...prev }; delete n[taskId]; return n; });
        refetch();
      }, 3000);
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail || '触发失败';
      setTriggerMsg((prev) => ({ ...prev, [taskId]: msg }));
    } finally {
      setTriggering(null);
    }
  };

  const handleWatchdog = async () => {
    setWatchdogRunning(true);
    setWatchdogResult(null);
    try {
      const res = await apiClient.post('/api/admin/scheduler/watchdog', {});
      setWatchdogResult(res.data);
    } catch {
      setWatchdogResult({ missed_count: -1, missed: [] });
    } finally {
      setWatchdogRunning(false);
    }
  };

  const grouped = data
    ? data.tasks.reduce<Record<string, SchedulerTask[]>>((acc, t) => {
        const g = t.group || '其他';
        if (!acc[g]) acc[g] = [];
        acc[g].push(t);
        return acc;
      }, {})
    : {};

  const groupLabels: Record<string, string> = {
    daily: '每日数据',
    data_fetch: '数据拉取',
    gate: '数据门控',
    factor: '因子计算',
    indicator: '技术指标',
    strategy: '策略',
    macro: '宏观',
    sentiment: '情绪',
    health: '健康检查',
    candidate: '候选池',
    report: '报告',
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div className="text-xs text-gray-400">{data ? `截至 ${data.as_of}` : ''}</div>
        <div className="flex gap-2">
          <button
            onClick={handleWatchdog}
            disabled={watchdogRunning}
            className="text-xs px-3 py-1.5 rounded border border-orange-200 bg-orange-50 text-orange-600 hover:bg-orange-100 disabled:opacity-50"
          >
            {watchdogRunning ? '检测中...' : '漏执行检测'}
          </button>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="text-xs px-2.5 py-1 rounded border border-gray-200 bg-white text-gray-500 hover:bg-gray-50 disabled:opacity-50"
          >
            {isFetching ? '刷新中...' : '刷新'}
          </button>
        </div>
      </div>

      {watchdogResult && (
        <div className={`mb-4 p-3 rounded-lg border text-xs ${watchdogResult.missed_count === 0 ? 'bg-green-50 border-green-200 text-green-700' : watchdogResult.missed_count < 0 ? 'bg-red-50 border-red-200 text-red-600' : 'bg-orange-50 border-orange-200 text-orange-700'}`}>
          {watchdogResult.missed_count < 0 ? '检测失败，请查看日志' :
           watchdogResult.missed_count === 0 ? '所有计划任务均已按时执行' :
           `检测到 ${watchdogResult.missed_count} 个漏执行任务，已自动触发重试：${watchdogResult.missed.map(t => `${t.name}（超时${t.missed_by_minutes}分钟）`).join('、')}`}
        </div>
      )}

      {isLoading && <div className="text-sm text-gray-400 py-8 text-center">加载中...</div>}
      {error && <div className="text-sm text-red-500 py-4 text-center">加载失败</div>}

      {data && (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-50 text-gray-400 border-b border-gray-100">
                <th className="text-left px-3 py-2 font-medium">任务名称</th>
                <th className="text-center px-3 py-2 font-medium w-20">计划时间</th>
                <th className="text-center px-3 py-2 font-medium w-20">今日状态</th>
                <th className="text-left px-3 py-2 font-medium w-32">最近执行</th>
                <th className="text-left px-3 py-2 font-medium w-28">前置条件</th>
                <th className="text-right px-3 py-2 font-medium w-28">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {Object.entries(grouped).map(([group, tasks]) => (
                <Fragment key={`g-${group}`}>
                  <tr className="bg-gray-50/60">
                    <td colSpan={6} className="px-3 py-1.5 text-gray-400 font-medium text-xs">
                      {groupLabels[group] ?? group}
                    </td>
                  </tr>
                  {tasks.filter(t => t.enabled).map((task) => {
                    const msg = triggerMsg[task.id];
                    const isTriggering = triggering === task.id;
                    const canRun = task.deps_ok;
                    return (
                      <tr key={task.id} className="hover:bg-gray-50/50">
                        <td className="px-3 py-2">
                          <div className="flex items-center gap-1.5">
                            <span className="text-gray-700 font-medium">{task.name}</span>
                            {freqBadge(task.schedule, task.tags ?? [])}
                          </div>
                          <div className="text-gray-300 font-mono">{task.id}</div>
                        </td>
                        <td className="px-3 py-2 text-center text-gray-500 font-mono">
                          {scheduleDisplay(task.schedule)}
                        </td>
                        <td className="px-3 py-2 text-center">
                          {todayStatusBadge(task.today_status)}
                        </td>
                        <td className="px-3 py-2">
                          {task.latest_run ? (
                            <div>
                              <div className={task.latest_run.status === 'success' ? 'text-green-600' : task.latest_run.status === 'failed' ? 'text-red-500' : 'text-gray-400'}>
                                {task.latest_run.status}
                                {task.latest_run.duration_s > 0 && ` · ${task.latest_run.duration_s.toFixed(0)}s`}
                              </div>
                              <div className="text-gray-300 font-mono text-xs">
                                {task.latest_run.started_at?.slice(0, 16) ?? ''}
                              </div>
                              {task.latest_run.error_msg && (
                                <div className="text-red-400 truncate max-w-xs" title={task.latest_run.error_msg}>
                                  {task.latest_run.error_msg.slice(0, 40)}
                                </div>
                              )}
                            </div>
                          ) : (
                            <span className="text-gray-300">从未运行</span>
                          )}
                        </td>
                        <td className="px-3 py-2">
                          {task.depends_on.length === 0 ? (
                            <span className="text-gray-300">无</span>
                          ) : (
                            <div className="flex flex-col gap-0.5">
                              {task.deps_detail.map((dep) => (
                                <span key={dep.id} className={`text-xs ${dep.status === 'success' ? 'text-green-600' : dep.status === 'not_run' ? 'text-gray-400' : 'text-red-400'}`}>
                                  {dep.status === 'success' ? '[√]' : dep.status === 'not_run' ? '[?]' : '[x]'} {dep.id.replace('_gate_', '').replace('fetch_', '').replace('calc_', '')}
                                </span>
                              ))}
                            </div>
                          )}
                        </td>
                        <td className="px-3 py-2 text-right">
                          {msg ? (
                            <span className={`text-xs ${msg.includes('成功') ? 'text-green-600' : msg.includes('失败') ? 'text-red-500' : 'text-gray-400'}`}>
                              {msg}
                            </span>
                          ) : (
                            <div className="flex gap-1 justify-end">
                              <button
                                onClick={() => handleTrigger(task.id, false)}
                                disabled={isTriggering || !canRun}
                                title={!canRun ? `前置条件未满足: ${task.deps_detail.filter(d => d.status !== 'success').map(d => d.id).join(', ')}` : '立即执行（需前置条件已完成）'}
                                className={`text-xs px-2 py-1 rounded border transition-colors ${
                                  canRun && !isTriggering
                                    ? 'border-blue-200 bg-blue-50 text-blue-600 hover:bg-blue-100 cursor-pointer'
                                    : 'border-gray-100 bg-gray-50 text-gray-300 cursor-not-allowed'
                                }`}
                              >
                                {isTriggering ? '...' : '执行'}
                              </button>
                              {!canRun && (
                                <button
                                  onClick={() => handleTrigger(task.id, true)}
                                  disabled={isTriggering}
                                  title="忽略前置条件强制执行"
                                  className="text-xs px-2 py-1 rounded border border-orange-200 bg-orange-50 text-orange-500 hover:bg-orange-100 cursor-pointer"
                                >
                                  强制
                                </button>
                              )}
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
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
// Main Page
// ============================================================

export default function DataHealthPage() {
  const [tab, setTab] = useState<'completeness' | 'task-runs' | 'scheduler' | 'wechat'>('completeness');

  const tabItems: { key: typeof tab; label: string }[] = [
    { key: 'completeness', label: '数据完备度' },
    { key: 'task-runs',    label: '任务运行状态' },
    { key: 'scheduler',   label: '调度计划' },
    { key: 'wechat',      label: '公众号订阅' },
  ];

  return (
    <ProtectedRoute routePath="/data-health">
      <AppShell>
      <div>
        <div className="flex items-center justify-between mb-4">
          <h1 style={{ fontSize: '20px', fontWeight: 590, color: 'var(--text-primary)', letterSpacing: '-0.3px' }}>
            数据健康
          </h1>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 mb-5 border-b border-gray-200">
          {tabItems.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`px-3 py-2 text-xs font-medium border-b-2 -mb-px transition-colors ${
                tab === key
                  ? 'border-blue-500 text-blue-600'
                  : 'border-transparent text-gray-400 hover:text-gray-600'
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {tab === 'completeness' && <DataCompletenessTab />}
        {tab === 'task-runs' && <TaskRunStatusTab />}
        {tab === 'scheduler' && <SchedulerTab />}
        {tab === 'wechat' && <WechatSubscriptionsPanel />}
      </div>
      </AppShell>
    </ProtectedRoute>
  );
}
