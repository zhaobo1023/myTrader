# -*- coding: utf-8 -*-
"""
ReportBuilder - Markdown 研报组装器 v2.0

v2.0 改进：
- 新增执行摘要区块（报告开头的决策速览卡片）
- 章节标题更新为 v2.0 命名
- 支持 executive_summary 参数
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

## 执行摘要

{executive_summary}

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

## 执行摘要

{executive_summary}

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
            executive_summary=executive_summary or "[执行摘要未生成]",
            step1=self._section("一、财报关键发现", fundamental_results.get("step1", "[未生成]")),
            step2=self._section("二、驱动逻辑与护城河", fundamental_results.get("step2", "[未生成]")),
            step3=self._section("三、估值与预期偏差", fundamental_results.get("step3", "[未生成]")),
            step4=self._section("四、催化剂时间表", fundamental_results.get("step4", "[未生成]")),
            step5=self._section("五、风险与操作建议", fundamental_results.get("step5", "[未生成]")),
            tech_section=tech_section or "[技术面分析未生成]",
        )

    def build_fundamental_only(
        self,
        stock_code: str,
        stock_name: str,
        fundamental_results: Dict[str, str],
        executive_summary: str = "",
    ) -> str:
        """组装纯基本面研报（Step5 中技术面价位区块会被移除）"""
        today = date.today().isoformat()
        step5_content = self._strip_tech_price_section(fundamental_results.get("step5", "[未生成]"))
        return self._FUNDAMENTAL_TEMPLATE.format(
            stock_code=stock_code,
            stock_name=stock_name,
            today=today,
            executive_summary=executive_summary or "[执行摘要未生成]",
            step1=self._section("一、财报关键发现", fundamental_results.get("step1", "[未生成]")),
            step2=self._section("二、驱动逻辑与护城河", fundamental_results.get("step2", "[未生成]")),
            step3=self._section("三、估值与预期偏差", fundamental_results.get("step3", "[未生成]")),
            step4=self._section("四、催化剂时间表", fundamental_results.get("step4", "[未生成]")),
            step5=self._section("五、风险与操作建议", step5_content),
        )

    @staticmethod
    def _section(title: str, content: str) -> str:
        """Wrap content with a ## section header."""
        return f"## {title}\n\n{content}"

    @staticmethod
    def _strip_tech_price_section(content: str) -> str:
        """从 Step5 输出中移除技术面参考价位区块及相关残留文本（用于纯基本面报告）。"""
        # 移除正式的 #### 技术面参考价位 区块
        marker = "#### 技术面参考价位"
        idx = content.find(marker)
        if idx != -1:
            content = content[:idx].rstrip()

        # 移除 LLM 可能输出的残留提示性文本
        for stub in ["[无技术面数据]", "[技术面数据不足]", "[无技术面参考价位]"]:
            content = content.replace(stub, "").strip()

        return content
