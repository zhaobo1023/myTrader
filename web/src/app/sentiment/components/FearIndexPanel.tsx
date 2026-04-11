'use client';

import { useQuery } from '@tanstack/react-query';

export default function FearIndexPanel() {
  const { data, isLoading } = useQuery({
    queryKey: ['fear-index'],
    queryFn: async () => {
      const res = await fetch('/api/sentiment/fear-index');
      if (!res.ok) throw new Error('Failed to fetch fear index');
      return res.json();
    },
    refetchInterval: 300000, // 每5分钟刷新
  });

  const { data: history } = useQuery({
    queryKey: ['fear-index-history'],
    queryFn: async () => {
      const res = await fetch('/api/sentiment/fear-index/history?days=7');
      if (!res.ok) throw new Error('Failed to fetch history');
      return res.json();
    },
  });

  if (isLoading) {
    return <div className="animate-pulse">加载中...</div>;
  }

  if (!data) return null;

  const getScoreColor = (score: number) => {
    if (score <= 20) return 'bg-red-500';
    if (score <= 40) return 'bg-orange-500';
    if (score <= 60) return 'bg-yellow-500';
    if (score <= 80) return 'bg-lime-500';
    return 'bg-green-500';
  };

  return (
    <div className="space-y-6">
      {/* 综合评分 */}
      <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4">综合恐慌/贪婪评分</h3>
        <div className="flex items-center gap-6">
          <div className="flex-1">
            <div className="relative h-8 bg-gray-200 rounded-full overflow-hidden">
              <div
                className={`absolute h-full ${getScoreColor(data.fear_greed_score)} transition-all duration-500`}
                style={{ width: `${data.fear_greed_score}%` }}
              />
            </div>
            <div className="flex justify-between text-xs text-gray-600 mt-2">
              <span>极度恐慌</span>
              <span>中性</span>
              <span>极度贪婪</span>
            </div>
          </div>
          <div className="text-center">
            <div className="text-4xl font-bold text-gray-900">{data.fear_greed_score}</div>
            <div className="text-sm text-gray-600">{data.market_regime}</div>
          </div>
        </div>
      </div>

      {/* 指标卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <div className="text-sm text-gray-600 mb-1">VIX 恐慌指数</div>
          <div className="text-2xl font-bold text-gray-900">{data.vix.toFixed(2)}</div>
          <div className="text-xs text-gray-500 mt-1">{data.vix_level}</div>
        </div>

        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <div className="text-sm text-gray-600 mb-1">OVX 原油波动率</div>
          <div className="text-2xl font-bold text-gray-900">{data.ovx.toFixed(2)}</div>
          <div className="text-xs text-gray-500 mt-1">能源市场情绪</div>
        </div>

        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <div className="text-sm text-gray-600 mb-1">GVZ 黄金波动率</div>
          <div className="text-2xl font-bold text-gray-900">{data.gvz.toFixed(2)}</div>
          <div className="text-xs text-gray-500 mt-1">避险情绪</div>
        </div>

        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <div className="text-sm text-gray-600 mb-1">US10Y 收益率</div>
          <div className="text-2xl font-bold text-gray-900">{data.us10y.toFixed(2)}%</div>
          <div className="text-xs text-gray-500 mt-1">利率水平</div>
        </div>
      </div>

      {/* 策略建议 */}
      <div className="bg-white border border-gray-200 rounded-lg p-6">
        <h3 className="text-lg font-semibold mb-4">策略建议</h3>
        <div className="space-y-3">
          <div className="flex items-start gap-3">
            <div className="text-blue-500 mt-1">💡</div>
            <div>
              <div className="font-medium text-gray-900">利率策略</div>
              <div className="text-sm text-gray-600">{data.us10y_strategy}</div>
            </div>
          </div>
          {data.risk_alert && (
            <div className="flex items-start gap-3 bg-red-50 p-3 rounded-lg">
              <div className="text-red-500 mt-1">⚠️</div>
              <div>
                <div className="font-medium text-red-900">风险警报</div>
                <div className="text-sm text-red-700">{data.risk_alert}</div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* 历史趋势 */}
      {history && history.data && history.data.length > 0 && (
        <div className="bg-white border border-gray-200 rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4">7日趋势</h3>
          <div className="space-y-2">
            {history.data.slice(0, 7).map((item: any, idx: number) => (
              <div key={idx} className="flex items-center gap-4">
                <div className="text-sm text-gray-600 w-24">
                  {new Date(item.timestamp).toLocaleDateString('zh-CN')}
                </div>
                <div className="flex-1">
                  <div className="relative h-6 bg-gray-100 rounded overflow-hidden">
                    <div
                      className={`absolute h-full ${getScoreColor(item.fear_greed_score)}`}
                      style={{ width: `${item.fear_greed_score}%` }}
                    />
                  </div>
                </div>
                <div className="text-sm font-medium text-gray-900 w-12 text-right">
                  {item.fear_greed_score}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
