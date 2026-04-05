'use client';

import { useEffect, useState } from 'react';
import Navbar from '@/components/layout/Navbar';
import apiClient from '@/lib/api-client';
import { useAuthStore } from '@/lib/store';
import { useRouter } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useBacktestSSE } from '@/hooks/useBacktestSSE';

interface Strategy {
  id: number;
  name: string;
  description: string | null;
  params: Record<string, unknown> | null;
  is_active: boolean;
  created_at: string;
}

interface BacktestJob {
  job_id: number;
  status: string;
  progress: number;
  stage: string | null;
  total_return: number | null;
  annual_return: number | null;
  max_drawdown: number | null;
  sharpe_ratio: number | null;
  ic: number | null;
  icir: number | null;
  error_msg: string | null;
  created_at: string;
  finished_at: string | null;
}

interface BacktestForm {
  name: string;
  strategy_type: string;
  start_date: string;
  end_date: string;
  initial_cash: number;
  commission: number;
  position_pct: number;
}

const defaultForm: BacktestForm = {
  name: '',
  strategy_type: 'xgboost',
  start_date: '2024-01-01',
  end_date: '2025-12-31',
  initial_cash: 1000000,
  commission: 0.0002,
  position_pct: 95,
};

export default function StrategyPage() {
  const router = useRouter();
  const { user } = useAuthStore();
  const queryClient = useQueryClient();
  const [activeTab, setActiveTab] = useState<'strategies' | 'backtest'>('backtest');
  const [form, setForm] = useState<BacktestForm>(defaultForm);
  const [activeJobId, setActiveJobId] = useState<number | null>(null);

  useEffect(() => {
    if (!user) router.push('/login');
  }, [user, router]);

  const { status: backtestStatus, isStreaming } = useBacktestSSE(activeJobId);

  const { data: strategies } = useQuery<Strategy[]>({
    queryKey: ['strategies'],
    queryFn: () => apiClient.get('/api/strategy/strategies').then((r) => r.data),
    enabled: !!user && activeTab === 'strategies',
  });

  const { data: backtests } = useQuery<{ count: number; data: BacktestJob[] }>({
    queryKey: ['backtests'],
    queryFn: () => apiClient.get('/api/strategy/backtests').then((r) => r.data),
    enabled: !!user,
  });

  const submitBacktest = useMutation({
    mutationFn: (params: BacktestForm) =>
      apiClient.post('/api/strategy/backtest', params).then((r) => r.data),
    onSuccess: (data) => {
      setActiveJobId(data.job_id);
      queryClient.invalidateQueries({ queryKey: ['backtests'] });
    },
  });

  const createStrategy = useMutation({
    mutationFn: (data: { name: string; description: string }) =>
      apiClient.post('/api/strategy/strategies', data).then((r) => r.data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strategies'] });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    submitBacktest.mutate(form);
  };

  const statusColor = (s: string) => {
    if (s === 'done') return 'text-green-600 bg-green-50';
    if (s === 'failed') return 'text-red-600 bg-red-50';
    if (s === 'running') return 'text-blue-600 bg-blue-50';
    return 'text-gray-600 bg-gray-50';
  };

  const pctColor = (v: number | null | undefined) => {
    if (v == null) return 'text-gray-400';
    if (v >= 0) return 'text-green-600';
    return 'text-red-600';
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Strategy & Backtest</h1>
          <div className="flex gap-1 bg-gray-100 rounded-lg p-1">
            <button
              onClick={() => setActiveTab('backtest')}
              className={`px-4 py-1.5 text-sm rounded-md transition-colors ${
                activeTab === 'backtest' ? 'bg-white shadow-sm font-medium' : 'text-gray-600'
              }`}
            >
              Backtest
            </button>
            <button
              onClick={() => setActiveTab('strategies')}
              className={`px-4 py-1.5 text-sm rounded-md transition-colors ${
                activeTab === 'strategies' ? 'bg-white shadow-sm font-medium' : 'text-gray-600'
              }`}
            >
              Strategies
            </button>
          </div>
        </div>

        {activeTab === 'backtest' && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Backtest Form */}
            <div className="bg-white rounded-lg border p-4">
              <h2 className="text-lg font-medium mb-4">New Backtest</h2>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Name</label>
                  <input
                    type="text"
                    required
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                    className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    placeholder="My Backtest"
                  />
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Start Date</label>
                    <input
                      type="date"
                      required
                      value={form.start_date}
                      onChange={(e) => setForm({ ...form, start_date: e.target.value })}
                      className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">End Date</label>
                    <input
                      type="date"
                      required
                      value={form.end_date}
                      onChange={(e) => setForm({ ...form, end_date: e.target.value })}
                      className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Initial Cash</label>
                    <input
                      type="number"
                      value={form.initial_cash}
                      onChange={(e) => setForm({ ...form, initial_cash: Number(e.target.value) })}
                      className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Commission</label>
                    <input
                      type="number"
                      step="0.0001"
                      value={form.commission}
                      onChange={(e) => setForm({ ...form, commission: Number(e.target.value) })}
                      className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">Position %</label>
                    <input
                      type="number"
                      value={form.position_pct}
                      onChange={(e) => setForm({ ...form, position_pct: Number(e.target.value) })}
                      className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={submitBacktest.isPending || isStreaming}
                  className="w-full rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-blue-300"
                >
                  {submitBacktest.isPending ? 'Submitting...' : isStreaming ? 'Running...' : 'Run Backtest'}
                </button>
              </form>

              {/* Live Progress */}
              {backtestStatus && isStreaming && (
                <div className="mt-4 p-3 bg-gray-50 rounded-md">
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-gray-600">{backtestStatus.stage || 'Processing...'}</span>
                    <span className="font-medium">{backtestStatus.progress}%</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-blue-600 h-2 rounded-full transition-all duration-500"
                      style={{ width: `${backtestStatus.progress}%` }}
                    />
                  </div>
                </div>
              )}

              {/* Result */}
              {backtestStatus && backtestStatus.status === 'done' && (
                <div className="mt-4 p-4 bg-green-50 rounded-md border border-green-200">
                  <h3 className="text-sm font-medium text-green-800 mb-3">Backtest Complete</h3>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <span className="text-gray-500">Total Return</span>
                      <p className={`font-medium ${pctColor(backtestStatus.total_return)}`}>
                        {backtestStatus.total_return != null ? `${backtestStatus.total_return.toFixed(2)}%` : '--'}
                      </p>
                    </div>
                    <div>
                      <span className="text-gray-500">Annual Return</span>
                      <p className={`font-medium ${pctColor(backtestStatus.annual_return)}`}>
                        {backtestStatus.annual_return != null ? `${backtestStatus.annual_return.toFixed(2)}%` : '--'}
                      </p>
                    </div>
                    <div>
                      <span className="text-gray-500">Max Drawdown</span>
                      <p className="font-medium text-red-600">
                        {backtestStatus.max_drawdown != null ? `${backtestStatus.max_drawdown.toFixed(2)}%` : '--'}
                      </p>
                    </div>
                    <div>
                      <span className="text-gray-500">Sharpe Ratio</span>
                      <p className="font-medium">
                        {backtestStatus.sharpe_ratio != null ? backtestStatus.sharpe_ratio.toFixed(2) : '--'}
                      </p>
                    </div>
                    <div>
                      <span className="text-gray-500">IC</span>
                      <p className="font-medium">
                        {backtestStatus.ic != null ? backtestStatus.ic.toFixed(4) : '--'}
                      </p>
                    </div>
                    <div>
                      <span className="text-gray-500">ICIR</span>
                      <p className="font-medium">
                        {backtestStatus.icir != null ? backtestStatus.icir.toFixed(4) : '--'}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {backtestStatus && backtestStatus.status === 'failed' && (
                <div className="mt-4 p-4 bg-red-50 rounded-md border border-red-200">
                  <h3 className="text-sm font-medium text-red-800">Backtest Failed</h3>
                  <p className="text-sm text-red-600 mt-1">{backtestStatus.error_msg || 'Unknown error'}</p>
                </div>
              )}
            </div>

            {/* Backtest History */}
            <div className="bg-white rounded-lg border p-4">
              <h2 className="text-lg font-medium mb-4">History</h2>
              {backtests && backtests.data.length > 0 ? (
                <div className="max-h-[600px] overflow-y-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b bg-gray-50">
                        <th className="text-left px-3 py-2 font-medium text-gray-500">Job</th>
                        <th className="text-left px-3 py-2 font-medium text-gray-500">Status</th>
                        <th className="text-right px-3 py-2 font-medium text-gray-500">Return</th>
                        <th className="text-right px-3 py-2 font-medium text-gray-500">MaxDD</th>
                        <th className="text-right px-3 py-2 font-medium text-gray-500">Sharpe</th>
                        <th className="text-right px-3 py-2 font-medium text-gray-500">IC</th>
                      </tr>
                    </thead>
                    <tbody>
                      {backtests.data.map((job) => (
                        <tr
                          key={job.job_id}
                          className="border-b last:border-0 hover:bg-gray-50 cursor-pointer"
                          onClick={() => setActiveJobId(job.job_id)}
                        >
                          <td className="px-3 py-2 font-mono text-xs">{job.job_id}</td>
                          <td className="px-3 py-2">
                            <span className={`text-xs px-2 py-0.5 rounded-full ${statusColor(job.status)}`}>
                              {job.status}
                            </span>
                          </td>
                          <td className={`px-3 py-2 text-right ${pctColor(job.total_return)}`}>
                            {job.total_return != null ? `${job.total_return.toFixed(2)}%` : '--'}
                          </td>
                          <td className="px-3 py-2 text-right text-red-600">
                            {job.max_drawdown != null ? `${job.max_drawdown.toFixed(2)}%` : '--'}
                          </td>
                          <td className="px-3 py-2 text-right">
                            {job.sharpe_ratio != null ? job.sharpe_ratio.toFixed(2) : '--'}
                          </td>
                          <td className="px-3 py-2 text-right">
                            {job.ic != null ? job.ic.toFixed(4) : '--'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="py-8 text-center text-gray-400">No backtest history</div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'strategies' && (
          <div className="bg-white rounded-lg border p-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-medium">My Strategies</h2>
            </div>
            {strategies && strategies.length > 0 ? (
              <div className="space-y-3">
                {strategies.map((s) => (
                  <div key={s.id} className="flex items-center justify-between px-4 py-3 border rounded-lg hover:bg-gray-50">
                    <div>
                      <p className="font-medium text-gray-900">{s.name}</p>
                      <p className="text-xs text-gray-500 mt-0.5">{s.description || 'No description'}</p>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className={`text-xs px-2 py-0.5 rounded-full ${s.is_active ? 'bg-green-50 text-green-700' : 'bg-gray-50 text-gray-500'}`}>
                        {s.is_active ? 'Active' : 'Inactive'}
                      </span>
                      <span className="text-xs text-gray-400">{s.created_at.split('T')[0]}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-8 text-center text-gray-400">No strategies yet</div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
