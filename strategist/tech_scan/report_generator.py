# -*- coding: utf-8 -*-
"""
报告生成器

生成 Markdown 格式的技术面扫描报告。
支持：指数锚点、L1置顶、破位/警示分级、行业预警、背离识别+反弹目标、
RPS斜率转换榜、RPS衰减、成本安全垫+ATR止损、极度危险标记、
缩量回调降级、历史快照对比、交易日历提示。
"""
import re
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

from .signal_detector import (
    Signal, SignalLevel, SignalSeverity, SignalTag, SignalDetector,
    get_sector
)
from .chart_generator import ChartGenerator

logger = logging.getLogger(__name__)


def get_trading_calendar_hints(scan_date: datetime) -> List[str]:
    """获取交易日历提示"""
    hints = []
    if scan_date.month in (3, 6, 9, 12) and scan_date.day >= 28:
        hints.append("季末收盘日，注意机构调仓引起的异常波动")
    if scan_date.month in (1, 4, 7, 10) and scan_date.day >= 28:
        hints.append("月末收盘日")
    if scan_date.month == 12 and scan_date.day >= 28:
        hints.append("年末收官，关注基金排名博弈")
    if scan_date.weekday() == 4:
        hints.append("周五收盘，注意周末消息面风险")
    return hints


class ReportGenerator:
    """报告生成器"""

    # 极度危险阈值：亏损 > 8% 且有破位信号
    DANGER_PNL_THRESHOLD = -8.0

    def __init__(self, output_dir: str, generate_charts: bool = True):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.detector = SignalDetector()
        self.generate_charts = generate_charts
        self.chart_dir = self.output_dir / "charts"
        if generate_charts:
            self.chart_generator = ChartGenerator(str(self.chart_dir))

    def generate(
        self,
        df: pd.DataFrame,
        positions: List[Any],
        scan_date: Optional[datetime] = None,
        prev_report_path: Optional[str] = None,
        index_status: Optional[Dict] = None,
        full_df: Optional[pd.DataFrame] = None
    ) -> str:
        """
        生成扫描报告

        Args:
            df: 包含技术指标的 DataFrame（最新一天的数据）
            positions: 持仓列表
            scan_date: 扫描日期
            prev_report_path: 前一天报告路径
            index_status: 指数状态 {'name': str, 'code': str, 'trend': str, 'pct': float}
            full_df: 完整历史数据（用于图表生成）
        """
        if scan_date is None:
            scan_date = datetime.now()

        code_to_level = {p.code: p.level for p in positions}
        code_to_name = {p.code: p.name for p in positions}
        code_to_cost = {p.code: p.cost for p in positions if p.cost is not None}

        # 分析每只股票
        analysis_results = []
        for _, row in df.iterrows():
            stock_code = row['stock_code']
            signals = self.detector.detect_all(row)
            trend = self.detector.get_trend_status(row)

            close = row.get('close')
            cost = code_to_cost.get(stock_code)
            pnl_pct = None
            if cost and close and not pd.isna(close):
                pnl_pct = (close / cost - 1) * 100

            has_breakdown = any(
                s.level == SignalLevel.RED and s.severity == SignalSeverity.BREAKDOWN
                for s in signals
            )
            has_divergence = any(s.tag == SignalTag.DIVERGENCE for s in signals)
            has_oversold = any(s.tag == SignalTag.OVERSOLD_BOUNCE for s in signals)
            has_shrink = any(s.tag == SignalTag.SHRINK_PULLBACK for s in signals)
            has_rps_decay = any(s.tag == SignalTag.RPS_DECAY for s in signals)

            # 极度危险判定
            is_danger = (pnl_pct is not None
                         and pnl_pct < self.DANGER_PNL_THRESHOLD
                         and has_breakdown)

            # 缩量回调降级：如果红灯信号中也有缩量回调，降级为黄灯
            if has_shrink:
                # 将 RED 的「跌破」信号降级：不放入红灯区
                has_breakdown = False
                signals = [s for s in signals if not (
                    s.level == SignalLevel.RED
                    and s.name in ('跌破20日线', '跌破60日线')
                )]

            # 止损参考价
            stop_loss = self.detector.calc_stop_loss_price(row, method='atr')
            if not stop_loss:
                stop_loss = self.detector.calc_stop_loss_price(row, method='ma20')

            # 背离反弹目标
            div_target = self.detector.calc_divergence_target(row) if has_divergence else {}

            analysis_results.append({
                'code': stock_code,
                'name': code_to_name.get(stock_code, ''),
                'level': code_to_level.get(stock_code, ''),
                'close': close,
                'pct_change': row.get('pct_change'),
                'ma20': row.get('ma20'),
                'ma60': row.get('ma60'),
                'rps': row.get('rps_250') if pd.notna(row.get('rps_250')) else row.get('rps'),
                'rsi': row.get('rsi'),
                'trend': trend,
                'signals': signals,
                'row': row,
                'cost': cost,
                'pnl_pct': pnl_pct,
                'has_breakdown': has_breakdown,
                'has_divergence': has_divergence,
                'has_oversold': has_oversold,
                'has_shrink': has_shrink,
                'has_rps_decay': has_rps_decay,
                'is_danger': is_danger,
                'stop_loss': stop_loss,
                'div_target': div_target,
                'sector': get_sector(stock_code)
            })

        # 解析前一天报告
        prev_status = self._parse_prev_report(prev_report_path) if prev_report_path else {}

        # 信号分组
        red_alerts = []
        divergence_alerts = []
        for r in analysis_results:
            if r['has_divergence']:
                divergence_alerts.append(r)
            elif any(s.level == SignalLevel.RED for s in r['signals']):
                red_alerts.append(r)

        red_codes = {r['code'] for r in red_alerts}
        divergence_codes = {r['code'] for r in divergence_alerts}

        yellow_alerts = [
            r for r in analysis_results
            if r['code'] not in red_codes
            and r['code'] not in divergence_codes
            and any(s.level == SignalLevel.YELLOW for s in r['signals'])
        ]
        yellow_codes = {r['code'] for r in yellow_alerts} | red_codes | divergence_codes

        green_signals = [
            r for r in analysis_results
            if r['code'] not in yellow_codes
            and any(s.level == SignalLevel.GREEN for s in r['signals'])
        ]

        # 板块联动预警
        all_red_codes = red_codes | divergence_codes
        sector_alerts = self.detector.detect_sector_alerts(list(all_red_codes))

        # RPS 斜率转换榜
        slope_transitions = self.detector.detect_rps_slope_transition(analysis_results)

        # 极度危险列表
        danger_list = [r for r in analysis_results if r['is_danger']]

        # 生成图表
        chart_paths = {}
        if self.generate_charts and full_df is not None and not full_df.empty:
            logger.info("生成技术分析图表...")
            for r in analysis_results:
                try:
                    chart_path = self.chart_generator.generate_chart(
                        df=full_df,
                        stock_code=r['code'],
                        stock_name=r['name'],
                        analysis_result=r,
                        scan_date=scan_date
                    )
                    if chart_path:
                        chart_paths[r['code']] = chart_path
                except Exception as e:
                    logger.warning(f"生成 {r['code']} 图表失败: {e}")

            logger.info(f"图表生成完成: {len(chart_paths)} 张")

        # 生成报告
        report = self._build_report(
            scan_date=scan_date,
            total_count=len(positions),
            red_alerts=red_alerts,
            divergence_alerts=divergence_alerts,
            yellow_alerts=yellow_alerts,
            green_signals=green_signals,
            all_results=analysis_results,
            sector_alerts=sector_alerts,
            slope_transitions=slope_transitions,
            danger_list=danger_list,
            prev_status=prev_status,
            index_status=index_status,
            chart_paths=chart_paths
        )

        filename = f"TechScan_{scan_date.strftime('%Y%m%d')}.md"
        filepath = self.output_dir / filename
        filepath.write_text(report, encoding='utf-8')

        logger.info(f"报告已生成: {filepath}")
        return str(filepath), analysis_results

    def _parse_prev_report(self, report_path: str) -> Dict[str, str]:
        """解析前一天报告"""
        if not report_path or not Path(report_path).exists():
            return {}
        try:
            content = Path(report_path).read_text(encoding='utf-8')
            status = {}
            sections = [
                ("RED", r"## 🔴 红灯预警.*?(?=## 🔄|## ⚠️ 黄灯提醒)"),
                ("DIVERGENCE", r"## 🔄 底背离观察.*?## ⚠️ 黄灯提醒"),
                ("YELLOW", r"## ⚠️ 黄灯提醒.*?## 🟢 积极信号"),
                ("GREEN", r"## 🟢 积极信号.*?## 📊 全持仓概览"),
            ]
            for level_name, pattern in sections:
                match = re.search(pattern, content, re.DOTALL)
                if match:
                    for code_match in re.finditer(r'(\d{6}\.(?:SH|SZ))', match.group()):
                        status[code_match.group(1)] = level_name
            return status
        except Exception as e:
            logger.warning(f"解析前一天报告失败: {e}")
            return {}

    def _build_report(
        self,
        scan_date: datetime,
        total_count: int,
        red_alerts: List[Dict],
        divergence_alerts: List[Dict],
        yellow_alerts: List[Dict],
        green_signals: List[Dict],
        all_results: List[Dict],
        sector_alerts: List[Dict],
        slope_transitions: List[Dict],
        danger_list: List[Dict],
        prev_status: Dict[str, str],
        index_status: Optional[Dict],
        chart_paths: Optional[Dict[str, str]] = None
    ) -> str:
        """构建报告内容"""
        lines = []

        # 标题
        lines.append(f"# 技术面扫描报告 - {scan_date.strftime('%Y-%m-%d')}")
        lines.append("")
        lines.append(f"> 扫描时间: {scan_date.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"> 持仓数量: {total_count} 只 A股/ETF")
        lines.append(f"> 🔴 破位: {sum(1 for r in red_alerts if r['has_breakdown'])} | "
                      f"🔴 警示: {sum(1 for r in red_alerts if not r['has_breakdown'])} | "
                      f"⚠️ 黄灯: {len(yellow_alerts) + len(divergence_alerts)} | "
                      f"🟢 绿灯: {len(green_signals)}")

        if danger_list:
            lines.append(f"> 🚨 **极度危险: {len(danger_list)} 只** (亏损>{abs(self.DANGER_PNL_THRESHOLD):.0f}% + 破位信号)")

        calendar_hints = get_trading_calendar_hints(scan_date)
        if calendar_hints:
            lines.append(f"> 📅 {', '.join(calendar_hints)}")

        lines.append("")
        lines.append("---")
        lines.append("")

        # 指数锚点
        if index_status:
            lines.append(f"## 📌 大盘锚点: {index_status['name']} ({index_status['code']})")
            lines.append("")
            trend_emoji = {"强势多头": "🟢🟢", "多头排列": "🟢", "震荡整理": "⚪",
                           "空头排列": "🔴", "强势空头": "🔴🔴"}.get(index_status['trend'], "⚪")
            pct = index_status.get('pct')
            pct_str = f"{pct:+.2f}%" if pct else "-"
            lines.append(f"> 趋势: {trend_emoji} {index_status['trend']} | 最新涨跌: {pct_str}")
            if index_status['trend'] in ('空头排列', '强势空头'):
                lines.append("> ⚠️ 大盘偏弱，持仓中的「回踩」信号需提高警惕，可能是顺势回调而非支撑")
            elif index_status['trend'] in ('多头排列', '强势多头'):
                lines.append("> 大盘偏强，持仓中的「破位」可能是假摔，关注后续是否收回")
            lines.append("")

        # 极度危险警告（置顶）
        if danger_list:
            lines.append("## 🚨 极度危险 (建议执行减仓)")
            lines.append("")
            lines.append("> 亏损超过 8% 且出现破位信号，趋势可能已恶化")
            lines.append("")
            lines.append("| 代码 | 名称 | 层级 | 最新价 | 盈亏 | 止损参考 | 破位信号 |")
            lines.append("|------|------|------|--------|------|----------|----------|")
            for r in danger_list:
                red_sigs = [s.name for s in r['signals'] if s.level == SignalLevel.RED]
                stop_str = f"{r['stop_loss']['stop_price']:.2f} ({r['stop_loss']['method']})" if r['stop_loss'] else "-"
                pct = self._fmt_pct(r['pct_change'])
                close = self._fmt_price(r['close'])
                pnl = self._fmt_pnl(r['pnl_pct'])
                lines.append(
                    f"| **{r['code']}** | **{r['name']}** | {r['level']} | "
                    f"{close} | {pnl} | {stop_str} | {', '.join(red_sigs)} |"
                )
            lines.append("")

        # 板块联动预警
        if sector_alerts:
            lines.append("## 🏭 行业板块预警")
            lines.append("")
            for alert in sector_alerts:
                lines.append(f"- **{alert['sector']}** ({alert['count']}只红灯): {', '.join(alert['codes'])}")
            lines.append("")

        # RPS 斜率转换榜
        if slope_transitions:
            lines.append("## ⚡ RPS 强弱转换榜")
            lines.append("")
            lines.append("> RPS 排名尚可但斜率快速转负，需警惕掉头加速")
            lines.append("")
            lines.append("| 代码 | 名称 | 层级 | RPS | 斜率Z值 | 盈亏 |")
            lines.append("|------|------|------|-----|---------|------|")
            for t in slope_transitions:
                pnl = self._fmt_pnl(t.get('pnl_pct'))
                lines.append(
                    f"| {t['code']} | {t['name']} | {t['level']} | "
                    f"{t['rps']:.0f} | {t['slope']:.2f} | {pnl} |"
                )
            lines.append("")

        # 红灯预警
        if red_alerts:
            lines.append("## 🔴 红灯预警 (需关注)")
            lines.append("")

            level_order = {'L1': 0, 'L2': 1, 'L3': 2}
            sorted_red = sorted(
                red_alerts,
                key=lambda x: (0 if x['has_breakdown'] else 1, level_order.get(x['level'], 9))
            )

            lines.append("| 代码 | 名称 | 层级 | 最新价 | 涨跌幅 | 盈亏 | 止损参考 | 信号 |")
            lines.append("|------|------|------|--------|--------|------|----------|------|")

            for r in sorted_red:
                red_signals = [s for s in r['signals'] if s.level == SignalLevel.RED]
                red_signals.sort(key=lambda s: (0 if s.severity == SignalSeverity.BREAKDOWN else 1))
                signals_str = ", ".join([s.name for s in red_signals])

                if r['has_oversold']:
                    signals_str += " *(超卖，不宜杀跌)*"

                code_display = f"**{r['code']}**" if r['level'] == 'L1' else r['code']
                name_display = f"**{r['name']}**" if r['level'] == 'L1' else r['name']

                stop_str = f"{r['stop_loss']['stop_price']:.2f}" if r['stop_loss'] else "-"

                lines.append(
                    f"| {code_display} | {name_display} | {r['level']} | "
                    f"{self._fmt_price(r['close'])} | {self._fmt_pct(r['pct_change'])} | "
                    f"{self._fmt_pnl(r['pnl_pct'])} | {stop_str} | {signals_str} |"
                )
            lines.append("")

        # 背离信号
        if divergence_alerts:
            lines.append("## 🔄 底背离观察 (潜在筑底)")
            lines.append("")
            lines.append("> 价格破位但 MACD 金叉，指标与价格背离，列为黄灯观察区")
            lines.append("")
            lines.append("| 代码 | 名称 | 层级 | 最新价 | 涨跌幅 | 盈亏 | 反弹目标 | 空间 |")
            lines.append("|------|------|------|--------|--------|------|----------|------|")
            for r in divergence_alerts:
                dt = r['div_target']
                target_str = f"{dt['target_ma']}={dt['target_price']}" if dt else "-"
                space_str = f"+{dt['space_pct']}%" if dt else "-"
                lines.append(
                    f"| {r['code']} | {r['name']} | {r['level']} | "
                    f"{self._fmt_price(r['close'])} | {self._fmt_pct(r['pct_change'])} | "
                    f"{self._fmt_pnl(r['pnl_pct'])} | {target_str} | {space_str} |"
                )
            lines.append("")

        # 黄灯提醒
        if yellow_alerts:
            lines.append("## ⚠️ 黄灯提醒")
            lines.append("")
            lines.append("| 代码 | 名称 | 层级 | 最新价 | 涨跌幅 | 盈亏 | 提醒信号 |")
            lines.append("|------|------|------|--------|--------|------|----------|")
            for r in yellow_alerts:
                yellow_signals = [s for s in r['signals'] if s.level == SignalLevel.YELLOW]
                signals_str = ", ".join([s.name for s in yellow_signals])

                lines.append(
                    f"| {r['code']} | {r['name']} | {r['level']} | "
                    f"{self._fmt_price(r['close'])} | {self._fmt_pct(r['pct_change'])} | "
                    f"{self._fmt_pnl(r['pnl_pct'])} | {signals_str} |"
                )
            lines.append("")

        # 积极信号
        if green_signals:
            lines.append("## 🟢 积极信号")
            lines.append("")
            lines.append("| 代码 | 名称 | 层级 | 最新价 | 涨跌幅 | 盈亏 | 积极信号 |")
            lines.append("|------|------|------|--------|--------|------|----------|")
            for r in green_signals:
                green_sig = [s for s in r['signals'] if s.level == SignalLevel.GREEN]
                signals_str = ", ".join([s.name for s in green_sig])
                lines.append(
                    f"| {r['code']} | {r['name']} | {r['level']} | "
                    f"{self._fmt_price(r['close'])} | {self._fmt_pct(r['pct_change'])} | "
                    f"{self._fmt_pnl(r['pnl_pct'])} | {signals_str} |"
                )
            lines.append("")

        lines.append("---")
        lines.append("")

        # 全持仓概览
        lines.append("## 📊 全持仓概览")
        lines.append("")
        lines.append("| 代码 | 名称 | 层级 | 最新价 | MA20 | MA60 | RPS | 趋势 | 盈亏 | 止损 | 信号 |")
        lines.append("|------|------|------|--------|------|------|-----|------|------|------|------|")

        level_order = {'L1': 0, 'L2': 1, 'L3': 2}
        sorted_results = sorted(
            all_results,
            key=lambda x: (level_order.get(x['level'], 9), x['code'])
        )

        for r in sorted_results:
            stop_str = f"{r['stop_loss']['stop_price']:.2f}" if r['stop_loss'] else "-"
            rps = f"{r['rps']:.0f}" if r['rps'] is not None and not pd.isna(r['rps']) else "-"

            signals_str = ", ".join([s.name for s in r['signals'][:2]])
            if len(r['signals']) > 2:
                signals_str += "..."

            change_str = self._get_status_change(r['code'], r['signals'], prev_status)
            if change_str:
                signals_str = f"{signals_str} {change_str}"

            lines.append(
                f"| {r['code']} | {r['name']} | {r['level']} | "
                f"{self._fmt_price(r['close'])} | {self._fmt_price(r['ma20'])} | "
                f"{self._fmt_price(r['ma60'])} | {rps} | {r['trend']} | "
                f"{self._fmt_pnl(r['pnl_pct'])} | {stop_str} | {signals_str} |"
            )

        lines.append("")
        lines.append("---")
        lines.append("")

        # 技术指标明细
        lines.append("## 📈 技术指标明细")
        lines.append("")

        for r in sorted_results:
            row = r['row']
            lines.append(f"### {r['code']} {r['name']}")
            lines.append("")

            # 嵌入图表
            if chart_paths and r['code'] in chart_paths:
                chart_file = Path(chart_paths[r['code']]).name
                lines.append(f"![技术分析图](charts/{chart_file})")
                lines.append("")

            lines.append(f"- **趋势**: {r['trend']}")
            lines.append(f"- **板块**: {r['sector']}")

            # 盈亏
            if r['cost'] is not None and r['pnl_pct'] is not None:
                pnl_val = r['pnl_pct']
                warn = " ⚠️ 亏损较大" if pnl_val < -5 else ""
                lines.append(f"- **盈亏**: {pnl_val:+.2f}% (成本 {r['cost']:.2f}){warn}")

            # 止损参考
            if r['stop_loss']:
                sl = r['stop_loss']
                lines.append(f"- **止损参考**: {sl['method']}止损 = {sl['stop_price']:.2f} ({sl['description']})")

            # 均线偏离
            ma20_bias = row.get('ma20_bias')
            ma60_bias = row.get('ma60_bias')
            if ma20_bias is not None and not pd.isna(ma20_bias):
                bias_str = f"距MA20 {ma20_bias:+.1f}%"
                if ma60_bias is not None and not pd.isna(ma60_bias):
                    bias_str += f", 距MA60 {ma60_bias:+.1f}%"
                lines.append(f"- **均线偏离**: {bias_str}")

            # RPS
            rps = r['rps']
            if rps is not None and not pd.isna(rps):
                lines.append(f"- **RPS**: {rps:.0f}")

            rps_slope = row.get('rps_slope')
            if rps_slope is not None and not pd.isna(rps_slope):
                lines.append(f"- **RPS斜率**: Z={rps_slope:.2f}")

            # MACD
            dif = row.get('macd_dif')
            if dif is not None and not pd.isna(dif):
                dea = row.get('macd_dea')
                hist = row.get('macd_hist')
                lines.append(f"- **MACD**: DIF={dif:.3f}, DEA={dea:.3f}, 柱状={hist:.3f}")

            # RSI
            rsi = row.get('rsi')
            if rsi is not None and not pd.isna(rsi):
                lines.append(f"- **RSI(14)**: {rsi:.1f}")

            # ATR
            atr = row.get('atr_14')
            if atr is not None and not pd.isna(atr):
                lines.append(f"- **ATR(14)**: {atr:.2f}")

            # 成交量
            volume = row.get('volume')
            vol_ma5 = row.get('vol_ma5')
            volume_ratio = row.get('volume_ratio')
            if volume is not None and vol_ma5 is not None:
                if not pd.isna(volume) and not pd.isna(vol_ma5):
                    ratio_str = f" ({volume_ratio:.1f}x)" if volume_ratio and not pd.isna(volume_ratio) else ""
                    lines.append(f"- **成交量**: 今日 {self._format_volume(volume)}, 5日均量 {self._format_volume(vol_ma5)}{ratio_str}")

            # 信号
            if r['signals']:
                signals_detail = "; ".join([
                    f"{s.level.value} {s.name}: {s.description}"
                    for s in r['signals']
                ])
                lines.append(f"- **信号**: {signals_detail}")

            lines.append("")

        return "\n".join(lines)

    def _get_status_change(self, code: str, signals: List[Signal], prev_status: Dict[str, str]) -> str:
        """获取状态变化标注"""
        if not prev_status or code not in prev_status:
            return ""

        prev = prev_status[code]
        has_red = any(s.level == SignalLevel.RED for s in signals)
        has_divergence = any(s.tag == SignalTag.DIVERGENCE for s in signals)
        has_yellow = any(s.level == SignalLevel.YELLOW for s in signals)
        has_green = any(s.level == SignalLevel.GREEN for s in signals)

        if has_divergence:
            curr = "DIVERGENCE"
        elif has_red:
            curr = "RED"
        elif has_yellow:
            curr = "YELLOW"
        elif has_green:
            curr = "GREEN"
        else:
            curr = "NORMAL"

        if curr == prev:
            return ""

        emoji_map = {
            "RED": "🔴", "YELLOW": "⚠️", "GREEN": "🟢",
            "NORMAL": "⚪", "DIVERGENCE": "🔄"
        }
        return f"`{emoji_map.get(prev, prev)}->{emoji_map.get(curr, curr)}`"

    @staticmethod
    def _fmt_price(val) -> str:
        if val is not None and not pd.isna(val):
            return f"{val:.2f}"
        return "-"

    @staticmethod
    def _fmt_pct(val) -> str:
        if val is not None and not pd.isna(val):
            return f"{val:+.2f}%"
        return "-"

    @staticmethod
    def _fmt_pnl(val) -> str:
        if val is not None and not pd.isna(val):
            return f"{val:+.2f}%"
        return "-"

    @staticmethod
    def _format_volume(volume: float) -> str:
        if volume >= 1e8:
            return f"{volume/1e8:.2f}亿"
        elif volume >= 1e4:
            return f"{volume/1e4:.0f}万"
        else:
            return f"{volume:.0f}"
