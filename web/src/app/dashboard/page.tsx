'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '@/lib/store';
import Navbar from '@/components/layout/Navbar';
import {
  watchlistApi,
  scanResultsApi,
  marketApi,
  WatchlistItem,
  ScanResult,
  StockSearchResult,
} from '@/lib/api-client';

// --- Score badge color helper ---
function scoreBadgeClass(score: number | null): string {
  if (score === null) return 'bg-gray-100 text-gray-500';
  if (score >= 7) return 'bg-green-100 text-green-700 font-semibold';
  if (score >= 5) return 'bg-blue-100 text-blue-700 font-semibold';
  if (score >= 3) return 'bg-amber-100 text-amber-700 font-semibold';
  return 'bg-red-100 text-red-700 font-semibold';
}

// --- Severity border color ---
function severityBorderClass(severity: string): string {
  switch (severity) {
    case 'RED': return 'border-l-4 border-l-red-500';
    case 'YELLOW': return 'border-l-4 border-l-amber-400';
    case 'GREEN': return 'border-l-4 border-l-green-500';
    default: return 'border-l-4 border-l-gray-200';
  }
}

// --- Severity label text ---
function severityLabel(severity: string): { text: string; cls: string } {
  switch (severity) {
    case 'RED': return { text: 'Alert', cls: 'text-red-600 bg-red-50 border border-red-200' };
    case 'YELLOW': return { text: 'Watch', cls: 'text-amber-600 bg-amber-50 border border-amber-200' };
    case 'GREEN': return { text: 'Signal', cls: 'text-green-600 bg-green-50 border border-green-200' };
    default: return { text: 'Normal', cls: 'text-gray-500 bg-gray-50 border border-gray-200' };
  }
}

// --- Stock Card Component ---
function StockCard({
  item,
  scan,
  onRemove,
}: {
  item: WatchlistItem;
  scan?: ScanResult;
  onRemove: (code: string) => void;
}) {
  const sev = scan?.max_severity || 'NONE';
  const sevInfo = severityLabel(sev);
  const topSignals = scan?.signals?.slice(0, 2) || [];

  return (
    <div className={`bg-white rounded-lg shadow-sm border hover:shadow-md transition-shadow ${severityBorderClass(sev)}`}>
      <div className="p-4">
        {/* Header */}
        <div className="flex items-start justify-between mb-3">
          <div>
            <h3 className="font-semibold text-gray-900 text-sm leading-tight">{item.stock_name}</h3>
            <span className="text-xs text-gray-400 font-mono mt-0.5 block">{item.stock_code}</span>
          </div>
          <button
            onClick={() => onRemove(item.stock_code)}
            className="text-gray-300 hover:text-red-400 transition-colors text-xs ml-2 mt-0.5"
            title="Remove from watchlist"
          >
            x
          </button>
        </div>

        {/* Score */}
        {scan ? (
          <>
            <div className="flex items-center gap-2 mb-2">
              <span className={`text-sm px-2 py-0.5 rounded ${scoreBadgeClass(scan.score)}`}>
                {scan.score?.toFixed(1) ?? '--'} / 10
              </span>
              <span className={`text-xs px-1.5 py-0.5 rounded ${sevInfo.cls}`}>
                {sevInfo.text}
              </span>
            </div>
            <p className="text-xs text-gray-500 mb-2">{scan.score_label || 'Neutral'}</p>
            {/* Top signals */}
            {topSignals.length > 0 && (
              <ul className="space-y-0.5">
                {topSignals.map((s, i) => (
                  <li key={i} className="text-xs text-gray-500 truncate">
                    {s.type}
                  </li>
                ))}
              </ul>
            )}
            <p className="text-xs text-gray-300 mt-2">{scan.scan_date}</p>
          </>
        ) : (
          <p className="text-xs text-gray-400 mt-2">No scan data yet</p>
        )}
      </div>
    </div>
  );
}

