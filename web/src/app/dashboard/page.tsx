'use client';

import { useEffect } from 'react';
import { useAuthStore } from '@/lib/store';
import { useRouter } from 'next/navigation';
import Navbar from '@/components/layout/Navbar';
import apiClient from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';

interface PortfolioSummary {
  total_market_value: number;
  total_cost: number;
  total_pnl: number;
  total_pnl_pct: number;
  holdings_count: number;
  holdings: Array<{
    stock_code: string;
    stock_name: string;
    shares: number;
    cost_price: number;
    current_price: number;
    market_value: number;
    pnl: number;
    pnl_pct: number;
  }>;
}

export default function DashboardPage() {
  const router = useRouter();
  const { user, fetchUser } = useAuthStore();

  useEffect(() => {
    if (!user) {
      fetchUser().catch(() => router.push('/login'));
    }
  }, [user, fetchUser, router]);

  const { data: portfolio, isLoading: portfolioLoading } = useQuery<PortfolioSummary>({
    queryKey: ['portfolio'],
    queryFn: () => apiClient.get('/api/portfolio/summary').then((r) => r.data),
    refetchInterval: 30000,
    enabled: !!user,
  });

  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: () => apiClient.get('/health').then((r) => r.data),
  });

  const pnlColor = portfolio?.total_pnl_pct
    ? portfolio.total_pnl_pct >= 0
      ? 'text-green-600'
      : 'text-red-600'
    : 'text-gray-500';

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">Dashboard</h1>

        {/* Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
          <div className="bg-white rounded-lg border p-4">
            <p className="text-sm text-gray-500">Total Value</p>
            <p className="text-xl font-bold text-gray-900">
              {portfolio ? `${(portfolio.total_market_value / 10000).toFixed(2)}W` : '--'}
            </p>
          </div>
          <div className="bg-white rounded-lg border p-4">
            <p className="text-sm text-gray-500">Total PnL</p>
            <p className={`text-xl font-bold ${pnlColor}`}>
              {portfolio ? `${(portfolio.total_pnl / 10000).toFixed(2)}W` : '--'}
            </p>
          </div>
          <div className="bg-white rounded-lg border p-4">
            <p className="text-sm text-gray-500">PnL %</p>
            <p className={`text-xl font-bold ${pnlColor}`}>
              {portfolio ? `${portfolio.total_pnl_pct.toFixed(2)}%` : '--'}
            </p>
          </div>
          <div className="bg-white rounded-lg border p-4">
            <p className="text-sm text-gray-500">Holdings</p>
            <p className="text-xl font-bold text-gray-900">
              {portfolio ? portfolio.holdings_count : '--'}
            </p>
          </div>
        </div>

        {/* Holdings Table */}
        <div className="bg-white rounded-lg border">
          <div className="px-4 py-3 border-b">
            <h2 className="text-lg font-medium text-gray-900">Holdings</h2>
          </div>
          {portfolioLoading ? (
            <div className="p-8 text-center text-gray-400">Loading...</div>
          ) : portfolio && portfolio.holdings.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-gray-50">
                    <th className="text-left px-4 py-2 font-medium text-gray-500">Code</th>
                    <th className="text-left px-4 py-2 font-medium text-gray-500">Name</th>
                    <th className="text-right px-4 py-2 font-medium text-gray-500">Shares</th>
                    <th className="text-right px-4 py-2 font-medium text-gray-500">Cost</th>
                    <th className="text-right px-4 py-2 font-medium text-gray-500">Current</th>
                    <th className="text-right px-4 py-2 font-medium text-gray-500">Value</th>
                    <th className="text-right px-4 py-2 font-medium text-gray-500">PnL</th>
                    <th className="text-right px-4 py-2 font-medium text-gray-500">PnL%</th>
                  </tr>
                </thead>
                <tbody>
                  {portfolio.holdings.map((h) => (
                    <tr key={h.stock_code} className="border-b last:border-0 hover:bg-gray-50">
                      <td className="px-4 py-2 font-mono">{h.stock_code}</td>
                      <td className="px-4 py-2">{h.stock_name || '-'}</td>
                      <td className="px-4 py-2 text-right">{h.shares}</td>
                      <td className="px-4 py-2 text-right">{h.cost_price.toFixed(2)}</td>
                      <td className="px-4 py-2 text-right">{h.current_price?.toFixed(2) || '-'}</td>
                      <td className="px-4 py-2 text-right">{h.market_value?.toFixed(0) || '-'}</td>
                      <td className={`px-4 py-2 text-right ${(h.pnl || 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {h.pnl?.toFixed(2) || '-'}
                      </td>
                      <td className={`px-4 py-2 text-right ${(h.pnl_pct || 0) >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {h.pnl_pct?.toFixed(2) || '-'}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="p-8 text-center text-gray-400">
              No holdings found. Add positions to see your portfolio here.
            </div>
          )}
        </div>

        {/* System Status */}
        <div className="mt-8 text-xs text-gray-400">
          API Status: {health?.status || 'checking...'} |
          DB: {health?.db || '--'} | Redis: {health?.redis || '--'}
        </div>
      </main>
    </div>
  );
}
