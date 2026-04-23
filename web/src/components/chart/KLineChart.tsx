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
}

const DEFAULT_TOGGLE: IndicatorToggle = {
  ma: true,
  boll: false,
  volume: true,
  macd: false,
  rsi: false,
};

interface Props {
  stockCode: string;
  stockName?: string;
}

export default function KLineChart({ stockCode, stockName }: Props) {
  const mainRef = useRef<HTMLDivElement>(null);
  const macdRef = useRef<HTMLDivElement>(null);
  const rsiRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const macdChartRef = useRef<IChartApi | null>(null);
  const rsiChartRef = useRef<IChartApi | null>(null);

  const [period, setPeriod] = useState<Period>('daily');
  const [indicators, setIndicators] = useState<IndicatorToggle>(DEFAULT_TOGGLE);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState<KLineDataPoint[]>([]);
  const [error, setError] = useState('');

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
      // API returns chronological (ASC) order
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

  // Render chart when data changes
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
    chartRef.current = null;
    macdChartRef.current = null;
    rsiChartRef.current = null;
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

    for (const d of data) {
      const t = d.date as Time;
      candleData.push({ time: t, open: d.open, high: d.high, low: d.low, close: d.close });

      // Volume: color based on close vs open
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

      if (d.rsi_12 != null) rsiData.push({ time: t, value: d.rsi_12 });
    }

    // --- Main chart (candlestick + MA/BOLL) ---
    if (mainRef.current) {
      const mainHeight = indicators.macd || indicators.rsi ? 320 : 480;
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

      // Candlestick
      const candleSeries = chart.addSeries(CandlestickSeries, {
        upColor: '#ef4444',
        downColor: '#22c55e',
        borderUpColor: '#ef4444',
        borderDownColor: '#22c55e',
        wickUpColor: '#ef4444',
        wickDownColor: '#22c55e',
      });
      candleSeries.setData(candleData);

      // Volume (on main chart, separate price scale)
      if (indicators.volume) {
        const volSeries = chart.addSeries(HistogramSeries, {
          priceFormat: { type: 'volume' },
          priceScaleId: 'volume',
        });
        chart.priceScale('volume').applyOptions({
          scaleMargins: { top: 0.8, bottom: 0 },
        });
        volSeries.setData(volumeData);
      }

      // MA lines
      if (indicators.ma) {
        if (ma5Data.length) chart.addSeries(LineSeries, { color: '#f59e0b', lineWidth: 1, title: 'MA5' }).setData(ma5Data);
        if (ma10Data.length) chart.addSeries(LineSeries, { color: '#3b82f6', lineWidth: 1, title: 'MA10' }).setData(ma10Data);
        if (ma20Data.length) chart.addSeries(LineSeries, { color: '#a855f7', lineWidth: 1, title: 'MA20' }).setData(ma20Data);
        if (ma60Data.length) chart.addSeries(LineSeries, { color: '#06b6d4', lineWidth: 1, title: 'MA60' }).setData(ma60Data);
      }

      // BOLL bands
      if (indicators.boll) {
        if (bollUpper.length) chart.addSeries(LineSeries, { color: 'rgba(239,68,68,0.5)', lineWidth: 1, lineStyle: 2 }).setData(bollUpper);
        if (bollMiddle.length) chart.addSeries(LineSeries, { color: 'rgba(156,163,175,0.6)', lineWidth: 1 }).setData(bollMiddle);
        if (bollLower.length) chart.addSeries(LineSeries, { color: 'rgba(34,197,94,0.5)', lineWidth: 1, lineStyle: 2 }).setData(bollLower);
      }

      chart.timeScale().fitContent();
    }

    // --- MACD chart ---
    if (indicators.macd && macdRef.current) {
      const macdChart = createChart(macdRef.current, {
        width: macdRef.current.clientWidth,
        height: 120,
        layout: { background: { type: ColorType.Solid, color: bgColor }, textColor, fontSize: 11 },
        grid: { vertLines: { color: gridColor }, horzLines: { color: gridColor } },
        rightPriceScale: { borderColor: gridColor },
        timeScale: { borderColor: gridColor, timeVisible: false },
      });
      macdChartRef.current = macdChart;

      if (macdHist.length) macdChart.addSeries(HistogramSeries, { priceFormat: { type: 'price', precision: 3 } }).setData(macdHist);
      if (macdDif.length) macdChart.addSeries(LineSeries, { color: '#f59e0b', lineWidth: 1 }).setData(macdDif);
      if (macdDea.length) macdChart.addSeries(LineSeries, { color: '#3b82f6', lineWidth: 1 }).setData(macdDea);
      macdChart.timeScale().fitContent();
    }

    // --- RSI chart ---
    if (indicators.rsi && rsiRef.current) {
      const rsiChart = createChart(rsiRef.current, {
        width: rsiRef.current.clientWidth,
        height: 100,
        layout: { background: { type: ColorType.Solid, color: bgColor }, textColor, fontSize: 11 },
        grid: { vertLines: { color: gridColor }, horzLines: { color: gridColor } },
        rightPriceScale: { borderColor: gridColor },
        timeScale: { borderColor: gridColor, timeVisible: false },
      });
      rsiChartRef.current = rsiChart;

      if (rsiData.length) rsiChart.addSeries(LineSeries, { color: '#a855f7', lineWidth: 1 }).setData(rsiData);
      rsiChart.timeScale().fitContent();
    }
  }

  // Resize handler
  useEffect(() => {
    const handleResize = () => {
      chartRef.current?.applyOptions({ width: mainRef.current?.clientWidth });
      macdChartRef.current?.applyOptions({ width: macdRef.current?.clientWidth });
      rsiChartRef.current?.applyOptions({ width: rsiRef.current?.clientWidth });
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const toggleBtn = (key: keyof IndicatorToggle, label: string, color: string) => (
    <button
      onClick={() => setIndicators(prev => ({ ...prev, [key]: !prev[key] }))}
      style={{
        fontSize: '11px',
        padding: '3px 10px',
        borderRadius: '4px',
        border: indicators[key] ? `1px solid ${color}` : '1px solid var(--border-subtle)',
        background: indicators[key] ? `${color}18` : 'transparent',
        color: indicators[key] ? color : 'var(--text-muted)',
        cursor: 'pointer',
        fontWeight: indicators[key] ? 510 : 400,
      }}
    >
      {label}
    </button>
  );

  const periodBtn = (p: Period, label: string) => (
    <button
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
      <div style={{ display: 'flex', gap: '6px', marginBottom: '12px', flexWrap: 'wrap' }}>
        {toggleBtn('ma', 'MA', '#3b82f6')}
        {toggleBtn('boll', 'BOLL', '#f59e0b')}
        {toggleBtn('volume', 'VOL', '#6b7280')}
        {toggleBtn('macd', 'MACD', '#a855f7')}
        {toggleBtn('rsi', 'RSI', '#06b6d4')}
      </div>

      {/* Chart area */}
      {loading && <div style={{ color: 'var(--text-muted)', fontSize: '12px', padding: '40px 0', textAlign: 'center' }}>加载中...</div>}
      {error && <div style={{ color: 'var(--text-muted)', fontSize: '12px', padding: '40px 0', textAlign: 'center' }}>{error}</div>}
      <div ref={mainRef} style={{ display: data.length > 0 ? 'block' : 'none' }} />
      {indicators.macd && <div ref={macdRef} style={{ display: data.length > 0 ? 'block' : 'none', marginTop: '2px' }} />}
      {indicators.rsi && <div ref={rsiRef} style={{ display: data.length > 0 ? 'block' : 'none', marginTop: '2px' }} />}
    </div>
  );
}
