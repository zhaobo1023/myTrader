'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import OverviewCards from './components/OverviewCards';
import FearIndexPanel from './components/FearIndexPanel';
import NewsSentimentPanel from './components/NewsSentimentPanel';
import EventSignalPanel from './components/EventSignalPanel';
import PolymarketPanel from './components/PolymarketPanel';

export default function SentimentPage() {
  const [activeTab, setActiveTab] = useState<'fear' | 'news' | 'events' | 'polymarket'>('fear');

  const { data: overview, isLoading } = useQuery({
    queryKey: ['sentiment-overview'],
    queryFn: async () => {
      const res = await fetch('/api/sentiment/overview');
      if (!res.ok) throw new Error('Failed to fetch overview');
      return res.json();
    },
    refetchInterval: 60000, // 每分钟刷新
  });

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-7xl mx-auto">
        <div className="mb-6">
          <h1 className="text-3xl font-bold text-gray-900">舆情监控</h1>
          <p className="text-gray-600 mt-2">实时监控市场情绪、新闻事件和预测市场</p>
        </div>

        {/* 概览卡片 */}
        <OverviewCards data={overview} isLoading={isLoading} />

        {/* Tab 导航 */}
        <div className="bg-white rounded-lg shadow-sm mb-6">
          <div className="border-b border-gray-200">
            <nav className="flex -mb-px">
              <button
                onClick={() => setActiveTab('fear')}
                className={`px-6 py-3 text-sm font-medium border-b-2 ${
                  activeTab === 'fear'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                恐慌指数
              </button>
              <button
                onClick={() => setActiveTab('news')}
                className={`px-6 py-3 text-sm font-medium border-b-2 ${
                  activeTab === 'news'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                新闻舆情
              </button>
              <button
                onClick={() => setActiveTab('events')}
                className={`px-6 py-3 text-sm font-medium border-b-2 ${
                  activeTab === 'events'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                事件信号
              </button>
              <button
                onClick={() => setActiveTab('polymarket')}
                className={`px-6 py-3 text-sm font-medium border-b-2 ${
                  activeTab === 'polymarket'
                    ? 'border-blue-500 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
                }`}
              >
                预测市场
              </button>
            </nav>
          </div>
        </div>

        {/* Tab 内容 */}
        <div className="bg-white rounded-lg shadow-sm p-6">
          {activeTab === 'fear' && <FearIndexPanel />}
          {activeTab === 'news' && <NewsSentimentPanel />}
          {activeTab === 'events' && <EventSignalPanel />}
          {activeTab === 'polymarket' && <PolymarketPanel />}
        </div>
      </div>
    </div>
  );
}
