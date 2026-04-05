'use client';

import { useState, useEffect } from 'react';
import Navbar from '@/components/layout/Navbar';
import apiClient from '@/lib/api-client';
import { useAuthStore } from '@/lib/store';
import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';

export default function AnalysisPage() {
  const router = useRouter();
  const { user } = useAuthStore();
  const [code, setCode] = useState('');
  const [activeCode, setActiveCode] = useState('');

  useEffect(() => {
    if (!user) router.push('/login');
  }, [user, router]);

  const { data: tech, isLoading: techLoading } = useQuery({
    queryKey: ['technical', activeCode],
    queryFn: () =>
      apiClient.get('/api/analysis/technical', { params: { code: activeCode } }).then((r) => r.data),
    enabled: !!activeCode,
  });

  const { data: fundamental } = useQuery({
    queryKey: ['fundamental', activeCode],
    queryFn: () =>
      apiClient.get('/api/analysis/fundamental', { params: { code: activeCode } }).then((r) => r.data),
    enabled: !!activeCode,
  });

  const handleAnalyze = (e: React.FormEvent) => {
    e.preventDefault();
    if (code.trim()) setActiveCode(code.trim());
  };

  const scoreColor = (s: number) => {
    if (s > 20) return 'text-green-600';
    if (s < -20) return 'text-red-600';
    return 'text-yellow-600';
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">Analysis</h1>

        <form onSubmit={handleAnalyze} className="flex gap-2 mb-6">
          <input
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value)}
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

        {activeCode && (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Technical Analysis */}
            <div className="bg-white rounded-lg border p-4">
              <h2 className="text-lg font-medium mb-4">Technical Analysis</h2>
              {techLoading ? (
                <div className="py-8 text-center text-gray-400">Loading...</div>
              ) : (
                <>
                  <div className="flex items-center gap-4 mb-4">
                    <span className="text-sm text-gray-500">Score:</span>
                    <span className={`text-2xl font-bold ${scoreColor(tech?.score || 0)}`}>
                      {tech?.score || 0}
                    </span>
                  </div>
                  <p className="text-sm text-gray-600 mb-4">{tech?.summary}</p>
                  {tech?.signals?.length > 0 ? (
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
                    <p className="text-sm text-gray-400">No technical indicator data available for this stock.</p>
                  )}
                </>
              )}
            </div>

            {/* Fundamental Analysis */}
            <div className="bg-white rounded-lg border p-4">
              <h2 className="text-lg font-medium mb-4">Fundamental Analysis</h2>
              {fundamental ? (
                <>
                  <div className="flex items-center gap-4 mb-4">
                    <span className="text-sm text-gray-500">Score:</span>
                    <span className={`text-2xl font-bold ${scoreColor(fundamental.score || 0)}`}>
                      {fundamental.score}
                    </span>
                  </div>
                  <p className="text-sm text-gray-600 mb-4">{fundamental.summary}</p>

                  {fundamental.valuation.length > 0 && (
                    <div className="mb-4">
                      <h3 className="text-sm font-medium text-gray-700 mb-2">Valuation</h3>
                      <div className="space-y-1">
                        {fundamental.valuation.map((v: Record<string, unknown>, i: number) => (
                          <div key={i} className="flex justify-between text-sm px-2 py-1 bg-gray-50 rounded">
                            <span className="text-gray-600">{String(v.metric)}</span>
                            <span className="font-medium">{Number(v.value).toFixed(2)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {fundamental.growth.length > 0 && (
                    <div>
                      <h3 className="text-sm font-medium text-gray-700 mb-2">Growth</h3>
                      <div className="space-y-1">
                        {fundamental.growth.map((g: Record<string, unknown>, i: number) => (
                          <div key={i} className="flex justify-between text-sm px-2 py-1 bg-gray-50 rounded">
                            <span className="text-gray-600">{String(g.metric)}</span>
                            <span className="font-medium">{(Number(g.value) * 100).toFixed(1)}%</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="py-8 text-center text-gray-400">No fundamental data</div>
              )}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
