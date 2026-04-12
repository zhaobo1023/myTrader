'use client';

import { useParams, useRouter } from 'next/navigation';
import AppShell from '@/components/layout/AppShell';
import apiClient from '@/lib/api-client';
import { useQuery } from '@tanstack/react-query';

interface SignalItem {
  name: string;
  level: string;  // RED, YELLOW, GREEN, INFO
  description: string;
  severity: string;
  tag: string;
}

interface TechReportDetail {
  id: number;
  stock_code: string;
  stock_name: string;
  trade_date: string;
  score: number;
  score_label: string;
  max_severity: string;
  summary: string;
  signal_count: number;
  created_at: string;
  signals: SignalItem[];
  indicators: Record<string, number>;
}

const levelColor = (level: string) => {
  if (level === 'RED') return '#e5534b';
  if (level === 'YELLOW') return '#c69026';
  if (level === 'GREEN') return '#27a644';
  return 'var(--text-muted)';
};

const levelDot = (level: string) => {
  const color = levelColor(level);
  return (
    <span style={{
      display: 'inline-block',
      width: '8px',
      height: '8px',
      borderRadius: '50%',
      background: color,
      flexShrink: 0,
      marginTop: '3px',
    }} />
  );
};

const scoreBadgeStyle = (score: number): React.CSSProperties => {
  const color = score >= 20 ? '#27a644' : score <= -20 ? '#e5534b' : '#c69026';
  return {
    display: 'inline-block',
    padding: '3px 10px',
    borderRadius: '12px',
    fontSize: '13px',
    fontWeight: 510,
    color,
    background: `${color}18`,
    border: `1px solid ${color}40`,
  };
};

const severityColor = (s: string) => {
  if (s === 'RED') return '#e5534b';
  if (s === 'YELLOW') return '#c69026';
  if (s === 'GREEN') return '#27a644';
  return 'var(--text-muted)';
};

const indicatorRow = (label: string, value: number | undefined) => {
  if (value === undefined || value === null) return null;
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 8px', background: 'var(--bg-card)', borderRadius: '4px', fontSize: '12px' }}>
      <span style={{ color: 'var(--text-muted)' }}>{label}</span>
      <span style={{ color: 'var(--text-secondary)', fontWeight: 510 }}>{value.toFixed(3)}</span>
    </div>
  );
};

