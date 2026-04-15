'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import AppShell from '@/components/layout/AppShell';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { themePoolApi, ThemePoolItem } from '@/lib/api-client';
import { LLMCreateDialog, CandidateStock } from '@/components/theme-pool/LLMCreateDialog';

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
// Create Theme Modal
// ---------------------------------------------------------------------------

function CreateModal({ open, onClose, onCreate }: {
  open: boolean;
  onClose: () => void;
  onCreate: (name: string, desc: string) => void;
}) {
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');

  if (!open) return null;

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }} onClick={onClose}>
      <div style={{
        background: 'var(--bg-panel)', borderRadius: '10px', padding: '24px',
        width: '420px', maxWidth: '90vw',
      }} onClick={(e) => e.stopPropagation()}>
        <h3 style={{ margin: '0 0 16px', fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
          新建主题票池
        </h3>
        <div style={{ marginBottom: '12px' }}>
          <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px' }}>
            主题名称 *
          </label>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="如: AI算力 / 消费复苏 / 高股息"
            style={{
              width: '100%', padding: '8px 10px', borderRadius: '6px', fontSize: '13px',
              border: '1px solid var(--border-subtle)', background: 'var(--bg-canvas)',
              color: 'var(--text-primary)', outline: 'none', boxSizing: 'border-box',
            }}
          />
        </div>
        <div style={{ marginBottom: '20px' }}>
          <label style={{ display: 'block', fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '4px' }}>
            主题描述
          </label>
          <textarea
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            rows={3}
            placeholder="选股逻辑、投资主线..."
            style={{
              width: '100%', padding: '8px 10px', borderRadius: '6px', fontSize: '13px',
              border: '1px solid var(--border-subtle)', background: 'var(--bg-canvas)',
              color: 'var(--text-primary)', outline: 'none', resize: 'vertical', boxSizing: 'border-box',
            }}
          />
        </div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
          <button
            onClick={onClose}
            style={{
              padding: '7px 14px', borderRadius: '6px', fontSize: '12px',
              border: '1px solid var(--border-subtle)', background: 'transparent',
              color: 'var(--text-secondary)', cursor: 'pointer',
            }}
          >
            取消
          </button>
          <button
            onClick={() => { if (name.trim()) { onCreate(name.trim(), desc.trim()); setName(''); setDesc(''); } }}
            disabled={!name.trim()}
            style={{
              padding: '7px 14px', borderRadius: '6px', fontSize: '12px',
              border: 'none', background: 'var(--accent)', color: '#fff',
              cursor: name.trim() ? 'pointer' : 'not-allowed', opacity: name.trim() ? 1 : 0.5,
            }}
          >
            创建
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ThemePoolPage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [showCreate, setShowCreate] = useState(false);
  const [showLLMCreate, setShowLLMCreate] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['theme-pools', statusFilter],
    queryFn: () => themePoolApi.listThemes(statusFilter || undefined).then((r) => r.data),
  });

  const createMut = useMutation({
    mutationFn: ({ name, desc }: { name: string; desc: string }) =>
      themePoolApi.createTheme(name, desc || undefined),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['theme-pools'] });
      setShowCreate(false);
    },
  });

  const themes = data?.items || [];
  const tabs = ['', 'active', 'draft', 'archived'];
  const tabLabels: Record<string, string> = { '': '全部', active: '已上线', draft: '草稿', archived: '已归档' };

  return (
    <AppShell>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)' }}>主题票池</h1>
          <p style={{ margin: '4px 0 0', fontSize: '12px', color: 'var(--text-muted)' }}>
            多人协同主题选股，量化打分增强
          </p>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            data-track="theme_llm_create_open"
            onClick={() => setShowLLMCreate(true)}
            style={{
              padding: '7px 16px', borderRadius: '6px', fontSize: '12px', fontWeight: 500,
              border: '1px solid var(--accent)', background: 'transparent', color: 'var(--accent)', cursor: 'pointer',
            }}
          >
            AI 创建
          </button>
          <button
            data-track="theme_create_open"
            onClick={() => setShowCreate(true)}
            style={{
              padding: '7px 16px', borderRadius: '6px', fontSize: '12px', fontWeight: 500,
              border: 'none', background: 'var(--accent)', color: '#fff', cursor: 'pointer',
            }}
          >
            + 新建主题
          </button>
        </div>
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

      {/* Create modal */}
      <CreateModal
        open={showCreate}
        onClose={() => setShowCreate(false)}
        onCreate={(name, desc) => createMut.mutate({ name, desc })}
      />

      {/* LLM AI create dialog */}
      <LLMCreateDialog
        open={showLLMCreate}
        onClose={() => setShowLLMCreate(false)}
        onCreated={async (themeName, stocks) => {
          // 1. create theme
          const res = await themePoolApi.createTheme(themeName);
          const themeId: number = res.data.id;
          // 2. batch add selected stocks
          await themePoolApi.batchAddStocks(themeId, stocks.map(s => ({
            stock_code: s.stock_code,
            stock_name: s.stock_name,
            reason: s.reason,
          })));
          queryClient.invalidateQueries({ queryKey: ['theme-pools'] });
          setShowLLMCreate(false);
          router.push(`/theme-pool/${themeId}`);
        }}
      />
    </AppShell>
  );
}
