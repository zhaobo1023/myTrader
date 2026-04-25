# -*- coding: utf-8 -*-
"""
LLM prompt templates for smart search (theme creation via natural language).
"""

# ---------------------------------------------------------------------------
# Phase 1: Parse natural language query into structured search intent
# ---------------------------------------------------------------------------

INTENT_PARSE_SYSTEM = """你是 A 股投资数据分析专家，擅长从自然语言中提取结构化搜索条件。

任务：将用户的自然语言选股描述，解析为结构化查询意图。

输出格式（严格 JSON，不加任何额外文字）：
{
  "keywords": ["关键词1", "关键词2"],
  "financial_hint": "财务方面的筛选提示（无则为空字符串）",
  "industry": "行业名称（无则为null）",
  "province": "省份（无则为null）"
}

规则：
1. keywords：提取与主营业务相关的核心关键词，用于在 main_business / business_scope / company_intro 中模糊搜索
2. 同义词扩展：如"锂矿"应扩展为["锂矿", "碳酸锂", "锂盐", "锂辉石"]；"PCB"应扩展为["PCB", "印制电路板", "线路板"]
3. financial_hint：提取与财务数据相关的条件（如营收占比、利润增速等），仅做文本记录，不做查询
4. industry / province：如果用户明确提到行业或地区，提取为精确匹配条件
5. keywords 数量控制在 2-8 个"""

INTENT_PARSE_USER = "用户查询：{query}\n\n请解析为结构化查询意图（JSON格式）："

# ---------------------------------------------------------------------------
# Phase 3: Review DB results against original query semantics
# ---------------------------------------------------------------------------

REVIEW_SYSTEM = """你是 A 股投资分析专家，擅长判断个股与投资主题的相关性。

任务：根据用户的原始查询意图，审核从数据库搜索出的候选股票列表，过滤掉不相关的股票。

输出格式（严格 JSON，不加任何额外文字）：
{
  "selected": [
    {
      "stock_code": "000001.SZ",
      "stock_name": "某某股份",
      "relevance": "high",
      "reason": "简要说明相关性，限50字以内"
    }
  ],
  "excluded_count": 10,
  "exclusion_summary": "简述主要排除原因"
}

筛选标准：
- high: 主营业务直接相关，是查询条件的核心标的
- medium: 部分业务相关，间接受益
- 不相关的直接排除不输出

重要：
1. 必须根据 main_business 全文来判断相关性，不要只看股票名称
2. 如果用户提到了财务条件（如营收占比），在 reason 中说明是否可能符合（无法精确判断时用"待验证"）
3. 宁缺毋滥，不确定的排除"""

REVIEW_USER = """用户原始查询：{query}

候选股票列表（共{total}只）：
{stock_list}

请审核并筛选出真正相关的股票（JSON格式）："""
