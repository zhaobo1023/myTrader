'use client';

interface OverviewCardsProps {
  data?: {
    fear_index: {
      fear_greed_score: number;
      market_regime: string;
      vix: number;
      us10y: number;
    };
    event_count: number;
    bullish_count: number;
    bearish_count: number;
    smart_money_count: number;
  };
  isLoading: boolean;
}

export default function OverviewCards({ data, isLoading }: OverviewCardsProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-6">
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="bg-white rounded-lg shadow-sm p-6 animate-pulse">
            <div className="h-4 bg-gray-200 rounded w-1/2 mb-4"></div>
            <div className="h-8 bg-gray-200 rounded w-3/4"></div>
          </div>
        ))}
      </div>
    );
  }

  if (!data) return null;

  const getRegimeColor = (regime: string) => {
    if (regime.includes('fear')) return 'text-red-600';
    if (regime.includes('greed')) return 'text-green-600';
    return 'text-gray-600';
  };

  const getRegimeLabel = (regime: string) => {
    const labels: Record<string, string> = {
      extreme_fear: '极度恐慌',
      fear: '恐慌',
      neutral: '中性',
      greed: '贪婪',
      extreme_greed: '极度贪婪',
    };
    return labels[regime] || regime;
  };

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-6">
      {/* 恐慌指数卡片 */}
      <div className="bg-white rounded-lg shadow-sm p-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-600 mb-1">恐慌/贪婪指数</p>
            <p className={`text-3xl font-bold ${getRegimeColor(data.fear_index.market_regime)}`}>
              {data.fear_index.fear_greed_score}
            </p>
            <p className="text-xs text-gray-500 mt-1">
              {getRegimeLabel(data.fear_index.market_regime)}
            </p>
          </div>
          <div className="text-4xl">📊</div>
        </div>
      </div>

      {/* VIX 卡片 */}
      <div className="bg-white rounded-lg shadow-sm p-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-600 mb-1">VIX 恐慌指数</p>
            <p className="text-3xl font-bold text-gray-900">
              {data.fear_index.vix.toFixed(2)}
            </p>
            <p className="text-xs text-gray-500 mt-1">波动率指数</p>
          </div>
          <div className="text-4xl">📈</div>
        </div>
      </div>

      {/* US10Y 卡片 */}
      <div className="bg-white rounded-lg shadow-sm p-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-600 mb-1">US10Y 收益率</p>
            <p className="text-3xl font-bold text-gray-900">
              {data.fear_index.us10y.toFixed(2)}%
            </p>
            <p className="text-xs text-gray-500 mt-1">10年期国债</p>
          </div>
          <div className="text-4xl">💰</div>
        </div>
      </div>

      {/* 事件数量卡片 */}
      <div className="bg-white rounded-lg shadow-sm p-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-gray-600 mb-1">事件信号</p>
            <p className="text-3xl font-bold text-gray-900">{data.event_count}</p>
            <p className="text-xs text-gray-500 mt-1">
              <span className="text-green-600">↑{data.bullish_count}</span>
              {' / '}
              <span className="text-red-600">↓{data.bearish_count}</span>
            </p>
          </div>
          <div className="text-4xl">🎯</div>
        </div>
      </div>
    </div>
  );
}
