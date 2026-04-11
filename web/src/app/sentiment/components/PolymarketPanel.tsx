'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';

export default function PolymarketPanel() {
  const [keyword, setKeyword] = useState('');
  const [searchKeyword, setSearchKeyword] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['polymarket', searchKeyword],
    queryFn: async () => {
      if (!searchKeyword) return null;
      const res = await fetch(`/api/sentiment/polymarket?keyword=${encodeURIComponent(searchKeyword)}&min_volume=100000`);
      if (!res.ok) throw new Error('Failed to fetch Polymarket data');
      return res.json();
    },
    enabled: !!searchKeyword,
  });

  const handleSearch = () => {
    setSearchKeyword(keyword);
  };

  const getProbabilityColor = (prob: number) => {
    if (prob >= 70) return 'text-green-600';
    if (prob >= 50) return 'text-yellow-600';
    return 'text-red-600';
  };

  const formatVolume = (volume: number) => {
    if (volume >= 1000000) {
      return `$${(volume / 1000000).toFixed(1)}M`;
    }
    return `$${(volume / 1000).toFixed(0)}K`;
  };

  const smartMoneyCount = data?.data?.filter((e: any) => e.is_smart_money_signal).length || 0;

  return (
    <div className="space-y-6">
      {/* 搜索栏 */}
      <div className="flex gap-4">
        <input
          type="text"
          placeholder="输入关键词，如 tariff, election, crypto"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
          className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <button
          onClick={handleSearch}
          disabled={!keyword}
          className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
        >
          搜索
        </button>
      </div>

      {/* 提示信息 */}
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
        <div className="flex items-start gap-3">
          <div className="text-blue-500 text-xl">💡</div>
          <div className="text-sm text-blue-800">
            <div className="font-medium mb-1">关于 Polymarket</div>
            <div>Polymarket 是去中心化预测市场，可以用于判断市场对未来事件的预期。聪明钱信号：交易量 &gt; $1M 且概率极端（&gt;70% 或 &lt;30%）</div>
          </div>
        </div>
      </div>

      {/* 统计 */}
      {data && data.data && data.data.length > 0 && (
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-white border border-gray-200 rounded-lg p-4">
            <div className="text-sm text-gray-600">找到市场</div>
            <div className="text-2xl font-bold text-gray-900">{data.total}</div>
          </div>
          <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
            <div className="text-sm text-yellow-700">聪明钱信号</div>
            <div className="text-2xl font-bold text-yellow-900">{smartMoneyCount}</div>
          </div>
        </div>
      )}

      {/* 市场列表 */}
      {isLoading && (
        <div className="text-center py-8 text-gray-500">加载中...</div>
      )}

      {data && data.data && data.data.length === 0 && (
        <div className="text-center py-8 text-gray-500">
          未找到相关市场
        </div>
      )}

      {data && data.data && data.data.length > 0 && (
        <div className="space-y-4">
          {data.data.map((market: any, idx: number) => (
            <div key={idx} className="bg-white border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    {market.is_smart_money_signal && (
                      <span className="px-2 py-1 bg-yellow-100 text-yellow-800 rounded text-xs font-medium">
                        💰 聪明钱
                      </span>
                    )}
                    {market.category && (
                      <span className="px-2 py-1 bg-gray-100 text-gray-800 rounded text-xs">
                        {market.category}
                      </span>
                    )}
                  </div>
                  <h4 className="font-medium text-gray-900 mb-2">{market.market_question}</h4>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <div className="text-xs text-gray-500 mb-1">Yes 概率</div>
                      <div className={`text-2xl font-bold ${getProbabilityColor(market.yes_probability)}`}>
                        {market.yes_probability.toFixed(1)}%
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-gray-500 mb-1">交易量</div>
                      <div className="text-2xl font-bold text-gray-900">
                        {formatVolume(market.volume)}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              <div className="mt-3 pt-3 border-t border-gray-100">
                <div className="text-xs text-gray-500">
                  快照时间: {new Date(market.snapshot_time).toLocaleString('zh-CN')}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {!searchKeyword && (
        <div className="text-center py-12 text-gray-400">
          <div className="text-4xl mb-4">🔮</div>
          <div>输入关键词搜索预测市场</div>
          <div className="text-sm mt-2">推荐: tariff, election, crypto, fed</div>
        </div>
      )}
    </div>
  );
}
