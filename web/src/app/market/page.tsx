'use client';

import { useState } from 'react';
import Navbar from '@/components/layout/Navbar';
import apiClient from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';

export default function MarketPage() {
  const [searchCode, setSearchCode] = useState('600519');
  const [activeCode, setActiveCode] = useState('600519');
  const [rpsWindow, setRpsWindow] = useState(250);

  // K-line data
  const { data: kline, isLoading: klineLoading } = useQuery({
    queryKey: ['kline', activeCode],
    queryFn: () =>
      apiClient
        .get('/api/market/kline', { params: { code: activeCode, limit: 120 } })
        .then((r) => r.data),
    enabled: !!activeCode,
  });

  // RPS ranking
  const { data: rps } = useQuery({
    queryKey: ['rps', rpsWindow],
    queryFn: () =>
      apiClient
        .get('/api/market/rps', { params: { window: rpsWindow, top_n: 20 } })
        .then((r) => r.data),
  });

  // Latest date
  const { data: latestDate } = useQuery({
    queryKey: ['latestDate'],
    queryFn: () => apiClient.get('/api/market/latest-date').then((r) => r.data),
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchCode.trim()) {
      setActiveCode(searchCode.trim());
    }
  };

  const latestClose = kline?.data?.[kline.data.length - 1]?.close;
  const prevClose = kline?.data?.[kline.data.length - 2]?.close;
  const priceChange = latestClose && prevClose ? latestClose - prevClose : 0;
  const priceChangePct = prevClose ? (priceChange / prevClose) * 100 : 0;

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">Market</h1>

        {/* Search Bar */}
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
            Search
          </button>
        </form>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* K-line Area (placeholder for Lightweight Charts) */}
          <div className="lg:col-span-2 bg-white rounded-lg border p-4">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-medium">{activeCode}</h2>
                <p className="text-sm text-gray-500">
                  Latest: {latestDate?.latest_date || '--'}
                </p>
              </div>
              {latestClose && (
                <div className="text-right">
                  <p className="text-xl font-bold">{latestClose.toFixed(2)}</p>
                  <p
                    className={`text-sm ${
                      priceChange >= 0 ? 'text-red-600' : 'text-green-600'
                    }`}
                  >
                    {priceChange >= 0 ? '+' : ''}
                    {priceChange.toFixed(2)} ({priceChangePct.toFixed(2)}%)
                  </p>
                </div>
              )}
            </div>

            {klineLoading ? (
              <div className="h-64 flex items-center justify-center text-gray-400">
                Loading...
              </div>
            ) : kline?.data && kline.data.length > 0 ? (
              <div className="h-64 overflow-y-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="border-b bg-gray-50">
                      <th className="text-left px-2 py-1">Date</th>
                      <th className="text-right px-2 py-1">Open</th>
                      <th className="text-right px-2 py-1">High</th>
                      <th className="text-right px-2 py-1">Low</th>
                      <th className="text-right px-2 py-1">Close</th>
                      <th className="text-right px-2 py-1">Volume</th>
                    </tr>
                  </thead>
                  <tbody>
                    {kline.data.map((d: Record<string, unknown>, i: number) => (
                      <tr key={i} className="border-b last:border-0">
                        <td className="px-2 py-0.5">{String(d.trade_date)}</td>
                        <td className="text-right px-2 py-0.5">{Number(d.open).toFixed(2)}</td>
                        <td className="text-right px-2 py-0.5">{Number(d.high).toFixed(2)}</td>
                        <td className="text-right px-2 py-0.5">{Number(d.low).toFixed(2)}</td>
                        <td className="text-right px-2 py-0.5 font-medium">{Number(d.close).toFixed(2)}</td>
                        <td className="text-right px-2 py-0.5 text-gray-500">{Number(d.volume).toLocaleString()}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="h-64 flex items-center justify-center text-gray-400">
                No data for this stock code
              </div>
            )}
          </div>

          {/* RPS Ranking */}
          <div className="bg-white rounded-lg border p-4">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-medium">RPS Top 20</h2>
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
              <div className="max-h-96 overflow-y-auto">
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
