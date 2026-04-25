'use client';

import React, { useState, useRef, useCallback } from 'react';
import { useSSEFetch } from '@/hooks/useSSEFetch';
import { screenApi, ScreenStock, ScreenOptions, ScreenParams } from '@/lib/candidate-pool-api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SmartStock {
  stock_code: string;
  stock_name: string;
  relevance: 'high' | 'medium';
  reason: string;
  industry?: string;
  province?: string;
  close?: number | null;
  rps_250?: number | null;
  rps_120?: number | null;
  rps_20?: number | null;
  main_business_short?: string;
}

interface SelectedStock {
  stock_code: string;
  stock_name: string;
  reason?: string;
}

type TabMode = 'smart' | 'screen';
type Phase = 'idle' | 'searching' | 'done' | 'error';

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: (themeName: string, description: string, stocks: SelectedStock[]) => Promise<void>;
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const selectStyle: React.CSSProperties = {
  fontSize: '12px', padding: '5px 8px', borderRadius: '6px',
  border: '1px solid var(--border-subtle)', background: 'var(--bg-input)',
  color: 'var(--text-primary)',
};

const RELEVANCE_COLORS: Record<string, { bg: string; text: string }> = {
  high: { bg: 'rgba(39,166,68,0.12)', text: '#27a644' },
  medium: { bg: 'rgba(198,144,38,0.12)', text: '#c69026' },
};

// ---------------------------------------------------------------------------
// CreateThemeDialog
// ---------------------------------------------------------------------------

