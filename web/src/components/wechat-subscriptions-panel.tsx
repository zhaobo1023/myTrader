'use client';

import { useState } from 'react';
import { useQuery, useMutation } from '@tanstack/react-query';
import apiClient from '@/lib/api-client';

interface WechatFeed {
  id?: number;
  feed_id: string;
  name: string;
  description?: string;
  url?: string;
  is_active?: number;
  created_at?: string;
}

interface ArticlesExportData {
  period_days: number;
  feeds: Array<{
    feed_id: string;
    name: string;
    article_count: number;
    latest_article: string;
  }>;
}

export default function WechatSubscriptionsPanel() {
  const [showAddForm, setShowAddForm] = useState(false);
  const [feedId, setFeedId] = useState('');
  const [feedName, setFeedName] = useState('');
  const [feedDesc, setFeedDesc] = useState('');
  const [feedUrl, setFeedUrl] = useState('');
  const [submitMessage, setSubmitMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Fetch feeds list
  const { data: feeds, isLoading, error, refetch, isFetching } = useQuery<WechatFeed[]>({
    queryKey: ['wechat-feeds'],
    queryFn: async () => {
      const res = await apiClient.get('/api/wechat-feed/list');
      return res.data;
    },
  });

  // Fetch articles export
  const { data: articlesData } = useQuery<ArticlesExportData>({
    queryKey: ['wechat-articles-export'],
    queryFn: async () => {
      const res = await apiClient.get('/api/wechat-feed/articles-export', { params: { days: 1 } });
      return res.data;
    },
  });

  // Add feed mutation
  const addMutation = useMutation({
    mutationFn: async (data: { feed_id: string; name: string; description?: string; url?: string }) => {
      const res = await apiClient.post('/api/wechat-feed/add', data);
      return res.data;
    },
    onSuccess: () => {
      setSubmitMessage({ type: 'success', text: '[OK] 公众号已添加' });
      setFeedId('');
      setFeedName('');
      setFeedDesc('');
      setFeedUrl('');
      setShowAddForm(false);
      refetch();
      setTimeout(() => setSubmitMessage(null), 3000);
    },
    onError: (err: any) => {
      const errMsg = err.response?.data?.detail || '添加失败';
      setSubmitMessage({ type: 'error', text: `[BAD] ${errMsg}` });
    },
  });

  // Delete feed mutation
  const deleteMutation = useMutation({
    mutationFn: async (feedId: string) => {
      const res = await apiClient.delete(`/api/wechat-feed/${feedId}`);
      return res.data;
    },
    onSuccess: () => {
      setSubmitMessage({ type: 'success', text: '[OK] 公众号已删除' });
      refetch();
      setTimeout(() => setSubmitMessage(null), 3000);
    },
    onError: (err: any) => {
      const errMsg = err.response?.data?.detail || '删除失败';
      setSubmitMessage({ type: 'error', text: `[BAD] ${errMsg}` });
    },
  });

  // Sync feeds mutation
  const syncMutation = useMutation({
    mutationFn: async () => {
      const res = await apiClient.post('/api/wechat-feed/sync');
      return res.data;
    },
    onSuccess: (data) => {
      setSubmitMessage({ type: 'success', text: `[OK] 已同步 ${data.synced_count} 个新公众号` });
      refetch();
      setTimeout(() => setSubmitMessage(null), 3000);
    },
    onError: (err: any) => {
      const errMsg = err.response?.data?.detail || '同步失败';
      setSubmitMessage({ type: 'error', text: `[BAD] ${errMsg}` });
    },
  });

  const handleAddFeed = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!feedId.trim() || !feedName.trim()) {
      setSubmitMessage({ type: 'error', text: '[BAD] 公众号ID和名称不能为空' });
      return;
    }
    addMutation.mutate({
      feed_id: feedId.trim(),
      name: feedName.trim(),
      description: feedDesc.trim() || undefined,
      url: feedUrl.trim() || undefined,
    });
  };

  const handleDeleteFeed = (fid: string) => {
    if (confirm(`确定要删除 "${fid}" 吗？`)) {
      deleteMutation.mutate(fid);
    }
  };

  // Build article count map
  const articleCountMap = new Map(
    articlesData?.feeds.map((f) => [f.feed_id, f.article_count]) ?? []
  );

  return (
    <div>
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <h3 className="text-sm font-medium text-gray-800">公众号订阅</h3>
        <div className="flex gap-2">
          <button
            onClick={() => setShowAddForm(!showAddForm)}
            className="text-xs px-3 py-1.5 rounded border border-blue-200 bg-blue-50 text-blue-600 hover:bg-blue-100"
          >
            {showAddForm ? '取消' : '[+] 添加'}
          </button>
          <button
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
            className="text-xs px-3 py-1.5 rounded border border-gray-200 bg-white text-gray-500 hover:bg-gray-50 disabled:opacity-50"
          >
            {syncMutation.isPending ? '同步中...' : '同步'}
          </button>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="text-xs px-2.5 py-1 rounded border border-gray-200 bg-white text-gray-500 hover:bg-gray-50 disabled:opacity-50"
          >
            {isFetching ? '刷新中...' : '刷新'}
          </button>
        </div>
      </div>

      {submitMessage && (
        <div
          className={`mb-4 p-2.5 rounded text-xs font-mono ${
            submitMessage.type === 'success'
              ? 'bg-green-50 text-green-700'
              : 'bg-red-50 text-red-600'
          }`}
        >
          {submitMessage.text}
        </div>
      )}

      {showAddForm && (
        <div className="mb-4 p-3 bg-gray-50 rounded-lg border border-gray-200">
          <form onSubmit={handleAddFeed} className="space-y-2">
            <div>
              <label className="block text-xs text-gray-600 mb-1">公众号ID (feed_id)</label>
              <input
                type="text"
                value={feedId}
                onChange={(e) => setFeedId(e.target.value)}
                placeholder="例: wechat_official_account"
                className="w-full px-2 py-1 text-xs border border-gray-300 rounded focus:outline-none focus:border-blue-400"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">公众号名称</label>
              <input
                type="text"
                value={feedName}
                onChange={(e) => setFeedName(e.target.value)}
                placeholder="例: 财联社"
                className="w-full px-2 py-1 text-xs border border-gray-300 rounded focus:outline-none focus:border-blue-400"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">描述 (可选)</label>
              <input
                type="text"
                value={feedDesc}
                onChange={(e) => setFeedDesc(e.target.value)}
                placeholder="例: 财经新闻快讯"
                className="w-full px-2 py-1 text-xs border border-gray-300 rounded focus:outline-none focus:border-blue-400"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">URL (可选)</label>
              <input
                type="url"
                value={feedUrl}
                onChange={(e) => setFeedUrl(e.target.value)}
                placeholder="例: https://example.com/feed"
                className="w-full px-2 py-1 text-xs border border-gray-300 rounded focus:outline-none focus:border-blue-400"
              />
            </div>
            <div className="flex gap-2 pt-2">
              <button
                type="submit"
                disabled={addMutation.isPending}
                className="flex-1 px-3 py-1.5 text-xs rounded border border-green-200 bg-green-50 text-green-600 hover:bg-green-100 disabled:opacity-50"
              >
                {addMutation.isPending ? '添加中...' : '确认添加'}
              </button>
            </div>
          </form>
        </div>
      )}

      {isLoading && <div className="text-sm text-gray-400 py-4 text-center">加载中...</div>}
      {error && (
        <div className="text-sm text-red-500 py-4 text-center">加载失败，请确认已登录管理员账号</div>
      )}

      {feeds && feeds.length > 0 && (
        <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-gray-50 text-gray-400 border-b border-gray-100">
                <th className="text-left px-3 py-2 font-medium">公众号名称</th>
                <th className="text-left px-3 py-2 font-medium">ID</th>
                <th className="text-center px-3 py-2 font-medium w-20">今日文章</th>
                <th className="text-left px-3 py-2 font-medium w-32">描述</th>
                <th className="text-right px-3 py-2 font-medium w-24">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {feeds.map((feed) => {
                const articleCount = articleCountMap.get(feed.feed_id) ?? 0;
                return (
                  <tr key={feed.feed_id} className="hover:bg-gray-50/50">
                    <td className="px-3 py-2 text-gray-700 font-medium">{feed.name}</td>
                    <td className="px-3 py-2 text-gray-500 font-mono text-xs">{feed.feed_id}</td>
                    <td className="px-3 py-2 text-center">
                      <span className={`text-xs font-medium ${articleCount > 0 ? 'text-green-600' : 'text-gray-300'}`}>
                        {articleCount}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-gray-500 truncate max-w-xs" title={feed.description}>
                      {feed.description || '-'}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button
                        onClick={() => handleDeleteFeed(feed.feed_id)}
                        disabled={deleteMutation.isPending}
                        className="text-xs px-2 py-1 rounded border border-red-200 bg-red-50 text-red-600 hover:bg-red-100 disabled:opacity-50"
                      >
                        {deleteMutation.isPending ? '...' : '[x] 删除'}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {feeds && feeds.length === 0 && !isLoading && (
        <div className="text-sm text-gray-400 py-8 text-center">暂无订阅的公众号</div>
      )}
    </div>
  );
}
