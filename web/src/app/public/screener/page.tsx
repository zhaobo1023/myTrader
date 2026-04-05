'use client';

import { useState } from 'react';
import Link from 'next/link';
import apiClient from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';

export default function PublicScreenerPage() {
  const [searchCode, setSearchCode] = useState('');
  const [activeCode, setActiveCode] = useState('');
  const [rpsWindow, setRpsWindow] = useState(120);

  const { data: tech } = useQuery({
    queryKey: ['public-technical', activeCode],
    queryFn: () =>
      apiClient.get('/api/analysis/technical', { params: { code: activeCode } }).then((r) => r.data),
    enabled: !!activeCode,
  });

  const { data: rps } = useQuery({
    queryKey: ['public-rps', rpsWindow],
    queryFn: () =>
      apiClient.get('/api/market/rps', { params: { window: rpsWindow, top_n: 30 } }).then((r) => r.data),
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchCode.trim()) setActiveCode(searchCode.trim());
  };

  const scoreColor = (s: number) => {
    if (s > 20) return 'text-green-600';
    if (s < -20) return 'text-red-600';
    return 'text-yellow-600';
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Minimal header for public page */}
      <header className="bg-white border-b">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex h-14 items-center justify-between">
            <Link href="/" className="text-lg font-bold text-gray-900">
              myTrader
            </Link>
            <div className="flex items-center gap-4">
              <span className="text-sm text-gray-500">Public Screener</span>
              <Link href="/login" className="text-sm text-blue-600 hover:text-blue-500 font-medium">
                Sign In
              </Link>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900 mb-2">Stock Screener</h1>
          <p className="text-sm text-gray-500">
            Free access to RPS rankings and technical analysis. Sign up for full features.
          </p>
        </div>

        {/* Search */}
        <form onSubmit={handleSearch} className="flex gap-2 mb-6">
          <input
            type="text"
            value={searchCode}
            onChange={(e) => setSearchCode(e.target.value)}
            placeholder="Enter stock code (e.g. 600519)"
            className="w-64 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
          <button
            type="submit"
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          >
            Analyze
          </button>
        </form>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Technical Analysis */}
          {activeCode && (
            <div className="bg-white rounded-lg border p-4">
              <h2 className="text-lg font-medium mb-4">
                Technical: {activeCode}
              </h2>
              {tech ? (
                <>
                  <div className="flex items-center gap-4 mb-4">
                    <span className="text-sm text-gray-500">Score:</span>
                    <span className={`text-2xl font-bold ${scoreColor(tech.score || 0)}`}>
                      {tech.score || 0}
                    </span>
                  </div>
                  <p className="text-sm text-gray-600 mb-4">{tech.summary}</p>
                  {tech.signals?.length > 0 ? (
                    <div className="space-y-2">
                      {tech.signals.map((s: Record<string, unknown>, i: number) => (
                        <div
                          key={i}
                          className={`flex items-center gap-2 text-sm px-3 py-2 rounded ${
                            s.signal === 'bullish'
                              ? 'bg-green-50 text-green-700'
                              : s.signal === 'bearish'
                                ? 'bg-red-50 text-red-700'
                                : 'bg-gray-50 text-gray-600'
                          }`}
                        >
                          <span className="font-medium">{String(s.name)}</span>
                          <span className="text-xs">{String(s.description)}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-gray-400">No signals available</p>
                  )}
                </>
              ) : (
                <div className="py-8 text-center text-gray-400">Loading...</div>
              )}
            </div>
          )}

          {/* RPS Ranking */}
          <div className={`bg-white rounded-lg border p-4 ${!activeCode ? 'lg:col-span-3' : ''}`}>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-medium">RPS Rankings</h2>
              <select
                value={rpsWindow}
                onChange={(e) => setRpsWindow(Number(e.target.value))}
                className="rounded-md border border-gray-300 px-2 py-1 text-sm"
              >
                <option value={20}>20 days</option>
                <option value={60}>60 days</option>
                <option value={120}>120 days</option>
                <option value={250}>250 days</option>
              </select>
            </div>

            {rps?.data && rps.data.length > 0 ? (
              <div className="max-h-[600px] overflow-y-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-gray-50">
                      <th className="text-left px-2 py-1 font-medium text-gray-500">#</th>
                      <th className="text-left px-2 py-1 font-medium text-gray-500">Code</th>
                      <th className="text-right px-2 py-1 font-medium text-gray-500">RPS</th>
                      <th className="text-right px-2 py-1 font-medium text-gray-500">Slope</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rps.data.map((item: Record<string, unknown>, i: number) => (
                      <tr
                        key={i}
                        className="border-b last:border-0 hover:bg-gray-50 cursor-pointer"
                        onClick={() => {
                          setActiveCode(String(item.stock_code).split('.')[0]);
                          setSearchCode(String(item.stock_code).split('.')[0]);
                        }}
                      >
                        <td className="px-2 py-1 text-gray-400">{i + 1}</td>
                        <td className="px-2 py-1 font-mono">{String(item.stock_code)}</td>
                        <td className="text-right px-2 py-1">{Number(item.rps).toFixed(1)}</td>
                        <td className="text-right px-2 py-1 text-gray-500">
                          {item.rps_slope ? Number(item.rps_slope).toFixed(2) : '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="py-8 text-center text-gray-400">No RPS data</div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
