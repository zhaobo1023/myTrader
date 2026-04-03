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

        # Extract RPS values from latest row
        rps_120 = latest.get('rps_120')
        rps_250 = latest.get('rps_250')
        rps_slope = latest.get('rps_slope')

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
        """Generate HTML report v2.0 with scoring, interpretation, and structured analysis."""
        import base64
        from pathlib import Path

        # Chart image
        chart_img_html = ''
        if chart_path:
            chart_b64 = base64.b64encode(Path(chart_path).read_bytes()).decode('utf-8')
            chart_img_html = f'<img src="data:image/png;base64,{chart_b64}" style="max-width:100%;border:1px solid #ddd;border-radius:4px;margin-bottom:20px;">'

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

        # --- Build MA rows ---
        ma_rows = ''
        for w in [5, 20, 60, 120, 250]:
            ma = latest.get(f'ma{w}')
            if ma is not None and not np.isnan(ma):
                bias = (latest['close'] / ma - 1) * 100
                color = '#27ae60' if latest['close'] > ma else '#e74c3c'
                tag = 'above' if latest['close'] > ma else 'below'
                # Interpretation
                if w == 5:
                    interp = '短期趋势向上' if latest['close'] > ma else '短期趋势向下'
                elif w == 20:
                    interp = '中期趋势向上' if latest['close'] > ma else '中期趋势向下'
                elif w == 60:
                    interp = '长期趋势向上' if latest['close'] > ma else '长期趋势向下'
                else:
                    interp = '年线支撑有效' if latest['close'] > ma else '跌破年线'
                ma_rows += f'<tr><td>MA{w}</td><td>{ma:.2f}</td><td style="color:{color}">{bias:+.2f}%</td><td style="color:{color}">{tag}</td><td style="font-size:12px;color:#666">{interp}</td></tr>'

        # --- Score bar ---
        score_pct = score_result.score / 10 * 100
        score_color = '#27ae60' if score_result.score >= 6 else ('#f39c12' if score_result.score >= 4 else '#e74c3c')
        badge_color = {'强势多头': '#27ae60', '偏多': '#2ecc71', '中性震荡': '#f39c12', '偏空': '#e67e22', '强势空头': '#e74c3c'}.get(score_result.trend_label, '#95a5a6')
        pattern_color = {'green': '#27ae60', 'orange': '#e67e22', 'red': '#e74c3c', 'yellow': '#f39c12', 'gray': '#95a5a6'}.get(ma_pattern.color, '#95a5a6')

        # Score breakdown
        bd = score_result.breakdown or {'ma': 0, 'macd': 0, 'kdj': 0, 'rsi': 0, 'vol_price': 0}

        # --- Alerts ---
        alerts_html = ''
        danger_alerts = [a for a in alerts if a.category == 'danger']
        opp_alerts = [a for a in alerts if a.category == 'opportunity']
        if danger_alerts:
            alerts_html += '<h3 style="color:#e74c3c;margin-top:15px">[RED] 风险提示</h3>'
            for a in danger_alerts:
                level_tag = f'[{a.level.upper()}] ' if a.level != 'medium' else ''
                alerts_html += f'<div class="danger-alert">{level_tag}{a.name}: {a.description}</div>'
        if opp_alerts:
            alerts_html += '<h3 style="color:#27ae60;margin-top:15px">[OK] 机会信号</h3>'
            for a in opp_alerts:
                alerts_html += f'<div class="opportunity-alert">{a.name}: {a.description}</div>'
        if not alerts:
            alerts_html = '<div class="opportunity-alert">暂无明显技术面风险信号</div>'

        # --- Divergence ---
        div_html = ''
        if divergence.get('type') != '无背驰':
            div_color = '#e74c3c' if divergence['type'] == '顶背驰' else '#27ae60'
            div_html = f'<div class="danger-alert" style="border-left-color:{div_color}">[SIGNAL] MACD {divergence["type"]} (confidence: {divergence["confidence"]})<br>{divergence["description"]}</div>'

        # --- KDJ signals ---
        kdj_sig_html = ''
        for s in kdj_signals:
            sig_color = '#e74c3c' if 'RED' in str(s.level) else ('#27ae60' if 'GREEN' in str(s.level) else '#f39c12')
            kdj_sig_html += f'<div style="color:{sig_color};margin:2px 0;font-size:13px">{s.level.value} {s.name}: {s.description}</div>'

        # --- RSI zone bar ---
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

        # --- BOLL ---
        boll_html = ''
        if boll_interp:
            boll_html = f'''<div class="info-card">
        <h2>BOLL (20, 2)</h2>
        <table><tr><th>Upper</th><th>Middle (MA20)</th><th>Lower</th><th>%B</th><th>Bandwidth</th></tr>
        <tr><td>{boll_interp["upper"]:.2f}</td><td>{boll_interp["middle"]:.2f}</td><td>{boll_interp["lower"]:.2f}</td><td>{boll_interp["pctb"]:.2f}</td><td>{boll_interp["bandwidth"]*100:.1f}%</td></tr></table>
        <p style="margin:8px 0"><b>Position:</b> {boll_interp["position"]} - {boll_interp["pos_desc"]}</p>
        <p style="margin:8px 0"><b>Width:</b> {boll_interp["width_signal"]}</p>
        </div>'''

        # --- Volume-price quadrant ---
        vp = vp_quadrant
        vp_color_map = {'green': '#27ae60', 'yellow': '#f39c12', 'orange': '#e67e22', 'red': '#e74c3c'}
        vp_c = vp_color_map.get(vp.color, '#95a5a6')
        vp_grid = f'''<div class="quadrant-grid" style="margin:10px 0">
        <div class="quadrant-cell" style="background:#eafaf1;border:2px solid {'#27ae60' if vp.label=='放量上涨' else '#ddd'}">放量上涨 [OK]<br><span style="font-size:10px"> 最强买入信号</span></div>
        <div class="quadrant-cell" style="background:#fef9e7;border:2px solid {'#f39c12' if vp.label=='缩量上涨' else '#ddd'}">缩量上涨 [WARN]<br><span style="font-size:10px"> 上涨乏力</span></div>
        <div class="quadrant-cell" style="background:#fef5e7;border:2px solid {'#e67e22' if vp.label=='缩量下跌' else '#ddd'}">缩量下跌 [OK]<br><span style="font-size:10px"> 正常回调</span></div>
        <div class="quadrant-cell" style="background:#fdedec;border:2px solid {'#e74c3c' if vp.label=='放量下跌' else '#ddd'}">放量下跌 [RED]<br><span style="font-size:10px"> 危险信号</span></div>
        </div>'''

        # --- Stop-loss ---
        sl_rows = ''
        sl_atr = self.detector.calc_stop_loss_price(latest, method='atr')
        if sl_atr:
            sl_rows += f'<tr><td>ATR</td><td>{sl_atr["stop_price"]:.2f}</td><td>{sl_atr["description"]}</td></tr>'
        sl_ma = self.detector.calc_stop_loss_price(latest, method='ma20')
        if sl_ma:
            sl_rows += f'<tr><td>MA20</td><td>{sl_ma["stop_price"]:.2f}</td><td>{sl_ma["description"]}</td></tr>'

        # --- Key levels ---
        sr_rows = ''
        for l in resistances:
            sr_rows += f'<tr><td style="color:#e74c3c">{l.source}</td><td>{l.price:.2f}</td><td>{l.level_type}</td><td>{l.strength}</td></tr>'
        for l in supports:
            sr_rows += f'<tr><td style="color:#27ae60">{l.source}</td><td>{l.price:.2f}</td><td>{l.level_type}</td><td>{l.strength}</td></tr>'

        # --- Recent days ---
        recent_rows = ''
        n = min(10, len(df))
        for _, row in df.tail(n).iterrows():
            p = row.get('pct_change', 0)
            vol = row.get('volume', 0)
            p_color = '#e74c3c' if p >= 0 else '#27ae60'
            recent_rows += f'<tr><td>{row["trade_date"].strftime("%m-%d")}</td><td>{row["close"]:.2f}</td><td style="color:{p_color}">{p:+.2f}%</td><td>{vol:.0f}</td></tr>'
        features_html = ' | '.join(recent_features) if recent_features else ''

        # --- Price info ---
        pct = latest.get('pct_change', 0)
        prev_close = latest.get('prev_close', latest['close'])
        turnover = latest.get('turnover_rate')
        turnover_html = f'<td>{turnover:.2f}%</td>' if turnover is not None and not pd.isna(turnover) else '<td>N/A</td>'

        # Pre-compute stop-loss display values to avoid f-string format spec issues
        sl_atr_display = f'{sl_atr["stop_price"]:.2f}' if sl_atr else 'N/A'
        sl_ma_display = f'{sl_ma["stop_price"]:.2f}' if sl_ma else 'N/A'
        kdj_k_display = f'{kdj_interp["k"]:.1f}' if kdj_interp["k"] is not None else 'N/A'
        kdj_d_display = f'{kdj_interp["d"]:.1f}' if kdj_interp["d"] is not None else 'N/A'
        kdj_j_display = f'{kdj_interp["j"]:.1f}' if kdj_interp["j"] is not None else 'N/A'
        rsi_display = f'{rsi_val:.1f}' if rsi_val is not None and not np.isnan(rsi_val) else 'N/A'
        close_display = f'{latest["close"]:.2f}'

        # --- RPS display ---
        rps_html = ''
        if rps_250 is not None and not pd.isna(rps_250):
            rps_val = float(rps_250)
            rps_color = '#e74c3c' if rps_val >= 90 else ('#f39c12' if rps_val >= 80 else '#95a5a6')
            rps_bg = '#ffeaea' if rps_val >= 90 else ('#fff8e1' if rps_val >= 80 else '#f5f5f5')
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

        html = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>{code} {stock_name} - Technical Scan v2.0</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 860px; margin: 0 auto; padding: 20px; background: #f5f5f5; color: #333; }}
