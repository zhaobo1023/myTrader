# -*- coding: utf-8 -*-
"""牛熊信号 Markdown 报告生成"""
import os
import logging
from datetime import date
from typing import List
from .schemas import BullBearSignal

logger = logging.getLogger(__name__)


def generate_report(signals: List[BullBearSignal], output_dir: str) -> str:
    """Generate markdown report for bull/bear signals"""
    if not signals:
        return ""

    os.makedirs(output_dir, exist_ok=True)
    latest = signals[-1]
    report_path = os.path.join(output_dir, f"bull_bear_report_{latest.calc_date}.md")

    lines = []
    lines.append(f"# Bull/Bear Regime Report - {latest.calc_date}")
    lines.append("")
    lines.append(f"## Current Regime: {latest.regime} (score: {latest.composite_score})")
    lines.append("")

    # Signal table
    lines.append("## Indicator Signals")
    lines.append("")
    lines.append("| Indicator | Value | MA20 | Trend | Signal |")
    lines.append("|-----------|-------|------|-------|--------|")

    bond_signal_str = {1: 'BULLISH', -1: 'BEARISH', 0: 'NEUTRAL'}.get(latest.cn_10y_signal, 'N/A')
    usdcny_signal_str = {1: 'BULLISH', -1: 'BEARISH', 0: 'NEUTRAL'}.get(latest.usdcny_signal, 'N/A')
    div_signal_str = {1: 'BULLISH', -1: 'BEARISH', 0: 'NEUTRAL'}.get(latest.dividend_signal, 'N/A')

    bond_val = f"{latest.cn_10y_value}" if latest.cn_10y_value is not None else 'N/A'
    bond_ma = f"{latest.cn_10y_ma20}" if latest.cn_10y_ma20 is not None else 'N/A'
    usdcny_val = f"{latest.usdcny_value}" if latest.usdcny_value is not None else 'N/A'
    usdcny_ma = f"{latest.usdcny_ma20}" if latest.usdcny_ma20 is not None else 'N/A'
    div_val = f"{latest.dividend_relative:.4f}" if latest.dividend_relative is not None else 'N/A'
    div_ma = f"{latest.dividend_rel_ma20}" if latest.dividend_rel_ma20 is not None else 'N/A'

    lines.append(f"| 10Y Bond | {bond_val} | {bond_ma} | {latest.cn_10y_trend or 'N/A'} | {bond_signal_str} |")
    lines.append(f"| USDCNY | {usdcny_val} | {usdcny_ma} | {latest.usdcny_trend or 'N/A'} | {usdcny_signal_str} |")
    lines.append(f"| Dividend/CSI300 | {div_val} | {div_ma} | {latest.dividend_trend or 'N/A'} | {div_signal_str} |")
    lines.append("")

    # Regime history (last 20)
    lines.append("## Recent Regime History (last 20 days)")
    lines.append("")
    lines.append("| Date | Score | Regime |")
    lines.append("|------|-------|--------|")
    for s in signals[-20:]:
        lines.append(f"| {s.calc_date} | {s.composite_score} | {s.regime} |")
    lines.append("")

    # Interpretation
    lines.append("## Interpretation")
    lines.append("")
    lines.append("- **BULL** (score >= 2): Favorable macro conditions for equity allocation")
    lines.append("- **BEAR** (score <= -2): Defensive positioning recommended")
    lines.append("- **NEUTRAL**: Mixed signals, maintain current allocation")
    lines.append("")
    lines.append("### Signal Logic")
    lines.append("- 10Y Bond: Yield DOWN + < 2.5% = bullish; UP + > 3.0% = bearish")
    lines.append("- USDCNY: RMB appreciating = bullish; depreciating + momentum = bearish")
    lines.append("- Dividend/CSI300: Dividend underperforming = risk-on (bullish)")

    content = '\n'.join(lines)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(content)

    logger.info(f"Report saved: {report_path}")
    return report_path