export default function ReportDetailPage() {
  const params = useParams();
  const router = useRouter();
  const code = decodeURIComponent(params.code as string);
  const date = params.date as string;

  const { data: report, isLoading, isError } = useQuery<TechReportDetail>({
    queryKey: ['tech-report-detail', code, date],
    queryFn: () =>
      apiClient.get(`/api/analysis/reports/${encodeURIComponent(code)}/${date}`).then((r) => r.data),
  });

  // Group signals by level priority: RED > YELLOW > GREEN > INFO
  const groupedSignals: Record<string, SignalItem[]> = { RED: [], YELLOW: [], GREEN: [], INFO: [] };
  if (report?.signals) {
    for (const sig of report.signals) {
      const lvl = sig.level in groupedSignals ? sig.level : 'INFO';
      groupedSignals[lvl].push(sig);
    }
  }

  const ind = report?.indicators || {};

  const topBar = (
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
      <button
        onClick={() => router.push('/analysis')}
        style={{
          background: 'none',
          border: '1px solid var(--border-subtle)',
          borderRadius: '6px',
          padding: '4px 10px',
          fontSize: '12px',
          color: 'var(--text-secondary)',
          cursor: 'pointer',
        }}
      >
        &larr; 返回分析
      </button>
      {report && (
        <span style={{ fontSize: '14px', fontWeight: 510, color: 'var(--text-primary)' }}>
          {report.stock_name || report.stock_code}
          <span style={{ fontWeight: 400, color: 'var(--text-muted)', marginLeft: '6px', fontSize: '12px' }}>
            ({report.stock_code})
          </span>
        </span>
      )}
    </div>
  );

  return (
    <AppShell topBar={topBar}>
      {isLoading && (
        <div style={{ fontSize: '13px', color: 'var(--text-muted)', padding: '40px 0', textAlign: 'center' }}>
          加载中...
        </div>
      )}
      {isError && (
        <div style={{ fontSize: '13px', color: '#e5534b', padding: '40px 0', textAlign: 'center' }}>
          报告不存在或加载失败
        </div>
      )}

      {report && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* Title bar */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            flexWrap: 'wrap',
            padding: '14px 16px',
            background: 'var(--bg-panel)',
            border: '1px solid var(--border-subtle)',
            borderLeft: `3px solid ${severityColor(report.max_severity)}`,
            borderRadius: '8px',
          }}>
            <span style={{ fontSize: '18px', fontWeight: 590, color: 'var(--text-primary)' }}>
              {report.stock_name || report.stock_code}
            </span>
            <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
              {report.stock_code}
            </span>
            <span style={{ fontSize: '12px', color: 'var(--text-muted)', marginLeft: '4px' }}>
              {report.trade_date}
            </span>
            <span style={scoreBadgeStyle(report.score)}>
              {report.score > 0 ? '+' : ''}{report.score} &nbsp; {report.score_label}
            </span>
            {report.max_severity !== 'NONE' && (
              <span style={{
                fontSize: '12px',
                color: severityColor(report.max_severity),
                background: `${severityColor(report.max_severity)}15`,
                padding: '2px 8px',
                borderRadius: '4px',
              }}>
                {report.max_severity}
              </span>
            )}
          </div>

          {/* Signals */}
          {report.signals.length > 0 && (
            <div style={{
              background: 'var(--bg-panel)',
              border: '1px solid var(--border-subtle)',
              borderRadius: '8px',
              padding: '16px',
            }}>
              <div style={{ fontSize: '13px', fontWeight: 510, color: 'var(--text-primary)', marginBottom: '12px' }}>
                信号列表 ({report.signal_count})
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {(['RED', 'YELLOW', 'GREEN', 'INFO'] as const).map((lvl) =>
                  groupedSignals[lvl].map((sig, i) => (
                    <div
                      key={`${lvl}-${i}`}
                      style={{
                        display: 'flex',
                        gap: '10px',
                        alignItems: 'flex-start',
                        padding: '8px 10px',
                        background: `${levelColor(lvl)}0a`,
                        borderRadius: '6px',
                        fontSize: '12px',
                      }}
                    >
                      {levelDot(lvl)}
                      <div style={{ flex: 1 }}>
                        <span style={{ fontWeight: 510, color: levelColor(lvl) }}>{sig.name}</span>
                        <span style={{ color: 'var(--text-secondary)', marginLeft: '8px' }}>{sig.description}</span>
                        {sig.tag && (
                          <span style={{
                            marginLeft: '8px',
                            fontSize: '10px',
                            color: 'var(--text-muted)',
                            background: 'var(--bg-card)',
                            padding: '1px 5px',
                            borderRadius: '3px',
                          }}>
                            {sig.tag}
                          </span>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {/* Indicators grid */}
          <div style={{
            background: 'var(--bg-panel)',
            border: '1px solid var(--border-subtle)',
            borderRadius: '8px',
            padding: '16px',
          }}>
            <div style={{ fontSize: '13px', fontWeight: 510, color: 'var(--text-primary)', marginBottom: '12px' }}>
              技术指标
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              {/* MA */}
              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>均线</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                  {indicatorRow('MA5', ind.ma5)}
                  {indicatorRow('MA20', ind.ma20)}
                  {indicatorRow('MA60', ind.ma60)}
                  {indicatorRow('MA250', ind.ma250)}
                </div>
              </div>
              {/* MACD + RSI */}
              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>动量</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                  {indicatorRow('MACD DIF', ind.macd_dif)}
                  {indicatorRow('MACD DEA', ind.macd_dea)}
                  {indicatorRow('MACD Hist', ind.macd_hist)}
                  {indicatorRow('RSI(14)', ind.rsi)}
                </div>
              </div>
              {/* BOLL + ATR */}
              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>波动</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                  {indicatorRow('ATR(14)', ind.atr_14)}
                  {indicatorRow('BOLL 上', ind.boll_upper)}
                  {indicatorRow('BOLL 中', ind.boll_middle)}
                  {indicatorRow('BOLL 下', ind.boll_lower)}
                </div>
              </div>
              {/* Volume */}
              <div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>量能</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                  {indicatorRow('量比', ind.volume_ratio)}
                  {indicatorRow('vol_ma5', ind.vol_ma5)}
                  {indicatorRow('vol_ma20', ind.vol_ma20)}
                </div>
              </div>
            </div>
          </div>

          {/* Summary */}
          <div style={{
            background: 'var(--bg-panel)',
            border: '1px solid var(--border-subtle)',
            borderRadius: '8px',
            padding: '16px',
          }}>
            <div style={{ fontSize: '13px', fontWeight: 510, color: 'var(--text-primary)', marginBottom: '8px' }}>
              摘要
            </div>
            <div style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: '1.7' }}>
              <span style={{ fontWeight: 510, color: 'var(--text-primary)', marginRight: '6px' }}>
                {report.score_label}
              </span>
              {report.summary}
            </div>
            <div style={{ marginTop: '8px', fontSize: '11px', color: 'var(--text-muted)' }}>
              生成时间: {report.created_at}
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
