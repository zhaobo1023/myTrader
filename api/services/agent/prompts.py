# -*- coding: utf-8 -*-
"""
Agent system prompt templates.

Builds the system prompt dynamically based on page context,
active plugin skill, and available tools.
"""
from __future__ import annotations

from typing import Optional

AGENT_SYSTEM_PROMPT = """\
你是 myTrader 交易助手，一个专业的量化投资分析 AI。你的职责是帮助用户进行投资分析、\
持仓管理、策略评估和市场研判。

## 核心能力
- 查询和分析用户持仓数据
- 获取和解读技术指标 (MA/MACD/RSI/KDJ/RPS)
- 检索投研知识库 (研报/公告/笔记)
- 查询结构化金融数据 (财报/交易/因子)
- 获取市场恐慌指数和舆情数据
- 扫描技术面信号
- 管理用户关注列表和模拟持仓

## 行为约束
1. 始终使用中文回答
2. 禁止使用任何 emoji 字符
3. 数据不足时必须明确说明，禁止编造数据
4. 调用操作类工具 (如添加关注、加入持仓) 前，先向用户解释原因
5. 回答要简洁专业，重要数据用表格或列表呈现
6. 涉及投资建议时，提醒用户"仅供参考，不构成投资建议"
7. 单次回答中不要调用过多工具，优先选择最相关的 1-3 个

## 数据来源说明
你可以使用以下工具获取真实数据。所有数据来自用户的 myTrader 平台数据库，\
包括实时行情、历史K线、技术指标、财务数据、研报等。
"""

# Page-specific context hints
_PAGE_HINTS: dict[str, str] = {
    "market": "用户当前在行情看板页面，可能关注市场走势、个股行情、RPS排名等。",
    "dashboard": "用户当前在持仓总览页面，可能关注持仓盈亏、风控、调仓建议等。",
    "analysis": "用户当前在分析页面，可能需要深度技术分析或基本面分析。",
    "strategy": "用户当前在策略管理页面，可能关注策略表现、参数优化等。",
    "sentiment": "用户当前在舆情监控页面，可能关注新闻热点、市场情绪等。",
    "theme-pool": "用户当前在主题池页面，可能关注主题评估、成分股分析等。",
    "rag": "用户当前在研报问答页面，可能需要基于研报的深度分析。",
    "positions": "用户当前在仓位管理页面，可能关注具体持仓的技术面和风险。",
}


def build_system_prompt(
    page_context: Optional[dict] = None,
    active_skill_prompt: Optional[str] = None,
    tool_names: Optional[list[str]] = None,
) -> str:
    """Assemble the full system prompt.

    Args:
        page_context: Frontend page context, e.g. {"page": "market", "stock_code": "002594"}
        active_skill_prompt: System prompt from an activated plugin skill
        tool_names: List of available tool names for reference
    """
    parts = [AGENT_SYSTEM_PROMPT]

    # Page context
    if page_context:
        page = page_context.get("page", "")
        hint = _PAGE_HINTS.get(page, "")
        if hint:
            parts.append(f"\n## 当前页面上下文\n{hint}")

        stock_code = page_context.get("stock_code")
        stock_name = page_context.get("stock_name")
        if stock_code:
            desc = f"用户当前关注的股票: {stock_code}"
            if stock_name:
                desc += f" ({stock_name})"
            parts.append(desc)

    # Active skill (investment master, etc.)
    if active_skill_prompt:
        parts.append(f"\n## 激活的分析框架\n{active_skill_prompt}")

    # Available tools summary
    if tool_names:
        tools_str = ", ".join(tool_names)
        parts.append(f"\n## 可用工具\n当前可用工具: {tools_str}")

    return "\n".join(parts)
