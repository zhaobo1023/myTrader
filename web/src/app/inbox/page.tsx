'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import AppShell from '@/components/layout/AppShell';
import { inboxApi, InboxMessageItem } from '@/lib/api-client';

const TYPE_LABELS: Record<string, string> = {
  daily_report: '日报',
  alert: '预警',
  system: '系统',
  strategy_signal: '信号',
};

const TYPE_COLORS: Record<string, string> = {
  daily_report: 'var(--accent)',
  alert: 'var(--amber)',
  system: 'var(--text-muted)',
  strategy_signal: 'var(--green)',
};

export default function InboxPage() {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [filterType, setFilterType] = useState<string | undefined>(undefined);
  const [page, setPage] = useState(1);

  const { data: listData, isLoading } = useQuery({
    queryKey: ['inbox', filterType, page],
    queryFn: () => inboxApi.list({ message_type: filterType, page, page_size: 20 }).then(r => r.data),
  });

  const { data: detail } = useQuery({
    queryKey: ['inbox-detail', selectedId],
    queryFn: () => selectedId ? inboxApi.get(selectedId).then(r => r.data) : null,
    enabled: !!selectedId,
  });

  const markAllMut = useMutation({
    mutationFn: () => inboxApi.markAllRead(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['inbox'] }),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => inboxApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['inbox'] });
      if (selectedId === deleteMut.variables) setSelectedId(null);
    },
  });

  const items = listData?.items || [];
  const total = listData?.total || 0;
  const unreadCount = listData?.unread_count || 0;
  const totalPages = Math.ceil(total / 20);

  const filterTabs = [
    { key: undefined, label: '全部' },
    { key: 'daily_report', label: '日报' },
    { key: 'alert', label: '预警' },
    { key: 'system', label: '系统' },
    { key: 'strategy_signal', label: '信号' },
  ];

  const cardStyle: React.CSSProperties = {
    background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)', borderRadius: '8px', overflow: 'hidden',
  };

  return (
    <AppShell>
      <div style={{ maxWidth: '1100px', margin: '0 auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
          <h1 style={{ fontSize: '20px', fontWeight: 600, color: 'var(--text-primary)' }}>
            信箱 {unreadCount > 0 && <span style={{ fontSize: '13px', color: 'var(--accent)', fontWeight: 400 }}>({unreadCount} 未读)</span>}
          </h1>
          {unreadCount > 0 && (
            <button onClick={() => markAllMut.mutate()} style={{ padding: '4px 12px', fontSize: '12px', background: 'var(--bg-canvas)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)', borderRadius: '6px', cursor: 'pointer' }}>
              全部已读
            </button>
          )}
        </div>

        {/* Filter tabs */}
        <div style={{ display: 'flex', gap: '4px', marginBottom: '16px' }}>
          {filterTabs.map(tab => (
            <button
              key={tab.key ?? 'all'}
              onClick={() => { setFilterType(tab.key); setPage(1); setSelectedId(null); }}
              style={{
                padding: '4px 12px', fontSize: '12px', borderRadius: '12px', cursor: 'pointer', border: 'none',
                background: filterType === tab.key ? 'var(--accent)' : 'var(--bg-canvas)',
                color: filterType === tab.key ? '#fff' : 'var(--text-secondary)',
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: selectedId ? '360px 1fr' : '1fr', gap: '16px' }}>
          {/* Message list */}
          <div style={cardStyle}>
            {isLoading && <div style={{ padding: '20px', color: 'var(--text-muted)', fontSize: '13px' }}>加载中...</div>}
            {items.map(msg => (
              <div
                key={msg.id}
                onClick={() => { setSelectedId(msg.id); queryClient.invalidateQueries({ queryKey: ['inbox', filterType, page] }); }}
                style={{
                  padding: '12px 16px', cursor: 'pointer', borderBottom: '1px solid var(--border-subtle)',
                  background: selectedId === msg.id ? 'var(--bg-canvas)' : 'transparent',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
                  {!msg.is_read && <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--accent)', flexShrink: 0 }} />}
                  <span style={{ fontSize: '11px', padding: '1px 6px', borderRadius: '3px', background: `${TYPE_COLORS[msg.message_type] || 'var(--text-muted)'}20`, color: TYPE_COLORS[msg.message_type] || 'var(--text-muted)' }}>
                    {TYPE_LABELS[msg.message_type] || msg.message_type}
                  </span>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginLeft: 'auto' }}>
                    {msg.created_at.slice(0, 10)}
                  </span>
                </div>
                <div style={{ fontSize: '13px', color: msg.is_read ? 'var(--text-secondary)' : 'var(--text-primary)', fontWeight: msg.is_read ? 400 : 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {msg.title}
                </div>
              </div>
            ))}
            {!isLoading && items.length === 0 && (
              <div style={{ padding: '40px 20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>暂无消息</div>
            )}
            {/* Pagination */}
            {totalPages > 1 && (
              <div style={{ display: 'flex', justifyContent: 'center', gap: '8px', padding: '12px' }}>
                <button disabled={page <= 1} onClick={() => setPage(p => p - 1)} style={{ fontSize: '12px', padding: '2px 8px', cursor: 'pointer', border: '1px solid var(--border-subtle)', borderRadius: '4px', background: 'var(--bg-panel)' }}>上一页</button>
                <span style={{ fontSize: '12px', color: 'var(--text-muted)', lineHeight: '24px' }}>{page}/{totalPages}</span>
                <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)} style={{ fontSize: '12px', padding: '2px 8px', cursor: 'pointer', border: '1px solid var(--border-subtle)', borderRadius: '4px', background: 'var(--bg-panel)' }}>下一页</button>
              </div>
            )}
          </div>

          {/* Message detail */}
          {selectedId && (
            <div style={{ ...cardStyle, padding: '20px' }}>
              {detail ? (
                <>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                    <h2 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)' }}>{detail.title}</h2>
                    <button
                      onClick={() => { if (confirm('确认删除?')) deleteMut.mutate(detail.id); }}
                      style={{ fontSize: '12px', color: 'var(--red)', background: 'none', border: 'none', cursor: 'pointer' }}
                    >
                      删除
                    </button>
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '16px' }}>
                    {TYPE_LABELS[detail.message_type] || detail.message_type} | {detail.created_at.replace('T', ' ').slice(0, 19)}
                  </div>
                  <div style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: '1.7', whiteSpace: 'pre-wrap' }}>
                    {detail.content || '(无内容)'}
                  </div>
                </>
              ) : (
                <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>加载中...</div>
              )}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
