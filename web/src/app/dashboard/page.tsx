'use client';

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
// [AUTH-DISABLED] import { useRouter } from 'next/navigation';
import axios from 'axios';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
// [AUTH-DISABLED] import { useAuthStore } from '@/lib/store';
import AppShell from '@/components/layout/AppShell';
import {
  watchlistApi,
  scanResultsApi,
  marketApi,
  WatchlistItem,
  ScanResult,
  StockSearchResult,
} from '@/lib/api-client';

function scoreBadgeStyle(score: number | null): React.CSSProperties {
  if (score === null) return { background: 'var(--bg-tag)', color: 'var(--text-muted)' };
  if (score >= 7) return { background: 'rgba(26,158,65,0.12)', color: 'var(--green)' };
  if (score >= 5) return { background: 'rgba(94,106,210,0.12)', color: 'var(--accent)' };
  if (score >= 3) return { background: 'rgba(176,125,16,0.12)', color: 'var(--amber)' };
  return { background: 'rgba(214,59,52,0.12)', color: 'var(--red)' };
}

function severityBorderColor(severity: string): string {
  switch (severity) {
    case 'RED':    return 'var(--red)';
    case 'YELLOW': return 'var(--amber)';
    case 'GREEN':  return 'var(--green)';
    default:       return 'var(--border-solid)';
  }
}

function severityLabel(severity: string): { text: string; color: string } {
  switch (severity) {
    case 'RED':    return { text: 'Alert',  color: 'var(--red)' };
    case 'YELLOW': return { text: 'Watch',  color: 'var(--amber)' };
    case 'GREEN':  return { text: 'Signal', color: 'var(--green)' };
    default:       return { text: 'Normal', color: 'var(--text-muted)' };
  }
}

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
    <div
      style={{
        background: 'var(--bg-panel)',
        border: '1px solid var(--border-subtle)',
        borderLeft: `3px solid ${severityBorderColor(sev)}`,
        borderRadius: '8px',
        padding: '14px',
        transition: 'background 0.12s',
      }}
      onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-card-hover)'; }}
      onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-panel)'; }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '10px' }}>
        <div>
          <div style={{ fontSize: '13px', fontWeight: 510, color: 'var(--text-primary)' }}>{item.stock_name}</div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'var(--font-geist-mono)', marginTop: '2px' }}>{item.stock_code}</div>
        </div>
        <button
          onClick={() => onRemove(item.stock_code)}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', fontSize: '14px', padding: '0 2px', lineHeight: 1 }}
          title="Remove"
        >
          x
        </button>
      </div>

      {scan ? (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '6px' }}>
            <span style={{ fontSize: '12px', padding: '2px 8px', borderRadius: '4px', fontWeight: 510, ...scoreBadgeStyle(scan.score) }}>
              {scan.score?.toFixed(1) ?? '--'} / 10
            </span>
            <span style={{ fontSize: '11px', color: sevInfo.color }}>{sevInfo.text}</span>
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginBottom: '6px' }}>{scan.score_label || 'Neutral'}</div>
          {topSignals.length > 0 && (
            <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
              {topSignals.map((s, i) => (
                <li key={i} style={{ fontSize: '11px', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {s.type}
                </li>
              ))}
            </ul>
          )}
          <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '8px' }}>{scan.scan_date}</div>
        </>
      ) : (
        <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>No scan data yet</div>
      )}
    </div>
  );
}

