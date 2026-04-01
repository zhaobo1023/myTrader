# -*- coding: utf-8 -*-
"""markdown report generator for log bias daily"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

SIGNAL_DISPLAY = {
    'overheat': '[RED] overheat',
    'breakout': '[YELLOW] breakout',
    'pullback': '[GREEN] pullback',
    'normal': '[GRAY] normal',
    'stall': '[RED] stall',
}


class ReportGenerator:
    """generate markdown daily report"""

    def __init__(self, output_dir: str, etf_names: Dict[str, str]):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.etf_names = etf_names

    def generate(self, summary_data: List[dict], report_date: str) -> str:
        """
        generate report

        Args:
            summary_data: list of dicts, each with keys:
                ts_code, name, close, log_bias, signal_state, prev_state
            report_date: YYYY-MM-DD

        Returns:
            path to the generated report file
        """
        if not summary_data:
            logger.warning("No data to generate report")
            return ''

        df = pd.DataFrame(summary_data)

        lines = []
        lines.append(f"# Log Bias Daily Report - {report_date}")
        lines.append("")

        # signal summary
        lines.append("## Signal Summary")
        lines.append("")
        lines.append("| Status | Count | ETFs |")
        lines.append("|--------|-------|------|")

        for state in ['overheat', 'breakout', 'pullback', 'normal', 'stall']:
            subset = df[df['signal_state'] == state]
            if len(subset) == 0:
                names_str = '-'
            else:
                names_str = ', '.join(subset['name'].tolist())
            display = SIGNAL_DISPLAY.get(state, state)
            lines.append(f"| {display} | {len(subset)} | {names_str} |")

        lines.append("")

        # detail table sorted by log_bias desc
        lines.append("## Detail Data")
        lines.append("")
        lines.append("| ETF | Code | Close | LogBias | Status | Change |")
        lines.append("|-----|------|-------|---------|--------|--------|")

        df_sorted = df.sort_values('log_bias', ascending=False)
        for _, row in df_sorted.iterrows():
            display = SIGNAL_DISPLAY.get(row['signal_state'], row['signal_state'])
            change = f"{row.get('prev_state', '')}->{row['signal_state']}" if row.get('prev_state') and row['prev_state'] != row['signal_state'] else '-'
            lines.append(
                f"| {row['name']} | {row['ts_code']} | {row['close']:.4f} | "
                f"{row['log_bias']:.2f}% | {display} | {change} |"
            )

        lines.append("")
        lines.append("---")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        report_text = "\n".join(lines)
        filename = f"LogBias_{report_date.replace('-', '')}.md"
        filepath = self.output_dir / filename
        filepath.write_text(report_text, encoding='utf-8')
        logger.info(f"Report saved: {filepath}")
        return str(filepath)
