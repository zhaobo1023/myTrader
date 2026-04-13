'use client';

import React, { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import AppShell from '@/components/layout/AppShell';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  themePoolApi, marketApi,
  ThemePoolItem, ThemeStockItem, StockSearchResult,
} from '@/lib/api-client';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function pct(v: number | null | undefined): string {
  if (v == null) return '-';
  return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`;
}

function score(v: number | null | undefined): string {
  if (v == null) return '-';
  return v.toFixed(0);
}

function returnColor(v: number | null | undefined): string {
  if (v == null) return 'var(--text-muted)';
  return v >= 0 ? '#16a34a' : '#ef4444';
}

const STATUS_LABELS: Record<string, string> = {
  draft: '草稿', active: '已上线', archived: '已归档',
};
const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  draft: { bg: '#f3f4f6', text: '#6b7280' },
  active: { bg: '#dcfce7', text: '#16a34a' },
  archived: { bg: '#fef3c7', text: '#d97706' },
};
const HUMAN_STATUS_LABELS: Record<string, string> = {
  normal: '普通', focused: '重点关注', watching: '观察', excluded: '已剔除',
};
const HUMAN_STATUS_COLORS: Record<string, string> = {
  normal: 'var(--text-muted)', focused: '#3b82f6', watching: '#f59e0b', excluded: '#9ca3af',
};
const FILTER_LABELS: Record<string, string> = {
  '': '全部', focused: '重点关注', watching: '观察', normal: '普通', excluded: '已剔除',
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
// Add Stock Component
// ---------------------------------------------------------------------------

function AddStockSection({ themeId, onAdded }: { themeId: number; onAdded: () => void }) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<StockSearchResult[]>([]);
  const [reason, setReason] = useState('');
  const [selected, setSelected] = useState<StockSearchResult | null>(null);
  const [searching, setSearching] = useState(false);

  const addMut = useMutation({
    mutationFn: (s: StockSearchResult) =>
      themePoolApi.addStock(themeId, s.stock_code, s.stock_name, reason || undefined),
    onSuccess: () => {
      setSelected(null);
      setQuery('');
      setReason('');
      setResults([]);
      onAdded();
    },
  });

  async function doSearch(q: string) {
    setQuery(q);
    if (q.length < 2) { setResults([]); return; }
    setSearching(true);
    try {
      const res = await marketApi.search(q);
      const list = Array.isArray(res.data) ? res.data : (res.data as any).data || [];
      setResults(list.slice(0, 8));
    } catch { setResults([]); }
    setSearching(false);
  }

  return (
    <div style={{
      padding: '12px 16px', borderRadius: '8px', marginBottom: '16px',
      border: '1px solid var(--border-subtle)', background: 'var(--bg-panel)',
    }}>
      <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-start' }}>
        <div style={{ flex: 1, position: 'relative' }}>
          <input
            value={query}
            onChange={(e) => doSearch(e.target.value)}
            placeholder="输入股票代码或名称搜索..."
            style={{
              width: '100%', padding: '7px 10px', borderRadius: '6px', fontSize: '12px',
              border: '1px solid var(--border-subtle)', background: 'var(--bg-canvas)',
              color: 'var(--text-primary)', outline: 'none', boxSizing: 'border-box',
            }}
          />
          {results.length > 0 && !selected && (
            <div style={{
              position: 'absolute', top: '100%', left: 0, right: 0, zIndex: 10,
              background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)',
              borderRadius: '6px', marginTop: '4px', maxHeight: '200px', overflowY: 'auto',
            }}>
              {results.map((r) => (
                <div
                  key={r.stock_code}
                  onClick={() => { setSelected(r); setQuery(`${r.stock_code} ${r.stock_name}`); setResults([]); }}
                  style={{
                    padding: '6px 10px', fontSize: '12px', cursor: 'pointer',
                    color: 'var(--text-primary)',
                  }}
                  onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-nav-hover)'; }}
                  onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = 'transparent'; }}
                >
                  <span style={{ fontWeight: 500 }}>{r.stock_code}</span>
                  <span style={{ marginLeft: '8px', color: 'var(--text-secondary)' }}>{r.stock_name}</span>
                </div>
              ))}
            </div>
          )}
        </div>
        <input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="推荐理由（选填）"
          style={{
            width: '200px', padding: '7px 10px', borderRadius: '6px', fontSize: '12px',
            border: '1px solid var(--border-subtle)', background: 'var(--bg-canvas)',
            color: 'var(--text-primary)', outline: 'none', boxSizing: 'border-box',
          }}
        />
        <button
          onClick={() => selected && addMut.mutate(selected)}
          disabled={!selected || addMut.isPending}
          style={{
            padding: '7px 14px', borderRadius: '6px', fontSize: '12px', fontWeight: 500,
            border: 'none', background: 'var(--accent)', color: '#fff',
            cursor: selected ? 'pointer' : 'not-allowed', opacity: selected ? 1 : 0.5,
            whiteSpace: 'nowrap',
          }}
        >
          + 添加
        </button>
      </div>
      {addMut.isError && (
        <div style={{ marginTop: '6px', fontSize: '11px', color: '#ef4444' }}>
          {(addMut.error as Error)?.message || '添加失败'}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Vote Button
// ---------------------------------------------------------------------------

function VoteButton({ stockId, upVotes, downVotes, myVote, onVoted }: {
  stockId: number;
  upVotes: number;
  downVotes: number;
  myVote: number | null;
  onVoted: () => void;
}) {
  const voteMut = useMutation({
    mutationFn: (v: number) => themePoolApi.vote(stockId, v),
    onSuccess: onVoted,
  });
  const unvoteMut = useMutation({
    mutationFn: () => themePoolApi.removeVote(stockId),
    onSuccess: onVoted,
  });

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
      <button
        onClick={(e) => { e.stopPropagation(); myVote === 1 ? unvoteMut.mutate() : voteMut.mutate(1); }}
        style={{
          padding: '2px 4px', border: 'none', borderRadius: '3px', cursor: 'pointer',
          fontSize: '12px', lineHeight: 1,
          background: myVote === 1 ? '#dcfce7' : 'transparent',
          color: myVote === 1 ? '#16a34a' : 'var(--text-muted)',
        }}
        title="看好"
      >
        +{upVotes}
      </button>
      <button
        onClick={(e) => { e.stopPropagation(); myVote === -1 ? unvoteMut.mutate() : voteMut.mutate(-1); }}
        style={{
          padding: '2px 4px', border: 'none', borderRadius: '3px', cursor: 'pointer',
          fontSize: '12px', lineHeight: 1,
          background: myVote === -1 ? '#fee2e2' : 'transparent',
          color: myVote === -1 ? '#ef4444' : 'var(--text-muted)',
        }}
        title="看空"
      >
        -{downVotes}
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Human Status Dropdown
// ---------------------------------------------------------------------------

function HumanStatusSelect({ stockId, current, onChanged }: {
  stockId: number; current: string; onChanged: () => void;
}) {
  const mut = useMutation({
    mutationFn: (s: string) => themePoolApi.updateHumanStatus(stockId, s),
    onSuccess: onChanged,
  });

  return (
    <select
      value={current}
      onChange={(e) => mut.mutate(e.target.value)}
      onClick={(e) => e.stopPropagation()}
      style={{
        padding: '2px 4px', borderRadius: '4px', fontSize: '11px',
        border: '1px solid var(--border-subtle)', background: 'var(--bg-canvas)',
        color: HUMAN_STATUS_COLORS[current] || 'var(--text-muted)',
        cursor: 'pointer', outline: 'none',
      }}
    >
      {Object.entries(HUMAN_STATUS_LABELS).map(([k, v]) => (
        <option key={k} value={k}>{v}</option>
      ))}
    </select>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function ThemeDetailPage() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const themeId = Number(params.themeId);

  const [statusFilter, setStatusFilter] = useState('');
  const [sortBy, setSortBy] = useState('total_score');
  const [editNote, setEditNote] = useState<{ id: number; note: string } | null>(null);

  // Fetch theme detail
  const { data: theme } = useQuery({
    queryKey: ['theme', themeId],
    queryFn: () => themePoolApi.getTheme(themeId).then((r) => r.data),
  });

  // Fetch stocks
  const { data: stocksData, isLoading: stocksLoading } = useQuery({
    queryKey: ['theme-stocks', themeId, statusFilter, sortBy],
    queryFn: () => themePoolApi.listStocks(themeId, {
      human_status: statusFilter || undefined,
      sort_by: sortBy,
    }).then((r) => r.data),
  });

  const stocks = stocksData?.items || [];

  // Status change mutation
  const statusMut = useMutation({
    mutationFn: (s: string) => themePoolApi.changeStatus(themeId, s),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['theme', themeId] }),
  });

  // Score trigger mutation
  const [scoreMsg, setScoreMsg] = useState<string | null>(null);
  const scoreMut = useMutation({
    mutationFn: () => themePoolApi.triggerScore(themeId),
    onSuccess: () => {
      setScoreMsg('评分计算已启动，请稍后刷新');
      setTimeout(() => { setScoreMsg(null); refetchStocks(); }, 5000);
    },
  });

  // Delete mutation
  const deleteMut = useMutation({
    mutationFn: () => themePoolApi.deleteTheme(themeId),
    onSuccess: () => router.push('/theme-pool'),
  });

  // Remove stock mutation
  const removeMut = useMutation({
    mutationFn: (code: string) => themePoolApi.removeStock(themeId, code),
    onSuccess: () => refetchStocks(),
  });

  // Note mutation
  const noteMut = useMutation({
    mutationFn: ({ id, note }: { id: number; note: string }) => themePoolApi.updateNote(id, note),
    onSuccess: () => { setEditNote(null); refetchStocks(); },
  });

  function refetchStocks() {
    queryClient.invalidateQueries({ queryKey: ['theme-stocks', themeId] });
  }

  const nextStatus = theme?.status === 'draft' ? 'active' : theme?.status === 'active' ? 'archived' : 'active';
  const nextStatusLabel = theme?.status === 'draft' ? '上线' : theme?.status === 'active' ? '归档' : '重新上线';

  // Table headers
  const columns = [
    { key: 'stock', label: '股票', width: '130px' },
    { key: 'recommender', label: '推荐人', width: '80px' },
    { key: 'reason', label: '推荐理由', width: '120px' },
    { key: 'rps_20', label: 'RPS20', width: '55px' },
    { key: 'tech', label: '技术面', width: '50px' },
    { key: 'fund', label: '基本面', width: '50px' },
    { key: 'total', label: '综合', width: '50px' },
    { key: 'return_5d', label: '5日%', width: '55px' },
    { key: 'return_20d', label: '20日%', width: '55px' },
    { key: 'votes', label: '投票', width: '70px' },
    { key: 'status', label: '标记', width: '85px' },
    { key: 'actions', label: '', width: '60px' },
  ];

  return (
    <AppShell>
      {/* Header */}
      <div style={{ marginBottom: '16px' }}>
        <button
          onClick={() => router.push('/theme-pool')}
          style={{
            background: 'none', border: 'none', cursor: 'pointer', padding: 0,
            fontSize: '12px', color: 'var(--text-muted)', marginBottom: '8px', display: 'block',
          }}
        >
          &larr; 返回主题列表
        </button>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <h1 style={{ margin: 0, fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)' }}>
            {theme?.name || '...'}
          </h1>
          {theme && <StatusBadge status={theme.status} />}
          <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            {theme?.stock_count || 0} 只股票
          </span>
          <div style={{ flex: 1 }} />
          {theme && (
            <>
              <button
                onClick={() => scoreMut.mutate()}
                disabled={scoreMut.isPending}
                style={{
                  padding: '5px 12px', borderRadius: '6px', fontSize: '11px',
                  border: '1px solid var(--border-subtle)', background: 'transparent',
                  color: 'var(--accent)', cursor: scoreMut.isPending ? 'not-allowed' : 'pointer',
                  opacity: scoreMut.isPending ? 0.6 : 1,
                }}
              >
                {scoreMut.isPending ? '计算中...' : '计算评分'}
              </button>
              <button
                onClick={() => statusMut.mutate(nextStatus)}
                disabled={statusMut.isPending}
                style={{
                  padding: '5px 12px', borderRadius: '6px', fontSize: '11px',
                  border: '1px solid var(--border-subtle)', background: 'transparent',
                  color: 'var(--text-secondary)', cursor: 'pointer',
                }}
              >
                {nextStatusLabel}
              </button>
              {theme.status === 'draft' && (
                <button
                  onClick={() => { if (confirm('确定删除这个草稿主题?')) deleteMut.mutate(); }}
                  style={{
                    padding: '5px 12px', borderRadius: '6px', fontSize: '11px',
                    border: '1px solid #fecaca', background: 'transparent',
                    color: '#ef4444', cursor: 'pointer',
                  }}
                >
                  删除
                </button>
              )}
            </>
          )}
        </div>
        {theme?.description && (
          <p style={{ margin: '6px 0 0', fontSize: '12px', color: 'var(--text-secondary)' }}>
            {theme.description}
          </p>
        )}
      </div>

      {/* Status/Score messages */}
      {statusMut.isError && (
        <div style={{ marginBottom: '8px', padding: '8px 12px', borderRadius: '6px', background: '#fef2f2', color: '#ef4444', fontSize: '12px' }}>
          {(statusMut.error as any)?.response?.data?.detail || '状态变更失败'}
        </div>
      )}
      {scoreMsg && (
        <div style={{ marginBottom: '8px', padding: '8px 12px', borderRadius: '6px', background: '#f0fdf4', color: '#16a34a', fontSize: '12px' }}>
          {scoreMsg}
        </div>
      )}
      {scoreMut.isError && (
        <div style={{ marginBottom: '8px', padding: '8px 12px', borderRadius: '6px', background: '#fef2f2', color: '#ef4444', fontSize: '12px' }}>
          {(scoreMut.error as any)?.response?.data?.detail || '评分触发失败'}
        </div>
      )}

      {/* Add stock */}
      <AddStockSection themeId={themeId} onAdded={refetchStocks} />

      {/* Filters */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '12px', alignItems: 'center' }}>
        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>筛选:</span>
        {['', 'focused', 'watching', 'normal', 'excluded'].map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            style={{
              padding: '3px 8px', borderRadius: '4px', fontSize: '11px',
              border: 'none', cursor: 'pointer',
              background: statusFilter === s ? 'var(--bg-nav-active)' : 'transparent',
              color: statusFilter === s ? 'var(--text-primary)' : 'var(--text-tertiary)',
            }}
          >
            {FILTER_LABELS[s]}
          </button>
        ))}
        <div style={{ flex: 1 }} />
        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>排序:</span>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
          style={{
            padding: '3px 8px', borderRadius: '4px', fontSize: '11px',
            border: '1px solid var(--border-subtle)', background: 'var(--bg-canvas)',
            color: 'var(--text-secondary)', outline: 'none',
          }}
        >
          <option value="total_score">综合评分</option>
          <option value="rps_20">RPS 20日</option>
          <option value="return_5d">5日涨跌幅</option>
          <option value="return_20d">20日涨跌幅</option>
          <option value="added_at">添加时间</option>
        </select>
      </div>

      {/* Stock table */}
      <div style={{ overflowX: 'auto' }}>
        <table style={{
          width: '100%', borderCollapse: 'collapse', fontSize: '12px',
        }}>
          <thead>
            <tr>
              {columns.map((col) => (
                <th
                  key={col.key}
                  style={{
                    padding: '8px 6px', textAlign: 'left', fontWeight: 500,
                    color: 'var(--text-muted)', borderBottom: '1px solid var(--border-subtle)',
                    width: col.width, whiteSpace: 'nowrap', fontSize: '11px',
                  }}
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {stocksLoading ? (
              <tr><td colSpan={columns.length} style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>加载中...</td></tr>
            ) : stocks.length === 0 ? (
              <tr><td colSpan={columns.length} style={{ padding: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>暂无股票，请在上方搜索添加</td></tr>
            ) : (
              stocks.map((s) => {
                const sc = s.latest_score;
                const isExcluded = s.human_status === 'excluded';
                return (
                  <tr
                    key={s.id}
                    style={{
                      borderBottom: '1px solid var(--border-subtle)',
                      opacity: isExcluded ? 0.45 : 1,
                    }}
                  >
                    {/* Stock */}
                    <td style={{ padding: '8px 6px' }}>
                      <div style={{ fontWeight: 510, color: 'var(--text-primary)' }}>{s.stock_code}</div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{s.stock_name}</div>
                    </td>
                    {/* Recommender */}
                    <td style={{ padding: '8px 6px', color: 'var(--text-secondary)' }}>
                      {s.recommender_email?.split('@')[0] || '-'}
                    </td>
                    {/* Reason */}
                    <td style={{ padding: '8px 6px', color: 'var(--text-secondary)', maxWidth: '120px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}
                      title={s.reason || ''}
                    >
                      {s.reason || '-'}
                    </td>
                    {/* RPS */}
                    <td style={{ padding: '8px 6px', color: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>
                      {score(sc?.rps_20)}
                    </td>
                    {/* Tech */}
                    <td style={{ padding: '8px 6px', color: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>
                      {score(sc?.tech_score)}
                    </td>
                    {/* Fund */}
                    <td style={{ padding: '8px 6px', color: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>
                      {score(sc?.fundamental_score)}
                    </td>
                    {/* Total */}
                    <td style={{ padding: '8px 6px', fontWeight: 600, color: 'var(--text-primary)', fontVariantNumeric: 'tabular-nums' }}>
                      {score(sc?.total_score)}
                    </td>
                    {/* 5D return */}
                    <td style={{ padding: '8px 6px', color: returnColor(sc?.return_5d), fontVariantNumeric: 'tabular-nums' }}>
                      {pct(sc?.return_5d)}
                    </td>
                    {/* 20D return */}
                    <td style={{ padding: '8px 6px', color: returnColor(sc?.return_20d), fontVariantNumeric: 'tabular-nums' }}>
                      {pct(sc?.return_20d)}
                    </td>
                    {/* Votes */}
                    <td style={{ padding: '8px 6px' }}>
                      <VoteButton
                        stockId={s.id}
                        upVotes={s.up_votes}
                        downVotes={s.down_votes}
                        myVote={s.my_vote}
                        onVoted={refetchStocks}
                      />
                    </td>
                    {/* Human status */}
                    <td style={{ padding: '8px 6px' }}>
                      <HumanStatusSelect stockId={s.id} current={s.human_status} onChanged={refetchStocks} />
                    </td>
                    {/* Actions */}
                    <td style={{ padding: '8px 6px' }}>
                      <div style={{ display: 'flex', gap: '4px' }}>
                        <button
                          onClick={(e) => { e.stopPropagation(); setEditNote({ id: s.id, note: s.note || '' }); }}
                          title="编辑批注"
                          style={{
                            padding: '2px 6px', borderRadius: '3px', border: 'none',
                            background: 'transparent', color: 'var(--text-muted)',
                            cursor: 'pointer', fontSize: '11px',
                          }}
                        >
                          批注
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            if (confirm(`确定移除 ${s.stock_code}?`)) removeMut.mutate(s.stock_code);
                          }}
                          title="移除"
                          style={{
                            padding: '2px 6px', borderRadius: '3px', border: 'none',
                            background: 'transparent', color: '#ef4444',
                            cursor: 'pointer', fontSize: '11px',
                          }}
                        >
                          x
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Note edit modal */}
      {editNote && (
        <div style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 1000,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }} onClick={() => setEditNote(null)}>
          <div style={{
            background: 'var(--bg-panel)', borderRadius: '10px', padding: '20px',
            width: '400px', maxWidth: '90vw',
          }} onClick={(e) => e.stopPropagation()}>
            <h4 style={{ margin: '0 0 12px', fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>
              编辑批注
            </h4>
            <textarea
              value={editNote.note}
              onChange={(e) => setEditNote({ ...editNote, note: e.target.value })}
              rows={4}
              style={{
                width: '100%', padding: '8px 10px', borderRadius: '6px', fontSize: '12px',
                border: '1px solid var(--border-subtle)', background: 'var(--bg-canvas)',
                color: 'var(--text-primary)', outline: 'none', resize: 'vertical', boxSizing: 'border-box',
              }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '12px' }}>
              <button
                onClick={() => setEditNote(null)}
                style={{
                  padding: '6px 12px', borderRadius: '6px', fontSize: '11px',
                  border: '1px solid var(--border-subtle)', background: 'transparent',
                  color: 'var(--text-secondary)', cursor: 'pointer',
                }}
              >
                取消
              </button>
              <button
                onClick={() => noteMut.mutate({ id: editNote.id, note: editNote.note })}
                style={{
                  padding: '6px 12px', borderRadius: '6px', fontSize: '11px',
                  border: 'none', background: 'var(--accent)', color: '#fff', cursor: 'pointer',
                }}
              >
                保存
              </button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
