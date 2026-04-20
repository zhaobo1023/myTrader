# -*- coding: utf-8 -*-
"""策略权重分配报告"""
import os
import logging
from typing import List, Dict
from .schemas import StrategyWeight

logger = logging.getLogger(__name__)


def generate_report(weights: List[StrategyWeight], suggestions: List[Dict], output_dir: str) -> str:
    """Generate markdown allocation report"""
    if not weights:
        return ""
    
    os.makedirs(output_dir, exist_ok=True)
    calc_date = weights[0].calc_date
    report_path = os.path.join(output_dir, f"allocation_report_{calc_date}.md")
    
    regime = weights[0].regime
    crowding = weights[0].crowding_level
    
    lines = []
    lines.append(f"# Strategy Allocation Report - {calc_date}")
    lines.append("")
    lines.append(f"**Regime**: {regime} | **Crowding**: {crowding}")
    lines.append("")
    
    # Weight table
    lines.append("## Target Weights")
    lines.append("")
    lines.append("| Strategy | Base | Regime Adj | Crowding Adj | Final |")
    lines.append("|----------|------|------------|--------------|-------|")
    for w in weights:
        lines.append(
            f"| {w.strategy_name} | {w.base_weight:.0%} | "
            f"{w.regime_adjustment:+.0%} | {w.crowding_adjustment:+.0%} | "
            f"**{w.final_weight:.1%}** |"
        )
    lines.append("")
    
    # Rebalance suggestions
    if suggestions:
        lines.append("## Rebalance Suggestions")
        lines.append("")
        lines.append("| Strategy | Current | Target | Action | Delta |")
        lines.append("|----------|---------|--------|--------|-------|")
        for s in suggestions:
            current_str = f"{s['current']:.1f}%" if s['current'] is not None else "N/A"
            delta_str = f"{s['delta']:+.1f}pp" if s['delta'] is not None else "-"
            lines.append(f"| {s['strategy']} | {current_str} | {s['target']:.1f}% | {s['action']} | {delta_str} |")
        lines.append("")
    
    # Notes
    lines.append("## Notes")
    lines.append("")
    lines.append("- Weights are normalized to sum = 100%")
    lines.append("- Constraints: each strategy clamped to [5%, 60%]")
    lines.append("- HOLD: delta < 5pp, no rebalance needed")
    lines.append("- Crowding penalty reduces momentum strategies in HIGH/CRITICAL crowding")
    
    content = '\n'.join(lines)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    logger.info(f"Report saved: {report_path}")
    return report_path
