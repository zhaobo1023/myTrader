'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

export default function EventSignalPanel() {
  const [eventType, setEventType] = useState<string>('all');
  const [days, setDays] = useState(3);

  const { data, isLoading } = useQuery({
    queryKey: ['event-signals', eventType, days],
    queryFn: async () => {
      let url = `/api/sentiment/events?days=${days}`;
      if (eventType !== 'all') {
        url += `&event_type=${eventType}`;
      }
      const res = await fetch(url);
      if (!res.ok) throw new Error('Failed to fetch events');
      return res.json();
    },
  });

  const getSignalBadge = (signal: string) => {
    const badges: Record<string, { color: string; label: string }> = {
      strong_buy: { color: 'bg-green-600 text-white', label: '强烈买入' },
      buy: { color: 'bg-green-500 text-white', label: '买入' },
      hold: { color: 'bg-yellow-500 text-white', label: '持有' },
      sell: { color: 'bg-red-500 text-white', label: '卖出' },
      strong_sell: { color: 'bg-red-600 text-white', label: '强烈卖出' },
    };
    return badges[signal] || { color: 'bg-gray-500 text-white', label: signal };
  };

  const getEventTypeBadge = (type: string) => {
    const badges: Record<string, { color: string; label: string }> = {
      bullish: { color: 'bg-green-100 text-green-800', label: '利好' },
      bearish: { color: 'bg-red-100 text-red-800', label: '利空' },
      policy: { color: 'bg-blue-100 text-blue-800', label: '政策' },
    };
    return badges[type] || { color: 'bg-gray-100 text-gray-800', label: type };
  };

  const stats = data?.data ? {
    total: data.total,
    bullish: data.data.filter((e: any) => e.event_type === 'bullish').length,
    bearish: data.data.filter((e: any) => e.event_type === 'bearish').length,
    policy: data.data.filter((e: any) => e.event_type === 'policy').length,
  } : { total: 0, bullish: 0, bearish: 0, policy: 0 };

  return (
    <div className="space-y-6">
      {/* 筛选栏 */}
      <div className="flex items-center gap-4">
        <div className="flex gap-2">
          <button
            onClick={() => setEventType('all')}
            className={`px-4 py-2 rounded-lg text-sm font-medium ${
              eventType === 'all'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            全部
          </button>
          <button
            onClick={() => setEventType('bullish')}
            className={`px-4 py-2 rounded-lg text-sm font-medium ${
              eventType === 'bullish'
                ? 'bg-green-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            利好
          </button>
          <button
            onClick={() => setEventType('bearish')}
            className={`px-4 py-2 rounded-lg text-sm font-medium ${
              eventType === 'bearish'
                ? 'bg-red-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            利空
          </button>
          <button
            onClick={() => setEventType('policy')}
            className={`px-4 py-2 rounded-lg text-sm font-medium ${
              eventType === 'policy'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            政策
          </button>
        </div>

        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value={1}>最近1天</option>
          <option value={3}>最近3天</option>
          <option value={7}>最近7天</option>
          <option value={30}>最近30天</option>
        </select>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-4 gap-4">
        <div className="bg-white border border-gray-200 rounded-lg p-4">
          <div className="text-sm text-gray-600">总事件</div>
          <div className="text-2xl font-bold text-gray-900">{stats.total}</div>
        </div>
        <div className="bg-green-50 border border-green-200 rounded-lg p-4">
          <div className="text-sm text-green-700">利好事件</div>
          <div className="text-2xl font-bold text-green-900">{stats.bullish}</div>
        </div>
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <div className="text-sm text-red-700">利空事件</div>
          <div className="text-2xl font-bold text-red-900">{stats.bearish}</div>
        </div>
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <div className="text-sm text-blue-700">政策事件</div>
          <div className="text-2xl font-bold text-blue-900">{stats.policy}</div>
        </div>
      </div>

      {/* 事件列表 */}
      {isLoading && (
        <div className="text-center py-8 text-gray-500">加载中...</div>
      )}

      {data && data.data && data.data.length === 0 && (
        <div className="text-center py-8 text-gray-500">暂无事件</div>
      )}

      {data && data.data && data.data.length > 0 && (
        <div className="space-y-3">
          {data.data.map((event: any, idx: number) => {
            const signalBadge = getSignalBadge(event.signal);
            const typeBadge = getEventTypeBadge(event.event_type);

            return (
              <div key={idx} className="bg-white border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-2">
                      <span className={`px-2 py-1 rounded text-xs font-medium ${typeBadge.color}`}>
                        {typeBadge.label}
                      </span>
                      <span className={`px-2 py-1 rounded text-xs font-medium ${signalBadge.color}`}>
                        {signalBadge.label}
                      </span>
                      {event.stock_code && (
                        <span className="px-2 py-1 bg-gray-100 text-gray-800 rounded text-xs font-medium">
                          {event.stock_code}
                        </span>
                      )}
                    </div>
                    <h4 className="font-medium text-gray-900 mb-1">{event.news_title}</h4>
                    <div className="text-sm text-gray-600 mb-2">
                      类别: {event.event_category}
                    </div>
                    <div className="text-sm text-gray-600">
                      {event.signal_reason}
                    </div>
                    {event.matched_keywords && event.matched_keywords.length > 0 && (
                      <div className="flex items-center gap-2 mt-2">
                        <span className="text-xs text-gray-500">关键词:</span>
                        {event.matched_keywords.map((kw: string, i: number) => (
                          <span key={i} className="px-2 py-0.5 bg-blue-50 text-blue-700 rounded text-xs">
                            {kw}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="text-xs text-gray-500 whitespace-nowrap">
                    {event.trade_date}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
