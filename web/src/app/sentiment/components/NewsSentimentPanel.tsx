'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

export default function NewsSentimentPanel() {
  const [stockCode, setStockCode] = useState('');
  const [searchCode, setSearchCode] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['news-sentiment', searchCode],
    queryFn: async () => {
      if (!searchCode) return null;
      const res = await fetch(`/api/sentiment/news?stock_code=${searchCode}&days=3`);
      if (!res.ok) throw new Error('Failed to fetch news');
      return res.json();
    },
    enabled: !!searchCode,
  });

  const handleSearch = () => {
    setSearchCode(stockCode);
  };

  const getSentimentBadge = (sentiment: string) => {
    const badges: Record<string, { color: string; label: string }> = {
      positive: { color: 'bg-green-100 text-green-800', label: '利好' },
      negative: { color: 'bg-red-100 text-red-800', label: '利空' },
      neutral: { color: 'bg-gray-100 text-gray-800', label: '中性' },
    };
    return badges[sentiment] || badges.neutral;
  };

  const getStrengthStars = (strength: number) => {
    return '⭐'.repeat(strength);
  };

  return (
    <div className="space-y-6">
      {/* 搜索栏 */}
      <div className="flex gap-4">
        <input
          type="text"
          placeholder="输入股票代码，如 002594"
          value={stockCode}
          onChange={(e) => setStockCode(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
          className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          onClick={handleSearch}
          disabled={!stockCode}
          className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
        >
          搜索
        </button>
      </div>

      {/* 新闻列表 */}
      {isLoading && (
        <div className="text-center py-8 text-gray-500">加载中...</div>
      )}

      {data && data.data && data.data.length === 0 && (
        <div className="text-center py-8 text-gray-500">
          未找到相关新闻
        </div>
      )}

      {data && data.data && data.data.length > 0 && (
        <div className="space-y-4">
          <div className="text-sm text-gray-600">
            共找到 {data.total} 条新闻
          </div>
          {data.data.map((news: any, idx: number) => (
            <div key={idx} className="bg-white border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <h4 className="font-medium text-gray-900 mb-2">{news.title}</h4>
                  {news.content && (
                    <p className="text-sm text-gray-600 mb-3 line-clamp-2">
                      {news.content}
                    </p>
                  )}
                  <div className="flex items-center gap-4 text-xs text-gray-500">
                    {news.source && <span>来源: {news.source}</span>}
                    {news.publish_time && (
                      <span>{new Date(news.publish_time).toLocaleString('zh-CN')}</span>
                    )}
                    {news.stock_code && <span>股票: {news.stock_code}</span>}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {!searchCode && (
        <div className="text-center py-12 text-gray-400">
          请输入股票代码开始搜索
        </div>
      )}
    </div>
  );
}