function SearchBar({ onAdd }: { onAdd: (code: string, name: string) => Promise<void> }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<StockSearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [searching, setSearching] = useState(false);
  const [adding, setAdding] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setQuery(val);
    if (timerRef.current) clearTimeout(timerRef.current);
    if (!val.trim()) { setResults([]); setOpen(false); return; }
    timerRef.current = setTimeout(async () => {
      setSearching(true);
      try {
        const res = await marketApi.search(val.trim());
        // API 返回 { count, data: [] } 结构
        const results = Array.isArray(res.data) ? res.data : [];
        setResults(results.slice(0, 8));
        setOpen(true);
      } catch { setResults([]); }
      finally { setSearching(false); }
    }, 300);
  }, []);

  const handleAdd = useCallback(async (stock: StockSearchResult) => {
    setAdding(stock.stock_code);
    try {
      await onAdd(stock.stock_code, stock.stock_name);
      setQuery(''); setResults([]); setOpen(false);
    } finally { setAdding(null); }
  }, [onAdd]);

  return (
    <div ref={containerRef} className="search-bar-container" style={{ position: 'relative', width: '320px' }}>
      <div style={{ position: 'relative' }}>
        <input
          type="text"
          value={query}
          onChange={handleChange}
          onFocus={() => results.length > 0 && setOpen(true)}
          placeholder="搜索股票、ETF..."
          style={{
            width: '100%',
            padding: '6px 32px 6px 12px',
            background: 'var(--bg-input)',
            border: '1px solid var(--border-subtle)',
            borderRadius: '6px',
            fontSize: '13px',
            color: 'var(--text-primary)',
            outline: 'none',
            boxSizing: 'border-box',
          }}
          onFocusCapture={(e) => { (e.target as HTMLInputElement).style.borderColor = 'var(--border-std)'; }}
          onBlurCapture={(e) => { (e.target as HTMLInputElement).style.borderColor = 'var(--border-subtle)'; }}
        />
        <span style={{ position: 'absolute', right: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)', fontSize: '12px' }}>
          {searching ? '...' : 'S'}
        </span>
      </div>

      {open && results.length > 0 && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 4px)', left: 0, right: 0,
          background: 'var(--bg-panel)', border: '1px solid var(--border-std)',
          borderRadius: '8px', overflow: 'hidden', zIndex: 50,
          boxShadow: '0 8px 24px rgba(0,0,0,0.10)',
        }}>
          {results.map((stock) => (
            <div
              key={stock.stock_code}
              style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', borderBottom: '1px solid var(--border-subtle)', cursor: 'pointer' }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-card-hover)'; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'transparent'; }}
            >
              <div>
                <span style={{ fontSize: '13px', fontWeight: 510, color: 'var(--text-primary)' }}>{stock.stock_name}</span>
                <span style={{ fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'var(--font-geist-mono)', marginLeft: '8px' }}>{stock.stock_code}</span>
              </div>
              <button
                onClick={() => handleAdd(stock)}
                disabled={adding === stock.stock_code}
                style={{
                  fontSize: '11px', background: 'var(--accent-bg)', color: '#fff',
                  border: 'none', borderRadius: '4px', padding: '3px 10px', cursor: 'pointer',
                  opacity: adding === stock.stock_code ? 0.5 : 1,
                }}
              >
                {adding === stock.stock_code ? '...' : '+ 添加'}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function DashboardPage() {
  // [AUTH-DISABLED] const router = useRouter();
  // [AUTH-DISABLED] const { user, fetchUser } = useAuthStore();
  const queryClient = useQueryClient();

  // [AUTH-DISABLED] useEffect(() => { if (!user) { fetchUser().catch(() => router.push('/login')); } }, [user, fetchUser, router]);

  const { data: watchlistData, isLoading: wLoading } = useQuery({
    queryKey: ['watchlist'],
    queryFn: () => watchlistApi.list().then((r) => r.data),
    enabled: true,
  });

  const { data: scanResults } = useQuery({
    queryKey: ['scan-results'],
    queryFn: () => scanResultsApi.list().then((r) => r.data),
    enabled: true,
  });

  const scanMap = useMemo<Record<string, ScanResult>>(() => {
    if (!scanResults) return {};
    return Object.fromEntries(scanResults.map((r) => [r.stock_code, r]));
  }, [scanResults]);

  const latestScanDate = scanResults && scanResults.length > 0
    ? scanResults.reduce((max, r) => r.scan_date > max ? r.scan_date : max, scanResults[0].scan_date)
    : undefined;

  const addMutation = useMutation({
    mutationFn: ({ code, name }: { code: string; name: string }) => watchlistApi.add(code, name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['watchlist'] }),
  });

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
      if (axios.isAxiosError(err) && err.response?.status === 409) return;
      throw err;
    }
  }, [addMutation]);

  const handleRemove = useCallback((code: string) => { removeMutation.mutate(code); }, [removeMutation]);

  const watchlistItems = watchlistData?.items || [];

  const topBar = <SearchBar onAdd={handleAdd} />;

  return (
    <AppShell topBar={topBar}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <h2 style={{ fontSize: '16px', fontWeight: 510, color: 'var(--text-primary)', margin: 0 }}>自选股</h2>
          <span style={{ fontSize: '12px', color: 'var(--text-muted)', background: 'var(--bg-tag)', padding: '2px 8px', borderRadius: '10px' }}>
            {watchlistItems.length}
          </span>
        </div>
        {latestScanDate && (
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>最近扫描: {latestScanDate}</span>
        )}
      </div>

      {wLoading ? (
        <div className="grid-responsive-5" style={{ gap: '12px' }}>
          {[...Array(5)].map((_, i) => (
            <div key={i} style={{ background: 'var(--bg-card)', borderRadius: '8px', height: '140px', opacity: 0.4 }} />
          ))}
        </div>
      ) : watchlistItems.length === 0 ? (
        <div style={{
          background: 'var(--bg-card)', border: '1px solid var(--border-subtle)',
          borderRadius: '12px', padding: '64px 24px', textAlign: 'center',
        }}>
          <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '6px' }}>
            在顶部搜索栏添加股票
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', opacity: 0.6 }}>每日5维度扫描结果将在此显示</div>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '12px' }}>
          {watchlistItems.map((item) => (
            <StockCard key={item.id} item={item} scan={scanMap[item.stock_code]} onRemove={handleRemove} />
          ))}
        </div>
      )}
    </AppShell>
  );
}
