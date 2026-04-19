'use client';

import React, { useState } from 'react';
import QuickAddMenu from '@/components/stock/QuickAddMenu';
import { candidatePoolApi } from '@/lib/candidate-pool-api';

interface IndustryStock {
  stock_code: string;
  stock_name: string;
  close: number | null;
  rps_250: number | null;
  rps_120: number | null;
  rps_20: number | null;
  rps_slope: number | null;
  in_pool: boolean;
  trade_date: string;
}

function rpsColor(v: number | null): string {
  if (v == null) return 'var(--text-muted)';
  if (v >= 90) return '#27a644';
  if (v >= 70) return '#5e6ad2';
  if (v < 40)  return '#e5534b';
  return 'var(--text-secondary)';
}

export default function IndustryStockScreener() {
  const [industries, setIndustries] = useState<string[]>([]);
  const [selectedIndustry, setSelectedIndustry] = useState('');
  const [minRps, setMinRps] = useState('60');
  const [sortBy, setSortBy] = useState('rps_250');
  const [stocks, setStocks] = useState<IndustryStock[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingIndustries, setLoadingIndustries] = useState(false);
  const [expanded, setExpanded] = useState(true);
  const [msg, setMsg] = useState<string | null>(null);

  async function loadIndustries() {
    if (industries.length > 0) return;
    setLoadingIndustries(true);
    try {
      const res = await candidatePoolApi.industries();
      setIndustries((res.data as { data?: string[] }).data || []);
    } catch {
      // ignore
    } finally {
      setLoadingIndustries(false);
    }
  }

  async function search() {
    if (!selectedIndustry) return;
    setLoading(true);
    setMsg(null);
    try {
      const params: { industry_name: string; sort_by?: string; min_rps?: string } = {
        industry_name: selectedIndustry,
        sort_by: sortBy,
      };
      if (minRps) params.min_rps = minRps;
      const res = await candidatePoolApi.industryStocks(params);
      setStocks((res.data as { data?: IndustryStock[] }).data || []);
    } catch {
      setMsg('查询失败');
    } finally {
      setLoading(false);
    }
  }

  // Load industries on mount
  React.useEffect(() => { loadIndustries(); }, []);

  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border-subtle)',
      borderRadius: '10px',
      overflow: 'hidden',
    }}>
      {/* Header */}
      <div
        onClick={() => setExpanded(e => !e)}
        style={{
          padding: '16px 20px', cursor: 'pointer', userSelect: 'none',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px',
        }}
      >
        <div>
          <div style={{ fontSize: '15px', fontWeight: 590, color: 'var(--text-primary)', marginBottom: '3px' }}>
            行业选股
          </div>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            选择行业，按 RPS 筛选个股，一键加入候选池
          </div>
        </div>
        <span style={{ fontSize: '16px', color: 'var(--text-muted)' }}>{expanded ? '▲' : '▼'}</span>
      </div>

      {expanded && (
        <>
          {/* Filters */}
          <div style={{
            padding: '12px 20px', borderTop: '1px solid var(--border-subtle)',
            display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'flex-end',
          }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>行业</label>
              <select
                value={selectedIndustry}
                onChange={e => setSelectedIndustry(e.target.value)}
                style={{
                  fontSize: '12px', padding: '6px 10px', borderRadius: '6px',
                  border: '1px solid var(--border-std)', background: 'var(--bg-input)',
                  color: 'var(--text-primary)', minWidth: '120px',
                }}
              >
                <option value=''>选择行业...</option>
                {loadingIndustries && <option disabled>加载中...</option>}
                {industries.map(ind => (
                  <option key={ind} value={ind}>{ind}</option>
                ))}
              </select>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>RPS250 最低</label>
              <input
                type='number'
                value={minRps}
                onChange={e => setMinRps(e.target.value)}
                min={0} max={100} step={5}
                style={{
                  fontSize: '12px', padding: '6px 10px', borderRadius: '6px', width: '80px',
                  border: '1px solid var(--border-std)', background: 'var(--bg-input)',
                  color: 'var(--text-primary)',
                }}
              />
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
              <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>排序</label>
              <select
                value={sortBy}
                onChange={e => setSortBy(e.target.value)}
                style={{
                  fontSize: '12px', padding: '6px 10px', borderRadius: '6px',
                  border: '1px solid var(--border-std)', background: 'var(--bg-input)',
                  color: 'var(--text-primary)',
                }}
              >
                <option value='rps_250'>RPS250</option>
                <option value='rps_120'>RPS120</option>
                <option value='rps_20'>RPS20</option>
                <option value='rps_slope'>RPS斜率</option>
              </select>
            </div>
            <button
              onClick={search}
              disabled={!selectedIndustry || loading}
              style={{
                fontSize: '12px', padding: '7px 18px', borderRadius: '6px', fontWeight: 510,
                background: !selectedIndustry || loading ? 'transparent' : 'var(--accent)',
                border: `1px solid ${!selectedIndustry || loading ? 'var(--border-subtle)' : 'var(--accent)'}`,
                color: !selectedIndustry || loading ? 'var(--text-muted)' : '#fff',
                cursor: !selectedIndustry || loading ? 'default' : 'pointer',
              }}
            >
              {loading ? '查询中...' : '查询'}
            </button>
          </div>

          {msg && (
            <div style={{ padding: '6px 20px', fontSize: '12px', color: 'var(--accent)' }}>{msg}</div>
          )}

          {/* Results */}
          {stocks.length > 0 && (
            <div className="table-scroll" style={{ borderTop: '1px solid var(--border-subtle)' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', minWidth: '520px' }}>
                <thead>
                  <tr style={{ background: 'var(--bg-panel)' }}>
                    {['代码', '名称', '收盘', 'RPS250', 'RPS120', 'RPS20', 'RPS斜率', '操作'].map(h => (
                      <th key={h} style={{
                        padding: '8px 12px', textAlign: 'left', fontWeight: 510,
                        color: 'var(--text-muted)', fontSize: '11px',
                        borderBottom: '1px solid var(--border-subtle)', whiteSpace: 'nowrap',
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {stocks.map((stock, i) => (
                      <tr
                        key={stock.stock_code}
                        style={{ background: i % 2 === 0 ? 'transparent' : 'var(--bg-card)', borderBottom: '1px solid var(--border-subtle)' }}
                        onMouseEnter={e => { (e.currentTarget as HTMLTableRowElement).style.background = 'var(--bg-card-hover)'; }}
                        onMouseLeave={e => { (e.currentTarget as HTMLTableRowElement).style.background = i % 2 === 0 ? 'transparent' : 'var(--bg-card)'; }}
                      >
                        <td style={{ padding: '8px 12px', fontFamily: 'var(--font-geist-mono)', color: 'var(--text-muted)', fontSize: '11px' }}>{stock.stock_code}</td>
                        <td style={{ padding: '8px 12px', fontWeight: 510, color: 'var(--text-primary)' }}>{stock.stock_name}</td>
                        <td style={{ padding: '8px 12px', color: 'var(--text-secondary)' }}>
                          {stock.close != null ? stock.close.toFixed(2) : '--'}
                        </td>
                        <td style={{ padding: '8px 12px', fontWeight: 600, color: rpsColor(stock.rps_250) }}>
                          {stock.rps_250 != null ? stock.rps_250.toFixed(1) : '--'}
                        </td>
                        <td style={{ padding: '8px 12px', color: rpsColor(stock.rps_120) }}>
                          {stock.rps_120 != null ? stock.rps_120.toFixed(1) : '--'}
                        </td>
                        <td style={{ padding: '8px 12px', color: rpsColor(stock.rps_20) }}>
                          {stock.rps_20 != null ? stock.rps_20.toFixed(1) : '--'}
                        </td>
                        <td style={{ padding: '8px 12px', color: (stock.rps_slope ?? 0) > 0 ? '#27a644' : '#e5534b' }}>
                          {stock.rps_slope != null ? (stock.rps_slope > 0 ? '+' : '') + stock.rps_slope.toFixed(2) : '--'}
                        </td>
                        <td style={{ padding: '8px 12px' }}>
                          <QuickAddMenu
                            stockCode={stock.stock_code}
                            stockName={stock.stock_name}
                            sourceType="industry"
                            sourceDetail={selectedIndustry}
                            snapshot={{
                              rps_250: stock.rps_250,
                              rps_120: stock.rps_120,
                              close: stock.close,
                              industry_name: selectedIndustry,
                            }}
                          />
                        </td>
                      </tr>
                  ))}
                </tbody>
              </table>
              <div style={{ padding: '8px 12px', background: 'var(--bg-panel)', borderTop: '1px solid var(--border-subtle)', fontSize: '11px', color: 'var(--text-muted)' }}>
                {selectedIndustry} · 共 {stocks.length} 只  · {stocks[0]?.trade_date || ''}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
