# -*- coding: utf-8 -*-
"""
ReportBuilder - Markdown 研报组装器

将五步法各步骤结果组装为标准化 Markdown 研报。
两种模式：comprehensive（含技术面）/ fundamental_only（纯基本面）。
"""
from datetime import date
from typing import Dict, Optional


class ReportBuilder:
    """研报 Markdown 组装器"""

    _COMPREHENSIVE_TEMPLATE = """\
# {stock_name}（{stock_code}）深度研报

> **报告类型**: 综合研报（基本面 + 技术面）
> **报告日期**: {today}
> **分析框架**: 五步法基本面 + 技术面综合分析

---

{step1}

---

{step2}

---

{step3}

---

{step4}

---

{step5}

---

## 六、技术面分析

{tech_section}

---

*本报告由 myTrader 智能研报系统生成，仅供参考，不构成投资建议。*
"""

    _FUNDAMENTAL_TEMPLATE = """\
# {stock_name}（{stock_code}）基本面研报

> **报告日期**: {today}
> **分析框架**: 五步法基本面分析

---

{step1}

---

{step2}

---

{step3}

---

{step4}

---

{step5}

---

*本报告由 myTrader 智能研报系统生成，仅供参考，不构成投资建议。*
"""

    def build_comprehensive(
        self,
        stock_code: str,
        stock_name: str,
        fundamental_results: Dict[str, str],
        tech_section: str,
        executive_summary: str = "",
    ) -> str:
        """组装综合研报（基本面 + 技术面）"""
        today = date.today().isoformat()
        return self._COMPREHENSIVE_TEMPLATE.format(
            stock_code=stock_code,
            stock_name=stock_name,
            today=today,
            step1=self._section("一、信息差分析", fundamental_results.get("step1", "[未生成]")),
            step2=self._section("二、逻辑差分析", fundamental_results.get("step2", "[未生成]")),
            step3=self._section("三、预期差分析", fundamental_results.get("step3", "[未生成]")),
            step4=self._section("四、催化剂识别", fundamental_results.get("step4", "[未生成]")),
            step5=self._section("五、综合结论", fundamental_results.get("step5", "[未生成]")),
            tech_section=tech_section or "[技术面分析未生成]",
        )

    def build_fundamental_only(
        self,
        stock_code: str,
        stock_name: str,
        fundamental_results: Dict[str, str],
    ) -> str:
        """组装纯基本面研报"""
        today = date.today().isoformat()
        return self._FUNDAMENTAL_TEMPLATE.format(
            stock_code=stock_code,
            stock_name=stock_name,
            today=today,
            step1=self._section("一、信息差分析", fundamental_results.get("step1", "[未生成]")),
            step2=self._section("二、逻辑差分析", fundamental_results.get("step2", "[未生成]")),
            step3=self._section("三、预期差分析", fundamental_results.get("step3", "[未生成]")),
            step4=self._section("四、催化剂识别", fundamental_results.get("step4", "[未生成]")),
            step5=self._section("五、综合结论", fundamental_results.get("step5", "[未生成]")),
        )

    @staticmethod
    def _section(title: str, content: str) -> str:
        """Wrap content with a ## section header."""
        return f"## {title}\n\n{content}"
