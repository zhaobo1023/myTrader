'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { themePoolApi } from '@/lib/api-client';
import { CreateThemeDialog } from '@/components/theme-pool/CreateThemeDialog';

// ---------------------------------------------------------------------------
// Status helpers
// ---------------------------------------------------------------------------

const STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  active: '已上线',
  archived: '已归档',
};

const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  draft: { bg: '#f3f4f6', text: '#6b7280' },
  active: { bg: '#dcfce7', text: '#16a34a' },
  archived: { bg: '#fef3c7', text: '#d97706' },
};

function StatusBadge({ status }: { status: string }) {
  const c = STATUS_COLORS[status] || STATUS_COLORS.draft;
  return (
    <span style={{
      display: 'inline-block', padding: '2px 8px', borderRadius: '4px',
      fontSize: '11px', fontWeight: 500, background: c.bg, color: c.text,
    }}>
      {STATUS_LABELS[status] || status}
    </span>
  );
}

// ---------------------------------------------------------------------------
// ThemePoolContent
// ---------------------------------------------------------------------------

export default function ThemePoolContent() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [showCreateDialog, setShowCreateDialog] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['theme-pools', statusFilter],
    queryFn: () => themePoolApi.listThemes(statusFilter || undefined).then((r) => r.data),
  });

  const themes = data?.items || [];
  const tabs = ['', 'active', 'draft', 'archived'];
  const tabLabels: Record<string, string> = { '': '全部', active: '已上线', draft: '草稿', archived: '已归档' };

  return (
    <>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)' }}>主题票池</h2>
          <p style={{ margin: '4px 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
            多人协同主题选股，量化打分增强
          </p>
        </div>
        <button
          data-track="theme_create_open"
          onClick={() => setShowCreateDialog(true)}
          style={{
            padding: '7px 16px', borderRadius: '6px', fontSize: '12px', fontWeight: 500,
            border: 'none', background: 'var(--accent)', color: '#fff', cursor: 'pointer',
          }}
        >
          + 创建主题
        </button>
      </div>

      {/* Status tabs */}
      <div style={{ display: 'flex', gap: '4px', marginBottom: '16px' }}>
        {tabs.map((t) => (
          <button
            key={t}
            onClick={() => setStatusFilter(t)}
            style={{
              padding: '5px 12px', borderRadius: '6px', fontSize: '12px',
              border: 'none', cursor: 'pointer',
              background: statusFilter === t ? 'var(--bg-nav-active)' : 'transparent',
              color: statusFilter === t ? 'var(--text-primary)' : 'var(--text-tertiary)',
              fontWeight: statusFilter === t ? 510 : 400,
            }}
          >
            {tabLabels[t]}
          </button>
        ))}
      </div>

      {/* Theme cards */}
      {isLoading ? (
        <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
          加载中...
        </div>
      ) : themes.length === 0 ? (
        <div style={{ padding: '40px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
          暂无主题，点击右上角创建一个
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '12px' }}>
          {themes.map((theme) => (
            <div
              key={theme.id}
              onClick={() => router.push(`/theme-pool/${theme.id}`)}
              style={{
                padding: '16px', borderRadius: '8px', cursor: 'pointer',
                border: '1px solid var(--border-subtle)', background: 'var(--bg-panel)',
                transition: 'border-color 0.12s',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--accent)';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLDivElement).style.borderColor = 'var(--border-subtle)';
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                <span style={{ fontSize: '14px', fontWeight: 560, color: 'var(--text-primary)' }}>{theme.name}</span>
                <StatusBadge status={theme.status} />
              </div>
              {theme.description && (
                <p style={{
                  margin: '0 0 10px', fontSize: '12px', color: 'var(--text-secondary)',
                  overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {theme.description}
                </p>
              )}
              <div style={{ display: 'flex', gap: '16px', fontSize: '11px', color: 'var(--text-muted)' }}>
                <span>{theme.stock_count} 只股票</span>
                <span>创建人: {theme.creator_email?.split('@')[0] || '未知'}</span>
                <span>{new Date(theme.created_at).toLocaleDateString()}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Unified create theme dialog */}
      <CreateThemeDialog
        open={showCreateDialog}
        onClose={() => setShowCreateDialog(false)}
        onCreated={async (themeName, description, stocks) => {
          const res = await themePoolApi.createTheme(themeName, description || undefined);
          const themeId: number = res.data.id;
          if (stocks.length > 0) {
            await themePoolApi.batchAddStocks(themeId, stocks.map(s => ({
              stock_code: s.stock_code,
              stock_name: s.stock_name,
              reason: s.reason,
            })));
          }
          queryClient.invalidateQueries({ queryKey: ['theme-pools'] });
          setShowCreateDialog(false);
          router.push(`/theme-pool/${themeId}`);
        }}
      />
    </>
  );
}