export function CreateThemeDialog({ open, onClose, onCreated }: Props) {
  // Theme info
  const [themeName, setThemeName] = useState('');
  const [themeDesc, setThemeDesc] = useState('');

  // Tab
  const [tabMode, setTabMode] = useState<TabMode>('smart');

  // Shared selection across tabs
  const [selectedMap, setSelectedMap] = useState<Map<string, SelectedStock>>(new Map());

  // Smart search state
  const [smartQuery, setSmartQuery] = useState('');
  const [smartPhase, setSmartPhase] = useState<Phase>('idle');
  const [smartResults, setSmartResults] = useState<SmartStock[]>([]);
  const [smartMsg, setSmartMsg] = useState('');
  const [smartIntent, setSmartIntent] = useState<Record<string, unknown> | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const { stream } = useSSEFetch();

  // Screen state
  const [screenOptions, setScreenOptions] = useState<ScreenOptions>({ provinces: [], industries: [] });
  const [screenParams, setScreenParams] = useState<ScreenParams>({});
  const [screenKeyword, setScreenKeyword] = useState('');
  const [screenResults, setScreenResults] = useState<ScreenStock[]>([]);
  const [screenLoading, setScreenLoading] = useState(false);
  const [screenSearched, setScreenSearched] = useState(false);
  const [screenOptionsLoaded, setScreenOptionsLoaded] = useState(false);

  // Creating state
  const [creating, setCreating] = useState(false);

  // Load screen options lazily
  const loadScreenOptions = useCallback(async () => {
    if (screenOptionsLoaded) return;
    try {
      const res = await screenApi.options();
      setScreenOptions(res.data as ScreenOptions);
      setScreenOptionsLoaded(true);
    } catch {
      // ignore
    }
  }, [screenOptionsLoaded]);

  // ---------------------------------------------------------------------------
  // Smart search
  // ---------------------------------------------------------------------------

  async function handleSmartSearch() {
    if (!smartQuery.trim()) return;

    // Abort previous
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setSmartPhase('searching');
    setSmartResults([]);
    setSmartMsg('正在解析查询意图...');
    setSmartIntent(null);

    try {
      await stream(
        '/api/theme-pool/llm/smart-search',
        { query: smartQuery.trim(), max_results: 50 },
        (event) => {
          const t = event.type ?? '';
          switch (t) {
            case 'start':
              setSmartMsg(event.message as string);
              break;
            case 'phase':
              setSmartMsg(event.message as string);
              break;
            case 'intent_parsed':
              setSmartIntent(event.intent as Record<string, unknown>);
              break;
            case 'raw_results':
              setSmartMsg(event.message as string);
              break;
            case 'candidate_list':
              setSmartResults((event.stocks as SmartStock[]) || []);
              break;
            case 'done':
              setSmartPhase('done');
              setSmartMsg(event.summary as string);
              break;
            case 'error':
              setSmartPhase('error');
              setSmartMsg(event.message as string || '搜索失败');
              break;
          }
        },
        ctrl.signal,
      );
      // If phase wasn't set to done/error by events
      setSmartPhase((prev) => prev === 'searching' ? 'done' : prev);
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') return;
      setSmartPhase('error');
      setSmartMsg(err instanceof Error ? err.message : '搜索失败');
    }
  }

  // ---------------------------------------------------------------------------
  // Screen search
  // ---------------------------------------------------------------------------

  async function handleScreenSearch() {
    setScreenLoading(true);
    setScreenSearched(true);
    try {
      const params: ScreenParams = { ...screenParams, limit: 200 };
      if (screenKeyword.trim()) params.keyword = screenKeyword.trim();
      const res = await screenApi.screen(params);
      setScreenResults((res.data as { data?: ScreenStock[] }).data || []);
    } catch {
      setScreenResults([]);
    } finally {
      setScreenLoading(false);
    }
  }

  function handleScreenReset() {
    setScreenParams({});
    setScreenKeyword('');
    setScreenResults([]);
    setScreenSearched(false);
  }

  // ---------------------------------------------------------------------------
  // Selection management
  // ---------------------------------------------------------------------------

  function toggleSelect(code: string, name: string, reason?: string) {
    setSelectedMap((prev) => {
      const next = new Map(prev);
      if (next.has(code)) {
        next.delete(code);
      } else {
        next.set(code, { stock_code: code, stock_name: name, reason });
      }
      return next;
    });
  }

  function selectAll(stocks: { stock_code: string; stock_name: string; reason?: string }[]) {
    setSelectedMap((prev) => {
      const next = new Map(prev);
      for (const s of stocks) {
        if (!next.has(s.stock_code)) {
          next.set(s.stock_code, { stock_code: s.stock_code, stock_name: s.stock_name, reason: s.reason });
        }
      }
      return next;
    });
  }

  function deselectAll(codes: string[]) {
    setSelectedMap((prev) => {
      const next = new Map(prev);
      for (const c of codes) next.delete(c);
      return next;
    });
  }

  // ---------------------------------------------------------------------------
  // Create
  // ---------------------------------------------------------------------------

  async function handleCreate() {
    if (!themeName.trim() || selectedMap.size === 0) return;
    setCreating(true);
    try {
      await onCreated(themeName.trim(), themeDesc.trim(), Array.from(selectedMap.values()));
      // Reset state
      setThemeName('');
      setThemeDesc('');
      setSelectedMap(new Map());
      setSmartQuery('');
      setSmartResults([]);
      setSmartPhase('idle');
      setScreenResults([]);
      setScreenSearched(false);
    } catch {
      // handled by parent
    } finally {
      setCreating(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Cleanup on close
  // ---------------------------------------------------------------------------

  function handleClose() {
    abortRef.current?.abort();
    onClose();
  }

  // ---------------------------------------------------------------------------
  // Tab switch handler
  // ---------------------------------------------------------------------------

  function handleTabSwitch(tab: TabMode) {
    setTabMode(tab);
    if (tab === 'screen') {
      loadScreenOptions();
    }
  }

  if (!open) return null;

  const selectedCount = selectedMap.size;

  // Check if all smart results are selected
  const smartAllSelected = smartResults.length > 0 && smartResults.every(s => selectedMap.has(s.stock_code));
  const screenAllSelected = screenResults.length > 0 && screenResults.every(s => selectedMap.has(s.stock_code));

  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 1000,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
      onClick={handleClose}
    >
      <div
        style={{
          background: 'var(--bg-panel)', borderRadius: '12px', padding: '0',
          width: '780px', maxWidth: '95vw', maxHeight: '90vh',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{
          padding: '20px 24px 16px', borderBottom: '1px solid var(--border-subtle)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
            <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
              创建主题票池
            </h3>
            <button
              onClick={handleClose}
              style={{
                background: 'none', border: 'none', fontSize: '16px',
                color: 'var(--text-muted)', cursor: 'pointer', padding: '2px 6px',
              }}
            >
              x
            </button>
          </div>

          {/* Theme name + description */}
          <div style={{ display: 'flex', gap: '12px', marginBottom: '12px' }}>
            <div style={{ flex: '0 0 200px' }}>
              <label style={{ display: 'block', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>
                主题名称 *
              </label>
              <input
                value={themeName}
                onChange={(e) => setThemeName(e.target.value)}
                placeholder="如: AI算力 / 消费复苏"
                style={{
                  width: '100%', padding: '7px 10px', borderRadius: '6px', fontSize: '12px',
                  border: '1px solid var(--border-subtle)', background: 'var(--bg-canvas)',
                  color: 'var(--text-primary)', outline: 'none', boxSizing: 'border-box',
                }}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label style={{ display: 'block', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>
                描述
              </label>
              <input
                value={themeDesc}
                onChange={(e) => setThemeDesc(e.target.value)}
                placeholder="选股逻辑、投资主线..."
                style={{
                  width: '100%', padding: '7px 10px', borderRadius: '6px', fontSize: '12px',
                  border: '1px solid var(--border-subtle)', background: 'var(--bg-canvas)',
                  color: 'var(--text-primary)', outline: 'none', boxSizing: 'border-box',
                }}
              />
            </div>
          </div>

          {/* Tab buttons */}
          <div style={{ display: 'flex', gap: '2px' }}>
            {(['smart', 'screen'] as const).map((tab) => (
              <button
                key={tab}
                onClick={() => handleTabSwitch(tab)}
                style={{
                  padding: '6px 16px', fontSize: '12px', fontWeight: tabMode === tab ? 510 : 400,
                  border: 'none', borderBottom: tabMode === tab ? '2px solid var(--accent)' : '2px solid transparent',
                  background: 'transparent', cursor: 'pointer',
                  color: tabMode === tab ? 'var(--text-primary)' : 'var(--text-tertiary)',
                }}
              >
                {tab === 'smart' ? '智能搜索' : '条件筛选'}
              </button>
            ))}
          </div>
        </div>

        {/* Content area */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px 24px' }}>

          {/* ---- Smart Search Tab ---- */}
          {tabMode === 'smart' && (
            <div>
              <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
                <input
                  value={smartQuery}
                  onChange={(e) => setSmartQuery(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleSmartSearch(); }}
                  placeholder="输入选股条件，如: 锂矿营收占比超30%的公司、PCB业务增速高的..."
                  style={{
                    flex: 1, padding: '8px 12px', borderRadius: '6px', fontSize: '12px',
                    border: '1px solid var(--border-subtle)', background: 'var(--bg-canvas)',
                    color: 'var(--text-primary)', outline: 'none',
                  }}
                />
                <button
                  onClick={handleSmartSearch}
                  disabled={smartPhase === 'searching' || !smartQuery.trim()}
                  style={{
                    padding: '8px 20px', borderRadius: '6px', fontSize: '12px', fontWeight: 510,
                    border: 'none', background: 'var(--accent)', color: '#fff',
                    cursor: (smartPhase === 'searching' || !smartQuery.trim()) ? 'not-allowed' : 'pointer',
                    opacity: (smartPhase === 'searching' || !smartQuery.trim()) ? 0.6 : 1,
                  }}
                >
                  {smartPhase === 'searching' ? '搜索中...' : '搜索'}
                </button>
              </div>

              {/* Progress / message */}
              {smartMsg && (
                <div style={{
                  marginBottom: '10px', padding: '8px 12px', borderRadius: '6px',
                  background: smartPhase === 'error' ? 'rgba(229,83,75,0.08)' : 'var(--bg-card)',
                  fontSize: '12px',
                  color: smartPhase === 'error' ? '#e5534b' : 'var(--text-secondary)',
                }}>
                  {smartPhase === 'searching' && (
                    <span style={{ display: 'inline-block', marginRight: '6px', animation: 'spin 1s linear infinite' }}>...</span>
                  )}
                  {smartMsg}
                </div>
              )}

              {/* Intent display */}
              {smartIntent && (
                <div style={{
                  marginBottom: '10px', padding: '8px 12px', borderRadius: '6px',
                  background: 'var(--bg-surface)', fontSize: '11px', color: 'var(--text-muted)',
                }}>
                  AI 解析: 关键词 [{(smartIntent.keywords as string[] || []).join(', ')}]
                  {smartIntent.industry ? <span> | 行业: {String(smartIntent.industry)}</span> : null}
                  {smartIntent.province ? <span> | 省份: {String(smartIntent.province)}</span> : null}
                  {smartIntent.financial_hint ? <span> | 财务提示: {String(smartIntent.financial_hint)}</span> : null}
                </div>
              )}

              {/* Results */}
              {smartResults.length > 0 && (
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                    <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                      共 {smartResults.length} 只结果
                    </span>
                    <button
                      onClick={() => {
                        if (smartAllSelected) {
                          deselectAll(smartResults.map(s => s.stock_code));
                        } else {
                          selectAll(smartResults.map(s => ({
                            stock_code: s.stock_code, stock_name: s.stock_name, reason: s.reason,
                          })));
                        }
                      }}
                      style={{
                        fontSize: '11px', padding: '3px 10px', borderRadius: '4px',
                        border: '1px solid var(--border-subtle)', background: 'transparent',
                        color: 'var(--text-secondary)', cursor: 'pointer',
                      }}
                    >
                      {smartAllSelected ? '取消全选' : '全选'}
                    </button>
                  </div>

                  <div style={{ borderRadius: '8px', border: '1px solid var(--border-subtle)', overflow: 'hidden' }}>
                    <div className="table-scroll" style={{ maxHeight: '320px', overflowY: 'auto' }}>
                      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px', minWidth: '600px' }}>
                        <thead>
                          <tr style={{ background: 'var(--bg-panel)' }}>
                            <th style={thStyle}></th>
                            <th style={thStyle}>股票</th>
                            <th style={thStyle}>相关度</th>
                            <th style={thStyle}>行业</th>
                            <th style={thStyle}>RPS250</th>
                            <th style={thStyle}>收盘价</th>
                            <th style={thStyle}>理由/主营</th>
                          </tr>
                        </thead>
                        <tbody>
                          {smartResults.map((s, i) => (
                            <tr key={s.stock_code} style={{ background: i % 2 === 0 ? 'transparent' : 'var(--bg-surface)' }}>
                              <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                                <input
                                  type="checkbox"
                                  checked={selectedMap.has(s.stock_code)}
                                  onChange={() => toggleSelect(s.stock_code, s.stock_name, s.reason)}
                                  style={{ cursor: 'pointer' }}
                                />
                              </td>
                              <td style={{ padding: '6px 8px', whiteSpace: 'nowrap' }}>
                                <span style={{ fontWeight: 510 }}>{s.stock_name}</span>
                                <span style={{ color: 'var(--text-muted)', marginLeft: '4px', fontSize: '10px' }}>{s.stock_code}</span>
                              </td>
                              <td style={{ padding: '6px 8px' }}>
                                <span style={{
                                  fontSize: '10px', padding: '1px 6px', borderRadius: '3px',
                                  background: RELEVANCE_COLORS[s.relevance]?.bg || 'var(--bg-tag)',
                                  color: RELEVANCE_COLORS[s.relevance]?.text || 'var(--text-muted)',
                                  fontWeight: 510,
                                }}>
                                  {s.relevance === 'high' ? 'HIGH' : 'MED'}
                                </span>
                              </td>
                              <td style={{ padding: '6px 8px', color: 'var(--text-secondary)', whiteSpace: 'nowrap', maxWidth: '100px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                {s.industry || '-'}
                              </td>
                              <td style={{
                                padding: '6px 8px', fontFamily: 'var(--font-geist-mono)',
                                color: (s.rps_250 ?? 0) >= 80 ? '#27a644' : 'var(--text-secondary)',
                                fontWeight: 510,
                              }}>
                                {s.rps_250 != null ? s.rps_250.toFixed(1) : '-'}
                              </td>
                              <td style={{ padding: '6px 8px', fontFamily: 'var(--font-geist-mono)' }}>
                                {s.close != null ? s.close.toFixed(2) : '-'}
                              </td>
                              <td style={{
                                padding: '6px 8px', color: 'var(--text-secondary)',
                                maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                              }} title={s.reason || s.main_business_short || ''}>
                                {s.reason || s.main_business_short || '-'}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ---- Screen Tab ---- */}
          {tabMode === 'screen' && (
            <div>
              {/* Filter controls */}
              <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '12px', alignItems: 'flex-end' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>省份/地区</label>
                  <select
                    value={screenParams.province || ''}
                    onChange={e => setScreenParams(p => ({ ...p, province: e.target.value || undefined }))}
                    style={selectStyle}
                  >
                    <option value=''>全部省份</option>
                    {screenOptions.provinces.map(p => <option key={p} value={p}>{p}</option>)}
                  </select>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>行业分类</label>
                  <select
                    value={screenParams.industry || ''}
                    onChange={e => setScreenParams(p => ({ ...p, industry: e.target.value || undefined }))}
                    style={{ ...selectStyle, maxWidth: '200px' }}
                  >
                    <option value=''>全部行业</option>
                    {screenOptions.industries.map(ind => <option key={ind} value={ind}>{ind}</option>)}
                  </select>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>上市年限</label>
                  <div style={{ display: 'flex', gap: '4px', alignItems: 'center' }}>
                    <select
                      value={screenParams.listed_years_min ?? ''}
                      onChange={e => setScreenParams(p => ({ ...p, listed_years_min: e.target.value ? Number(e.target.value) : undefined }))}
                      style={selectStyle}
                    >
                      <option value=''>不限</option>
                      <option value='1'>1年+</option>
                      <option value='3'>3年+</option>
                      <option value='5'>5年+</option>
                      <option value='10'>10年+</option>
                    </select>
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>至</span>
                    <select
                      value={screenParams.listed_years_max ?? ''}
                      onChange={e => setScreenParams(p => ({ ...p, listed_years_max: e.target.value ? Number(e.target.value) : undefined }))}
                      style={selectStyle}
                    >
                      <option value=''>不限</option>
                      <option value='1'>1年内</option>
                      <option value='3'>3年内</option>
                      <option value='5'>5年内</option>
                      <option value='10'>10年内</option>
                    </select>
                  </div>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>RPS250 最低</label>
                  <select
                    value={screenParams.min_rps ?? ''}
                    onChange={e => setScreenParams(p => ({ ...p, min_rps: e.target.value ? Number(e.target.value) : undefined }))}
                    style={selectStyle}
                  >
                    <option value=''>不限</option>
                    <option value='60'>60+</option>
                    <option value='70'>70+</option>
                    <option value='80'>80+</option>
                    <option value='90'>90+</option>
                  </select>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <label style={{ fontSize: '11px', color: 'var(--text-muted)' }}>排序</label>
                  <select
                    value={screenParams.sort_by || 'rps_250'}
                    onChange={e => setScreenParams(p => ({ ...p, sort_by: e.target.value }))}
                    style={selectStyle}
                  >
                    <option value='rps_250'>RPS250</option>
                    <option value='rps_120'>RPS120</option>
                    <option value='rps_20'>RPS20</option>
                    <option value='rps_slope'>RPS斜率</option>
                  </select>
                </div>
              </div>

              {/* Keyword + action buttons */}
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '12px' }}>
                <input
                  value={screenKeyword}
                  onChange={e => setScreenKeyword(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') handleScreenSearch(); }}
                  placeholder='主营业务关键词，如：磷化工、尿素、铝...'
                  style={{
                    flex: 1, fontSize: '12px', padding: '7px 12px', borderRadius: '6px',
                    border: '1px solid var(--border-subtle)', background: 'var(--bg-canvas)',
                    color: 'var(--text-primary)', maxWidth: '360px', outline: 'none',
                  }}
                />
                <button
                  onClick={handleScreenSearch}
                  disabled={screenLoading}
                  style={{
                    fontSize: '12px', padding: '7px 16px', borderRadius: '6px',
                    background: 'var(--accent)', color: '#fff', border: 'none',
                    cursor: screenLoading ? 'not-allowed' : 'pointer', opacity: screenLoading ? 0.7 : 1,
                  }}
                >
                  {screenLoading ? '搜索中...' : '搜索'}
                </button>
                <button
                  onClick={handleScreenReset}
                  style={{
                    fontSize: '12px', padding: '7px 12px', borderRadius: '6px',
                    background: 'transparent', color: 'var(--text-muted)',
                    border: '1px solid var(--border-subtle)', cursor: 'pointer',
                  }}
                >
                  重置
                </button>
              </div>

              {/* Screen results */}
              {screenSearched && (
                screenLoading ? (
                  <div style={{ padding: '20px', textAlign: 'center', fontSize: '12px', color: 'var(--text-muted)' }}>搜索中...</div>
                ) : screenResults.length === 0 ? (
                  <div style={{ padding: '20px', textAlign: 'center', fontSize: '12px', color: 'var(--text-muted)' }}>无匹配结果</div>
                ) : (
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                      <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                        共 {screenResults.length} 只结果
                      </span>
                      <button
                        onClick={() => {
                          if (screenAllSelected) {
                            deselectAll(screenResults.map(s => s.stock_code));
                          } else {
                            selectAll(screenResults.map(s => ({
                              stock_code: s.stock_code, stock_name: s.stock_name,
                            })));
                          }
                        }}
                        style={{
                          fontSize: '11px', padding: '3px 10px', borderRadius: '4px',
                          border: '1px solid var(--border-subtle)', background: 'transparent',
                          color: 'var(--text-secondary)', cursor: 'pointer',
                        }}
                      >
                        {screenAllSelected ? '取消全选' : '全选'}
                      </button>
                    </div>

                    <div style={{ borderRadius: '8px', border: '1px solid var(--border-subtle)', overflow: 'hidden' }}>
                      <div className="table-scroll" style={{ maxHeight: '320px', overflowY: 'auto' }}>
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px', minWidth: '600px' }}>
                          <thead>
                            <tr style={{ background: 'var(--bg-panel)' }}>
                              <th style={thStyle}></th>
                              <th style={thStyle}>股票</th>
                              <th style={thStyle}>省份</th>
                              <th style={thStyle}>行业</th>
                              <th style={thStyle}>上市日期</th>
                              <th style={thStyle}>主营摘要</th>
                              <th style={thStyle}>RPS250</th>
                              <th style={thStyle}>收盘价</th>
                            </tr>
                          </thead>
                          <tbody>
                            {screenResults.map((s, i) => (
                              <tr key={s.stock_code} style={{ background: i % 2 === 0 ? 'transparent' : 'var(--bg-surface)' }}>
                                <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                                  <input
                                    type="checkbox"
                                    checked={selectedMap.has(s.stock_code)}
                                    onChange={() => toggleSelect(s.stock_code, s.stock_name)}
                                    style={{ cursor: 'pointer' }}
                                  />
                                </td>
                                <td style={{ padding: '6px 8px', whiteSpace: 'nowrap' }}>
                                  <span style={{ fontWeight: 510 }}>{s.stock_name}</span>
                                  <span style={{ color: 'var(--text-muted)', marginLeft: '4px', fontSize: '10px' }}>{s.stock_code}</span>
                                </td>
                                <td style={{ padding: '6px 8px', color: 'var(--text-secondary)', whiteSpace: 'nowrap' }}>{s.province || '-'}</td>
                                <td style={{ padding: '6px 8px', color: 'var(--text-secondary)', whiteSpace: 'nowrap', maxWidth: '100px', overflow: 'hidden', textOverflow: 'ellipsis' }}>{s.industry || '-'}</td>
                                <td style={{ padding: '6px 8px', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{s.listed_date || '-'}</td>
                                <td style={{ padding: '6px 8px', color: 'var(--text-secondary)', maxWidth: '160px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={s.main_business_short || ''}>{s.main_business_short || '-'}</td>
                                <td style={{
                                  padding: '6px 8px', fontFamily: 'var(--font-geist-mono)',
                                  color: (s.rps_250 ?? 0) >= 80 ? '#27a644' : (s.rps_250 ?? 0) >= 60 ? '#c69026' : 'var(--text-secondary)',
                                  fontWeight: 510,
                                }}>
                                  {s.rps_250 != null ? s.rps_250.toFixed(1) : '-'}
                                </td>
                                <td style={{ padding: '6px 8px', fontFamily: 'var(--font-geist-mono)' }}>
                                  {s.close != null ? s.close.toFixed(2) : '-'}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </div>
                )
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{
          padding: '14px 24px', borderTop: '1px solid var(--border-subtle)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
            已选: {selectedCount} 只
          </span>
          <div style={{ display: 'flex', gap: '8px' }}>
            <button
              onClick={handleClose}
              style={{
                padding: '7px 16px', borderRadius: '6px', fontSize: '12px',
                border: '1px solid var(--border-subtle)', background: 'transparent',
                color: 'var(--text-secondary)', cursor: 'pointer',
              }}
            >
              取消
            </button>
            <button
              onClick={handleCreate}
              disabled={!themeName.trim() || selectedCount === 0 || creating}
              style={{
                padding: '7px 20px', borderRadius: '6px', fontSize: '12px', fontWeight: 510,
                border: 'none', background: 'var(--accent)', color: '#fff',
                cursor: (!themeName.trim() || selectedCount === 0 || creating) ? 'not-allowed' : 'pointer',
                opacity: (!themeName.trim() || selectedCount === 0 || creating) ? 0.5 : 1,
              }}
            >
              {creating ? '创建中...' : `创建主题 (写入 ${selectedCount} 只)`}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Shared th style
const thStyle: React.CSSProperties = {
  padding: '6px 8px', textAlign: 'left', color: 'var(--text-muted)',
  fontWeight: 400, borderBottom: '1px solid var(--border-subtle)', whiteSpace: 'nowrap',
  position: 'sticky', top: 0, background: 'var(--bg-panel)', zIndex: 1,
};
