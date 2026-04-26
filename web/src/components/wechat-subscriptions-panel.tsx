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
    mutationFn: async (data: { feed_id: string; description?: string; url?: string }) => {
      const res = await apiClient.post('/api/wechat-feed/add', data);
      return res.data;
    },
    onSuccess: () => {
      setSubmitMessage({ type: 'success', text: '[OK] 公众号已添加' });
      setFeedId('');
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
    mutationFn: async (targetFeedId: string) => {
      const res = await apiClient.delete(`/api/wechat-feed/${encodeURIComponent(targetFeedId)}`);
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
    if (!feedId.trim()) {
      setSubmitMessage({ type: 'error', text: '[BAD] 公众号ID不能为空' });
      return;
    }
    addMutation.mutate({
      feed_id: feedId.trim(),
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
        <h3 className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>公众号订阅</h3>
        <div className="flex gap-2">
          <button
            onClick={() => setShowAddForm(!showAddForm)}
            className="text-xs px-3 py-1.5 rounded"
            style={{
              border: '1px solid var(--border-subtle)',
              background: 'var(--bg-surface)',
              color: 'var(--accent)',
            }}
          >
            {showAddForm ? '取消' : '[+] 添加'}
          </button>
          <button
            onClick={() => syncMutation.mutate()}
            disabled={syncMutation.isPending}
            className="text-xs px-3 py-1.5 rounded disabled:opacity-50"
            style={{
              border: '1px solid var(--border-subtle)',
              background: 'var(--bg-surface)',
              color: 'var(--text-secondary)',
            }}
          >
            {syncMutation.isPending ? '同步中...' : '同步'}
          </button>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="text-xs px-2.5 py-1 rounded disabled:opacity-50"
            style={{
              border: '1px solid var(--border-subtle)',
              background: 'var(--bg-surface)',
              color: 'var(--text-secondary)',
            }}
          >
            {isFetching ? '刷新中...' : '刷新'}
          </button>
        </div>
      </div>

      {submitMessage && (
        <div
          className="mb-4 p-2.5 rounded text-xs font-mono"
          style={{
            background: submitMessage.type === 'success' ? 'var(--bg-surface)' : 'var(--bg-surface)',
            color: submitMessage.type === 'success' ? 'var(--up)' : 'var(--down)',
            border: `1px solid ${submitMessage.type === 'success' ? 'var(--up-soft)' : 'var(--down-soft)'}`,
          }}
        >
          {submitMessage.text}
        </div>
      )}

      {showAddForm && (
        <div
          className="mb-4 p-3 rounded-lg"
          style={{
            background: 'var(--bg-panel)',
            border: '1px solid var(--border-subtle)',
          }}
        >
          <form onSubmit={handleAddFeed} className="space-y-2">
            <div>
              <label className="block text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>
                公众号ID (feed_id)
              </label>
              <input
                type="text"
                value={feedId}
                onChange={(e) => setFeedId(e.target.value)}
                placeholder="例: wechat_official_account"
                className="w-full px-2 py-1 text-xs rounded focus:outline-none"
                style={{
                  background: 'var(--bg-input)',
                  border: '1px solid var(--border-subtle)',
                  color: 'var(--text-primary)',
                }}
              />
            </div>
            <div>
              <label className="block text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>
                描述 (可选)
              </label>
              <input
                type="text"
                value={feedDesc}
                onChange={(e) => setFeedDesc(e.target.value)}
                placeholder="例: 财经新闻快讯"
                className="w-full px-2 py-1 text-xs rounded focus:outline-none"
                style={{
                  background: 'var(--bg-input)',
                  border: '1px solid var(--border-subtle)',
                  color: 'var(--text-primary)',
                }}
              />
            </div>
            <div>
              <label className="block text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>
                URL (可选)
              </label>
              <input
                type="url"
                value={feedUrl}
                onChange={(e) => setFeedUrl(e.target.value)}
                placeholder="例: https://example.com/feed"
                className="w-full px-2 py-1 text-xs rounded focus:outline-none"
                style={{
                  background: 'var(--bg-input)',
                  border: '1px solid var(--border-subtle)',
                  color: 'var(--text-primary)',
                }}
              />
            </div>
            <div className="flex gap-2 pt-2">
              <button
                type="submit"
                disabled={addMutation.isPending}
                className="flex-1 px-3 py-1.5 text-xs rounded disabled:opacity-50"
                style={{
                  border: '1px solid var(--border-subtle)',
                  background: 'var(--bg-surface)',
                  color: 'var(--up)',
                }}
              >
                {addMutation.isPending ? '添加中...' : '确认添加'}
              </button>
            </div>
          </form>
        </div>
      )}

      {isLoading && (
        <div className="text-sm py-4 text-center" style={{ color: 'var(--text-muted)' }}>加载中...</div>
      )}
      {error && (
        <div className="text-sm py-4 text-center" style={{ color: 'var(--down)' }}>
          加载失败，请确认已登录管理员账号
        </div>
      )}

      {feeds && feeds.length > 0 && (
        <div
          className="rounded-lg overflow-hidden"
          style={{ border: '1px solid var(--border-subtle)' }}
        >
          <table className="w-full text-xs">
            <thead>
              <tr style={{ background: 'var(--bg-panel)', borderBottom: '1px solid var(--border-subtle)' }}>
                <th className="text-left px-3 py-2 font-medium" style={{ color: 'var(--text-muted)' }}>公众号名称</th>
                <th className="text-left px-3 py-2 font-medium" style={{ color: 'var(--text-muted)' }}>ID</th>
                <th className="text-center px-3 py-2 font-medium w-20" style={{ color: 'var(--text-muted)' }}>今日文章</th>
                <th className="text-left px-3 py-2 font-medium w-32" style={{ color: 'var(--text-muted)' }}>描述</th>
                <th className="text-right px-3 py-2 font-medium w-24" style={{ color: 'var(--text-muted)' }}>操作</th>
              </tr>
            </thead>
            <tbody>
              {feeds.map((feed) => {
                const articleCount = articleCountMap.get(feed.feed_id) ?? 0;
                return (
                  <tr
                    key={feed.feed_id}
                    style={{ borderTop: '1px solid var(--border-subtle)' }}
                  >
                    <td className="px-3 py-2 font-medium" style={{ color: 'var(--text-primary)' }}>{feed.name}</td>
                    <td className="px-3 py-2 font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>{feed.feed_id}</td>
                    <td className="px-3 py-2 text-center">
                      <span
                        className="text-xs font-medium"
                        style={{ color: articleCount > 0 ? 'var(--up)' : 'var(--text-muted)' }}
                      >
                        {articleCount}
                      </span>
                    </td>
                    <td
                      className="px-3 py-2 truncate max-w-xs"
                      style={{ color: 'var(--text-secondary)' }}
                      title={feed.description}
                    >
                      {feed.description || '-'}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button
                        onClick={() => handleDeleteFeed(feed.feed_id)}
                        disabled={deleteMutation.isPending}
                        className="text-xs px-2 py-1 rounded disabled:opacity-50"
                        style={{
                          border: '1px solid var(--down-soft)',
                          background: 'var(--bg-surface)',
                          color: 'var(--down)',
                        }}
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
        <div className="text-sm py-8 text-center" style={{ color: 'var(--text-muted)' }}>暂无订阅的公众号</div>
      )}
    </div>
  );
}
