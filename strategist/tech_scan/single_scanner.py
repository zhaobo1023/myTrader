# -*- coding: utf-8 -*-
"""
单股技术面扫描器

复用 tech_scan 模块的 DataFetcher / IndicatorCalculator / SignalDetector，
提供单只股票的快速技术面扫描，输出纯文本报告。

CLI:
    DB_ENV=online python -m strategist.tech_scan.single_scanner --stock 688386
    DB_ENV=online python -m strategist.tech_scan.single_scanner --stock 688386.SH --lookback 300
"""
import argparse
import json
import sys
import os
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Optional

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from strategist.tech_scan.data_fetcher import DataFetcher
from strategist.tech_scan.indicator_calculator import IndicatorCalculator
from strategist.tech_scan.signal_detector import SignalDetector, SignalLevel, get_sector
from strategist.tech_scan.chart_generator import ChartGenerator
from strategist.tech_scan.report_engine import ReportEngine


def _fmt_code(raw: str) -> str:
    """Normalize stock code to XXXXXX.SH/SZ format."""
    raw = raw.strip()
    if '.' in raw:
        return raw.upper()
    if raw.startswith('6') or raw.startswith('9'):
        return f'{raw}.SH'
    return f'{raw}.SZ'


class SingleStockScanner:
    """Single stock technical scanner."""

    def __init__(self, env: str = 'online', lookback_days: int = 300, generate_chart: bool = False, output_dir: str = 'output/single_scan'):
        self.env = env
        self.lookback_days = lookback_days
        self.fetcher = DataFetcher(env=env)
        self.calculator = IndicatorCalculator()
        self.detector = SignalDetector()
        self.generate_chart = generate_chart
        self.output_dir = output_dir
        if generate_chart:
            from pathlib import Path
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            self.chart_generator = ChartGenerator(output_dir)

    def scan(self, code: str, output_format: str = 'html', stock_name: str = None) -> str:
        """
        Scan a single stock and return a report.

        Args:
            code: stock code, e.g. '688386' or '688386.SH'
            output_format: 'html', 'markdown' or 'text' (default: html)
            stock_name: stock name (optional, will fetch if not provided)

        Returns:
            Report string in specified format.
        """
        code = _fmt_code(code)
        df = self.fetcher.fetch_daily_data([code], lookback_days=self.lookback_days)

        if df.empty:
            return f'[RED] No data found for {code} in {self.env} DB.'

        df = self.calculator.calculate_all(df)

        # Fetch RPS data
        try:
            rps_df = self.fetcher.fetch_rps_data([code])
            if not rps_df.empty:
                rps_cols = ['stock_code', 'trade_date']
                for col in ['rps_120', 'rps_250', 'rps_slope']:
                    if col in rps_df.columns:
                        rps_cols.append(col)
                df = df.merge(rps_df[rps_cols], on=['stock_code', 'trade_date'], how='left')
        except Exception:
            pass  # RPS is optional, don't fail if unavailable

        latest = df.iloc[-1]
        latest_date = latest['trade_date'].strftime('%Y-%m-%d')

        # Fetch stock name if not provided
        if stock_name is None:
            stock_name = self._fetch_stock_name(code)
        
        # Generate chart if requested
        chart_path = None
        if self.generate_chart:
            analysis_result = self._build_analysis_result(latest, code, stock_name)
            try:
                chart_path = self.chart_generator.generate_chart(
                    df=df,
                    stock_code=code,
                    stock_name=stock_name,
                    analysis_result=analysis_result,
                    scan_date=datetime.now()
                )
            except Exception as e:
                print(f'Warning: Chart generation failed: {e}')
        
        # ReportEngine analysis for v2.0
        engine = ReportEngine()
        score_result = engine.calc_score(latest)
        ma_pattern = engine.classify_ma_pattern(latest)
        macd_interp = engine.interpret_macd(latest)
        rsi_val = latest.get('rsi')
        rsi_interp = engine.interpret_rsi(rsi_val) if rsi_val is not None and not pd.isna(rsi_val) else None
        kdj_interp = engine.interpret_kdj(latest)
        boll_interp = engine.interpret_boll(latest)
        vp_quadrant = engine.analyze_volume_price(latest)
        divergence = self.detector.detect_macd_divergence(df) if len(df) >= 20 else {'type': '无背驰', 'confidence': '低', 'description': '数据不足'}
        kdj_signals = self.detector.detect_kdj_signals(latest)
        alerts = engine.detect_alerts(latest, divergence, kdj_signals)
        supports, resistances = engine.calc_key_levels(latest, df)
        recent_features = engine.analyze_recent_pattern(df)

        # Extract RPS values (use most recent non-NaN, RPS may lag 1-2 days)
        rps_120 = rps_250 = rps_slope = None
        for col in ['rps_120', 'rps_250', 'rps_slope']:
            if col in df.columns:
                valid = df[col].dropna()
                if not valid.empty:
                    val = valid.iloc[-1]
                    if col == 'rps_120':
                        rps_120 = val
                    elif col == 'rps_250':
                        rps_250 = val
                    else:
                        rps_slope = val

        if output_format == 'html':
            return self._generate_html_report(
                code, stock_name, df, latest, latest_date, chart_path,
                score_result=score_result, ma_pattern=ma_pattern,
                macd_interp=macd_interp, rsi_interp=rsi_interp,
                kdj_interp=kdj_interp, boll_interp=boll_interp,
                vp_quadrant=vp_quadrant, divergence=divergence,
                kdj_signals=kdj_signals, alerts=alerts,
                supports=supports, resistances=resistances,
                recent_features=recent_features,
                rps_120=rps_120, rps_250=rps_250, rps_slope=rps_slope
            )
        elif output_format == 'markdown':
            return self._generate_markdown_report(code, stock_name, df, latest, latest_date, chart_path)
        else:
            return self._generate_text_report(code, stock_name, df, latest, latest_date)

    def _build_analysis_result(self, latest: pd.Series, code: str, stock_name: str) -> dict:
        """Build analysis result dict for chart generation."""
        signals = self.detector.detect_all(latest)
        trend = self.detector.get_trend_status(latest)
        stop_loss = self.detector.calc_stop_loss_price(latest, method='atr')
        if not stop_loss:
            stop_loss = self.detector.calc_stop_loss_price(latest, method='ma20')
        
        return {
            'code': code,
            'name': stock_name,
            'level': 'L1',
            'close': latest.get('close'),
            'pct_change': latest.get('pct_change'),
            'ma20': latest.get('ma20'),
            'ma60': latest.get('ma60'),
            'rps': latest.get('rps_250') if pd.notna(latest.get('rps_250')) else latest.get('rps'),
            'rsi': latest.get('rsi'),
            'trend': trend,
            'signals': signals,
            'row': latest,
            'cost': None,
            'pnl_pct': None,
            'has_breakdown': False,
            'has_divergence': False,
            'has_oversold': False,
            'has_shrink': False,
            'has_rps_decay': False,
            'is_danger': False,
            'stop_loss': stop_loss,
            'div_target': {},
            'sector': get_sector(code)
        }

    @staticmethod
    def _fetch_stock_name(code: str) -> str:
        """Fetch stock name: DB first, then akshare fallback."""
        # 1. Try DB
        try:
            from strategist.tech_scan.data_fetcher import DataFetcher
            fetcher = DataFetcher(env='online')
            name_map = fetcher.fetch_stock_names([code])
            name = name_map.get(code)
            if name and name != code:
                return name
        except Exception:
            pass

        # 2. Try akshare
        try:
            import akshare as ak
            pure_code = code.split('.')[0]
            df = ak.stock_individual_info_em(symbol=pure_code)
            if df is not None and not df.empty:
                row = df[df['item'] == '股票简称']
                if not row.empty:
                    return str(row['value'].iloc[0])
        except Exception:
            pass

        return code

    @staticmethod
    def _clean_for_json(data_list):
        """Replace NaN with None for JSON serialization."""
        cleaned = []
        for item in data_list:
            if isinstance(item, list):
                cleaned.append([None if (v is None or (isinstance(v, float) and np.isnan(v))) else v for v in item])
            else:
                cleaned.append(None if (item is None or (isinstance(item, float) and np.isnan(item))) else item)
        return cleaned

    def _build_echarts_html(self, df: pd.DataFrame, display_days: int = 120) -> str:
        """Generate ECharts interactive K-line chart HTML."""
        display_df = df.tail(display_days).copy()
        dates = display_df['trade_date'].dt.strftime('%m-%d').tolist()

        # OHLC data: [open, close, low, high] for ECharts
        ohlc_data = display_df.apply(
            lambda r: [round(r['open'], 2), round(r['close'], 2), round(r['low'], 2), round(r['high'], 2)],
            axis=1
        ).tolist()

        def clean_series(series):
            return [round(v, 2) if v is not None and not pd.isna(v) else None for v in series]

        ma5_data = clean_series(display_df.get('ma5', pd.Series()))
        ma20_data = clean_series(display_df.get('ma20', pd.Series()))
        ma60_data = clean_series(display_df.get('ma60', pd.Series()))
        ma250_data = clean_series(display_df.get('ma250', pd.Series()))

        boll_upper = clean_series(display_df.get('boll_upper', pd.Series()))
        boll_lower = clean_series(display_df.get('boll_lower', pd.Series()))

        volume_data = display_df.apply(
            lambda r: [
                int(r['volume']),
                round(r['pct_change'], 2) if not pd.isna(r.get('pct_change', 0)) else 0
            ],
            axis=1
        ).tolist()

        macd_dif_data = clean_series(display_df.get('macd_dif', pd.Series()))
        macd_dea_data = clean_series(display_df.get('macd_dea', pd.Series()))
        macd_hist_data = [round(v, 4) if v is not None and not pd.isna(v) else None for v in display_df.get('macd_hist', pd.Series())]

        # Serialize data arrays to JSON
        dates_json = json.dumps(dates)
        ohlc_json = json.dumps(self._clean_for_json(ohlc_data))
        ma5_json = json.dumps(ma5_data)
        ma20_json = json.dumps(ma20_data)
        ma60_json = json.dumps(ma60_data)
        ma250_json = json.dumps(ma250_data)
        boll_upper_json = json.dumps(boll_upper)
        boll_lower_json = json.dumps(boll_lower)
        volume_json = json.dumps(self._clean_for_json(volume_data))
        macd_dif_json = json.dumps(macd_dif_data)
        macd_dea_json = json.dumps(macd_dea_data)
        macd_hist_json = json.dumps(macd_hist_data)

        echarts_js = f'''
var chartDom = document.getElementById('kline_chart');
var myChart = echarts.init(chartDom);
var option = {{
    animation: false,
    tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'cross' }} }},
    legend: {{ data: ['MA5', 'MA20', 'MA60', 'MA250', 'BOLL\u4e0a\u8f68', 'BOLL\u4e0b\u8f68', 'MACD DIF', 'MACD DEA'], top: 10 }},
    grid: [
        {{ left: '8%', right: '3%', top: '8%', height: '55%' }},
        {{ left: '8%', right: '3%', top: '70%', height: '10%' }},
        {{ left: '8%', right: '3%', top: '84%', height: '14%' }}
    ],
    xAxis: [
        {{ type: 'category', data: {dates_json}, gridIndex: 0, show: false, boundaryGap: true }},
        {{ type: 'category', data: {dates_json}, gridIndex: 1, show: false, boundaryGap: true }},
        {{ type: 'category', data: {dates_json}, gridIndex: 2, boundaryGap: true }}
    ],
    yAxis: [
        {{ scale: true, gridIndex: 0, splitArea: {{ show: false }} }},
        {{ scale: true, gridIndex: 1, splitNumber: 2, splitArea: {{ show: false }} }},
        {{ scale: true, gridIndex: 2, splitNumber: 2, splitArea: {{ show: false }} }}
    ],
    dataZoom: [
        {{ type: 'inside', xAxisIndex: [0, 1, 2], start: 50, end: 100 }},
        {{ show: true, xAxisIndex: [0, 1, 2], type: 'slider', top: '95%', start: 50, end: 100 }}
    ],
    series: [
        {{ name: 'K\u7ebf', type: 'candlestick', xAxisIndex: 0, yAxisIndex: 0,
          data: {ohlc_json}, itemStyle: {{ color: '#e74c3c', color0: '#27ae60', borderColor: '#e74c3c', borderColor0: '#27ae60' }} }},
        {{ name: 'MA5', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: {ma5_json}, smooth: true, lineStyle: {{ width: 1 }}, symbol: 'none' }},
        {{ name: 'MA20', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: {ma20_json}, smooth: true, lineStyle: {{ width: 1 }}, symbol: 'none' }},
        {{ name: 'MA60', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: {ma60_json}, smooth: true, lineStyle: {{ width: 1 }}, symbol: 'none' }},
        {{ name: 'MA250', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: {ma250_json}, smooth: true, lineStyle: {{ width: 1 }}, symbol: 'none' }},
        {{ name: 'BOLL\u4e0a\u8f68', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: {boll_upper_json}, lineStyle: {{ type: 'dashed', width: 0.8 }}, symbol: 'none' }},
        {{ name: 'BOLL\u4e0b\u8f68', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: {boll_lower_json}, lineStyle: {{ type: 'dashed', width: 0.8 }}, symbol: 'none' }},
        {{ name: '\u6210\u4ea4\u91cf', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: {volume_json},
          itemStyle: {{ color: function(p) {{ return p.data[1] >= 0 ? '#e74c3c' : '#27ae60'; }} }} }},
        {{ name: 'MACD\u67f1', type: 'bar', xAxisIndex: 2, yAxisIndex: 2, data: {macd_hist_json},
          itemStyle: {{ color: function(p) {{ return p.value >= 0 ? '#e74c3c' : '#27ae60'; }} }} }},
        {{ name: 'MACD DIF', type: 'line', xAxisIndex: 2, yAxisIndex: 2, data: {macd_dif_json}, symbol: 'none', lineStyle: {{ width: 1 }} }},
        {{ name: 'MACD DEA', type: 'line', xAxisIndex: 2, yAxisIndex: 2, data: {macd_dea_json}, symbol: 'none', lineStyle: {{ width: 1 }} }}
    ]
}};
myChart.setOption(option);
window.addEventListener('resize', function() {{ myChart.resize(); }});
'''

        return f'''<div id="kline_chart" style="width:100%;height:600px;margin-bottom:20px;border:1px solid #ddd;border-radius:4px;"></div>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<script>
{echarts_js}
</script>'''

    def _generate_text_report(self, code: str, stock_name: str, df: pd.DataFrame, latest: pd.Series, latest_date: str) -> str:
        """Generate plain text report."""
        lines = []
        lines.append('=' * 65)
        lines.append(f'  {code} {stock_name} Technical Scan Report')
        lines.append(f'  Data as of: {latest_date}  |  Rows: {len(df)}  |  DB: {self.env}')
        lines.append('=' * 65)

        # 1. Price & MAs
        lines.append('')
        lines.append('--- 1. Price & Moving Averages ---')
        pct = latest.get('pct_change', 0)
        prev_close = latest.get('prev_close', latest['close'])
        lines.append(
            f'  Close: {latest["close"]:.2f}  '
            f'Prev: {prev_close:.2f}  '
            f'Chg: {pct:+.2f}%'
        )
        for w in [5, 20, 60, 120, 250]:
            ma = latest.get(f'ma{w}')
            if ma is not None and not np.isnan(ma):
                bias = (latest['close'] / ma - 1) * 100
                tag = '[OK] above' if latest['close'] > ma else '[WARN] below'
                lines.append(f'  MA{w}: {ma:.2f}  (bias {bias:+.2f}%) {tag}')

        # 2. Trend
        lines.append('')
        lines.append('--- 2. Trend Status ---')
        trend = self.detector.get_trend_status(latest)
        lines.append(f'  MA alignment: {trend}')

        # 3. MACD
        lines.append('')
        lines.append('--- 3. MACD (12,26,9) ---')
        dif = latest['macd_dif']
        dea = latest['macd_dea']
        hist = latest['macd_hist']
        lines.append(f'  DIF: {dif:.3f}  DEA: {dea:.3f}  Histogram: {hist:.3f}')
        if dif > 0 and dea > 0:
            lines.append('  Status: bullish zone (both above zero)')
        elif dif < 0 and dea < 0:
            lines.append('  Status: bearish zone (both below zero)')
        else:
            lines.append('  Status: transitional')

        # 4. RSI
        lines.append('')
        lines.append('--- 4. RSI (14) ---')
        rsi = latest.get('rsi')
        if rsi is not None and not np.isnan(rsi):
            lines.append(f'  RSI14: {rsi:.1f}')
            if rsi > 70:
                lines.append('  [WARN] Overbought (>70)')
            elif rsi < 30:
                lines.append('  [WARN] Oversold (<30)')
            else:
                lines.append('  [OK] Neutral')

        # 5. Volume
        lines.append('')
        lines.append('--- 5. Volume ---')
        vr = latest.get('volume_ratio')
        if vr is not None and not np.isnan(vr):
            lines.append(f'  Volume ratio (vs 5d avg): {vr:.2f}')
            if vr > 2.0:
                lines.append('  [SIGNAL] Significant volume surge')
            elif vr > 1.5:
                lines.append('  [WARN] Mild volume expansion')
            elif vr < 0.5:
                lines.append('  [WARN] Significant volume shrinkage')
            else:
                lines.append('  [OK] Normal')

        # 6. ATR
        lines.append('')
        lines.append('--- 6. Volatility (ATR14) ---')
        atr = latest.get('atr_14')
        if atr is not None and not np.isnan(atr):
            lines.append(
                f'  ATR14: {atr:.2f}  '
                f'(daily range ~{atr / latest["close"] * 100:.1f}%)'
            )

        # 7. Signals
        lines.append('')
        lines.append('--- 7. Signal Detection ---')
        signals = self.detector.detect_all(latest)
        if signals:
            for s in signals:
                sev = f' [{s.severity.value}]' if s.severity else ''
                lines.append(f'  {s.level.value} {s.name}{sev}: {s.description}')
        else:
            lines.append('  [OK] No significant signals')

        # 8. Stop-loss reference
        lines.append('')
        lines.append('--- 8. Stop-Loss Reference ---')
        sl_atr = SignalDetector.calc_stop_loss_price(latest, method='atr')
        if sl_atr:
            lines.append(f'  ATR stop: {sl_atr["stop_price"]:.2f}  ({sl_atr["description"]})')
        sl_ma = SignalDetector.calc_stop_loss_price(latest, method='ma20')
        if sl_ma:
            lines.append(f'  MA20 stop: {sl_ma["stop_price"]:.2f}  ({sl_ma["description"]})')

        # 9. Recent N days
        lines.append('')
        n = min(10, len(df))
        lines.append(f'--- 9. Recent {n} Trading Days ---')
        for _, row in df.tail(n).iterrows():
            p = row.get('pct_change', 0)
            sign = '+' if p > 0 else ''
            vol = row.get('volume', 0)
            lines.append(
                f'  {row["trade_date"].strftime("%m-%d")}  '
                f'{row["close"]:>8.2f}  {sign}{p:>6.2f}%  '
                f'Vol:{vol:>8.0f}'
            )

        # 10. Support / Resistance
        lines.append('')
        lines.append('--- 10. Support / Resistance ---')
        r20 = df.tail(20)
        lines.append(f'  20-day high: {r20["high"].max():.2f}')
        lines.append(f'  20-day low:  {r20["low"].min():.2f}')
        ma60 = latest.get('ma60')
        if ma60 is not None and not np.isnan(ma60):
            lines.append(f'  MA60 S/R:    {ma60:.2f}')
        ma250 = latest.get('ma250')
        if ma250 is not None and not np.isnan(ma250):
            lines.append(f'  MA250 S/R:   {ma250:.2f}')

        lines.append('')
        lines.append('=' * 65)

        return '\n'.join(lines)
    
    def _generate_html_report(self, code: str, stock_name: str, df: pd.DataFrame, latest: pd.Series, latest_date: str, chart_path=None,
                              score_result=None, ma_pattern=None, macd_interp=None,
                              rsi_interp=None, kdj_interp=None, boll_interp=None,
                              vp_quadrant=None, divergence=None, kdj_signals=None,
                              alerts=None, supports=None, resistances=None,
                              recent_features=None,
                              rps_120=None, rps_250=None, rps_slope=None):
        """Generate HTML report v2.0 with scoring, interpretation, and structured analysis using Jinja2."""
        from pathlib import Path

        # Build chart HTML: ECharts first, fallback to matplotlib base64
        chart_html = ''
        if self.generate_chart:
            try:
                chart_html = self._build_echarts_html(df, display_days=120)
            except Exception as e:
                import logging
                logging.getLogger('tech_scan').warning(f'ECharts generation failed: {e}, falling back to matplotlib')
                if chart_path:
                    import base64
                    chart_b64 = base64.b64encode(Path(chart_path).read_bytes()).decode('utf-8')
                    chart_html = f'<img src="data:image/png;base64,{chart_b64}" style="max-width:100%;border:1px solid #ddd;border-radius:4px;margin-bottom:20px;">'

        # Fallbacks if ReportEngine not used
        if score_result is None:
            from strategist.tech_scan.report_engine import ScoreResult
            score_result = ScoreResult(score=5.0, trend_label='N/A', action_advice='N/A', breakdown={'ma': 0, 'macd': 0, 'kdj': 0, 'rsi': 0, 'vol_price': 0})
        if ma_pattern is None:
            from strategist.tech_scan.report_engine import MAPattern
            ma_pattern = MAPattern('N/A', 'gray', 'N/A')
        if macd_interp is None:
            macd_interp = {'dif': 0, 'dea': 0, 'hist': 0, 'status': 'N/A', 'hist_trend': 'N/A', 'hist_color': 'red'}
        if rsi_interp is None:
            rsi_interp = {'zone': 'N/A', 'color': 'gray', 'desc': 'N/A'}
        if kdj_interp is None:
            kdj_interp = {'k': None, 'd': None, 'j': None, 'status': 'N/A', 'zone': 'N/A', 'desc': ''}
        if boll_interp is None:
            boll_interp = None
        if vp_quadrant is None:
            from strategist.tech_scan.report_engine import VolumePriceQuadrant
            vp_quadrant = VolumePriceQuadrant('N/A', 'gray', 'N/A')
        if divergence is None:
            divergence = {'type': '无背驰', 'confidence': '低', 'description': '无数据'}
        if kdj_signals is None:
            kdj_signals = []
        if alerts is None:
            alerts = []
        if supports is None:
            supports = []
        if resistances is None:
            resistances = []
        if recent_features is None:
            recent_features = []
        if rps_120 is None:
            rps_120 = latest.get('rps_120')
        if rps_250 is None:
            rps_250 = latest.get('rps_250')
        if rps_slope is None:
            rps_slope = latest.get('rps_slope')

        # --- Build MA rows (list of dicts for template) ---
        ma_rows = []
        for w in [5, 20, 60, 120, 250]:
            ma = latest.get(f'ma{w}')
            if ma is not None and not np.isnan(ma):
                bias = (latest['close'] / ma - 1) * 100
                color = '#27ae60' if latest['close'] > ma else '#e74c3c'
                tag = 'above' if latest['close'] > ma else 'below'
                if w == 5:
                    interp = '短期趋势向上' if latest['close'] > ma else '短期趋势向下'
                elif w == 20:
                    interp = '中期趋势向上' if latest['close'] > ma else '中期趋势向下'
                elif w == 60:
                    interp = '长期趋势向上' if latest['close'] > ma else '长期趋势向下'
                else:
                    interp = '年线支撑有效' if latest['close'] > ma else '跌破年线'
                ma_rows.append({
                    'name': f'MA{w}',
                    'price': f'{ma:.2f}',
                    'bias': f'{bias:+.2f}%',
                    'color': color,
                    'tag': tag,
                    'interp': interp,
                })

        # --- Score bar ---
        score_pct = score_result.score / 10 * 100
        badge_color = {'强势多头': '#27ae60', '偏多': '#2ecc71', '中性震荡': '#f39c12', '偏空': '#e67e22', '强势空头': '#e74c3c'}.get(score_result.trend_label, '#95a5a6')
        pattern_color = {'green': '#27ae60', 'orange': '#e67e22', 'red': '#e74c3c', 'yellow': '#f39c12', 'gray': '#95a5a6'}.get(ma_pattern.color, '#95a5a6')

        # Score breakdown - ensure keys exist
        bd = score_result.breakdown or {'ma': 0, 'macd': 0, 'kdj': 0, 'rsi': 0, 'vol_price': 0}
        bd = {k: bd.get(k, 0) for k in ('ma', 'macd', 'kdj', 'rsi', 'vol_price')}

        # --- RSI zone bar (complex visual, keep as pre-built HTML) ---
        rsi_val = latest.get('rsi')
        rsi_bar_html = ''
        if rsi_val is not None and not np.isnan(rsi_val):
            rsi_pos = max(0, min(100, rsi_val))
            rsi_bar_html = f'''<div style="position:relative;height:20px;border-radius:4px;background:linear-gradient(to right,#27ae60 0%,#27ae60 30%,#95a5a6 30%,#95a5a6 40%,#2ecc71 40%,#2ecc71 70%,#f39c12 70%,#f39c12 80%,#e74c3c 80%);margin:8px 0">
        <div style="position:absolute;top:-2px;left:{rsi_pos}%;width:3px;height:24px;background:#2c3e50;border-radius:2px"></div>
        <div style="position:absolute;top:22px;left:{rsi_pos}%;transform:translateX(-50%);font-size:11px;color:#333;font-weight:bold">{rsi_val:.1f}</div>
        </div>
        <div style="display:flex;justify-content:space-between;font-size:10px;color:#888;margin-bottom:8px">
        <span>&lt;30 超卖</span><span>30-40 偏弱</span><span>40-50 中性</span><span>50-70 偏强</span><span>70-80 偏买</span><span>&gt;80 超买</span>
        </div>'''

        # --- Volume-price quadrant (keep as pre-built HTML) ---
        vp = vp_quadrant
        vp_color_map = {'green': '#27ae60', 'yellow': '#f39c12', 'orange': '#e67e22', 'red': '#e74c3c'}
        vp_c = vp_color_map.get(vp.color, '#95a5a6')
        vp_grid_html = f'''<div class="quadrant-grid" style="margin:10px 0">
        <div class="quadrant-cell" style="background:#eafaf1;border:2px solid {'#27ae60' if vp.label=='放量上涨' else '#ddd'}">放量上涨 [OK]<br><span style="font-size:10px"> 最强买入信号</span></div>
        <div class="quadrant-cell" style="background:#fef9e7;border:2px solid {'#f39c12' if vp.label=='缩量上涨' else '#ddd'}">缩量上涨 [WARN]<br><span style="font-size:10px"> 上涨乏力</span></div>
        <div class="quadrant-cell" style="background:#fef5e7;border:2px solid {'#e67e22' if vp.label=='缩量下跌' else '#ddd'}">缩量下跌 [OK]<br><span style="font-size:10px"> 正常回调</span></div>
        <div class="quadrant-cell" style="background:#fdedec;border:2px solid {'#e74c3c' if vp.label=='放量下跌' else '#ddd'}">放量下跌 [RED]<br><span style="font-size:10px"> 危险信号</span></div>
        </div>'''

        # --- Stop-loss rows (list of dicts for template) ---
        sl_rows = []
        sl_atr = self.detector.calc_stop_loss_price(latest, method='atr')
        if sl_atr:
            sl_rows.append({'method': 'ATR', 'price': f'{sl_atr["stop_price"]:.2f}', 'description': sl_atr["description"]})
        sl_ma = self.detector.calc_stop_loss_price(latest, method='ma20')
        if sl_ma:
            sl_rows.append({'method': 'MA20', 'price': f'{sl_ma["stop_price"]:.2f}', 'description': sl_ma["description"]})

        # --- Key levels: pass supports/resistances as lists of dicts ---
        support_dicts = []
        for l in supports:
            support_dicts.append({'source': l.source, 'price': l.price, 'level_type': l.level_type, 'strength': l.strength})
        resistance_dicts = []
        for l in resistances:
            resistance_dicts.append({'source': l.source, 'price': l.price, 'level_type': l.level_type, 'strength': l.strength})

        # --- Recent days (list of dicts for template) ---
        n_recent = min(10, len(df))
        recent_rows = []
        for _, row in df.tail(n_recent).iterrows():
            p = row.get('pct_change', 0)
            vol = row.get('volume', 0)
            p_color = '#e74c3c' if p >= 0 else '#27ae60'
            recent_rows.append({
                'date': row['trade_date'].strftime('%m-%d'),
                'close': f'{row["close"]:.2f}',
                'pct': f'{p:+.2f}%',
                'pct_color': p_color,
                'vol': f'{vol:.0f}',
            })

        # --- Price info ---
        pct = latest.get('pct_change', 0)
        prev_close = latest.get('prev_close', latest['close'])
        turnover = latest.get('turnover_rate')
        turnover_html = f'<td>{turnover:.2f}%</td>' if turnover is not None and not pd.isna(turnover) else '<td>N/A</td>'

        # Pre-compute display values
        sl_atr_display = f'{sl_atr["stop_price"]:.2f}' if sl_atr else 'N/A'
        sl_ma_display = f'{sl_ma["stop_price"]:.2f}' if sl_ma else 'N/A'
        rsi_display = f'{rsi_val:.1f}' if rsi_val is not None and not np.isnan(rsi_val) else 'N/A'
        close_display = f'{latest["close"]:.2f}'

        # --- KDJ display values ---
        kdj_interp_dict = dict(kdj_interp) if isinstance(kdj_interp, dict) else {
            'k': None, 'd': None, 'j': None, 'status': 'N/A', 'zone': 'N/A', 'desc': ''
        }
        kdj_interp_dict['k_display'] = f'{kdj_interp_dict["k"]:.1f}' if kdj_interp_dict['k'] is not None else 'N/A'
        kdj_interp_dict['d_display'] = f'{kdj_interp_dict["d"]:.1f}' if kdj_interp_dict['d'] is not None else 'N/A'
        kdj_interp_dict['j_display'] = f'{kdj_interp_dict["j"]:.1f}' if kdj_interp_dict['j'] is not None else 'N/A'

        # --- KDJ signals: convert to simple dicts for template ---
        kdj_signal_dicts = []
        for s in kdj_signals:
            level_str = s.level.value if hasattr(s.level, 'value') else str(s.level)
            kdj_signal_dicts.append({
                'name': s.name,
                'description': s.description,
                'level_str': level_str,
            })

        # --- RPS display ---
        rps_html = ''
        if rps_250 is not None and not pd.isna(rps_250):
            rps_val = float(rps_250)
            rps_color = '#e74c3c' if rps_val >= 90 else ('#f39c12' if rps_val >= 80 else '#95a5a6')
            rps_html = f'<span class="badge" style="background:{rps_color};margin-left:8px">RPS250: {rps_val:.0f}</span>'
            if rps_val >= 90:
                rps_html += ' <span style="font-size:11px;color:#e74c3c">[强势]</span>'
            elif rps_val >= 80:
                rps_html += ' <span style="font-size:11px;color:#f39c12">[偏强]</span>'
            elif rps_val >= 50:
                rps_html += ' <span style="font-size:11px;color:#888">[中性]</span>'
            else:
                rps_html += ' <span style="font-size:11px;color:#888">[偏弱]</span>'
        elif rps_120 is not None and not pd.isna(rps_120):
            rps_val = float(rps_120)
            rps_color = '#e74c3c' if rps_val >= 90 else ('#f39c12' if rps_val >= 80 else '#95a5a6')
            rps_html = f'<span class="badge" style="background:{rps_color};margin-left:8px">RPS120: {rps_val:.0f}</span>'

        # --- Build template context ---
        ctx = {
            'code': code,
            'stock_name': stock_name,
            'latest_date': latest_date,
            'env': self.env,
            'df_len': len(df),
            'chart_html': chart_html,
            'score_result': {
                'score': score_result.score,
                'trend_label': score_result.trend_label,
                'action_advice': score_result.action_advice,
                'breakdown': bd,
            },
            'ma_pattern': {
                'name': ma_pattern.name,
                'color': ma_pattern.color,
                'description': ma_pattern.description,
            },
            'macd_interp': macd_interp,
            'rsi_interp': rsi_interp,
            'rsi_display': rsi_display,
            'rsi_bar_html': rsi_bar_html,
            'kdj_interp': kdj_interp_dict,
            'kdj_signals': kdj_signal_dicts,
            'boll_interp': boll_interp,
            'vp_quadrant': {
                'label': vp.label,
                'color': vp.color,
                'description': vp.description,
                'color_mapped': vp_c,
            },
            'divergence': divergence,
            'alerts': alerts,
            'supports': support_dicts,
            'resistances': resistance_dicts,
            'recent_features': recent_features,
            'recent_rows': recent_rows,
            'ma_rows': ma_rows,
            'sl_rows': sl_rows,
            'rps_html': rps_html,
            'turnover_html': turnover_html,
            'vp_grid_html': vp_grid_html,
            'close_display': close_display,
            'pct': pct,
            'prev_close': prev_close,
            'sl_atr_display': sl_atr_display,
            'sl_ma_display': sl_ma_display,
            'badge_color': badge_color,
            'pattern_color': pattern_color,
            'score_pct': score_pct,
            'generated_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'n_recent': n_recent,
            'volume': latest.get('volume', 0),
            'vol_ma5': latest.get('vol_ma5', 0),
            'volume_ratio': latest.get('volume_ratio', 0),
        }

        # --- Load and render Jinja2 template ---
        template_dir = os.path.join(os.path.dirname(__file__), 'templates')
        env = Environment(loader=FileSystemLoader(template_dir), autoescape=False)
        template = env.get_template('report_v2.html')
        return template.render(**ctx)

    def _generate_markdown_report(self, code: str, stock_name: str, df: pd.DataFrame, latest: pd.Series, latest_date: str, chart_path: str = None) -> str:
        """Generate Markdown report with optional chart."""
        lines = []
        lines.append(f'# {code} {stock_name} - 技术面分析报告')
        lines.append('')
        lines.append(f'> **扫描日期**: {latest_date}  ')
        lines.append(f'> **数据行数**: {len(df)}  ')
        lines.append(f'> **数据源**: {self.env} DB')
        lines.append('')
        lines.append('---')
        lines.append('')
        
        # Chart
        if chart_path:
            from pathlib import Path
            chart_file = Path(chart_path).name
            lines.append(f'![技术分析图]({chart_file})')
            lines.append('')
        
        # 1. Price & MAs
        lines.append('## 📊 价格与均线')
        lines.append('')
        pct = latest.get('pct_change', 0)
        prev_close = latest.get('prev_close', latest['close'])
        lines.append(f'- **收盘价**: {latest["close"]:.2f}')
        lines.append(f'- **前收盘**: {prev_close:.2f}')
        lines.append(f'- **涨跌幅**: {pct:+.2f}%')
        lines.append('')
        lines.append('| 均线 | 价格 | 偏离度 | 状态 |')
        lines.append('|------|------|--------|------|')
        for w in [5, 20, 60, 120, 250]:
            ma = latest.get(f'ma{w}')
            if ma is not None and not np.isnan(ma):
                bias = (latest['close'] / ma - 1) * 100
                status = '✅ 上方' if latest['close'] > ma else '⚠️ 下方'
                lines.append(f'| MA{w} | {ma:.2f} | {bias:+.2f}% | {status} |')
        lines.append('')
        
        # 2. Trend
        lines.append('## 📈 趋势状态')
        lines.append('')
        trend = self.detector.get_trend_status(latest)
        trend_emoji = {'强势多头': '🟢🟢', '多头排列': '🟢', '震荡整理': '⚪', '空头排列': '🔴', '强势空头': '🔴🔴'}.get(trend, '⚪')
        lines.append(f'- **均线排列**: {trend_emoji} {trend}')
        lines.append('')
        
        # 3. MACD
        lines.append('## 🔄 MACD (12,26,9)')
        lines.append('')
        dif = latest['macd_dif']
        dea = latest['macd_dea']
        hist = latest['macd_hist']
        lines.append(f'- **DIF**: {dif:.3f}')
        lines.append(f'- **DEA**: {dea:.3f}')
        lines.append(f'- **柱状图**: {hist:.3f}')
        if dif > 0 and dea > 0:
            lines.append('- **状态**: 多头区域（均在零轴上方）')
        elif dif < 0 and dea < 0:
            lines.append('- **状态**: 空头区域（均在零轴下方）')
        else:
            lines.append('- **状态**: 过渡区域')
        lines.append('')
        
        # 4. RSI
        lines.append('## 💹 RSI (14)')
        lines.append('')
        rsi = latest.get('rsi')
        if rsi is not None and not np.isnan(rsi):
            lines.append(f'- **RSI14**: {rsi:.1f}')
            if rsi > 70:
                lines.append('- **状态**: ⚠️ 超买 (>70)')
            elif rsi < 30:
                lines.append('- **状态**: ⚠️ 超卖 (<30)')
            else:
                lines.append('- **状态**: ✅ 中性')
        lines.append('')
        
        # 5. Volume
        lines.append('## 📦 成交量')
        lines.append('')
        vr = latest.get('volume_ratio')
        if vr is not None and not np.isnan(vr):
            lines.append(f'- **量比** (vs 5日均量): {vr:.2f}')
            if vr > 2.0:
                lines.append('- **状态**: 🔥 显著放量')
            elif vr > 1.5:
                lines.append('- **状态**: ⚠️ 温和放量')
            elif vr < 0.5:
                lines.append('- **状态**: ⚠️ 显著缩量')
            else:
                lines.append('- **状态**: ✅ 正常')
        lines.append('')
        
        # 6. ATR
        lines.append('## 📉 波动率 (ATR14)')
        lines.append('')
        atr = latest.get('atr_14')
        if atr is not None and not np.isnan(atr):
            lines.append(f'- **ATR14**: {atr:.2f}')
            lines.append(f'- **日均波幅**: ~{atr / latest["close"] * 100:.1f}%')
        lines.append('')
        
        # 7. Signals
        lines.append('## 🚦 信号检测')
        lines.append('')
        signals = self.detector.detect_all(latest)
        if signals:
            for s in signals:
                sev = f' [{s.severity.value}]' if s.severity else ''
                lines.append(f'- {s.level.value} **{s.name}**{sev}: {s.description}')
        else:
            lines.append('- ✅ 无显著信号')
        lines.append('')
        
        # 8. Stop-loss
        lines.append('## 🛑 止损参考')
        lines.append('')
        sl_atr = SignalDetector.calc_stop_loss_price(latest, method='atr')
        if sl_atr:
            lines.append(f'- **ATR止损**: {sl_atr["stop_price"]:.2f} ({sl_atr["description"]})')
        sl_ma = SignalDetector.calc_stop_loss_price(latest, method='ma20')
        if sl_ma:
            lines.append(f'- **MA20止损**: {sl_ma["stop_price"]:.2f} ({sl_ma["description"]})')
        lines.append('')
        
        # 9. Recent days
        lines.append('## 📅 近期走势 (最近10日)')
        lines.append('')
        lines.append('| 日期 | 收盘价 | 涨跌幅 | 成交量 |')
        lines.append('|------|--------|--------|--------|')
        n = min(10, len(df))
        for _, row in df.tail(n).iterrows():
            p = row.get('pct_change', 0)
            vol = row.get('volume', 0)
            lines.append(f'| {row["trade_date"].strftime("%m-%d")} | {row["close"]:.2f} | {p:+.2f}% | {vol:.0f} |')
        lines.append('')
        
        # 10. Support / Resistance
        lines.append('## 🎯 支撑/压力位')
        lines.append('')
        r20 = df.tail(20)
        lines.append(f'- **20日高点**: {r20["high"].max():.2f}')
        lines.append(f'- **20日低点**: {r20["low"].min():.2f}')
        ma60 = latest.get('ma60')
        if ma60 is not None and not np.isnan(ma60):
            lines.append(f'- **MA60**: {ma60:.2f}')
        ma250 = latest.get('ma250')
        if ma250 is not None and not np.isnan(ma250):
            lines.append(f'- **MA250**: {ma250:.2f}')
        lines.append('')
        
        lines.append('---')
        lines.append('')
        lines.append(f'*报告生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*')
        
        return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='Single stock technical scan')
    parser.add_argument('--stock', type=str, required=True, help='Stock code, e.g. 688386 or 688386.SH')
    parser.add_argument('--env', type=str, default='online', choices=['local', 'online'], help='DB environment')
    parser.add_argument('--lookback', type=int, default=300, help='Lookback trading days (default 300)')
    parser.add_argument('--chart', action='store_true', help='Generate K-line chart')
    parser.add_argument('--markdown', action='store_true', help='Output in Markdown format')
    parser.add_argument('--output', type=str, help='Save report to file (auto-detect format from extension)')
    parser.add_argument('--name', type=str, help='Stock name (optional, will fetch if not provided)')
    args = parser.parse_args()

    scanner = SingleStockScanner(
        env=args.env,
        lookback_days=args.lookback,
        generate_chart=args.chart
    )
    
    output_format = 'html' if not args.markdown else 'markdown'

    report = scanner.scan(args.stock, output_format=output_format, stock_name=args.name)

    # Default output path if not specified
    if not args.output:
        code_fmt = _fmt_code(args.stock).replace('.', '_')
        date_str = datetime.now().strftime('%Y%m%d')
        args.output = f'{scanner.output_dir}/{code_fmt}_{date_str}.html'

    from pathlib import Path
    import shutil
    import base64
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # If chart was generated, embed it into the report as base64
    if args.chart and scanner.generate_chart:
        chart_files = list(Path(scanner.output_dir).glob(f"{_fmt_code(args.stock).replace('.', '_')}*.png"))
        for chart_src in chart_files:
            chart_b64 = base64.b64encode(chart_src.read_bytes()).decode('utf-8')
            chart_data_uri = f'data:image/png;base64,{chart_b64}'
            report = report.replace(f']({chart_src.name})', f']({chart_data_uri})')

    output_path.write_text(report, encoding='utf-8')
    print(f'Report saved to: {output_path}')


if __name__ == '__main__':
    main()
