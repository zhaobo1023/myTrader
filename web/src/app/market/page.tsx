'use client';

import { useState } from 'react';
import Navbar from '@/components/layout/Navbar';
import SignalBadge from '@/components/market/SignalBadge';
import MiniSparkline from '@/components/market/MiniSparkline';
import apiClient, { marketOverviewApi, MarketOverviewSummary } from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';

// ---------------------------------------------------------------------------
// Overview tab components
// ---------------------------------------------------------------------------

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
    <div className="bg-white rounded-lg border border-gray-200 p-4">
      <div className="flex items-start justify-between mb-2">
        <div>
          <p className="text-sm font-medium text-gray-900">{title}</p>
          {subtitle && <p className="text-xs text-gray-500">{subtitle}</p>}
        </div>
        {signal && !unavailable && <SignalBadge signal={signal} />}
      </div>
      {unavailable ? (
        <p className="text-sm text-gray-400 italic">No data yet (run fetch_all_indicators first)</p>
      ) : (
        <>
          {value && <p className="text-xl font-semibold text-gray-900 mt-1">{value}</p>}
          {children}
          <p className="text-xs text-gray-500 mt-2 leading-relaxed">{description}</p>
        </>
      )}
    </div>
  );
}

function SectionHeader({ title }: { title: string }) {
  return (
    <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mt-6 mb-3">{title}</h2>
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
      {/* Macro Pulse row */}
      <SectionHeader title="Macro Pulse" />
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {/* QVIX */}
        <StatCard
          title="QVIX"
          subtitle="A-share fear index"
          value={mp?.qvix?.value != null ? mp.qvix.value.toFixed(2) : undefined}
          signal={mp?.qvix?.signal}
          unavailable={!mp?.qvix?.value}
          description="Market fear gauge. >25 fearful, >35 panic."
        />
        {/* North flow */}
        <StatCard
          title="Northbound Flow"
          subtitle="5-day total (bn CNY)"
          value={mp?.north_flow?.sum_5d != null ? `${mp.north_flow.sum_5d > 0 ? '+' : ''}${fmt(mp.north_flow.sum_5d)}` : undefined}
          signal={mp?.north_flow?.signal}
          unavailable={!mp?.north_flow}
          description="Foreign capital 5-day net inflow via Stock Connect."
        />
        {/* M2 */}
        <StatCard
          title="M2 YoY"
          subtitle="Broad money supply"
          value={mp?.m2_yoy?.value != null ? `${fmt(mp.m2_yoy.value)}%` : undefined}
          unavailable={!mp?.m2_yoy?.value}
          description="M2 year-over-year growth rate. Higher = looser liquidity."
        />
        {/* PMI */}
        <StatCard
          title="Mfg PMI"
          subtitle="Manufacturing"
          value={mp?.pmi_mfg?.value != null ? fmt(mp.pmi_mfg.value) : undefined}
          signal={mp?.pmi_mfg?.signal}
          unavailable={!mp?.pmi_mfg?.value}
          description="Purchasing Managers Index. >50 expansion, <50 contraction."
        />
        {/* AH Premium */}
        <StatCard
          title="AH Premium"
          subtitle="A vs H share"
          value={mp?.ah_premium?.value != null ? fmt(mp.ah_premium.value, 1) : undefined}
          signal={mp?.ah_premium?.signal}
          unavailable={!mp?.ah_premium?.value}
          description="AH premium index. >140 = A shares expensive vs H shares."
        />
      </div>

      {/* Market metrics row */}
      <SectionHeader title="Market Metrics" />
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {/* Market turnover */}
        <StatCard
          title="Market Turnover Rate"
          subtitle={mt?.last_date}
          value={mt?.available ? `${fmt(mt.value as number)}%` : undefined}
          signal={(mt?.signal as string) ?? undefined}
          unavailable={!mt?.available}
          description={`Daily avg turnover rate. 252d percentile: ${fmt(mt?.pct_rank as number, 0)}th. High = active speculation.`}
        >
          {mt?.available && mt.series && (mt.series as Array<{value?: number}>).length > 0 && (
            <MiniSparkline
              data={mt.series as Array<{value?: number}>}
              valueKey="value"
              width={100}
              height={32}
              color="#6366f1"
              className="mt-1"
            />
          )}
        </StatCard>

        {/* Stock-bond spread CN */}
        <StatCard
          title="Stock-Bond Spread (CN)"
          subtitle="EP minus CN 10Y bond"
          value={sbs?.available ? `${fmt(sbs.spread_cn as number)}%` : undefined}
          signal={(sbs?.signal_cn as string) ?? undefined}
          unavailable={!sbs?.available}
          description="CSI300 earnings yield minus China 10Y bond yield. >3% very attractive."
        />

        {/* Stock-bond spread US */}
        <StatCard
          title="Stock-Bond Spread (US)"
          subtitle="EP minus US 10Y bond"
          value={sbs?.available ? `${fmt(sbs.spread_us as number)}%` : undefined}
          signal={(sbs?.signal_us as string) ?? undefined}
          unavailable={!sbs?.available}
          description="CSI300 earnings yield minus US 10Y bond yield. >2% attractive."
        />
      </div>

      {/* Style rotation */}
      <SectionHeader title="Rotation Tri-Prism" />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {/* Scale rotation */}
        <StatCard
          title="Scale Rotation"
          subtitle="Large cap vs Small cap (CSI300/CSI1000)"
          value={scale?.available ? `Score: ${scale.total ?? '--'}` : undefined}
          signal={scale?.strength as string}
          unavailable={!scale?.available}
          description={`Direction: ${scale?.direction ?? '--'}. 3 sub-signals: Bollinger, 5Y MA, 40d momentum. Score >= 2 confirmed.`}
        >
          {scale?.available && scale.series && (scale.series as Array<{ratio?: number}>).length > 0 && (
            <MiniSparkline
              data={scale.series as Array<{ratio?: number}>}
              valueKey="ratio"
              width={100}
              height={32}
              color="#8b5cf6"
              className="mt-1"
            />
          )}
        </StatCard>

        {/* Style rotation */}
        <StatCard
          title="Style Rotation"
          subtitle="Growth vs Value (CSI300 Growth/Value)"
          value={style?.available ? `Score: ${style.total ?? '--'}` : undefined}
          signal={style?.strength as string}
          unavailable={!style?.available}
          description={`Direction: ${style?.direction ?? '--'}. 3 sub-signals: Bollinger, 5Y MA, 40d momentum. Score >= 2 confirmed.`}
        >
          {style?.available && style.series && (style.series as Array<{ratio?: number}>).length > 0 && (
            <MiniSparkline
              data={style.series as Array<{ratio?: number}>}
              valueKey="ratio"
              width={100}
              height={32}
              color="#ec4899"
              className="mt-1"
            />
          )}
        </StatCard>
      </div>

      {/* Dividend tracking */}
      <SectionHeader title="Dividend Tracking (CSI Dividend Index)" />
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {/* Yield spread */}
        {(() => {
          const ys = div?.yield_spread as (Record<string, unknown> & {available?: boolean; spread?: number; signal?: string; div_yield?: number; cn_bond?: number});
          return (
            <StatCard
              title="Dividend Yield Spread"
              subtitle="Div yield minus CN 10Y bond"
              value={ys?.available !== false ? `${fmt(ys?.spread as number)}%` : undefined}
              signal={ys?.signal as string}
              unavailable={!ys || ys.available === false}
              description={`Div yield: ${fmt(ys?.div_yield as number)}%, Bond: ${fmt(ys?.cn_bond as number)}%. >3% very attractive.`}
            />
          );
        })()}

        {/* 40d rel return A vs full */}
        {(() => {
          const rr = div?.rel_return_40d as (Record<string, unknown> & {available?: boolean; value?: number; signal?: string});
          return (
            <StatCard
              title="40d Return vs Full A"
              subtitle="CSI Dividend vs Zhongzheng QuanA"
              value={rr?.available !== false ? `${fmt(rr?.value as number)}%` : undefined}
              signal={rr?.signal as string}
              unavailable={!rr || rr.available === false}
              description="40-day relative return of dividend index vs full A-share index. >8% overextended, <-5% buy signal."
            />
          );
        })()}

        {/* 40d A vs HK dividend */}
        {(() => {
          const ah = div?.ah_rel_return_40d as (Record<string, unknown> & {available?: boolean; value?: number; signal?: string});
          return (
            <StatCard
              title="40d Return A vs HK Div"
              subtitle="A-share Div vs HK-listed Div index"
              value={ah?.available !== false ? `${fmt(ah?.value as number)}%` : undefined}
              signal={ah?.signal as string}
              unavailable={!ah || ah.available === false}
              description="40-day relative return: A vs HK dividend index. Positive = A shares outperforming."
            />
          );
        })()}
      </div>

      {/* 5Y anchor + equity fund */}
      <SectionHeader title="Valuation Anchors" />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {/* 5Y anchor */}
        <StatCard
          title="5-Year Anchor"
          subtitle={`Zhongzheng QuanA vs 5Y MA | ${anchor?.last_date ?? ''}`}
          value={anchor?.available ? `${fmt(anchor.deviation_pct as number)}% deviation` : undefined}
          signal={anchor?.signal as string}
          unavailable={!anchor?.available}
          description="Current price vs 5-year moving average. <-10% undervalued, >+20% overvalued."
        >
          {anchor?.available && anchor.series && (anchor.series as Array<{value?: number}>).length > 0 && (
            <MiniSparkline
              data={anchor.series as Array<{value?: number}>}
              valueKey="value"
              width={120}
              height={36}
              color="#0ea5e9"
              className="mt-1"
            />
          )}
        </StatCard>

        {/* Equity fund rolling */}
        <StatCard
          title="Equity Fund 3Y Rolling Return"
          subtitle={`Blended equity fund index | ${efr?.last_date ?? ''}`}
          value={efr?.available ? `${fmt(efr.current_pct as number)}% ann.` : undefined}
          signal={efr?.signal as string}
          unavailable={!efr?.available}
          description="3-year annualized return of the equity fund composite index. <-10% near bottom, >30% potential bubble."
        >
          {efr?.available && efr.series && (efr.series as Array<{value?: number}>).length > 0 && (
            <MiniSparkline
              data={efr.series as Array<{value?: number}>}
              valueKey="value"
              width={120}
              height={36}
              color="#10b981"
              className="mt-1"
            />
          )}
        </StatCard>
      </div>

      <p className="text-xs text-gray-400 mt-6">
        Updated: {data.updated_at} | Cache refreshes every 6 hours
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Stocks tab (existing K-line + RPS)
// ---------------------------------------------------------------------------

function StocksTab() {
  const [searchCode, setSearchCode] = useState('600519');
  const [activeCode, setActiveCode] = useState('600519');
  const [rpsWindow, setRpsWindow] = useState(250);

  const { data: kline, isLoading: klineLoading } = useQuery({
    queryKey: ['kline', activeCode],
    queryFn: () =>
      apiClient
        .get('/api/market/kline', { params: { code: activeCode, limit: 120 } })
        .then((r) => r.data),
    enabled: !!activeCode,
  });

  const { data: rps } = useQuery({
    queryKey: ['rps', rpsWindow],
    queryFn: () =>
      apiClient
        .get('/api/market/rps', { params: { window: rpsWindow, top_n: 20 } })
        .then((r) => r.data),
  });

  const { data: latestDate } = useQuery({
    queryKey: ['latestDate'],
    queryFn: () => apiClient.get('/api/market/latest-date').then((r) => r.data),
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchCode.trim()) setActiveCode(searchCode.trim());
  };

  const latestClose = kline?.data?.[kline.data.length - 1]?.close;
  const prevClose = kline?.data?.[kline.data.length - 2]?.close;
  const priceChange = latestClose && prevClose ? latestClose - prevClose : 0;
  const priceChangePct = prevClose ? (priceChange / prevClose) * 100 : 0;

  return (
    <div>
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
                <p className={`text-sm ${priceChange >= 0 ? 'text-red-600' : 'text-green-600'}`}>
                  {priceChange >= 0 ? '+' : ''}
                  {priceChange.toFixed(2)} ({priceChangePct.toFixed(2)}%)
                </p>
              </div>
            )}
          </div>

          {klineLoading ? (
            <div className="h-64 flex items-center justify-center text-gray-400">Loading...</div>
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
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

type TabKey = 'overview' | 'stocks';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'overview', label: 'Market Overview' },
  { key: 'stocks', label: 'Stocks' },
];

export default function MarketPage() {
  const [activeTab, setActiveTab] = useState<TabKey>('overview');

  const { data: overview, isLoading: overviewLoading, error: overviewError } = useQuery({
    queryKey: ['marketOverview'],
    queryFn: () => marketOverviewApi.summary().then((r) => r.data),
    staleTime: 30 * 60 * 1000, // 30 min client-side stale time
  });

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {/* Tab bar */}
        <div className="flex gap-1 mb-6 border-b border-gray-200">
          {TABS.map((tab) => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-2 text-sm font-medium transition-colors rounded-t-md ${
                activeTab === tab.key
                  ? 'border-b-2 border-blue-600 text-blue-700 bg-white'
                  : 'text-gray-500 hover:text-gray-700 hover:bg-gray-100'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab === 'overview' && (
          <>
            {overviewLoading && (
              <div className="py-16 text-center text-gray-400 text-sm">
                Computing market signals... (first load may take 10-20s)
              </div>
            )}
            {overviewError && (
              <div className="py-8 text-center text-red-500 text-sm">
                Failed to load market overview. Check API connection.
              </div>
            )}
            {overview && !overviewLoading && <OverviewTab data={overview} />}
          </>
        )}

        {activeTab === 'stocks' && <StocksTab />}
      </main>
    </div>
  );
}