// --- Search Dropdown ---
function SearchBar({ onAdd }: { onAdd: (code: string, name: string) => Promise<void> }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<StockSearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [searching, setSearching] = useState(false);
  const [adding, setAdding] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setQuery(val);
    if (timerRef.current) clearTimeout(timerRef.current);
    if (!val.trim()) {
      setResults([]);
      setOpen(false);
      return;
    }
    timerRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const res = await marketApi.search(val.trim());
        setResults(res.data.slice(0, 8));
        setOpen(true);
      } catch {
        setResults([]);
      } finally {
        setSearching(false);
      }
    }, 300);
  };

  const handleAdd = async (stock: StockSearchResult) => {
    setAdding(stock.stock_code);
    try {
      await onAdd(stock.stock_code, stock.stock_name);
      setQuery('');
      setResults([]);
      setOpen(false);
    } finally {
      setAdding(null);
    }
  };

  return (
    <div ref={containerRef} className="relative w-full max-w-xl">
      <div className="relative">
        <input
          type="text"
          value={query}
          onChange={handleChange}
          onFocus={() => results.length > 0 && setOpen(true)}
          placeholder="Search stocks, ETFs..."
          className="w-full px-4 py-2.5 pr-10 border border-gray-200 rounded-full text-sm bg-white shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
        />
        {searching ? (
          <div className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
        ) : (
          <svg className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        )}
      </div>

      {open && results.length > 0 && (
        <div className="absolute top-full mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg z-50 overflow-hidden">
          {results.map((stock) => (
            <div
              key={stock.stock_code}
              className="flex items-center justify-between px-4 py-2.5 hover:bg-gray-50 cursor-pointer"
            >
              <div>
                <span className="text-sm font-medium text-gray-900">{stock.stock_name}</span>
                <span className="text-xs text-gray-400 font-mono ml-2">{stock.stock_code}</span>
                {stock.industry && <span className="text-xs text-gray-400 ml-2">{stock.industry}</span>}
              </div>
              <button
                onClick={() => handleAdd(stock)}
                disabled={adding === stock.stock_code}
                className="text-xs bg-blue-600 text-white px-3 py-1 rounded-full hover:bg-blue-700 disabled:bg-blue-300 ml-4 flex-shrink-0"
              >
                {adding === stock.stock_code ? '...' : '+ Add'}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// --- Main Page ---
export default function DashboardPage() {
  const router = useRouter();
  const { user, fetchUser } = useAuthStore();
  const queryClient = useQueryClient();

  // Auth guard
  useEffect(() => {
    if (!user) {
      fetchUser().catch(() => router.push('/login'));
    }
  }, [user, fetchUser, router]);

  // Data fetching
  const { data: watchlistData, isLoading: wLoading } = useQuery({
    queryKey: ['watchlist'],
    queryFn: () => watchlistApi.list().then((r) => r.data),
    enabled: !!user,
  });

  const { data: scanResults } = useQuery({
    queryKey: ['scan-results'],
    queryFn: () => scanResultsApi.list().then((r) => r.data),
    enabled: !!user,
  });

  // Build scan result map keyed by stock_code
  const scanMap: Record<string, ScanResult> = {};
  if (scanResults) {
    for (const r of scanResults) {
      scanMap[r.stock_code] = r;
    }
  }

  // Latest scan date
  const latestScanDate = scanResults?.[0]?.scan_date;

  // Add to watchlist mutation
  const addMutation = useMutation({
    mutationFn: ({ code, name }: { code: string; name: string }) =>
      watchlistApi.add(code, name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['watchlist'] }),
  });

  // Remove from watchlist mutation
  const removeMutation = useMutation({
    mutationFn: (code: string) => watchlistApi.remove(code),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['watchlist'] });
      queryClient.invalidateQueries({ queryKey: ['scan-results'] });
    },
  });

  const handleAdd = useCallback(async (code: string, name: string) => {
    try {
      await addMutation.mutateAsync({ code, name });
    } catch (err: unknown) {
      const e = err as { response?: { status?: number } };
      if (e?.response?.status === 409) {
        // Already in watchlist - silently ignore
      }
    }
  }, [addMutation]);

  const handleRemove = useCallback((code: string) => {
    removeMutation.mutate(code);
  }, [removeMutation]);

  const watchlistItems = watchlistData?.items || [];

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar searchBar={<SearchBar onAdd={handleAdd} />} />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Watchlist Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-semibold text-gray-900">Watchlist</h2>
            <span className="text-sm text-gray-400 bg-gray-100 px-2 py-0.5 rounded-full">
              {watchlistItems.length}
            </span>
          </div>
          {latestScanDate && (
            <span className="text-xs text-gray-400">Last scan: {latestScanDate}</span>
          )}
        </div>

        {/* Stock Grid */}
        {wLoading ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="bg-white rounded-lg border h-36 animate-pulse" />
            ))}
          </div>
        ) : watchlistItems.length === 0 ? (
          <div className="bg-white rounded-lg border p-12 text-center">
            <svg className="w-10 h-10 text-gray-300 mx-auto mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <p className="text-gray-500 text-sm">Search stocks above to build your watchlist</p>
            <p className="text-gray-400 text-xs mt-1">Daily 5-dimension scan results will appear here</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
            {watchlistItems.map((item) => (
              <StockCard
                key={item.id}
                item={item}
                scan={scanMap[item.stock_code]}
                onRemove={handleRemove}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
