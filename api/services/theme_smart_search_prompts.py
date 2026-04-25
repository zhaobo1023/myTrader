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
1. keywords：提取与主营业务相关的核心关键词，用于在数据库 main_business / business_scope / company_intro 字段中做 LIKE 模糊匹配
2. [关键] 每个关键词必须短小精悍，2-4个汉字为佳，绝对禁止将用户原话或长句作为关键词
3. 同义词扩展：积极扩展同义词和上下游关键词，提高召回率
4. financial_hint：提取与财务数据相关的条件（如营收占比、利润增速等），仅做文本记录，不做查询
5. industry / province：如果用户提到了行业或地区，提取出来。industry 用于匹配数据库 industry 字段（如"煤炭开采和洗选业"）
6. keywords 数量控制在 3-8 个

示例：
- "煤炭生产加工占比较高的公司" -> {"keywords": ["煤炭", "煤矿", "煤炭开采", "煤炭生产", "焦煤", "动力煤"], "financial_hint": "煤炭业务营收占比较高", "industry": "煤炭", "province": null}
- "锂矿营收占比超30%的公司" -> {"keywords": ["锂矿", "碳酸锂", "锂盐", "锂辉石", "锂电"], "financial_hint": "锂矿营收占比超30%", "industry": null, "province": null}
- "江苏省的半导体公司" -> {"keywords": ["半导体", "芯片", "集成电路", "晶圆"], "financial_hint": "", "industry": "半导体", "province": "江苏"}
- "PCB业务增速高的" -> {"keywords": ["PCB", "印制电路板", "线路板", "覆铜板"], "financial_hint": "PCB业务增速高", "industry": null, "province": null}
- "电解铝行业龙头" -> {"keywords": ["电解铝", "铝冶炼", "氧化铝", "铝加工", "铝业"], "financial_hint": "", "industry": "有色金属冶炼", "province": null}"""

INTENT_PARSE_USER = "用户查询：{query}\n\n请解析为结构化查询意图（JSON格式）："

# ---------------------------------------------------------------------------
# Phase 3: Review DB results against original query semantics
# ---------------------------------------------------------------------------

REVIEW_SYSTEM = """你是 A 股投资分析专家，擅长判断个股与投资主题的相关性。

任务：根据用户的原始查询意图，审核从数据库搜索出的候选股票列表，严格过滤掉不相关的股票。

输出格式（严格 JSON，不加任何额外文字）：
{
  "selected": [
    {
      "stock_code": "000001.SZ",
      "stock_name": "某某股份",
      "relevance": "high",
      "reason": "必须填写：说明该股票与查询条件的具体关联，限50字"
    }
  ],
  "excluded_count": 10,
  "exclusion_summary": "简述主要排除原因"
}

筛选标准：
- high: 该业务是公司主营业务或核心收入来源
- medium: 公司有该业务但非主营，或属于产业链上下游
- 不相关的、仅因关键词碰巧出现在经营范围中但实际业务不相关的，必须排除

重要：
1. 必须仔细阅读每只股票的 main_business 全文来判断相关性，不要只看股票名称或行业分类
2. reason 字段必须填写，说明具体哪部分业务与查询相关
3. 如果用户提到了财务条件（如营收占比），在 reason 中说明是否可能符合（无法精确判断时用"待验证"）
4. 严格过滤：主营业务完全不沾边的必须排除，不要为了凑数而保留弱相关股票
5. 例如搜索"煤炭"时，主营是水泥、电气设备、合金材料的公司即使经营范围偶然提到煤炭也应排除"""

REVIEW_USER = """用户原始查询：{query}

候选股票列表（共{total}只）：
{stock_list}

请审核并筛选出真正相关的股票（JSON格式）："""
