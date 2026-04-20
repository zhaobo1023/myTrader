'use client';

import { useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient, { positionsApi, PositionItem } from '@/lib/api-client';
import { useAddToCandidate } from '@/hooks/useStockAdd';
import StockSearchInput from '@/components/stock/StockSearchInput';
import type { StockSearchResult } from '@/lib/api-client';

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || '';

const LEVELS = ['L1', 'L2', 'L3'];

// 风险等级颜色映射
const LEVEL_COLOR: Record<string, string> = {
  LOW: '#16a34a',
  MEDIUM: '#ca8a04',
  HIGH: '#ea580c',
  CRITICAL: '#dc2626',
};

const LEVEL_BG: Record<string, string> = {
  LOW: 'rgba(22,163,74,0.07)',
  MEDIUM: 'rgba(202,138,4,0.07)',
  HIGH: 'rgba(234,88,12,0.07)',
  CRITICAL: 'rgba(220,38,38,0.08)',
};

const LEVEL_BORDER: Record<string, string> = {
  LOW: 'rgba(22,163,74,0.22)',
  MEDIUM: 'rgba(202,138,4,0.22)',
  HIGH: 'rgba(234,88,12,0.22)',
  CRITICAL: 'rgba(220,38,38,0.25)',
};

const LEVEL_LABEL: Record<string, string> = {
  LOW: '低风险',
  MEDIUM: '中等风险',
  HIGH: '偏高风险',
  CRITICAL: '极高风险',
};

// 分层风控扫描结果类型（V2）
type DataStatus = {
  name: string;
  latest_date: string;
  delay_days: number;
  status: string;
};

type LayerResult = {
  score: number;
  level: string;
  details: Record<string, unknown>;
  suggestions: string[];
};

type MacroResult = LayerResult & { suggested_max_exposure: number };
type RegimeResult = LayerResult & { market_state: string; avg_correlation: number; high_corr_pairs: [string, string, number][] };
type SectorResult = LayerResult & { industry_breakdown: Record<string, number>; overvalued_industries: string[] };

type StockResult = {
  stock_code: string;
  stock_name: string;
  score: number;
  sub_scores: Record<string, number>;
  alerts: string[];
  stop_loss_hit: boolean;
};

type LayeredRiskResult = {
  scan_time: string;
  user_id: number;
  overall_score: number;
  overall_suggestions: string[];
  data_status: DataStatus[];
  macro: MacroResult;
  regime: RegimeResult;
  sector: SectorResult;
  stocks: StockResult[];
};

function levelColor(level: string) { return LEVEL_COLOR[level] ?? '#888'; }
function levelBg(level: string) { return LEVEL_BG[level] ?? 'transparent'; }
function levelBorder(level: string) { return LEVEL_BORDER[level] ?? 'rgba(0,0,0,0.1)'; }
function levelLabel(level: string) { return LEVEL_LABEL[level] ?? level; }

function ScoreChip({ score, level }: { score: number; level: string }) {
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '4px',
      padding: '2px 8px', borderRadius: '4px',
      background: levelBg(level), border: `1px solid ${levelBorder(level)}`,
      fontSize: '12px', fontWeight: 600, color: levelColor(level),
    }}>
      {Math.round(score)} · {levelLabel(level)}
    </span>
  );
}

