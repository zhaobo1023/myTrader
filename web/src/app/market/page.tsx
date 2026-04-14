'use client';

import { useState } from 'react';
import AppShell from '@/components/layout/AppShell';
import SignalBadge from '@/components/market/SignalBadge';
import MiniSparkline from '@/components/market/MiniSparkline';
import apiClient, { marketOverviewApi, MarketOverviewSummary } from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';

interface StatCardProps {
  title: string;
  subtitle?: string;
  value?: string | null;
  signal?: string;
  description: string;
  children?: React.ReactNode;
  unavailable?: boolean;
}

function StatCard({ title, subtitle, value, signal, description, children, unavailable }: StatCardProps) {
  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1px solid var(--border-subtle)',
      borderRadius: '8px',
      padding: '14px 16px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
        <div>
          <p style={{ fontSize: '13px', fontWeight: 510, color: 'var(--text-secondary)', margin: 0 }}>{title}</p>
          {subtitle && <p style={{ fontSize: '11px', color: 'var(--text-muted)', margin: '2px 0 0' }}>{subtitle}</p>}
        </div>
        {signal && !unavailable && <SignalBadge signal={signal} />}
      </div>
      {unavailable ? (
        <p style={{ fontSize: '12px', color: 'var(--text-muted)', fontStyle: 'italic' }}>暂无数据 (需先运行 fetch_all_indicators)</p>
      ) : (
        <>
          {value && <p style={{ fontSize: '22px', fontWeight: 590, color: 'var(--text-primary)', margin: '4px 0 0', letterSpacing: '-0.3px' }}>{value}</p>}
          {children}
          <p style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '8px', lineHeight: 1.5 }}>{description}</p>
        </>
      )}
    </div>
  );
}

