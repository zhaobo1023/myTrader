# -*- coding: utf-8 -*-
"""
EightSectionAssembler - Markdown report assembler.

Responsibilities:
1. Assemble 8 chapters into complete Markdown report
2. Write to ~/Documents/notes/Finance/
3. Return full Markdown string for DB storage
"""
import os
from datetime import date
from typing import Dict


class EightSectionAssembler:
    """Assemble eight-section analysis report."""

    REPORT_TEMPLATE = """\
# {stock_name}（{stock_code}）全面分析

> 报告类型: 八章节结构化分析
> 报告日期: {today}
> 数据来源: myTrader 系统（MySQL）

---

{ch1}

---

{ch2}

---

{ch3}

---

{ch4}

---

{ch5_6}

---

{ch7}

---

{ch8}

---

*本报告由 myTrader 智能研报系统生成，基于数据库实际数据。*
*免责声明：本分析仅供参考，不构成投资建议。投资有风险，入市需谨慎。*
"""

    def assemble(self, stock_code: str, stock_name: str,
                 chapters: Dict[str, str]) -> str:
        """Assemble full report from chapters."""
        return self.REPORT_TEMPLATE.format(
            stock_name=stock_name,
            stock_code=stock_code,
            today=date.today().strftime("%Y-%m-%d"),
            ch1=chapters.get("ch1", ""),
            ch2=chapters.get("ch2", ""),
            ch3=chapters.get("ch3", ""),
            ch4=chapters.get("ch4", ""),
            ch5_6=chapters.get("ch5_6", ""),
            ch7=chapters.get("ch7", ""),
            ch8=chapters.get("ch8", ""),
        )

    def write_to_file(self, stock_name: str, content: str) -> str:
        """Write report to ~/Documents/notes/Finance/.

        Returns:
            File path of the written report.
        """
        output_dir = os.path.expanduser("~/Documents/notes/Finance")
        os.makedirs(output_dir, exist_ok=True)

        today_str = date.today().strftime("%Y%m%d")
        filename = f"{stock_name}-全面分析-{today_str}.md"
        filepath = os.path.join(output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        return filepath
