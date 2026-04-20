# -*- coding: utf-8 -*-
"""拥挤度 Markdown 报告生成"""
import os
import logging
from typing import List
from .schemas import CrowdingScore

logger = logging.getLogger(__name__)


def generate_report(scores: List[CrowdingScore], output_dir: str) -> str:
    """Generate markdown report for crowding scores"""
    if not scores:
        return ""
    
    os.makedirs(output_dir, exist_ok=True)
    latest = scores[-1]
    report_path = os.path.join(output_dir, f"crowding_report_{latest.calc_date}.md")
    
    lines = []
    lines.append(f"# Crowding Monitor Report - {latest.calc_date}")
    lines.append("")
    
    # Level indicator
    level_label = {
        'LOW': '[OK] LOW',
        'MEDIUM': '[NOTE] MEDIUM', 
        'HIGH': '[WARN] HIGH',
        'CRITICAL': '[RED] CRITICAL',
    }
    lines.append(f"## Current Level: {level_label.get(latest.crowding_level, latest.crowding_level)}")
    lines.append(f"**Composite Score**: {latest.crowding_score:.1f} / 100")
    lines.append("")
    
    # Component breakdown
    lines.append("## Component Breakdown")
    lines.append("")
    lines.append("| Component | Value | Description |")
    lines.append("|-----------|-------|-------------|")
    
    hhi_str = f"{latest.turnover_hhi:.4f}" if latest.turnover_hhi is not None else "N/A"
    hhi_pct_str = f"{latest.turnover_hhi_percentile:.1%}" if latest.turnover_hhi_percentile is not None else "N/A"
    lines.append(f"| Turnover HHI | {hhi_str} (pctl: {hhi_pct_str}) | Industry concentration |")
    
    north_str = f"{latest.northbound_deviation:.2f} sigma" if latest.northbound_deviation is not None else "N/A"
    lines.append(f"| Northbound Deviation | {north_str} | Flow deviation from trend |")
    
    margin_str = f"{latest.margin_concentration:.4f}" if latest.margin_concentration is not None else "N/A (no data)"
    lines.append(f"| Margin Concentration | {margin_str} | Leveraged trading focus |")
    
    svd_str = f"{latest.svd_top1_ratio:.4f}" if latest.svd_top1_ratio is not None else "N/A"
    lines.append(f"| SVD Top1 Ratio | {svd_str} | Factor concentration |")
    lines.append("")
    
    # Recent history
    lines.append("## Recent History (last 20 days)")
    lines.append("")
    lines.append("| Date | Score | Level |")
    lines.append("|------|-------|-------|")
    for s in scores[-20:]:
        lines.append(f"| {s.calc_date} | {s.crowding_score:.1f} | {s.crowding_level} |")
    lines.append("")
    
    # Interpretation
    lines.append("## Level Interpretation")
    lines.append("")
    lines.append("- **LOW** (< 25): Normal market conditions")
    lines.append("- **MEDIUM** (25-50): Increasing concentration, monitor closely")
    lines.append("- **HIGH** (50-75): Significant crowding, reduce momentum exposure")
    lines.append("- **CRITICAL** (> 75): Extreme crowding, high crash probability")
    lines.append("")
    lines.append("## Action Guidelines")
    lines.append("")
    lines.append("- HIGH: Reduce momentum strategy weight by 10-20%")
    lines.append("- CRITICAL: Cut momentum exposure by 30-50%, increase hedging")
    
    content = '\n'.join(lines)
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    logger.info(f"Report saved: {report_path}")
    return report_path