function SectionHeader({ title }: { title: string }) {
  return (
    <h2 style={{ fontSize: '11px', fontWeight: 510, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.8px', margin: '24px 0 10px' }}>{title}</h2>
  );
}

function OverviewTab({ data }: { data: MarketOverviewSummary }) {
  const mp = data.macro_pulse;
  const mt = data.market_turnover;
  const sbs = data.stock_bond_spread;
  const anchor = data.anchor_5y;
  const scale = data.scale_rotation;
  const style = data.style_rotation;
  const div = data.dividend;
  const efr = data.equity_fund_rolling;

  const fmt = (v: number | null | undefined, decimals = 2) =>
    v !== null && v !== undefined ? v.toFixed(decimals) : '--';

  return (
    <div>
      <SectionHeader title="Macro Pulse" />
      <div className="grid-responsive-5">
        <StatCard title="QVIX" subtitle="A股恐慌指数" value={mp?.qvix?.value != null ? mp.qvix.value.toFixed(2) : undefined} signal={mp?.qvix?.signal} unavailable={!mp?.qvix?.value} description="市场恐慌指标。>25恐慌, >35极度恐慌。" />
        <StatCard title="北向资金" subtitle="5日累计(亿)" value={mp?.north_flow?.sum_5d != null ? `${mp.north_flow.sum_5d > 0 ? '+' : ''}${fmt(mp.north_flow.sum_5d)}` : undefined} signal={mp?.north_flow?.signal} unavailable={!mp?.north_flow} description="外资通过沪深港通5日净流入。" />
        <StatCard title="M2同比" subtitle="广义货币供应" value={mp?.m2_yoy?.value != null ? `${fmt(mp.m2_yoy.value)}%` : undefined} unavailable={!mp?.m2_yoy?.value} description="M2同比增速，越高流动性越宽松。" />
        <StatCard title="制造业PMI" subtitle="景气度" value={mp?.pmi_mfg?.value != null ? fmt(mp.pmi_mfg.value) : undefined} signal={mp?.pmi_mfg?.signal} unavailable={!mp?.pmi_mfg?.value} description="采购经理人指数。>50扩张, <50收缩。" />
        <StatCard title="AH溢价" subtitle="A股 vs H股" value={mp?.ah_premium?.value != null ? fmt(mp.ah_premium.value, 1) : undefined} signal={mp?.ah_premium?.signal} unavailable={!mp?.ah_premium?.value} description="AH溢价指数。>140表示A股相对H股偏贵。" />
      </div>

      <SectionHeader title="市场指标" />
      <div className="grid-responsive-3">
        <StatCard title="市场换手率" subtitle={mt?.last_date} value={mt?.available ? `${fmt(mt.value as number)}%` : undefined} signal={(mt?.signal as string) ?? undefined} unavailable={!mt?.available} description={`日均换手率。252日百分位: ${fmt(mt?.pct_rank as number, 0)}%。高=投机活跃。`}>
          {mt?.available && mt.series && (mt.series as Array<{value?: number}>).length > 0 && (
            <MiniSparkline data={mt.series as Array<{value?: number}>} valueKey="value" width={100} height={28} color="#7170ff" className="mt-1" />
          )}
        </StatCard>
        <StatCard title="股债利差(A股)" subtitle="EP减中国10Y国债" value={sbs?.available ? `${fmt(sbs.spread_cn as number)}%` : undefined} signal={(sbs?.signal_cn as string) ?? undefined} unavailable={!sbs?.available} description="沪深300股息率减10年国债收益率。>3%极具吸引力。" />
        <StatCard title="股债利差(美股)" subtitle="EP减US 10Y国债" value={sbs?.available ? `${fmt(sbs.spread_us as number)}%` : undefined} signal={(sbs?.signal_us as string) ?? undefined} unavailable={!sbs?.available} description="沪深300股息率减美国10Y国债收益率。>2%有吸引力。" />
      </div>

      <SectionHeader title="风格轮动" />
      <div className="grid-responsive-2">
        <StatCard title="规模轮动" subtitle="大盘 vs 小盘 (沪深300/中证1000)" value={scale?.available ? `评分: ${scale.total ?? '--'}` : undefined} signal={scale?.strength as string} unavailable={!scale?.available} description={`方向: ${scale?.direction ?? '--'}。3个子信号: 布林带、5年均线、40日动量。`}>
          {scale?.available && scale.series && (scale.series as Array<{ratio?: number}>).length > 0 && (
            <MiniSparkline data={scale.series as Array<{ratio?: number}>} valueKey="ratio" width={100} height={28} color="#8b5cf6" className="mt-1" />
          )}
        </StatCard>
        <StatCard title="风格轮动" subtitle="成长 vs 价值" value={style?.available ? `评分: ${style.total ?? '--'}` : undefined} signal={style?.strength as string} unavailable={!style?.available} description={`方向: ${style?.direction ?? '--'}。3个子信号: 布林带、5年均线、40日动量。`}>
          {style?.available && style.series && (style.series as Array<{ratio?: number}>).length > 0 && (
            <MiniSparkline data={style.series as Array<{ratio?: number}>} valueKey="ratio" width={100} height={28} color="#ec4899" className="mt-1" />
          )}
        </StatCard>
      </div>

      <SectionHeader title="股息追踪 (中证红利)" />
      <div className="grid-responsive-3">
        {(() => {
          const ys = div?.yield_spread as (Record<string, unknown> & {available?: boolean; spread?: number; signal?: string; div_yield?: number; cn_bond?: number});
          return <StatCard title="股息利差" subtitle="股息率减10Y国债" value={ys?.available !== false ? `${fmt(ys?.spread as number)}%` : undefined} signal={ys?.signal as string} unavailable={!ys || ys.available === false} description={`股息率: ${fmt(ys?.div_yield as number)}%, 国债: ${fmt(ys?.cn_bond as number)}%. >3%极具吸引力。`} />;
        })()}
        {(() => {
          const rr = div?.rel_return_40d as (Record<string, unknown> & {available?: boolean; value?: number; signal?: string});
          return <StatCard title="40日超额收益" subtitle="红利 vs 中证全A" value={rr?.available !== false ? `${fmt(rr?.value as number)}%` : undefined} signal={rr?.signal as string} unavailable={!rr || rr.available === false} description="红利指数40日相对中证全A收益。>8%过热, <-5%买入信号。" />;
        })()}
        {(() => {
          const ah = div?.ah_rel_return_40d as (Record<string, unknown> & {available?: boolean; value?: number; signal?: string});
          return <StatCard title="40日超额 A vs HK红利" subtitle="A股红利 vs 港股红利" value={ah?.available !== false ? `${fmt(ah?.value as number)}%` : undefined} signal={ah?.signal as string} unavailable={!ah || ah.available === false} description="40日相对收益: A股红利 vs 港股红利。正值=A股跑赢。" />;
        })()}
      </div>

      <SectionHeader title="估值锚" />
      <div className="grid-responsive-2">
        <StatCard title="5年均线锚" subtitle={`中证全A vs 5年均线 | ${anchor?.last_date ?? ''}`} value={anchor?.available ? `${fmt(anchor.deviation_pct as number)}% 偏离` : undefined} signal={anchor?.signal as string} unavailable={!anchor?.available} description="当前价格与5年移动均线的偏离度。<-10%低估, >+20%高估。">
          {anchor?.available && anchor.series && (anchor.series as Array<{value?: number}>).length > 0 && (
            <MiniSparkline data={anchor.series as Array<{value?: number}>} valueKey="value" width={120} height={32} color="#0ea5e9" className="mt-1" />
          )}
        </StatCard>
        <StatCard title="权益基金3年滚动收益" subtitle={`混合偏股基金指数 | ${efr?.last_date ?? ''}`} value={efr?.available ? `${fmt(efr.current_pct as number)}% 年化` : undefined} signal={efr?.signal as string} unavailable={!efr?.available} description="权益基金3年年化收益。<-10%接近底部, >30%可能泡沫。">
          {efr?.available && efr.series && (efr.series as Array<{value?: number}>).length > 0 && (
            <MiniSparkline data={efr.series as Array<{value?: number}>} valueKey="value" width={120} height={32} color="#10b981" className="mt-1" />
          )}
        </StatCard>
      </div>

      <p style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '24px' }}>
        更新: {data.updated_at} | 缓存每6小时刷新
      </p>
    </div>
  );
}