function LayerCard({ title, score, level, children }: { title: string; score: number; level: string; children?: React.ReactNode }) {
  return (
    <div style={{
      borderRadius: '6px', border: `1px solid ${levelBorder(level)}`,
      background: levelBg(level), padding: '10px 14px', marginBottom: '8px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: children ? '8px' : 0 }}>
        <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>{title}</span>
        <ScoreChip score={score} level={level} />
      </div>
      {children}
    </div>
  );
}

// 从扫描结果的 stocks 数组建立 code -> name 映射，方便相关性对展示
function buildNameMap(stocks: StockResult[]): Record<string, string> {
  const map: Record<string, string> = {};
  for (const s of stocks) { map[s.stock_code] = s.stock_name || s.stock_code; }
  return map;
}

function corrLabel(corr: number): { text: string; color: string } {
  if (corr >= 0.8) return { text: '极高', color: '#dc2626' };
  if (corr >= 0.7) return { text: '较高', color: '#ea580c' };
  return { text: '偏高', color: '#ca8a04' };
}

function RiskScanV2Panel({ result, onClose }: { result: LayeredRiskResult; onClose: () => void }) {
  const overallLevel =
    result.overall_score >= 70 ? 'CRITICAL' :
    result.overall_score >= 50 ? 'HIGH' :
    result.overall_score >= 30 ? 'MEDIUM' : 'LOW';

  const triggeredStocks = result.stocks.filter(s => s.stop_loss_hit || s.alerts.length > 0);
  const normalStocks = result.stocks.filter(s => !s.stop_loss_hit && s.alerts.length === 0);
  const nameMap = buildNameMap(result.stocks);

  // 过滤掉后端建议里已由前端结构化展示的内容（相关性对、行业未知）
  const cleanSuggestions = result.overall_suggestions.filter(s =>
    !s.includes('高度相关') && !s.includes('未知 占比')
  );

  return (
    <div style={{ marginBottom: '16px', borderRadius: '8px', background: 'var(--bg-panel)', border: '1px solid var(--border-subtle)', overflow: 'hidden' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px 16px', borderBottom: '1px solid var(--border-subtle)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-primary)' }}>风控扫描结果 (V2)</span>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{result.scan_time}</span>
          <ScoreChip score={result.overall_score} level={overallLevel} />
        </div>
        <button onClick={onClose} style={{ fontSize: '12px', color: 'var(--text-muted)', background: 'none', border: 'none', cursor: 'pointer', padding: '2px 6px' }}>关闭</button>
      </div>

      <div style={{ padding: '12px 16px' }}>
        {/* L1 宏观 */}
        <LayerCard title="L1 宏观环境" score={result.macro.score} level={result.macro.level}>
          <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
            建议最大仓位: {Math.round(result.macro.suggested_max_exposure * 100)}%
          </div>
          {result.macro.suggestions.length > 0 && (
            <ul style={{ margin: '4px 0 0 0', paddingLeft: '16px', fontSize: '12px', color: 'var(--text-secondary)' }}>
              {result.macro.suggestions.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          )}
        </LayerCard>

        {/* L2 市场状态 */}
        <LayerCard title="L2 市场状态" score={result.regime.score} level={result.regime.level}>
          {result.regime.market_state && (
            <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '6px' }}>
              市场结构: <span style={{ color: 'var(--text-secondary)', fontWeight: 510 }}>{result.regime.market_state}</span>
              {' · '}持仓平均相关性: <span style={{ color: result.regime.avg_correlation > 0.6 ? '#ea580c' : result.regime.avg_correlation > 0.4 ? '#ca8a04' : '#16a34a', fontWeight: 510 }}>{result.regime.avg_correlation.toFixed(2)}</span>
            </div>
          )}
          {result.regime.high_corr_pairs && result.regime.high_corr_pairs.length > 0 && (
            <div style={{ marginBottom: '4px' }}>
              <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>高相关持仓对（相关系数 &gt; 0.6）</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                {result.regime.high_corr_pairs.slice(0, 5).map(([a, b, corr], i) => {
                  const { text, color } = corrLabel(corr);
                  return (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px' }}>
                      <span style={{ color: 'var(--text-secondary)' }}>{nameMap[a] || a}</span>
                      <span style={{ color: 'var(--text-muted)', fontSize: '10px' }}>↔</span>
                      <span style={{ color: 'var(--text-secondary)' }}>{nameMap[b] || b}</span>
                      <span style={{ fontSize: '11px', padding: '0 5px', borderRadius: '3px', background: `${color}15`, color, border: `1px solid ${color}40` }}>
                        {text} {corr.toFixed(2)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
          {result.regime.suggestions.length > 0 && (
            <ul style={{ margin: '4px 0 0 0', paddingLeft: '16px', fontSize: '12px', color: 'var(--text-secondary)' }}>
              {result.regime.suggestions.map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          )}
        </LayerCard>

        {/* L3 行业暴露（申万一级） */}
        <LayerCard title="L3 行业暴露（申万一级）" score={result.sector.score} level={result.sector.level}>
          {(() => {
            const known = Object.entries(result.sector.industry_breakdown).filter(([ind]) => ind !== '未知').sort((a, b) => b[1] - a[1]);
            const unknown = result.sector.industry_breakdown['未知'] || 0;
            return (
              <>
                {known.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginBottom: known.length > 0 ? '6px' : 0 }}>
                    {known.slice(0, 8).map(([ind, ratio]) => (
                      <span key={ind} style={{
                        fontSize: '12px', padding: '2px 8px', borderRadius: '4px',
                        background: ratio > 0.5 ? 'rgba(234,88,12,0.08)' : 'var(--bg-canvas)',
                        color: ratio > 0.5 ? '#ea580c' : 'var(--text-secondary)',
                        border: `1px solid ${ratio > 0.5 ? 'rgba(234,88,12,0.25)' : 'var(--border-subtle)'}`,
                        fontWeight: ratio > 0.3 ? 510 : 400,
                      }}>
                        {ind} <span style={{ opacity: 0.75 }}>{(ratio * 100).toFixed(0)}%</span>
                      </span>
                    ))}
                    {unknown > 0.05 && (
                      <span style={{ fontSize: '11px', padding: '2px 7px', borderRadius: '4px', background: 'var(--bg-canvas)', color: 'var(--text-muted)', border: '1px solid var(--border-subtle)', fontStyle: 'italic' }}>
                        待补充 {(unknown * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                )}
                {known.length === 0 && (
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px' }}>行业数据待补充</div>
                )}
              </>
            );
          })()}
          {result.sector.suggestions.filter(s => !s.includes('未知')).length > 0 && (
            <ul style={{ margin: '4px 0 0 0', paddingLeft: '16px', fontSize: '12px', color: 'var(--text-secondary)' }}>
              {result.sector.suggestions.filter(s => !s.includes('未知')).map((s, i) => <li key={i}>{s}</li>)}
            </ul>
          )}
        </LayerCard>

        {/* L4 个股预警 */}
        {result.stocks.length > 0 && (
          <div style={{ borderRadius: '6px', border: '1px solid var(--border-subtle)', padding: '10px 14px', marginBottom: '8px' }}>
            <div style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', marginBottom: '8px' }}>
              L4 个股预警
              {triggeredStocks.length > 0 && (
                <span style={{ marginLeft: '8px', fontSize: '11px', fontWeight: 400, color: '#ea580c' }}>{triggeredStocks.length}只触发预警</span>
              )}
            </div>

            {triggeredStocks.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', marginBottom: '8px' }}>
                {triggeredStocks.map((s, i) => (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'flex-start', gap: '10px',
                    padding: '7px 10px', borderRadius: '5px',
                    background: s.stop_loss_hit ? 'rgba(220,38,38,0.05)' : 'rgba(234,88,12,0.05)',
                    border: `1px solid ${s.stop_loss_hit ? 'rgba(220,38,38,0.2)' : 'rgba(234,88,12,0.18)'}`,
                  }}>
                    <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)', minWidth: '72px', whiteSpace: 'nowrap' }}>
                      {s.stock_name || s.stock_code}
                    </span>
                    <span style={{ fontSize: '12px', color: 'var(--text-muted)', minWidth: '34px' }}>
                      {Math.round(s.score)}分
                    </span>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                      {s.stop_loss_hit && (
                        <span style={{ fontSize: '11px', padding: '1px 6px', borderRadius: '3px', background: 'rgba(220,38,38,0.1)', color: '#dc2626' }}>触及止损</span>
                      )}
                      {s.alerts.map((a, j) => (
                        <span key={j} style={{ fontSize: '11px', padding: '1px 6px', borderRadius: '3px', background: 'rgba(234,88,12,0.1)', color: '#ea580c' }}>{a}</span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {normalStocks.length > 0 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                {normalStocks.map((s, i) => (
                  <span key={i} style={{ fontSize: '11px', padding: '1px 7px', borderRadius: '3px', background: 'rgba(22,163,74,0.07)', border: '1px solid rgba(22,163,74,0.18)', color: '#16a34a' }}>
                    {s.stock_name || s.stock_code} {Math.round(s.score)}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {/* 综合建议 */}
        {cleanSuggestions.length > 0 && (
          <div style={{ borderRadius: '6px', border: `1px solid ${levelBorder(overallLevel)}`, background: levelBg(overallLevel), padding: '10px 14px' }}>
            <div style={{ fontSize: '13px', fontWeight: 600, color: levelColor(overallLevel), marginBottom: '6px' }}>
              综合建议 · 总分 {Math.round(result.overall_score)}
            </div>
            <ul style={{ margin: 0, paddingLeft: '16px', fontSize: '12px', color: 'var(--text-secondary)' }}>
              {cleanSuggestions.map((s, i) => <li key={i} style={{ marginBottom: '3px' }}>{s}</li>)}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

export default function PositionsContent() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [showAdd, setShowAdd] = useState(false);
  const [analyzingId, setAnalyzingId] = useState<number | null>(null);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState({ stock_code: '', stock_name: '', level: 'L2', shares: '', cost_price: '', account: '', note: '' });
  const [movingId, setMovingId] = useState<number | null>(null);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [scanResult, setScanResult] = useState<LayeredRiskResult | null>(null);

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

  async function quickAnalyze(p: PositionItem) {
    if (analyzingId === p.id) return;
    setAnalyzingId(p.id);
    const code = p.stock_code;
    const name = p.stock_name || p.stock_code;
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    const authHeader: Record<string, string> = token ? { 'Authorization': `Bearer ${token}` } : {};

    try {
      // Check which report types already have a valid cached/pending report today
      const REPORT_TYPES = ['one_pager', 'five_section', 'fundamental'] as const;
      const checks = await Promise.allSettled(
        REPORT_TYPES.map(rt =>
          fetch(`${API_BASE}/api/analysis/report/latest?code=${encodeURIComponent(code)}&report_type=${rt}`, {
            headers: { ...authHeader },
          }).then(r => r.json())
        )
      );

      // Submit only missing/failed types
      const submitTasks: Promise<unknown>[] = [];
      checks.forEach((result, idx) => {
        const rt = REPORT_TYPES[idx];
        const data = result.status === 'fulfilled' ? result.value : null;
        // Skip if today's report is cached, or a task is currently pending/running
        const hasValid = data?.cached === true || data?.status === 'pending' || data?.status === 'running';
        if (!hasValid) {
          submitTasks.push(
            fetch(`${API_BASE}/api/analysis/report/submit`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', ...authHeader },
              body: JSON.stringify({ stock_code: code, stock_name: name, report_type: rt }),
            })
          );
        }
      });

      if (submitTasks.length > 0) {
        await Promise.allSettled(submitTasks);
      }
    } finally {
      setAnalyzingId(null);
    }

    router.push(`/stock?code=${encodeURIComponent(code)}`);
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
                const res = await apiClient.get('/api/risk/scan', { timeout: 90000 });
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
        <RiskScanV2Panel result={scanResult} onClose={() => setScanResult(null)} />
      )}

      {isLoading && <div style={{ color: 'var(--text-muted)', fontSize: '13px' }}>加载中...</div>}

      {/* Grouped by level */}
      {grouped.map(g => g.items.length > 0 && (
        <div key={g.level} style={{ marginBottom: '24px' }}>
          <h2 style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '10px' }}>{g.level} ({g.items.length})</h2>
          <div className="table-scroll" style={cardStyle}>
            <table style={{ width: '100%', fontSize: '13px', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
              <colgroup>
                <col style={{ width: '13%' }} />
                <col style={{ width: '17%' }} />
                <col style={{ width: '10%' }} />
                <col style={{ width: '10%' }} />
                <col style={{ width: '12%' }} />
                <col style={{ width: '38%' }} />
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
                    <td style={{ padding: '6px 8px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      <a
                        href={`/stock?code=${encodeURIComponent(p.stock_code)}`}
                        style={{ color: 'var(--accent)', textDecoration: 'none', fontSize: '13px' }}
                      >
                        {p.stock_code}
                      </a>
                    </td>
                    <td style={{ padding: '6px 8px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      <a
                        href={`/stock?code=${encodeURIComponent(p.stock_code)}`}
                        style={{ color: 'var(--text-secondary)', textDecoration: 'none', fontSize: '13px' }}
                      >
                        {p.stock_name || '-'}
                      </a>
                    </td>
                    <td style={{ padding: '6px 8px', textAlign: 'right', color: 'var(--text-primary)' }}>{p.shares ?? '-'}</td>
                    <td style={{ padding: '6px 8px', textAlign: 'right', color: 'var(--text-primary)' }}>{p.cost_price?.toFixed(2) ?? '-'}</td>
                    <td style={{ padding: '6px 8px', color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis' }}>{p.account || '-'}</td>
                    <td style={{ padding: '6px 8px', textAlign: 'right', whiteSpace: 'nowrap' }}>
                      <button onClick={() => startEdit(p)} style={{ fontSize: '12px', color: 'var(--accent)', background: 'none', border: 'none', cursor: 'pointer', marginRight: '8px' }}>编辑</button>
                      <button
                        onClick={() => quickAnalyze(p)}
                        disabled={analyzingId === p.id}
                        style={{ fontSize: '12px', color: '#7c3aed', background: 'none', border: 'none', cursor: analyzingId === p.id ? 'default' : 'pointer', marginRight: '8px', opacity: analyzingId === p.id ? 0.5 : 1 }}
                      >
                        {analyzingId === p.id ? '检查中...' : '深度分析'}
                      </button>
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
