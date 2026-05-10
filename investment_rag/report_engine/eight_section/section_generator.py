# -*- coding: utf-8 -*-
"""
EightSectionGenerator - 八章节生成引擎

混合渲染策略：
- 第1/3/7章: 纯 Python 模板渲染（不调 LLM）
- 第2/4/5+6/8章: LLM 生成（共4次调用）
"""
import logging
import re
from typing import Dict

from .prompts import (
    SYSTEM_PROMPT,
    CHAPTER2_PROMPT,
    CHAPTER4_PROMPT,
    CHAPTER5_6_PROMPT,
    CHAPTER8_PROMPT,
)

logger = logging.getLogger(__name__)


class EightSectionGenerator:
    """Eight-section report generator with mixed rendering strategy."""

    def __init__(self):
        from api.services.llm_client_factory import get_llm_client_for_scene
        self._llm_factory = get_llm_client_for_scene('report')

    def _call_llm(self, prompt: str, max_tokens: int = 2000) -> str:
        """Call LLM with temperature=0.3 for stability."""
        try:
            return self._llm_factory.call_sync(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                temperature=0.3,
                max_tokens=max_tokens,
            )
        except Exception as e:
            logger.error("[EightSection] LLM call failed: %s", e)
            return f"[LLM生成失败: {e}]"

    # ==============================================================
    # Chapter 1: Company Profile (template, no LLM)
    # ==============================================================

    def render_chapter1(self, data: Dict[str, str]) -> str:
        profile = data.get("company_profile", "(数据缺失)")
        return f"## 第一章：公司概览\n\n{profile}"

    # ==============================================================
    # Chapter 2: Financial Analysis (LLM)
    # ==============================================================

    def generate_chapter2(self, data: Dict[str, str], stock_name: str, stock_code: str) -> str:
        prompt = CHAPTER2_PROMPT.format(
            stock_name=stock_name,
            stock_code=stock_code,
            financial_summary=data.get("financial_summary", "(数据缺失)"),
            balance_sheet=data.get("balance_sheet", "(数据缺失)"),
            cashflow=data.get("cashflow", "(数据缺失)"),
            data_completeness=data.get("data_completeness", ""),
        )
        content = self._call_llm(prompt, max_tokens=2500)
        return f"## 第二章：财报分析\n\n{content}"

    # ==============================================================
    # Chapter 3: Comparable Companies (template, no LLM)
    # ==============================================================

    def render_chapter3(self, data: Dict[str, str]) -> str:
        comp = data.get("comparable_companies", "(数据缺失)")
        content = comp
        # Add key findings summary
        if "[无法" not in comp and "[同行业" not in comp:
            content += "\n\n### 关键发现\n\n（以上数据表格已包含完整的可比公司估值和财务对比，分析要点请参见投资观点卡片）"
        return f"## 第三章：可比公司分析\n\n{content}"

    # ==============================================================
    # Chapter 4: DCF Valuation (LLM)
    # ==============================================================

    def generate_chapter4(self, data: Dict[str, str], stock_name: str, stock_code: str) -> str:
        prompt = CHAPTER4_PROMPT.format(
            stock_name=stock_name,
            stock_code=stock_code,
            dcf_inputs=data.get("dcf_inputs", "(数据缺失)"),
            valuation_snapshot=data.get("valuation_snapshot", "(数据缺失)"),
        )
        content = self._call_llm(prompt, max_tokens=2000)
        return f"## 第四章：DCF估值框架\n\n{content}"

    # ==============================================================
    # Chapter 5+6: Competitive Landscape + Industry (LLM, merged)
    # ==============================================================

    def generate_chapter5_6(self, data: Dict[str, str], stock_name: str, stock_code: str) -> str:
        prompt = CHAPTER5_6_PROMPT.format(
            stock_name=stock_name,
            stock_code=stock_code,
            company_profile=data.get("company_profile", "(数据缺失)"),
            comparable_companies=data.get("comparable_companies", "(数据缺失)"),
            announcements=data.get("announcements", ""),
        )
        content = self._call_llm(prompt, max_tokens=2000)
        return content

    # ==============================================================
    # Chapter 7: Technical & Momentum (template, no LLM)
    # ==============================================================

    def render_chapter7(self, data: Dict[str, str]) -> str:
        tech = data.get("technical_factors", "(数据缺失)")
        quotes = data.get("daily_quotes", "(数据缺失)")

        parts = ["## 第七章：技术面与动量\n"]
        parts.append(tech)
        parts.append("\n")
        parts.append(quotes)

        # Simple signal summary
        signal = self._summarize_technical_signal(data)
        if signal:
            parts.append(f"\n### 技术面信号解读\n\n{signal}")

        return "\n".join(parts)

    def _summarize_technical_signal(self, data: Dict[str, str]) -> str:
        """Generate simple technical signal summary from pre-computed data."""
        lines = []

        # Check momentum from daily quotes
        quotes = data.get("daily_quotes", "")
        if "20日涨幅" in quotes:
            m = re.search(r"20日涨幅.*?([+-]?\d+\.?\d*)%", quotes)
            if m:
                mom20 = float(m.group(1))
                if mom20 > 30:
                    lines.append(f"判断: 短期涨幅显著（20日+{mom20:.0f}%），动能强劲，但需警惕回调")
                elif mom20 > 10:
                    lines.append(f"判断: 短期上涨动能良好（20日+{mom20:.0f}%）")
                elif mom20 < -20:
                    lines.append(f"判断: 短期跌幅较大（20日{mom20:.0f}%），弱势格局")
                else:
                    lines.append(f"判断: 短期走势平稳（20日{mom20:+.0f}%）")

        # Check RSI from technical factors
        tech = data.get("technical_factors", "")
        if "RSI超买" in tech:
            lines.append("判断: RSI进入超买区域，短期有回调压力")
        elif "RSI超卖" in tech:
            lines.append("判断: RSI进入超卖区域，可能存在反弹机会")

        # MA alignment
        if "多头排列" in tech:
            lines.append("判断: 均线多头排列，中期趋势向上")
        elif "空头排列" in tech:
            lines.append("判断: 均线空头排列，中期趋势向下")

        # Support and resistance levels from Bollinger Bands and MA
        ma_levels = []

        m = re.search(r"下轨=([\d.]+)", tech)
        if m:
            ma_levels.append(("布林带下轨", float(m.group(1))))
        m = re.search(r"上轨=([\d.]+)", tech)
        if m:
            ma_levels.append(("布林带上轨", float(m.group(1))))

        # Parse MA values from format: "MA5/MA10/MA20: 32.12 / 32.38 / 33.27"
        m = re.search(r"MA5/MA10/MA20:\s*([\d.]+)\s*/\s*([\d.]+)\s*/\s*([\d.]+)", tech)
        if m:
            ma_levels.append(("MA20", float(m.group(3))))
        m = re.search(r"MA60/MA120/MA250:\s*([\d.]+)\s*/\s*([\d.]+)\s*/\s*([\d.]+)", tech)
        if m:
            ma_levels.append(("MA60", float(m.group(1))))

        m = re.search(r"收盘价: ([\d.]+)", tech)
        close = float(m.group(1)) if m else None

        if close and ma_levels:
            # Classify as support (below close) or resistance (above close)
            support_levels = [(n, p) for n, p in ma_levels if p <= close]
            resistance_levels = [(n, p) for n, p in ma_levels if p > close]

            lines.append("\n**支撑与阻力位**:")
            if support_levels:
                supports = sorted(support_levels, key=lambda x: x[1], reverse=True)
                for name, price in supports[:3]:
                    pct = (price / close - 1) * 100
                    lines.append(f"- 支撑: {name} ({price:.2f}, {pct:+.1f}%)")
            if resistance_levels:
                resistances = sorted(resistance_levels, key=lambda x: x[1])
                for name, price in resistances[:3]:
                    pct = (price / close - 1) * 100
                    lines.append(f"- 阻力: {name} ({price:.2f}, {pct:+.1f}%)")

        return "\n".join(lines)

    # ==============================================================
    # Chapter 8: Investment Thesis Card (LLM)
    # ==============================================================

    def generate_chapter8(self, data: Dict[str, str], stock_name: str, stock_code: str,
                          chapters: Dict[str, str]) -> str:
        # Build summary of previous chapters for context
        summary_parts = []
        for key in ["ch1", "ch2", "ch3", "ch4", "ch5_6", "ch7"]:
            content = chapters.get(key, "")
            # Truncate each chapter to ~500 chars for summary
            if len(content) > 1000:
                content = content[:1000] + "..."
            if content:
                summary_parts.append(f"### {key}\n{content}")

        chapters_summary = "\n\n".join(summary_parts)

        prompt = CHAPTER8_PROMPT.format(
            stock_name=stock_name,
            stock_code=stock_code,
            chapters_summary=chapters_summary,
        )
        content = self._call_llm(prompt, max_tokens=1200)
        return f"## 第八章：投资观点卡片\n\n{content}"
