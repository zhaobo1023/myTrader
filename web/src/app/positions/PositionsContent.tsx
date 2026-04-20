'use client';

import { useState, useCallback } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient, { positionsApi, PositionItem } from '@/lib/api-client';
import { useAddToCandidate } from '@/hooks/useStockAdd';
import StockSearchInput from '@/components/stock/StockSearchInput';
import type { StockSearchResult } from '@/lib/api-client';

const LEVELS = ['L1', 'L2', 'L3'];

// 风控规则标识符 -> 中文描述
const RISK_RULE_LABELS: Record<string, string> = {
  atr_position_scaler: 'ATR仓位过大',
  max_position_pct: '单仓超限',
  max_drawdown: '回撤超限',
  stop_loss: '触及止损',
  stop_profit: '触及止盈',
  concentration: '集中度过高',
  sector_concentration: '行业集中',
  liquidity: '流动性不足',
  price_drop: '价格大跌',
  volume_anomaly: '成交量异常',
  ma_break: '跌破均线',
  rps_weak: 'RPS走弱',
  no_price_data: '无法获取价格',
  data_missing: '数据缺失',
};

function translateAlert(raw: string): string {
  // 去掉前缀 [WARN] / [REJECT]
  const stripped = raw.replace(/^\[(WARN|REJECT|HALT|INFO)\]\s*/i, '').trim();
  // 冒号前是规则key，冒号后是详情
  const colonIdx = stripped.indexOf(':');
  if (colonIdx === -1) {
    // 整段就是规则key
    return RISK_RULE_LABELS[stripped] ?? stripped;
  }
  const key = stripped.slice(0, colonIdx).trim();
  const detail = stripped.slice(colonIdx + 1).trim();
  const label = RISK_RULE_LABELS[key] ?? key;
  return detail ? `${label}：${detail}` : label;
}

type ScanResult = {
  portfolio_summary: Record<string, unknown>;
  stock_alerts: Array<{ stock_code: string; stock_name: string; level: string; alerts: string[] }>;
  portfolio_alerts: string[];
};

