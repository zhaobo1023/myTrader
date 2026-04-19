'use client';

import React, { useState, useRef, useEffect, useCallback } from 'react';
import { marketApi, StockSearchResult } from '@/lib/api-client';

interface StockSearchInputProps {
  onSelect: (stock: StockSearchResult) => void;
  placeholder?: string;
  width?: string | number;
}

export default function StockSearchInput({ onSelect, placeholder = '输入股票代码或名称', width = '240px' }: StockSearchInputProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<StockSearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const doSearch = useCallback(async (q: string) => {
    if (q.length < 2) { setResults([]); setOpen(false); return; }
    setLoading(true);
    try {
      const res = await marketApi.search(q);
      const list = (res.data?.data || []).slice(0, 8);
      setResults(list);
      setOpen(list.length > 0);
    } catch {
      setResults([]);
      setOpen(false);
    } finally {
      setLoading(false);
    }
  }, []);

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const v = e.target.value;
    setQuery(v);
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => doSearch(v), 300);
  }

  function handleSelect(stock: StockSearchResult) {
    onSelect(stock);
    setQuery('');
    setResults([]);
    setOpen(false);
  }

  // Cleanup debounce timer on unmount
  useEffect(() => {
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, []);

  // Close dropdown on outside click
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  return (
    <div ref={containerRef} style={{ position: 'relative', width }}>
      <input
        value={query}
        onChange={handleChange}
        onFocus={() => { if (results.length > 0) setOpen(true); }}
        placeholder={placeholder}
        style={{
          width: '100%', fontSize: '13px', padding: '7px 12px', borderRadius: '6px',
          border: '1px solid var(--border-std)', background: 'var(--bg-input)',
          color: 'var(--text-primary)', boxSizing: 'border-box',
        }}
      />
      {loading && (
        <span style={{ position: 'absolute', right: '10px', top: '50%', transform: 'translateY(-50%)', fontSize: '11px', color: 'var(--text-muted)' }}>
          ...
        </span>
      )}
      {open && results.length > 0 && (
        <div style={{
          position: 'absolute', top: '100%', left: 0, right: 0, marginTop: '4px',
          background: 'var(--bg-panel)', border: '1px solid var(--border-std)',
          borderRadius: '8px', boxShadow: '0 8px 24px rgba(0,0,0,0.15)',
          zIndex: 100, maxHeight: '320px', overflowY: 'auto',
        }}>
          {results.map((s) => (
            <div
              key={s.stock_code}
              onClick={() => handleSelect(s)}
              style={{
                padding: '8px 14px', cursor: 'pointer', display: 'flex',
                alignItems: 'center', gap: '10px', fontSize: '13px',
                borderBottom: '1px solid var(--border-subtle)',
              }}
              onMouseEnter={e => { (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-card-hover)'; }}
              onMouseLeave={e => { (e.currentTarget as HTMLDivElement).style.background = 'transparent'; }}
            >
              <span style={{ fontFamily: 'var(--font-geist-mono)', color: 'var(--text-muted)', fontSize: '12px', minWidth: '60px' }}>
                {s.stock_code}
              </span>
              <span style={{ color: 'var(--text-primary)', fontWeight: 510 }}>{s.stock_name}</span>
              {s.industry && (
                <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginLeft: 'auto' }}>{s.industry}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
