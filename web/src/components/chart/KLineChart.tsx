'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import {
  createChart,
  ColorType,
  CrosshairMode,
  CandlestickSeries,
  LineSeries,
  HistogramSeries,
  type IChartApi,
  type CandlestickData,
  type LineData,
  type HistogramData,
  type Time,
} from 'lightweight-charts';
import { chartApi, type KLineDataPoint } from '@/lib/chart-api';

type Period = 'daily' | 'weekly' | 'monthly';

interface IndicatorToggle {
  ma: boolean;
  boll: boolean;
  volume: boolean;
  macd: boolean;
  rsi: boolean;
  kdj: boolean;
}

const DEFAULT_TOGGLE: IndicatorToggle = {
  ma: true,
  boll: false,
  volume: true,
  macd: false,
  rsi: false,
  kdj: false,
};

interface Props {
  stockCode: string;
  stockName?: string;
}

// ---------------------------------------------------------------------------
// Indicator interpretation text
// ---------------------------------------------------------------------------

function getInterpretation(
  key: keyof IndicatorToggle,
  period: Period,
  data: KLineDataPoint[],
): string | null {
  if (data.length === 0) return null;

  const periodLabel = period === 'daily' ? '日' : period === 'weekly' ? '周' : '月';
  const windowLabel =
    period === 'daily' ? '近5日' : period === 'weekly' ? '近4周' : '近3个月';
  // Use the last N bars based on period
  const n = period === 'daily' ? 5 : period === 'weekly' ? 4 : 3;
  const recent = data.slice(-n);
  const last = data[data.length - 1];
  if (!last) return null;

  if (key === 'ma') {
    const ma5 = last.ma5;
    const ma20 = last.ma20;
    const close = last.close;
    if (ma5 == null || ma20 == null) return `MA：${windowLabel}数据不足，无法判断趋势。`;
    const aboveMa5 = close > ma5;
    const aboveMa20 = close > ma20;
    const goldenCross = ma5 > ma20;
    let trend = '';
    if (aboveMa5 && aboveMa20 && goldenCross) {
      trend = `收盘价（${close.toFixed(2)}）站上MA5（${ma5.toFixed(2)}）和MA20（${ma20.toFixed(2)}），短期多头排列，趋势偏强。`;
    } else if (!aboveMa5 && !aboveMa20 && !goldenCross) {
      trend = `收盘价（${close.toFixed(2)}）跌破MA5（${ma5.toFixed(2)}）和MA20（${ma20.toFixed(2)}），短期空头排列，趋势偏弱。`;
    } else if (aboveMa5 && !aboveMa20) {
      trend = `收盘价（${close.toFixed(2)}）站上MA5（${ma5.toFixed(2)}）但仍低于MA20（${ma20.toFixed(2)}），短期反弹但中期压力仍存。`;
    } else {
      trend = `均线多空交织，${periodLabel}K趋势方向尚不明确。`;
    }
    return `MA（${windowLabel}）：${trend}`;
  }

  if (key === 'boll') {
    const upper = last.boll_upper;
    const middle = last.boll_middle;
    const lower = last.boll_lower;
    const close = last.close;
    if (upper == null || middle == null || lower == null) return `BOLL：${windowLabel}数据不足。`;
    const bandwidth = ((upper - lower) / middle * 100).toFixed(1);
    let pos = '';
    if (close > upper) pos = `收盘价（${close.toFixed(2)}）突破上轨（${upper.toFixed(2)}），短期超买，注意回落风险。`;
    else if (close < lower) pos = `收盘价（${close.toFixed(2)}）跌破下轨（${lower.toFixed(2)}），短期超卖，可关注反弹机会。`;
    else if (close > middle) pos = `收盘价（${close.toFixed(2)}）运行在中轨（${middle.toFixed(2)}）上方，趋势偏多。`;
    else pos = `收盘价（${close.toFixed(2)}）运行在中轨（${middle.toFixed(2)}）下方，趋势偏空。`;
    return `BOLL（${windowLabel}）：${pos} 带宽 ${bandwidth}%${parseFloat(bandwidth) < 5 ? '，布林带收窄，可能面临方向选择。' : '。'}`;
  }

  if (key === 'macd') {
    const dif = last.macd_dif;
    const dea = last.macd_dea;
    const hist = last.macd_histogram;
    if (dif == null || dea == null || hist == null) return `MACD：${windowLabel}数据不足。`;
    const goldCross = dif > dea;
    const aboveZero = dif > 0;
    let sig = '';
    if (goldCross && aboveZero) sig = `DIF（${dif.toFixed(3)}）金叉DEA（${dea.toFixed(3)}）且位于零轴上方，多头动能强劲。`;
    else if (goldCross && !aboveZero) sig = `DIF（${dif.toFixed(3)}）金叉DEA（${dea.toFixed(3)}），但仍处零轴下方，反弹力度待观察。`;
    else if (!goldCross && !aboveZero) sig = `DIF（${dif.toFixed(3)}）死叉DEA（${dea.toFixed(3)}）且位于零轴下方，空头动能较强。`;
    else sig = `DIF（${dif.toFixed(3)}）死叉DEA（${dea.toFixed(3)}），虽在零轴上方但动能走弱。`;

    // Check recent histogram direction
    const recentHist = recent.map(d => d.macd_histogram).filter(v => v != null) as number[];
    const histTrend = recentHist.length >= 2
      ? (recentHist[recentHist.length - 1] > recentHist[0] ? '柱状图持续放大' : '柱状图持续缩小')
      : '';
    return `MACD（${windowLabel}）：${sig}${histTrend ? ` ${histTrend}。` : ''}`;
  }

  if (key === 'rsi') {
    const rsi = last.rsi_12;
    if (rsi == null) return `RSI：${windowLabel}数据不足。`;
    let level = '';
    if (rsi >= 70) level = `RSI-12（${rsi.toFixed(1)}）已进入超买区域（>70），短期注意获利了结风险。`;
    else if (rsi <= 30) level = `RSI-12（${rsi.toFixed(1)}）已进入超卖区域（<30），短期可能存在反弹机会。`;
    else if (rsi >= 50) level = `RSI-12（${rsi.toFixed(1)}）位于强势区间（50-70），多头动能尚存。`;
    else level = `RSI-12（${rsi.toFixed(1)}）位于弱势区间（30-50），多头动能偏弱。`;
    return `RSI（${windowLabel}）：${level}`;
  }

  if (key === 'kdj') {
    const k = last.kdj_k;
    const d = last.kdj_d;
    const j = last.kdj_j;
    if (k == null || d == null || j == null) return `KDJ：${windowLabel}数据不足。`;
    let sig = '';
    if (k > d && j > 80) sig = `K（${k.toFixed(1)}）上穿D（${d.toFixed(1)}），J值（${j.toFixed(1)}）偏高，短期存在超买迹象。`;
    else if (k < d && j < 20) sig = `K（${k.toFixed(1)}）下穿D（${d.toFixed(1)}），J值（${j.toFixed(1)}）偏低，短期可能超卖反弹。`;
    else if (k > d) sig = `K（${k.toFixed(1)}）高于D（${d.toFixed(1)}），KDJ呈多头排列，短期偏强。`;
    else sig = `K（${k.toFixed(1)}）低于D（${d.toFixed(1)}），KDJ呈空头排列，短期偏弱。`;
    return `KDJ（${windowLabel}）：${sig}`;
  }

  return null;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function KLineChart({ stockCode, stockName }: Props) {
  const mainRef = useRef<HTMLDivElement>(null);
  const macdRef = useRef<HTMLDivElement>(null);
  const rsiRef = useRef<HTMLDivElement>(null);
  const kdjRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const macdChartRef = useRef<IChartApi | null>(null);
  const rsiChartRef = useRef<IChartApi | null>(null);
  const kdjChartRef = useRef<IChartApi | null>(null);

  const [period, setPeriod] = useState<Period>('daily');
  const [indicators, setIndicators] = useState<IndicatorToggle>(DEFAULT_TOGGLE);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<KLineDataPoint[]>([]);
  const [error, setError] = useState('');
  const [activeInterpretation, setActiveInterpretation] = useState<keyof IndicatorToggle | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const res = await chartApi.combined(stockCode, period, 500);
      const rows = res.data.data;
      if (!rows || rows.length === 0) {
        setError('暂无数据');
        setData([]);
        return;
      }
      setData(rows);
    } catch {
      setError('加载失败');
      setData([]);
    } finally {
      setLoading(false);
    }
  }, [stockCode, period]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (data.length === 0) return;
    renderChart();
    return () => cleanup();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, indicators]);

  function cleanup() {
    chartRef.current?.remove();
    macdChartRef.current?.remove();
    rsiChartRef.current?.remove();
    kdjChartRef.current?.remove();
    chartRef.current = null;
    macdChartRef.current = null;
    rsiChartRef.current = null;
    kdjChartRef.current = null;
  }

  function renderChart() {
    cleanup();

    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    const bgColor = isDark ? '#0d1117' : '#ffffff';
    const textColor = isDark ? '#9ca3af' : '#6b7280';
    const gridColor = isDark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.04)';

    const candleData: CandlestickData<Time>[] = [];
    const volumeData: HistogramData<Time>[] = [];
    const ma5Data: LineData<Time>[] = [];
    const ma10Data: LineData<Time>[] = [];
    const ma20Data: LineData<Time>[] = [];
    const ma60Data: LineData<Time>[] = [];
    const bollUpper: LineData<Time>[] = [];
    const bollMiddle: LineData<Time>[] = [];
    const bollLower: LineData<Time>[] = [];
    const macdHist: HistogramData<Time>[] = [];
    const macdDif: LineData<Time>[] = [];
    const macdDea: LineData<Time>[] = [];
    const rsiData: LineData<Time>[] = [];
    const rsi70Line: LineData<Time>[] = [];
    const rsi50Line: LineData<Time>[] = [];
    const rsi30Line: LineData<Time>[] = [];
    const kdjK: LineData<Time>[] = [];
    const kdjD: LineData<Time>[] = [];
    const kdjJ: LineData<Time>[] = [];
    const kdj80Line: LineData<Time>[] = [];
    const kdj20Line: LineData<Time>[] = [];

    for (const d of data) {
      const t = d.date as Time;
      candleData.push({ time: t, open: d.open, high: d.high, low: d.low, close: d.close });

      const volColor = d.close >= d.open
        ? (isDark ? 'rgba(239,68,68,0.5)' : 'rgba(239,68,68,0.4)')
        : (isDark ? 'rgba(34,197,94,0.5)' : 'rgba(34,197,94,0.4)');
      volumeData.push({ time: t, value: d.volume, color: volColor });

      if (d.ma5 != null) ma5Data.push({ time: t, value: d.ma5 });
      if (d.ma10 != null) ma10Data.push({ time: t, value: d.ma10 });
      if (d.ma20 != null) ma20Data.push({ time: t, value: d.ma20 });
      if (d.ma60 != null) ma60Data.push({ time: t, value: d.ma60 });

      if (d.boll_upper != null) bollUpper.push({ time: t, value: d.boll_upper });
      if (d.boll_middle != null) bollMiddle.push({ time: t, value: d.boll_middle });
      if (d.boll_lower != null) bollLower.push({ time: t, value: d.boll_lower });

      if (d.macd_histogram != null) {
        const histColor = d.macd_histogram >= 0
          ? (isDark ? '#ef4444' : '#dc2626')
          : (isDark ? '#22c55e' : '#16a34a');
        macdHist.push({ time: t, value: d.macd_histogram, color: histColor });
      }
      if (d.macd_dif != null) macdDif.push({ time: t, value: d.macd_dif });
      if (d.macd_dea != null) macdDea.push({ time: t, value: d.macd_dea });

      if (d.rsi_12 != null) {
        rsiData.push({ time: t, value: d.rsi_12 });
        rsi70Line.push({ time: t, value: 70 });
        rsi50Line.push({ time: t, value: 50 });
        rsi30Line.push({ time: t, value: 30 });
      }

      if (d.kdj_k != null) kdjK.push({ time: t, value: d.kdj_k });
      if (d.kdj_d != null) kdjD.push({ time: t, value: d.kdj_d });
      if (d.kdj_j != null) kdjJ.push({ time: t, value: d.kdj_j });
      if (d.kdj_k != null) {
        kdj80Line.push({ time: t, value: 80 });
        kdj20Line.push({ time: t, value: 20 });
      }
    }

    const hasSubChart = indicators.macd || indicators.rsi || indicators.kdj;
    const mainHeight = hasSubChart ? 320 : 480;

    // --- Main chart ---
    if (mainRef.current) {
      const chart = createChart(mainRef.current, {
        width: mainRef.current.clientWidth,
        height: mainHeight,
        layout: {
          background: { type: ColorType.Solid, color: bgColor },
          textColor,
          fontSize: 11,
        },
        grid: {
          vertLines: { color: gridColor },
          horzLines: { color: gridColor },
        },
        crosshair: { mode: CrosshairMode.Normal },
        rightPriceScale: { borderColor: gridColor },
        timeScale: { borderColor: gridColor, timeVisible: false },
      });
      chartRef.current = chart;

      chart.addSeries(CandlestickSeries, {
        upColor: '#ef4444',
        downColor: '#22c55e',
        borderUpColor: '#ef4444',
        borderDownColor: '#22c55e',
        wickUpColor: '#ef4444',
        wickDownColor: '#22c55e',
      }).setData(candleData);

      if (indicators.volume) {
        const volSeries = chart.addSeries(HistogramSeries, {
          priceFormat: { type: 'volume' },
          priceScaleId: 'volume',
        });
        chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
        volSeries.setData(volumeData);
      }

      if (indicators.ma) {
        if (ma5Data.length) chart.addSeries(LineSeries, { color: '#f59e0b', lineWidth: 1, title: 'MA5' }).setData(ma5Data);
        if (ma10Data.length) chart.addSeries(LineSeries, { color: '#3b82f6', lineWidth: 1, title: 'MA10' }).setData(ma10Data);
        if (ma20Data.length) chart.addSeries(LineSeries, { color: '#a855f7', lineWidth: 1, title: 'MA20' }).setData(ma20Data);
        if (ma60Data.length) chart.addSeries(LineSeries, { color: '#06b6d4', lineWidth: 1, title: 'MA60' }).setData(ma60Data);
      }

      if (indicators.boll) {
        // Solid, clearly visible BOLL lines
        if (bollUpper.length) chart.addSeries(LineSeries, {
          color: isDark ? '#f87171' : '#ef4444', lineWidth: 1, lineStyle: 1, title: 'Upper',
        }).setData(bollUpper);
        if (bollMiddle.length) chart.addSeries(LineSeries, {
          color: isDark ? '#d1d5db' : '#6b7280', lineWidth: 1, lineStyle: 0, title: 'Mid',
        }).setData(bollMiddle);
        if (bollLower.length) chart.addSeries(LineSeries, {
          color: isDark ? '#4ade80' : '#22c55e', lineWidth: 1, lineStyle: 1, title: 'Lower',
        }).setData(bollLower);
      }

      chart.timeScale().fitContent();
    }

    // --- MACD sub-chart ---
    if (indicators.macd && macdRef.current) {
      const macdChart = createChart(macdRef.current, {
        width: macdRef.current.clientWidth,
        height: 110,
        layout: { background: { type: ColorType.Solid, color: bgColor }, textColor, fontSize: 10 },
        grid: { vertLines: { color: gridColor }, horzLines: { color: gridColor } },
        rightPriceScale: { borderColor: gridColor },
        timeScale: { borderColor: gridColor, timeVisible: false },
      });
      macdChartRef.current = macdChart;

      if (macdHist.length) macdChart.addSeries(HistogramSeries, {
        priceFormat: { type: 'price', precision: 3 },
      }).setData(macdHist);
      if (macdDif.length) macdChart.addSeries(LineSeries, {
        color: '#f59e0b', lineWidth: 1, title: 'DIF',
      }).setData(macdDif);
      if (macdDea.length) macdChart.addSeries(LineSeries, {
        color: '#3b82f6', lineWidth: 1, title: 'DEA',
      }).setData(macdDea);
      macdChart.timeScale().fitContent();
    }

    // --- RSI sub-chart ---
    if (indicators.rsi && rsiRef.current) {
      const rsiChart = createChart(rsiRef.current, {
        width: rsiRef.current.clientWidth,
        height: 100,
        layout: { background: { type: ColorType.Solid, color: bgColor }, textColor, fontSize: 10 },
        grid: { vertLines: { color: gridColor }, horzLines: { color: gridColor } },
        rightPriceScale: { borderColor: gridColor },
        timeScale: { borderColor: gridColor, timeVisible: false },
      });
      rsiChartRef.current = rsiChart;

      // Reference lines first (below RSI line)
      if (rsi70Line.length) rsiChart.addSeries(LineSeries, {
        color: isDark ? 'rgba(239,68,68,0.35)' : 'rgba(239,68,68,0.4)',
        lineWidth: 1, lineStyle: 1,
      }).setData(rsi70Line);
      if (rsi50Line.length) rsiChart.addSeries(LineSeries, {
        color: isDark ? 'rgba(156,163,175,0.3)' : 'rgba(107,114,128,0.3)',
        lineWidth: 1, lineStyle: 1,
      }).setData(rsi50Line);
      if (rsi30Line.length) rsiChart.addSeries(LineSeries, {
        color: isDark ? 'rgba(34,197,94,0.35)' : 'rgba(34,197,94,0.4)',
        lineWidth: 1, lineStyle: 1,
      }).setData(rsi30Line);
      // RSI line on top
      if (rsiData.length) rsiChart.addSeries(LineSeries, {
        color: '#a855f7', lineWidth: 1, title: 'RSI12',
      }).setData(rsiData);
      rsiChart.timeScale().fitContent();
    }

    // --- KDJ sub-chart ---
    if (indicators.kdj && kdjRef.current) {
      const kdjChart = createChart(kdjRef.current, {
        width: kdjRef.current.clientWidth,
        height: 100,
        layout: { background: { type: ColorType.Solid, color: bgColor }, textColor, fontSize: 10 },
        grid: { vertLines: { color: gridColor }, horzLines: { color: gridColor } },
        rightPriceScale: { borderColor: gridColor },
        timeScale: { borderColor: gridColor, timeVisible: false },
      });
      kdjChartRef.current = kdjChart;

      if (kdj80Line.length) kdjChart.addSeries(LineSeries, {
        color: isDark ? 'rgba(239,68,68,0.3)' : 'rgba(239,68,68,0.35)',
        lineWidth: 1, lineStyle: 1,
      }).setData(kdj80Line);
      if (kdj20Line.length) kdjChart.addSeries(LineSeries, {
        color: isDark ? 'rgba(34,197,94,0.3)' : 'rgba(34,197,94,0.35)',
        lineWidth: 1, lineStyle: 1,
      }).setData(kdj20Line);
      if (kdjK.length) kdjChart.addSeries(LineSeries, { color: '#f59e0b', lineWidth: 1, title: 'K' }).setData(kdjK);
      if (kdjD.length) kdjChart.addSeries(LineSeries, { color: '#3b82f6', lineWidth: 1, title: 'D' }).setData(kdjD);
      if (kdjJ.length) kdjChart.addSeries(LineSeries, { color: '#ef4444', lineWidth: 1, title: 'J' }).setData(kdjJ);
      kdjChart.timeScale().fitContent();
    }
  }

  // Resize handler
  useEffect(() => {
    const handleResize = () => {
      chartRef.current?.applyOptions({ width: mainRef.current?.clientWidth });
      macdChartRef.current?.applyOptions({ width: macdRef.current?.clientWidth });
      rsiChartRef.current?.applyOptions({ width: rsiRef.current?.clientWidth });
      kdjChartRef.current?.applyOptions({ width: kdjRef.current?.clientWidth });
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Toggle indicator and update active interpretation panel
  function handleToggle(key: keyof IndicatorToggle) {
    const nextOn = !indicators[key];
    setIndicators(prev => ({ ...prev, [key]: nextOn }));
    if (nextOn) {
      setActiveInterpretation(key);
    } else if (activeInterpretation === key) {
      setActiveInterpretation(null);
    }
  }

  const interpretationText = activeInterpretation && indicators[activeInterpretation]
    ? getInterpretation(activeInterpretation, period, data)
    : null;

  const toggleBtn = (key: keyof IndicatorToggle, label: string, color: string) => (
    <button
      key={key}
      onClick={() => handleToggle(key)}
      style={{
        fontSize: '11px',
        padding: '3px 10px',
        borderRadius: '4px',
        border: indicators[key]
          ? `1px solid ${color}`
          : activeInterpretation === key
            ? `1px solid ${color}80`
            : '1px solid var(--border-subtle)',
        background: indicators[key] ? `${color}18` : 'transparent',
        color: indicators[key] ? color : 'var(--text-muted)',
        cursor: 'pointer',
        fontWeight: indicators[key] ? 510 : 400,
        transition: 'all 0.15s',
      }}
    >
      {label}
    </button>
  );

  const periodBtn = (p: Period, label: string) => (
    <button
      key={p}
      onClick={() => setPeriod(p)}
      style={{
        fontSize: '11px',
        padding: '3px 12px',
        borderRadius: '4px',
        border: period === p ? '1px solid var(--accent)' : '1px solid var(--border-subtle)',
        background: period === p ? 'rgba(94,106,210,0.12)' : 'transparent',
        color: period === p ? 'var(--accent)' : 'var(--text-muted)',
        cursor: 'pointer',
        fontWeight: period === p ? 510 : 400,
      }}
    >
      {label}
    </button>
  );

  const lastData = data[data.length - 1];
  const prevData = data[data.length - 2];
  const pctChange = lastData && prevData ? ((lastData.close - prevData.close) / prevData.close * 100).toFixed(2) : '--';
  const isUp = lastData && prevData ? lastData.close >= prevData.close : true;

  // Sub-chart label pill
  const subLabel = (text: string) => (
    <div style={{
      fontSize: '10px',
      color: 'var(--text-muted)',
      padding: '1px 6px',
      marginBottom: '1px',
      marginTop: '6px',
    }}>
      {text}
    </div>
  );

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '15px', fontWeight: 600, color: 'var(--text-primary)' }}>
          {stockName || stockCode}
        </span>
        {lastData && (
          <>
            <span style={{ fontSize: '18px', fontWeight: 700, fontFamily: 'var(--font-geist-mono)', color: isUp ? 'var(--up)' : 'var(--down)' }}>
              {lastData.close.toFixed(2)}
            </span>
            <span style={{ fontSize: '12px', color: isUp ? 'var(--up)' : 'var(--down)' }}>
              {isUp ? '+' : ''}{pctChange}%
            </span>
          </>
        )}

        <div style={{ flex: 1 }} />

        {/* Period toggle */}
        <div style={{ display: 'flex', gap: '4px' }}>
          {periodBtn('daily', '日K')}
          {periodBtn('weekly', '周K')}
          {periodBtn('monthly', '月K')}
        </div>
      </div>

      {/* Indicator toggles */}
      <div style={{ display: 'flex', gap: '6px', marginBottom: '10px', flexWrap: 'wrap' }}>
        {toggleBtn('ma', 'MA', '#3b82f6')}
        {toggleBtn('boll', 'BOLL', '#f59e0b')}
        {toggleBtn('volume', 'VOL', '#6b7280')}
        {toggleBtn('macd', 'MACD', '#a855f7')}
        {toggleBtn('rsi', 'RSI', '#06b6d4')}
        {toggleBtn('kdj', 'KDJ', '#f97316')}
      </div>

      {/* Indicator interpretation panel */}
      {interpretationText && (
        <div style={{
          fontSize: '12px',
          lineHeight: '1.6',
          color: 'var(--text-secondary)',
          background: 'var(--bg-elevated)',
          border: '1px solid var(--border-subtle)',
          borderRadius: '6px',
          padding: '8px 12px',
          marginBottom: '10px',
        }}>
          {interpretationText}
        </div>
      )}

      {/* Chart area */}
      {loading && (
        <div style={{ color: 'var(--text-muted)', fontSize: '12px', padding: '40px 0', textAlign: 'center' }}>
          加载中...
        </div>
      )}
      {error && (
        <div style={{ color: 'var(--text-muted)', fontSize: '12px', padding: '40px 0', textAlign: 'center' }}>
          {error}
        </div>
      )}

      <div ref={mainRef} style={{ display: data.length > 0 ? 'block' : 'none' }} />

      {indicators.macd && (
        <>
          {subLabel('MACD  DIF  DEA')}
          <div ref={macdRef} style={{ display: data.length > 0 ? 'block' : 'none', marginTop: '1px' }} />
        </>
      )}
      {indicators.rsi && (
        <>
          {subLabel('RSI-12    70 / 50 / 30')}
          <div ref={rsiRef} style={{ display: data.length > 0 ? 'block' : 'none', marginTop: '1px' }} />
        </>
      )}
      {indicators.kdj && (
        <>
          {subLabel('KDJ    K  D  J    80 / 20')}
          <div ref={kdjRef} style={{ display: data.length > 0 ? 'block' : 'none', marginTop: '1px' }} />
        </>
      )}
    </div>
  );
}