function StocksTab() {
  const [searchCode, setSearchCode] = useState('600519');
  const [activeCode, setActiveCode] = useState('600519');
  const [rpsWindow, setRpsWindow] = useState(250);

  const { data: kline, isLoading: klineLoading } = useQuery({
    queryKey: ['kline', activeCode],
    queryFn: () => apiClient.get('/api/market/kline', { params: { code: activeCode, limit: 120 } }).then((r) => r.data),
    enabled: !!activeCode,
  });

  const { data: rps } = useQuery({
    queryKey: ['rps', rpsWindow],
    queryFn: () => apiClient.get('/api/market/rps', { params: { window: rpsWindow, top_n: 20 } }).then((r) => r.data),
  });

  const { data: latestDate } = useQuery({
    queryKey: ['latestDate'],
    queryFn: () => apiClient.get('/api/market/latest-date').then((r) => r.data),
  });

  const handleSearch = (e: React.FormEvent) => { e.preventDefault(); if (searchCode.trim()) setActiveCode(searchCode.trim()); };
  const latestClose = kline?.data?.[kline.data.length - 1]?.close;
  const prevClose = kline?.data?.[kline.data.length - 2]?.close;
  const priceChange = latestClose && prevClose ? latestClose - prevClose : 0;
  const priceChangePct = prevClose ? (priceChange / prevClose) * 100 : 0;

  const inputStyle: React.CSSProperties = {
    padding: '6px 12px', background: 'var(--bg-card-hover)',
    border: '1px solid var(--border-subtle)', borderRadius: '6px',
    fontSize: '13px', color: 'var(--text-primary)', outline: 'none',
  };

  return (
    <div>
      <form onSubmit={handleSearch} style={{ display: 'flex', gap: '8px', marginBottom: '20px', flexWrap: 'wrap' }}>
        <input type="text" value={searchCode} onChange={(e) => setSearchCode(e.target.value)} placeholder="输入股票代码 (如 600519)" style={{ ...inputStyle, flex: '1 1 160px', minWidth: 0 }} />
        <button type="submit" style={{ padding: '6px 16px', background: 'var(--accent-bg)', color: '#fff', border: 'none', borderRadius: '6px', fontSize: '13px', fontWeight: 510, cursor: 'pointer', flexShrink: 0 }}>查询</button>
      </form>

      <div className="layout-split">
        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <div>
              <h2 style={{ fontSize: '15px', fontWeight: 510, color: 'var(--text-primary)', margin: 0 }}>{activeCode}</h2>
              <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: '2px 0 0' }}>最新: {latestDate?.latest_date || '--'}</p>
            </div>
            {latestClose && (
              <div style={{ textAlign: 'right' }}>
                <p style={{ fontSize: '22px', fontWeight: 590, color: 'var(--text-primary)', margin: 0, letterSpacing: '-0.3px' }}>{latestClose.toFixed(2)}</p>
                <p style={{ fontSize: '13px', margin: '2px 0 0', color: priceChange >= 0 ? '#e5534b' : '#27a644' }}>
                  {priceChange >= 0 ? '+' : ''}{priceChange.toFixed(2)} ({priceChangePct.toFixed(2)}%)
                </p>
              </div>
            )}
          </div>

          {klineLoading ? (
            <div style={{ height: '240px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>加载中...</div>
          ) : kline?.data && kline.data.length > 0 ? (
            <div style={{ height: '240px', overflowY: 'auto' }} className="table-scroll">
              <table style={{ width: '100%', fontSize: '12px', borderCollapse: 'collapse', minWidth: '400px' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                    {['日期', '开盘', '最高', '最低', '收盘', '成交量'].map((h) => (
                      <th key={h} style={{ padding: '4px 8px', textAlign: h === '日期' ? 'left' : 'right', color: 'var(--text-muted)', fontWeight: 400 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {kline.data.map((d: Record<string, unknown>, i: number) => (
                    <tr key={i} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      <td style={{ padding: '4px 8px', color: 'var(--text-tertiary)' }}>{String(d.trade_date)}</td>
                      <td style={{ padding: '4px 8px', textAlign: 'right', color: 'var(--text-secondary)' }}>{Number(d.open).toFixed(2)}</td>
                      <td style={{ padding: '4px 8px', textAlign: 'right', color: 'var(--text-secondary)' }}>{Number(d.high).toFixed(2)}</td>
                      <td style={{ padding: '4px 8px', textAlign: 'right', color: 'var(--text-secondary)' }}>{Number(d.low).toFixed(2)}</td>
                      <td style={{ padding: '4px 8px', textAlign: 'right', fontWeight: 510, color: 'var(--text-primary)' }}>{Number(d.close).toFixed(2)}</td>
                      <td style={{ padding: '4px 8px', textAlign: 'right', color: 'var(--text-muted)' }}>{Number(d.volume).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ height: '240px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>暂无数据</div>
          )}
        </div>

        <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
            <h2 style={{ fontSize: '14px', fontWeight: 510, color: 'var(--text-primary)', margin: 0 }}>RPS Top 20</h2>
            <select
              value={rpsWindow}
              onChange={(e) => setRpsWindow(Number(e.target.value))}
              style={{ background: 'var(--bg-card-hover)', border: '1px solid var(--border-subtle)', borderRadius: '4px', padding: '3px 8px', fontSize: '12px', color: 'var(--text-secondary)', cursor: 'pointer' }}
            >
              <option value={20}>20日</option>
              <option value={60}>60日</option>
              <option value={120}>120日</option>
              <option value={250}>250日</option>
            </select>
          </div>

          {rps?.data && rps.data.length > 0 ? (
            <div style={{ maxHeight: '360px', overflowY: 'auto' }}>
              <table style={{ width: '100%', fontSize: '12px', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                    {['#', '代码', 'RPS', '斜率'].map((h) => (
                      <th key={h} style={{ padding: '4px 6px', textAlign: h === '#' || h === '代码' ? 'left' : 'right', color: 'var(--text-muted)', fontWeight: 400 }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rps.data.map((item: Record<string, unknown>, i: number) => (
                    <tr
                      key={i}
                      style={{ borderBottom: '1px solid var(--border-subtle)', cursor: 'pointer' }}
                      onMouseEnter={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = 'var(--bg-card)'; }}
                      onMouseLeave={(e) => { (e.currentTarget as HTMLTableRowElement).style.background = 'transparent'; }}
                      onClick={() => { setActiveCode(String(item.stock_code).split('.')[0]); setSearchCode(String(item.stock_code).split('.')[0]); }}
                    >
                      <td style={{ padding: '4px 6px', color: 'var(--text-muted)' }}>{i + 1}</td>
                      <td style={{ padding: '4px 6px', color: 'var(--text-secondary)', fontFamily: 'var(--font-geist-mono)' }}>{String(item.stock_code)}</td>
                      <td style={{ padding: '4px 6px', textAlign: 'right', color: 'var(--text-primary)', fontWeight: 510 }}>{Number(item.rps).toFixed(1)}</td>
                      <td style={{ padding: '4px 6px', textAlign: 'right', color: 'var(--text-muted)' }}>{item.rps_slope ? Number(item.rps_slope).toFixed(2) : '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px', paddingTop: '32px' }}>暂无RPS数据</div>
          )}
        </div>
      </div>
    </div>
  );
}

type TabKey = 'overview' | 'stocks';
const TABS: { key: TabKey; label: string }[] = [
  { key: 'overview', label: '市场概览' },
  { key: 'stocks',   label: '个股行情' },
];

export default function MarketPage() {
  const [activeTab, setActiveTab] = useState<TabKey>('overview');

  const { data: overview, isLoading: overviewLoading, error: overviewError } = useQuery({
    queryKey: ['marketOverview'],
    queryFn: () => marketOverviewApi.summary().then((r) => r.data),
    staleTime: 30 * 60 * 1000,
  });

  return (
    <AppShell>
      <div style={{ marginBottom: '20px' }}>
        <h1 style={{ fontSize: '20px', fontWeight: 590, color: 'var(--text-primary)', letterSpacing: '-0.3px' }}>行情</h1>
      </div>

      {/* Tab bar */}
      <div style={{ display: 'flex', gap: '2px', borderBottom: '1px solid var(--border-subtle)', marginBottom: '20px' }}>
        {TABS.map((tab) => {
          const active = activeTab === tab.key;
          return (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              style={{
                padding: '8px 16px', fontSize: '13px',
                fontWeight: active ? 510 : 400,
                color: active ? 'var(--text-primary)' : 'var(--text-tertiary)',
                background: 'none', border: 'none',
                borderBottom: active ? '2px solid var(--accent)' : '2px solid transparent',
                cursor: 'pointer', marginBottom: '-1px', transition: 'color 0.12s',
              }}
              onMouseEnter={(e) => { if (!active) (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-secondary)'; }}
              onMouseLeave={(e) => { if (!active) (e.currentTarget as HTMLButtonElement).style.color = 'var(--text-tertiary)'; }}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {activeTab === 'overview' && (
        <>
          {overviewLoading && <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px', paddingTop: '48px' }}>计算市场信号中... (首次加载约10-20秒)</div>}
          {overviewError && <div style={{ textAlign: 'center', color: '#e5534b', fontSize: '13px', paddingTop: '32px' }}>加载失败，请检查API连接。</div>}
          {overview && !overviewLoading && <OverviewTab data={overview} />}
        </>
      )}
      {activeTab === 'stocks' && <StocksTab />}
    </AppShell>
  );
}