h1 {{ border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
h2 {{ color: #2c3e50; border-left: 4px solid #3498db; padding-left: 10px; margin-top: 25px; }}
h3 {{ color: #34495e; margin-top: 15px; }}
.meta {{ color: #888; margin-bottom: 15px; }}
table {{ border-collapse: collapse; width: 100%; margin: 10px 0; background: white; }}
th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
th {{ background: #3498db; color: white; }}
tr:nth-child(even) {{ background: #f9f9f9; }}
.info-card {{ background: white; padding: 15px; border-radius: 8px; margin: 10px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
.badge {{ display: inline-block; padding: 4px 12px; border-radius: 12px; color: white; font-weight: bold; font-size: 14px; }}
.score-bar {{ height: 20px; border-radius: 10px; background: linear-gradient(to right, #e74c3c, #f1c40f, #27ae60); position: relative; margin: 10px 0; }}
.score-marker {{ position: absolute; top: -4px; width: 4px; height: 28px; background: #2c3e50; border-radius: 2px; }}
.danger-alert {{ border-left: 4px solid #e74c3c; background: #ffeaea; padding: 8px 12px; margin: 4px 0; border-radius: 4px; font-size: 13px; }}
.opportunity-alert {{ border-left: 4px solid #27ae60; background: #eafaf1; padding: 8px 12px; margin: 4px 0; border-radius: 4px; font-size: 13px; }}
.quadrant-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 4px; }}
.quadrant-cell {{ padding: 8px; text-align: center; border-radius: 4px; font-size: 12px; }}
@media (prefers-color-scheme: dark) {{
    body {{ background: #1a1a2e; color: #e0e0e0; }}
    .info-card {{ background: #16213e; box-shadow: 0 1px 3px rgba(255,255,255,0.05); }}
    h1 {{ border-bottom-color: #4a90d9; }}
    h2 {{ color: #e0e0e0; border-left-color: #4a90d9; }}
    th {{ background: #2c3e6b; }}
    td {{ border-color: #3a3a5c; }}
    table {{ background: #16213e; }}
    tr:nth-child(even) {{ background: #1a2744; }}
    .meta {{ color: #888; }}
    .danger-alert {{ background: #3d1f1f; }}
    .opportunity-alert {{ background: #1f3d2a; }}
}}
</style></head><body>
<h1>{stock_name} ({code}) - 技术面扫描</h1>
<div class="meta">扫描日期: {latest_date} | 数据行数: {len(df)} | 数据源: {self.env}</div>
{chart_img_html}

<!-- Section 1: Comprehensive Conclusion -->
<div class="info-card" style="border:2px solid {badge_color}">
<h2>综合结论</h2>
<table style="border:none;margin:0">
<tr style="border:none"><td style="border:none;width:120px"><b>评分:</b> {score_result.score}/10</td><td style="border:none">
<div class="score-bar"><div class="score-marker" style="left:{score_pct}%"></div></div>
</td></tr>
</table>
<p style="margin:5px 0;font-size:12px;color:#888">MA: {bd.get("ma", 0):.1f} | MACD: {bd.get("macd", 0):.1f} | KDJ: {bd.get("kdj", 0):.1f} | RSI: {bd.get("rsi", 0):.1f} | Vol-Price: {bd.get("vol_price", 0):.1f}</p>
<p style="margin:10px 0"><span class="badge" style="background:{badge_color}">{score_result.trend_label}</span>
<span class="badge" style="background:{pattern_color};margin-left:8px">{ma_pattern.name}</span>{rps_html}</p>
<p style="margin:8px 0"><b>操作建议:</b> {score_result.action_advice}</p>
<p style="margin:8px 0"><b>当前价:</b> {close_display} | <b>止损参考:</b> {sl_atr_display} (ATR) | {sl_ma_display} (MA20)</p>
{alerts_html}
</div>

<!-- Section 2: Trend Analysis -->
<div class="info-card">
<h2>趋势分析</h2>
<p style="margin:5px 0;color:#666">{ma_pattern.description}</p>
<table><tr><th>均线</th><th>价格</th><th>偏离度</th><th>位置</th><th>解读</th></tr>
<tr><td>Close</td><td>{close_display}</td><td colspan="2">昨收: {prev_close:.2f} | 涨跌: <span style="color:{'#e74c3c' if pct >= 0 else '#27ae60'}">{pct:+.2f}%</span></td><td>昨日收盘 {prev_close:.2f}, 今日 {pct:+.2f}%</td></tr>
{ma_rows}</table>
</div>

<!-- Section 3: Momentum -->
<div class="info-card">
<h2>动量分析</h2>
<h3>MACD (12,26,9)</h3>
<table><tr><th>DIF</th><th>DEA</th><th>Histogram</th><th>Status</th></tr>
<tr><td>{macd_interp["dif"]:.3f}</td><td>{macd_interp["dea"]:.3f}</td><td>{macd_interp["hist"]:.3f}</td><td>{macd_interp["status"]}</td></tr></table>
<p style="margin:5px 0;color:#666;font-size:13px">柱状图: {macd_interp["hist_trend"]}</p>
{div_html}

<h3>KDJ (9,3,3)</h3>
<table><tr><th>K</th><th>D</th><th>J</th><th>Status</th><th>Zone</th></tr>
<tr><td>{kdj_k_display}</td><td>{kdj_d_display}</td><td>{kdj_j_display}</td><td>{kdj_interp["status"]}</td><td>{kdj_interp["zone"]}</td></tr></table>
<p style="margin:5px 0;color:#666;font-size:13px">{kdj_interp["desc"]}</p>
{kdj_sig_html}
</div>

<!-- Section 4: Overbought/Oversold -->
<div class="info-card">
<h2>超买超卖分析</h2>
<h3>RSI (14)</h3>
<p style="margin:5px 0"><b>RSI: {rsi_display}</b> -> <span style="color:{rsi_interp["color"]}">{rsi_interp["zone"]}</span></p>
{rsi_bar_html}
<p style="margin:5px 0;color:#666;font-size:13px">{rsi_interp["desc"]}</p>
{boll_html}
</div>

<!-- Section 5: Volume-Price -->
<div class="info-card">
<h2>量价分析</h2>
<table><tr><th>成交量</th><th>5日均量</th><th>量比</th><th>换手率</th></tr>
<tr><td>{latest.get("volume", 0):.0f}</td><td>{latest.get("vol_ma5", 0):.0f}</td><td>{latest.get("volume_ratio", 0):.2f}</td>{turnover_html}</tr></table>
<p style="margin:10px 0"><b>量价信号:</b> <span class="badge" style="background:{vp_c}">{vp.label}</span> - {vp.description}</p>
{vp_grid}
</div>

<!-- Section 6: Key Levels -->
<div class="info-card">
<h2>关键价位</h2>
<table><tr><th>来源</th><th>价格</th><th>类型</th><th>强度</th></tr>
{sr_rows}</table>
<h3>止损参考</h3>
<table><tr><th>方法</th><th>价格</th><th>说明</th></tr>
{sl_rows}</table>
</div>

<!-- Section 7: Recent Days -->
<div class="info-card">
<h2>近{n}日走势</h2>
{f'<p style="margin:5px 0;color:#666;font-size:13px">[INFO] {features_html}</p>' if features_html else ''}
<table><tr><th>日期</th><th>收盘价</th><th>涨跌幅</th><th>成交量</th></tr>
{recent_rows}</table>
</div>

<p style="color:#aaa;text-align:center;margin-top:30px">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | Tech Scan v2.0</p>
<div class="disclaimer" style="margin-top:20px;padding:12px;background:#fff8e1;border-radius:6px;font-size:12px;color:#666;text-align:center;border:1px solid #ffe082">
<b>Disclaimer:</b> This report is auto-generated by AI/program. Data may be delayed or contain errors. For technical analysis and learning purposes only -- does NOT constitute any investment advice. Stock market has risks, trade with caution.
</div>
</body></html>'''
        return html

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