function ScanResultPanel({ result, onClose }: { result: ScanResult; onClose: () => void }) {
  const isReject = (level: string) => level === 'REJECT' || level === 'HALT';
  const rejectCount = result.stock_alerts.filter(sa => isReject(sa.level)).length;
  const warnCount = result.stock_alerts.filter(sa => !isReject(sa.level)).length;

  return (
    <div style={{ marginBottom: '16px', borderRadius: '8px', background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', borderBottom: '1px solid var(--border-subtle)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>风控扫描结果</span>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
            {String(result.portfolio_summary?.total_positions ?? '')}只持仓 · {String(result.portfolio_summary?.scan_date ?? '')}
          </span>
          {rejectCount > 0 && (
            <span style={{ fontSize: '11px', padding: '2px 7px', borderRadius: '4px', background: 'rgba(229,83,75,0.1)', color: '#e5534b', fontWeight: 600 }}>
              {rejectCount}只需注意
            </span>
          )}
          {warnCount > 0 && (
            <span style={{ fontSize: '11px', padding: '2px 7px', borderRadius: '4px', background: 'rgba(198,144,38,0.1)', color: '#c69026', fontWeight: 600 }}>
              {warnCount}只有提示
            </span>
          )}
        </div>
        <button onClick={onClose} style={{ fontSize: '12px', color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer', padding: '2px 6px' }}>关闭</button>
      </div>

      {result.portfolio_alerts.length === 0 && result.stock_alerts.length === 0 ? (
        <div style={{ padding: '14px 16px', fontSize: '13px', color: '#27a644' }}>所有持仓通过风控检查，无异常。</div>
      ) : (
        <div style={{ padding: '12px 16px' }}>
          {/* 组合级别告警 */}
          {result.portfolio_alerts.length > 0 && (
            <div style={{ marginBottom: '12px' }}>
              {result.portfolio_alerts.map((a, i) => (
                <div key={i} style={{ fontSize: '13px', color: '#c69026', padding: '6px 10px', background: 'rgba(198,144,38,0.06)', borderRadius: '5px', marginBottom: '4px' }}>
                  {translateAlert(a)}
                </div>
              ))}
            </div>
          )}

          {/* 个股告警列表 */}
          {result.stock_alerts.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {result.stock_alerts.map((sa, i) => {
                const reject = isReject(sa.level);
                return (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'flex-start', gap: '10px',
                    padding: '8px 10px', borderRadius: '6px',
                    background: reject ? 'rgba(229,83,75,0.05)' : 'rgba(198,144,38,0.04)',
                    border: `1px solid ${reject ? 'rgba(229,83,75,0.18)' : 'rgba(198,144,38,0.15)'}`,
                  }}>
                    {/* 股票名 */}
                    <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', minWidth: '72px', whiteSpace: 'nowrap' }}>
                      {sa.stock_name || sa.stock_code}
                    </span>
                    {/* 告警标签 */}
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                      {sa.alerts.map((a, j) => (
                        <span key={j} style={{
                          fontSize: '12px', padding: '2px 7px', borderRadius: '4px',
                          background: reject ? 'rgba(229,83,75,0.1)' : 'rgba(198,144,38,0.1)',
                          color: reject ? '#e5534b' : '#c69026',
                        }}>
                          {translateAlert(a)}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function PositionsContent() {
  const queryClient = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState({ stock_code: '', stock_name: '', level: 'L2', shares: '', cost_price: '', account: '', note: '' });
  const [movingId, setMovingId] = useState<number | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState<ScanResult | null>(null);

  const addCand = useAddToCandidate();

  const { data, isLoading } = useQuery({
    queryKey: ['positions'],
    queryFn: () => positionsApi.list().then(r => r.data),
  });

  const createMut = useMutation({
    mutationFn: (d: Parameters<typeof positionsApi.create>[0]) => positionsApi.create(d),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['positions'] }); resetForm(); },
  });

  const updateMut = useMutation({
    mutationFn: ({ id, data: d }: { id: number; data: Parameters<typeof positionsApi.update>[1] }) => positionsApi.update(id, d),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['positions'] }); resetForm(); },
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => positionsApi.remove(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['positions'] }),
  });

  const resetForm = useCallback(() => {
    setShowAdd(false);
    setEditId(null);
    setForm({ stock_code: '', stock_name: '', level: 'L2', shares: '', cost_price: '', account: '', note: '' });
  }, []);

  const handleSubmit = () => {
    const payload = {
      stock_code: form.stock_code,
      stock_name: form.stock_name || undefined,
      level: form.level || undefined,
      shares: form.shares ? parseInt(form.shares) : undefined,
      cost_price: form.cost_price ? parseFloat(form.cost_price) : undefined,
      account: form.account || undefined,
      note: form.note || undefined,
    };
    if (editId) {
      updateMut.mutate({ id: editId, data: payload });
    } else {
      createMut.mutate(payload);
    }
  };

  const startEdit = (p: PositionItem) => {
    setEditId(p.id);
    setShowAdd(true);
    setForm({
      stock_code: p.stock_code,
      stock_name: p.stock_name || '',
      level: p.level || 'L2',
      shares: p.shares?.toString() || '',
      cost_price: p.cost_price?.toString() || '',
      account: p.account || '',
      note: p.note || '',
    });
  };

  async function moveToCandidate(p: PositionItem) {
    setMovingId(p.id);
    setActionMsg(null);
    try {
      await addCand.mutateAsync({
        stock_code: p.stock_code,
        stock_name: p.stock_name || p.stock_code,
        source_type: 'manual',
        source_detail: `从实盘${p.level || ''}移入`,
        memo: p.note || null,
      });
      const shouldRemove = confirm(`${p.stock_name || p.stock_code} 已加入候选观察，是否同时从实盘持仓移除？`);
      if (shouldRemove) {
        try {
          await deleteMut.mutateAsync(p.id);
        } catch {
          setActionMsg('从实盘移除失败，请手动删除');
        }
      }
    } catch {
      setActionMsg('加入候选观察失败');
    } finally {
      setMovingId(null);
    }
  }

  const items = data?.items || [];
  const grouped = LEVELS.map(lv => ({
    level: lv,
    items: items.filter(p => p.level === lv),
  }));

  const cardStyle: React.CSSProperties = {
    background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)', borderRadius: '8px', padding: '16px', marginBottom: '12px',
  };

  return (
    <div style={{ maxWidth: '900px', margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <h2 style={{ fontSize: '16px', fontWeight: 600, color: 'var(--text-primary)', margin: 0 }}>实盘持仓</h2>
        <div style={{ display: 'flex', gap: '8px' }}>
          <button
            disabled={scanning}
            onClick={async () => {
              setScanning(true);
              setScanResult(null);
              try {
                const res = await apiClient.post('/api/positions/risk-scan', {}, { timeout: 60000 });
                setScanResult(res.data);
              } catch { setActionMsg('风控扫描失败'); }
              finally { setScanning(false); }
            }}
            style={{ padding: '6px 16px', fontSize: '13px', background: 'transparent', color: 'var(--accent)', border: '1px solid var(--accent)', borderRadius: '6px', cursor: scanning ? 'wait' : 'pointer', opacity: scanning ? 0.6 : 1 }}
          >
            {scanning ? '扫描中...' : '风控扫描'}
          </button>
          <button
            onClick={() => { resetForm(); setShowAdd(true); }}
            style={{ padding: '6px 16px', fontSize: '13px', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: '6px', cursor: 'pointer' }}
          >
            添加持仓
          </button>
        </div>
      </div>

      {/* Add/Edit Form */}
      {showAdd && (
        <div style={{ ...cardStyle, marginBottom: '20px' }}>
          <h3 style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '12px' }}>
            {editId ? '编辑持仓' : '添加持仓'}
          </h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: '10px' }}>
            {/* Stock search / display */}
            {editId ? (
              <div style={{ padding: '6px 10px', fontSize: '13px', border: '1px solid var(--border-subtle)', borderRadius: '6px', background: 'var(--bg-canvas)', color: 'var(--text-muted)' }}>
                {form.stock_name ? `${form.stock_name} (${form.stock_code})` : form.stock_code}
              </div>
            ) : (
              form.stock_code ? (
                <div
                  onClick={() => setForm({ ...form, stock_code: '', stock_name: '' })}
                  title="点击重新选择"
                  style={{ padding: '6px 10px', fontSize: '13px', border: '1px solid var(--accent)', borderRadius: '6px', background: 'color-mix(in srgb, var(--accent) 8%, transparent)', color: 'var(--text-primary)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
                >
                  <span>{form.stock_name ? `${form.stock_name} ${form.stock_code}` : form.stock_code}</span>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>x</span>
                </div>
              ) : (
                <StockSearchInput
                  placeholder="搜索股票代码或名称"
                  width="100%"
                  onSelect={(s: StockSearchResult) => setForm({ ...form, stock_code: s.stock_code, stock_name: s.stock_name })}
                />
              )
            )}
            <select value={form.level} onChange={e => setForm({ ...form, level: e.target.value })}
              style={{ padding: '6px 10px', fontSize: '13px', border: '1px solid var(--border-subtle)', borderRadius: '6px' }}>
              {LEVELS.map(l => <option key={l} value={l}>{l}</option>)}
            </select>
            <input placeholder="股数" type="number" value={form.shares} onChange={e => setForm({ ...form, shares: e.target.value })}
              style={{ padding: '6px 10px', fontSize: '13px', border: '1px solid var(--border-subtle)', borderRadius: '6px' }} />
            <input placeholder="成本价" type="number" step="0.01" value={form.cost_price} onChange={e => setForm({ ...form, cost_price: e.target.value })}
              style={{ padding: '6px 10px', fontSize: '13px', border: '1px solid var(--border-subtle)', borderRadius: '6px' }} />
            <input placeholder="账户" value={form.account} onChange={e => setForm({ ...form, account: e.target.value })}
              style={{ padding: '6px 10px', fontSize: '13px', border: '1px solid var(--border-subtle)', borderRadius: '6px' }} />
          </div>
          <input placeholder="备注" value={form.note} onChange={e => setForm({ ...form, note: e.target.value })}
            style={{ width: '100%', padding: '6px 10px', fontSize: '13px', border: '1px solid var(--border-subtle)', borderRadius: '6px', marginTop: '10px' }} />
          <div style={{ marginTop: '12px', display: 'flex', gap: '8px', alignItems: 'center' }}>
            <button
              onClick={handleSubmit}
              disabled={!form.stock_code || createMut.isPending || updateMut.isPending}
              style={{ padding: '6px 16px', fontSize: '13px', background: 'var(--accent)', color: '#fff', border: 'none', borderRadius: '6px', cursor: form.stock_code ? 'pointer' : 'not-allowed', opacity: form.stock_code ? 1 : 0.5 }}
            >
              {(createMut.isPending || updateMut.isPending) ? '保存中...' : (editId ? '保存' : '添加')}
            </button>
            <button onClick={resetForm} style={{ padding: '6px 16px', fontSize: '13px', background: 'var(--bg-canvas)', color: 'var(--text-secondary)', border: '1px solid var(--border-subtle)', borderRadius: '6px', cursor: 'pointer' }}>
              取消
            </button>
          </div>
        </div>
      )}

      {actionMsg && (
        <div style={{ marginBottom: '12px', padding: '8px 14px', borderRadius: '6px', background: 'rgba(229,83,75,0.06)', border: '1px solid rgba(229,83,75,0.2)', fontSize: '12px', color: '#e5534b' }}>
          {actionMsg}
        </div>
      )}

      {scanResult && (
        <ScanResultPanel result={scanResult} onClose={() => setScanResult(null)} />
      )}

      {isLoading && <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>加载中...</div>}

      {/* Grouped by level */}
      {grouped.map(g => g.items.length > 0 && (
        <div key={g.level} style={{ marginBottom: '24px' }}>
          <h2 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '10px' }}>{g.level} ({g.items.length})</h2>
          <div className="table-scroll" style={cardStyle}>
            <table style={{ width: '100%', fontSize: '13px', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
              <colgroup>
                <col style={{ width: '15%' }} />
                <col style={{ width: '20%' }} />
                <col style={{ width: '12%' }} />
                <col style={{ width: '12%' }} />
                <col style={{ width: '15%' }} />
                <col style={{ width: '26%' }} />
              </colgroup>
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-muted)' }}>
                  <th style={{ textAlign: 'left', padding: '6px 8px' }}>代码</th>
                  <th style={{ textAlign: 'left', padding: '6px 8px' }}>名称</th>
                  <th style={{ textAlign: 'right', padding: '6px 8px' }}>股数</th>
                  <th style={{ textAlign: 'right', padding: '6px 8px' }}>成本</th>
                  <th style={{ textAlign: 'left', padding: '6px 8px' }}>账户</th>
                  <th style={{ textAlign: 'right', padding: '6px 8px' }}>操作</th>
                </tr>
              </thead>
              <tbody>
                {g.items.map(p => (
                  <tr key={p.id} style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                    <td style={{ padding: '6px 8px', color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.stock_code}</td>
                    <td style={{ padding: '6px 8px', color: 'var(--text-secondary)', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.stock_name || '-'}</td>
                    <td style={{ padding: '6px 8px', textAlign: 'right', color: 'var(--text-primary)' }}>{p.shares ?? '-'}</td>
                    <td style={{ padding: '6px 8px', textAlign: 'right', color: 'var(--text-primary)' }}>{p.cost_price?.toFixed(2) ?? '-'}</td>
                    <td style={{ padding: '6px 8px', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.account || '-'}</td>
                    <td style={{ padding: '6px 8px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                      <button onClick={() => startEdit(p)} style={{ fontSize: '12px', color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer', marginRight: '8px' }}>编辑</button>
                      <button
                        onClick={() => moveToCandidate(p)}
                        disabled={movingId === p.id}
                        style={{ fontSize: '12px', color: '#5e6ad2', background: 'none', border: 'none', cursor: movingId === p.id ? 'default' : 'pointer', marginRight: '8px' }}
                      >
                        {movingId === p.id ? '移动中...' : '移至候选'}
                      </button>
                      <button onClick={() => { if (confirm('确认删除?')) deleteMut.mutate(p.id); }} style={{ fontSize: '12px', color: 'var(--red)', background: 'none', border: 'none', cursor: 'pointer' }}>删除</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}

      {!isLoading && items.length === 0 && (
        <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '40px 0', fontSize: '14px' }}>
          暂无持仓数据，点击「添加持仓」搜索股票后开始管理你的投资组合
        </div>
      )}
    </div>
  );
}
