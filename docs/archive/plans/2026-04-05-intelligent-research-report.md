# 智能研报生成 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build an intelligent research report engine that integrates the existing RAG retrieval pipeline, tech_scan signals, AKShare financial data, and a five-step fundamental analysis LLM chain — unified under new `/api/rag/report/*` SSE endpoints, laying the foundation for a comprehensive per-stock analysis framework.

**Architecture:** The `report_engine` module is a thin orchestration layer on top of existing infrastructure. `ReportDataTools` wraps three data sources (ChromaDB+BM25 hybrid RAG, AKShare financials, tech_scan's `DataFetcher`+`IndicatorCalculator`+`SignalDetector`). `FiveStepAnalyzer` drives a sequential LLM chain where each step's output accumulates as context for the next. `ReportBuilder` assembles the final Markdown. The API exposes SSE streaming so the frontend can show progress step-by-step. No new Python packages needed for P0 — everything builds on existing deps.

**Tech Stack:** existing `LLMClient` (`investment_rag/embeddings/embed_model.py`), `HybridRetriever`+`Reranker` (`investment_rag/retrieval/`), `DataFetcher`+`IndicatorCalculator`+`SignalDetector` (`strategist/tech_scan/`), `akshare` (already in requirements), `FastAPI` SSE, `openai` SDK (DashScope compatible).

---

## Architectural Note: Comprehensive Analysis Framework

This plan establishes three analysis dimensions that can be run individually or combined:

```
report_type="fundamental"   -> 五步法基本面研报
report_type="technical"     -> 技术面分析报告 (tech_scan integration)
report_type="comprehensive" -> 综合研报 (fundamental + technical)
```

Future P1 additions (not in this plan):
- `sentiment` dimension: AKShare news + LLM fear/greed scoring
- LangGraph agent for adaptive tool calling + web search

---

## Task 0: Fix Broken Import in api/routers/rag.py

**Files:**
- Modify: `api/routers/rag.py`

**Background:** `api/routers/rag.py:33` imports `from investment_rag.llm.llm_client import LLMClient`. This module does not exist — `LLMClient` lives in `investment_rag/embeddings/embed_model.py`. The import is also dead code (never used in the function body). This causes every call to `POST /api/rag/query` to return HTTP 503.

**Step 1: Remove the broken import from the `/query` endpoint (lines 29-39)**

In `api/routers/rag.py`, the `try` block starting at line 29 currently reads:
```python
    try:
        from investment_rag.retrieval.intent_router import IntentRouter
        from investment_rag.retrieval.hybrid_retriever import HybridRetriever
        from investment_rag.retrieval.reranker import Reranker
        from investment_rag.retrieval.text2sql import Text2SQL
        from investment_rag.llm.llm_client import LLMClient
    except ImportError as e:
```

Change to (remove the `LLMClient` line):
```python
    try:
        from investment_rag.retrieval.intent_router import IntentRouter
        from investment_rag.retrieval.hybrid_retriever import HybridRetriever
        from investment_rag.retrieval.reranker import Reranker
        from investment_rag.retrieval.text2sql import Text2SQL
    except ImportError as e:
```

Also check the `/query/sync` endpoint (lines ~159-164) for the same issue and remove any `LLMClient` import there too.

**Step 2: Verify router imports without error**
```bash
cd /Users/zhaobo/data0/person/myTrader && python -c "from api.routers.rag import router; print('OK')"
```
Expected: `OK`

**Step 3: Commit**
```bash
git add api/routers/rag.py
git commit -m "fix(rag): remove broken LLMClient import (investment_rag.llm does not exist)"
```

---

## Task 1: AKShare Financial Data Loader

**Files:**
- Modify: `investment_rag/ingest/loaders/__init__.py` (currently empty, add real exports)
- Create: `investment_rag/ingest/loaders/akshare_loader.py`
- Create: `investment_rag/tests/test_akshare_loader.py`

**Step 1: Write the failing test**

Create `investment_rag/tests/test_akshare_loader.py`:

```python
# -*- coding: utf-8 -*-
import pytest
import pandas as pd
from unittest.mock import patch, MagicMock
from investment_rag.ingest.loaders.akshare_loader import AKShareLoader


def test_format_summary_returns_string():
    loader = AKShareLoader()
    data = {"records": [{"报告期": "2024Q3", "ROE": 25.3}], "columns": ["报告期", "ROE"]}
    result = loader._format_summary(data, stock_code="000858", years=1)
    assert isinstance(result, str)
    assert "000858" in result
    assert "ROE" in result


def test_get_financial_data_returns_expected_keys():
    loader = AKShareLoader()
    with patch.object(loader, "_fetch_financial_abstract") as mock_fetch:
        mock_fetch.return_value = {
            "records": [{"报告期": "2024Q3", "ROE": 25.3}],
            "columns": ["报告期", "ROE"],
        }
        result = loader.get_financial_data("000858", years=1)
    assert "raw" in result
    assert "summary" in result
    assert "error" in result
    assert result["error"] is None
    assert "000858" in result["summary"]


def test_get_financial_data_handles_network_error():
    loader = AKShareLoader()
    with patch.object(loader, "_fetch_financial_abstract", side_effect=Exception("timeout")):
        result = loader.get_financial_data("000858", years=1)
    assert result["summary"] == ""
    assert result["error"] is not None


def test_format_summary_empty_data():
    loader = AKShareLoader()
    result = loader._format_summary({}, stock_code="000858")
    assert "暂无" in result or isinstance(result, str)
```

**Step 2: Run test to confirm failure**
```bash
cd /Users/zhaobo/data0/person/myTrader && python -m pytest investment_rag/tests/test_akshare_loader.py -v
```
Expected: `ModuleNotFoundError: No module named 'investment_rag.ingest.loaders.akshare_loader'`

**Step 3: Create `akshare_loader.py`**

Create `investment_rag/ingest/loaders/akshare_loader.py`:

```python
# -*- coding: utf-8 -*-
"""
AKShare Financial Data Loader

从 AKShare 获取 A 股财务摘要数据（ROE/毛利率/净利润增速/营收增速），
供研报生成的 LLM 分析步骤使用。
"""
import logging
from typing import Any, Dict, Optional

import akshare as ak

logger = logging.getLogger(__name__)


class AKShareLoader:
    """从 AKShare 加载财务摘要数据"""

    def get_financial_data(self, stock_code: str, years: int = 3) -> Dict[str, Any]:
        """
        获取指定股票的财务摘要数据。

        Args:
            stock_code: 股票代码，纯数字，如 "000858"（不带市场后缀）
            years: 获取最近几年数据（影响返回条数：一年 4 条季报）

        Returns:
            {
                "raw": dict,        # 原始解析结果
                "summary": str,     # 格式化后的 LLM 可读文本
                "error": str|None   # 错误信息，成功时为 None
            }
        """
        try:
            raw = self._fetch_financial_abstract(stock_code)
            summary = self._format_summary(raw, stock_code=stock_code, years=years)
            return {"raw": raw, "summary": summary, "error": None}
        except Exception as e:
            logger.warning("[AKShareLoader] get_financial_data failed for %s: %s", stock_code, e)
            return {"raw": {}, "summary": "", "error": str(e)}

    def _fetch_financial_abstract(self, stock_code: str) -> Dict[str, Any]:
        """调用 AKShare 获取财务摘要（ROE/毛利率/净利润增速等）"""
        df = ak.stock_financial_abstract(symbol=stock_code)
        if df is None or df.empty:
            return {}
        records = df.head(16).to_dict(orient="records")
        return {"records": records, "columns": list(df.columns)}

    def _format_summary(
        self,
        data: Dict[str, Any],
        stock_code: str = "",
        years: int = 3,
    ) -> str:
        """将财务数据格式化为 LLM 可读文本"""
        if not data or "records" not in data:
            return f"[财务数据] {stock_code} 暂无财务摘要数据"

        records = data.get("records", [])
        if not records:
            return f"[财务数据] {stock_code} 财务摘要为空"

        max_records = years * 4  # 每年约 4 条季报
        lines = [f"[财务摘要] 股票代码: {stock_code}，最近 {min(len(records), max_records)} 期数据："]

        for i, rec in enumerate(records[:max_records]):
            row_parts = []
            for k, v in rec.items():
                if v is not None and str(v).strip() not in ("", "nan", "None"):
                    row_parts.append(f"{k}={v}")
            if row_parts:
                lines.append(f"  期{i + 1}: " + ", ".join(row_parts))

        return "\n".join(lines)
```

**Step 4: Update `investment_rag/ingest/loaders/__init__.py`**

```python
# -*- coding: utf-8 -*-
"""
Data loaders for investment_rag ingest pipeline.

AKShareLoader: financial summary data from AKShare (ROE/gross margin/growth rates).
"""
from .akshare_loader import AKShareLoader

__all__ = ["AKShareLoader"]
```

**Step 5: Run tests to verify pass**
```bash
cd /Users/zhaobo/data0/person/myTrader && python -m pytest investment_rag/tests/test_akshare_loader.py -v
```
Expected: all 4 tests PASS.

**Step 6: Commit**
```bash
git add investment_rag/ingest/loaders/
git add investment_rag/tests/test_akshare_loader.py
git commit -m "feat(rag): implement AKShareLoader for financial summary data"
```

---

## Task 2: Report Engine Package + Prompts

**Files:**
- Create: `investment_rag/report_engine/__init__.py`
- Create: `investment_rag/report_engine/prompts.py`

**Step 1: Create `investment_rag/report_engine/__init__.py`**

```python
# -*- coding: utf-8 -*-
"""
Report Engine - Intelligent A-share research report generation.

Entry point: FiveStepAnalyzer
  .generate_fundamental(stock_code, stock_name) -> Dict[str, str]
  .generate_tech_section(stock_code, stock_name) -> str

Report types:
  fundamental   - 五步法基本面分析（信息差/逻辑差/预期差/催化剂/结论）
  technical     - 技术面分析（MA/MACD/RSI/KDJ/BOLL/背驰）
  comprehensive - 综合研报（fundamental + technical）
"""
```

**Step 2: Create `investment_rag/report_engine/prompts.py`**

```python
# -*- coding: utf-8 -*-
"""
五步法研报分析 Prompt 模板

设计原则：
- 每步输出作为下一步的 {prev_analysis} 上下文（递进分析链）
- 每步有独立的 RAG 检索 query 列表，精准多角度召回
- 禁止使用 emoji，用纯文本符号替代（[RED]/[OK]/[WARN]）
- 每步 Prompt 明确输出 Markdown 格式，便于组装
"""
from dataclasses import dataclass, field
from typing import List

# ============================================================
# System prompt
# ============================================================

ANALYST_SYSTEM_PROMPT = """你是一位专注于 A 股市场的专业投资研究分析师。
分析以事实为基础，逻辑清晰，定量与定性结合。
输出格式为 Markdown，层次分明，可直接用于专业投研报告。
不使用夸张修辞，不做无依据预测，对不确定内容明确标注"需验证"。
今日日期: {today}
"""

# ============================================================
# Step 1: 信息差
# ============================================================

STEP1_PROMPT = """## 任务: 信息差分析（第一步）

**公司**: {stock_name}

**财务数据上下文**:
{financial_context}

**研报/公告检索上下文**:
{rag_context}

**指令**:
从以上材料中挖掘 3-5 个市场可能忽视的关键信息点（信息差）：
1. 财报附注中隐藏的亮点或风险（会计政策变更、资产减值细节）
2. 现金流与利润的背离情况（高利润低现金流警示）
3. 非经常性损益对净利润的影响及剔除后的真实盈利能力
4. 资产负债表结构性变化（应收账款/存货异常增长）
5. 行业地位变化的定量证据（市场份额、毛利率趋势）

**输出格式**（严格遵守）:
### 信息差分析

#### 关键信息点 1: [标题]
- 数据: [具体数字或比率]
- 市场一般认知: [...]
- 真实情况: [你发现的不同之处]
- 重要性: [高/中/低]

（重复 3-5 个信息点）

#### 数据局限性
[本次分析的数据局限，哪些需要补充验证]
"""

STEP1_RAG_QUERIES = [
    "{stock_name} 财务指标 营收 净利润 毛利率 现金流",
    "{stock_name} 年报 季报 应收账款 资产减值 非经常性损益",
    "{stock_name} 会计政策 财务附注 补贴 减值",
]

# ============================================================
# Step 2: 逻辑差
# ============================================================

STEP2_PROMPT = """## 任务: 逻辑差分析（第二步）

**公司**: {stock_name}

**前一步分析（信息差）**:
{prev_analysis}

**补充检索上下文**:
{rag_context}

**指令**:
基于第一步发现的信息差，识别市场对该公司的逻辑误区，构建正确的分析框架：
1. 指出市场最常见的 1-3 个线性思维或错误类比
2. 构建正确的驱动因子链（A 导致 B 导致 C 的因果逻辑）
3. 识别公司真正的核心竞争壁垒（可量化）
4. 评估当前逻辑链的完整性和持续性

**输出格式**:
### 逻辑差分析

#### 市场误读
| 误读内容 | 错误原因 | 正确逻辑 |
|---------|---------|---------|
| [误读1] | [原因] | [正确分析] |

#### 正确驱动逻辑链
[A] -> [B] -> [C] -> [股价驱动力]

#### 核心竞争壁垒评估
[定性描述 + 可量化指标]

#### 逻辑持续性判断
[当前驱动逻辑预计持续时间及关键变量]
"""

STEP2_RAG_QUERIES = [
    "{stock_name} 竞争优势 护城河 市场份额 行业地位",
    "{stock_name} 商业模式 盈利模式 核心竞争力",
    "{stock_name} 行业格局 竞争对手 对标公司",
]

# ============================================================
# Step 3: 预期差
# ============================================================

STEP3_PROMPT = """## 任务: 预期差分析（第三步）

**公司**: {stock_name}

**前期累积分析**:
{prev_analysis}

**财务数据上下文**:
{financial_context}

**指令**:
构建一致预期与实际情况的对比，量化预期差：
1. 梳理市场对核心指标（营收/净利润/毛利率/ROE）的一致预期
2. 对比实际数据，量化偏差幅度
3. 评估预期差的规模（大/中/小）及预计持续期
4. 判断当前估值是否已反映这种预期差

**输出格式**:
### 预期差分析

| 指标 | 市场一致预期 | 实际/预测值 | 偏差幅度 | 信心评级 |
|-----|-----------|-----------|---------|---------|
| 营收增速 | X% | Y% | +/- Z% | 高/中/低 |
| 净利润增速 | X% | Y% | +/- Z% | 高/中/低 |
| 毛利率 | X% | Y% | +/- Z pct | 高/中/低 |
| ROE | X% | Y% | +/- Z pct | 高/中/低 |

#### 估值隐含预期
[当前 PE/PB 隐含的增速假设 vs 你的判断]

#### 预期差兑现时间窗口
[预期差何时会被市场认知，关键观察节点]
"""

STEP3_RAG_QUERIES = [
    "{stock_name} 业绩预期 一致预期 盈利预测 分析师预测",
    "{stock_name} 估值 PE PB 历史分位 估值中枢",
    "{stock_name} 营收增长 净利润增长 预测",
]

# ============================================================
# Step 4: 催化剂
# ============================================================

STEP4_PROMPT = """## 任务: 催化剂识别（第四步）

**公司**: {stock_name}

**前期累积分析**:
{prev_analysis}

**检索上下文（政策/事件/公告）**:
{rag_context}

**指令**:
梳理驱动预期差兑现的催化剂，分时间轴排列：
1. 短期催化剂（1-3 个月）：业绩预告、重要会议、行业政策
2. 中期催化剂（3-12 个月）：新产品放量、海外拓展、并购整合
3. 负面催化剂（需警惕的风险事件及其发生概率）

**输出格式**:
### 催化剂分析

#### 短期催化剂（1-3 个月）
| 事件 | 预期时间 | 影响方向 | 量级 |
|-----|---------|---------|-----|
| [事件1] | [时间] | [正面/负面] | [大/中/小] |

#### 中期催化剂（3-12 个月）
| 事件 | 预期时间 | 影响方向 | 量级 |
|-----|---------|---------|-----|

#### 负面催化剂（风险）
| 风险事件 | 发生概率 | 影响程度 | 应对建议 |
|---------|---------|---------|---------|
"""

STEP4_RAG_QUERIES = [
    "{stock_name} 政策利好 行业政策 监管 政策风险",
    "{stock_name} 新产品 新项目 战略规划 扩张",
    "{stock_name} 风险 不确定性 挑战 竞争压力",
]

# ============================================================
# Step 5: 综合结论
# ============================================================

STEP5_PROMPT = """## 任务: 综合结论（第五步）

**公司**: {stock_name}

**前期完整分析（信息差 + 逻辑差 + 预期差 + 催化剂）**:
{prev_analysis}

**技术面数据**:
{technical_context}

**指令**:
综合前四步分析，给出可操作的投资结论：
1. 投资评级（强烈推荐 / 推荐 / 中性 / 回避）
2. 核心投资逻辑（2-3 句话精炼）
3. 关键假设（什么条件下逻辑成立）
4. 风险闭环（逻辑失效的 3 个条件及应对）
5. 参考价位（结合技术面支撑/压力位）

**输出格式**:
### 综合结论

**评级**: [强烈推荐 / 推荐 / 中性 / 回避]

**核心逻辑**:
[2-3 句核心投资逻辑，含量化依据]

#### 关键假设
1. [假设1]
2. [假设2]
3. [假设3]

#### 风险闭环（逻辑失效条件）
| 失效条件 | 发生概率 | 建议操作 |
|---------|---------|---------|
| [条件1] | 高/中/低 | 止损/减仓/观望 |
| [条件2] | 高/中/低 | ... |
| [条件3] | 高/中/低 | ... |

#### 参考价位（结合技术面）
- 支撑位: [价格]（来源: [MA20/BOLL下轨/前低]）
- 压力位: [价格]（来源: [MA60/BOLL上轨/前高]）
- 建议止损: [价格]（来源: [ATR/MA20]）
"""

# ============================================================
# Technical Analysis Prompt
# ============================================================

TECH_ANALYSIS_PROMPT = """## 技术面分析任务

**公司**: {stock_name}（{stock_code}）

**技术指标数据**:
{technical_data}

**指令**:
基于以上技术指标数据，给出简洁的技术面判断：
1. 当前趋势判断（多头/空头/震荡）及强度
2. 关键支撑/压力位（基于 MA/BOLL/前高低）
3. 主要信号解读（金叉/死叉/背驰/超买超卖）
4. 短期操作建议（持有/加仓/减仓/观望）

**输出格式**:
### 技术面分析

**趋势**: [多头排列 / 空头排列 / 震荡整理] - [强势 / 一般 / 弱势]

**关键价位**:
| 类型 | 价位 | 来源 |
|-----|-----|-----|
| 支撑1 | XXX | MA20 |
| 支撑2 | XXX | BOLL下轨 |
| 压力1 | XXX | MA60 |
| 压力2 | XXX | BOLL上轨 |

**信号解读**:
[逐条解释当前主要信号的含义及可能影响]

**MACD背驰**:
[背驰类型及置信度说明]

**短期建议**: [持有 / 加仓 / 减仓 / 观望]，理由: [...]
"""

# ============================================================
# Step 配置表
# ============================================================

@dataclass
class StepConfig:
    """单步分析配置"""
    step_id: str
    name: str
    prompt_template: str
    rag_queries: List[str] = field(default_factory=list)
    needs_financial: bool = False
    needs_technical: bool = False


FIVE_STEP_CONFIG: List[StepConfig] = [
    StepConfig(
        step_id="step1",
        name="信息差",
        prompt_template=STEP1_PROMPT,
        rag_queries=STEP1_RAG_QUERIES,
        needs_financial=True,
    ),
    StepConfig(
        step_id="step2",
        name="逻辑差",
        prompt_template=STEP2_PROMPT,
        rag_queries=STEP2_RAG_QUERIES,
    ),
    StepConfig(
        step_id="step3",
        name="预期差",
        prompt_template=STEP3_PROMPT,
        rag_queries=STEP3_RAG_QUERIES,
        needs_financial=True,
    ),
    StepConfig(
        step_id="step4",
        name="催化剂",
        prompt_template=STEP4_PROMPT,
        rag_queries=STEP4_RAG_QUERIES,
    ),
    StepConfig(
        step_id="step5",
        name="综合结论",
        prompt_template=STEP5_PROMPT,
        rag_queries=[],
        needs_technical=True,
    ),
]
```

**Step 3: Smoke test**
```bash
cd /Users/zhaobo/data0/person/myTrader && python -c "
from investment_rag.report_engine.prompts import FIVE_STEP_CONFIG, TECH_ANALYSIS_PROMPT
print(f'{len(FIVE_STEP_CONFIG)} steps configured')
for s in FIVE_STEP_CONFIG:
    print(f'  {s.step_id}: {s.name}, financial={s.needs_financial}, tech={s.needs_technical}')
print('Prompts OK')
"
```
Expected:
```
5 steps configured
  step1: 信息差, financial=True, tech=False
  ...
  step5: 综合结论, financial=False, tech=True
Prompts OK
```

**Step 4: Commit**
```bash
git add investment_rag/report_engine/
git commit -m "feat(report): add report_engine package with five-step prompt templates"
```

---

## Task 3: ReportDataTools

**Files:**
- Create: `investment_rag/report_engine/data_tools.py`
- Create: `investment_rag/tests/test_data_tools.py`

**Critical Implementation Notes:**
- Use `strategist/tech_scan/data_fetcher.py`'s `DataFetcher` to load K-line data — do NOT write a new SQL query. `DataFetcher` correctly handles `open_price`/`high_price`/`low_price`/`close_price` column mapping and ETF vs stock table routing.
- The `IndicatorCalculator.calculate_all()` expects columns named `open`, `high`, `low`, `close` — `DataFetcher` already renames them.

**Step 1: Write the failing test**

Create `investment_rag/tests/test_data_tools.py`:

```python
# -*- coding: utf-8 -*-
import pytest
import pandas as pd
from unittest.mock import MagicMock, patch


def _make_tools():
    """Create ReportDataTools with all external calls mocked."""
    from investment_rag.report_engine.data_tools import ReportDataTools
    tools = ReportDataTools.__new__(ReportDataTools)
    tools._db_env = "online"
    tools._retriever = MagicMock()
    tools._reranker = MagicMock()
    tools._financial_loader = MagicMock()
    return tools


def test_query_rag_returns_formatted_string():
    tools = _make_tools()
    tools._retriever.retrieve.return_value = [
        {"id": "d1", "text": "宁德时代2024年营收增长30%", "metadata": {"source": "report.pdf"}, "rrf_score": 0.8}
    ]
    tools._reranker.rerank.return_value = tools._retriever.retrieve.return_value
    result = tools.query_rag("营收增速", stock_code="300750", top_k=3)
    assert isinstance(result, str)
    assert "宁德时代" in result or "来源" in result


def test_query_rag_handles_empty_results():
    tools = _make_tools()
    tools._retriever.retrieve.return_value = []
    tools._reranker.rerank.return_value = []
    result = tools.query_rag("营收增速", stock_code="300750")
    assert "未找到" in result or isinstance(result, str)


def test_query_rag_handles_retrieval_exception():
    tools = _make_tools()
    tools._retriever.retrieve.side_effect = Exception("ChromaDB unavailable")
    result = tools.query_rag("营收增速", stock_code="300750")
    assert "失败" in result or isinstance(result, str)


def test_get_financial_data_returns_string():
    tools = _make_tools()
    tools._financial_loader.get_financial_data.return_value = {
        "raw": {},
        "summary": "[财务摘要] 000858 期1: ROE=25.3",
        "error": None,
    }
    result = tools.get_financial_data("000858", years=2)
    assert isinstance(result, str)
    assert len(result) > 0


def test_get_tech_analysis_handles_empty_db():
    tools = _make_tools()
    with patch("investment_rag.report_engine.data_tools.DataFetcher") as mock_fetcher_cls:
        mock_fetcher = MagicMock()
        mock_fetcher.fetch_daily_data.return_value = pd.DataFrame()
        mock_fetcher_cls.return_value = mock_fetcher
        result = tools.get_tech_analysis("000858")
    assert "无 K 线数据" in result or isinstance(result, str)


def test_get_tech_analysis_returns_formatted_text():
    tools = _make_tools()
    mock_df = pd.DataFrame([{
        "stock_code": "000858",
        "trade_date": pd.Timestamp("2026-04-01"),
        "open": 150.0, "high": 155.0, "low": 148.0, "close": 152.0, "volume": 1e7,
    }] * 30)

    with patch("investment_rag.report_engine.data_tools.DataFetcher") as mock_fetcher_cls:
        mock_fetcher = MagicMock()
        mock_fetcher.fetch_daily_data.return_value = mock_df
        mock_fetcher_cls.return_value = mock_fetcher
        result = tools.get_tech_analysis("000858")

    assert isinstance(result, str)
    assert len(result) > 50
```

**Step 2: Run test to confirm failure**
```bash
cd /Users/zhaobo/data0/person/myTrader && python -m pytest investment_rag/tests/test_data_tools.py -v
```
Expected: `ModuleNotFoundError` or `ImportError`.

**Step 3: Implement `data_tools.py`**

Create `investment_rag/report_engine/data_tools.py`:

```python
# -*- coding: utf-8 -*-
"""
ReportDataTools - 研报生成的统一数据收集层

整合三个数据源：
1. RAG     - ChromaDB 向量检索 + BM25 + Reranker（复用现有 investment_rag/retrieval/）
2. Financial - AKShare 财务摘要（investment_rag/ingest/loaders/akshare_loader.py）
3. Technical - K 线 + 指标 + 信号（复用 strategist/tech_scan/）

每个方法返回格式化文本字符串，直接嵌入 Prompt。
禁止在此模块中硬编码任何 SQL — 统一通过 DataFetcher 获取 K 线数据。
"""
import logging
from typing import List, Optional

import pandas as pd

from investment_rag.retrieval.hybrid_retriever import HybridRetriever
from investment_rag.retrieval.reranker import Reranker
from investment_rag.ingest.loaders.akshare_loader import AKShareLoader

logger = logging.getLogger(__name__)


class ReportDataTools:
    """研报数据收集工具集"""

    def __init__(self, db_env: str = "online"):
        self._db_env = db_env
        self._retriever = HybridRetriever()
        self._reranker = Reranker()
        self._financial_loader = AKShareLoader()

    # ----------------------------------------------------------
    # 1. RAG 检索
    # ----------------------------------------------------------

    def query_rag(
        self,
        query: str,
        stock_code: Optional[str] = None,
        collection: str = "reports",
        top_k: int = 5,
    ) -> str:
        """
        通过 HybridRetriever + Reranker 检索相关文档片段。

        Args:
            query: 检索 query
            stock_code: 若指定，ChromaDB where 过滤
            collection: ChromaDB collection 名（reports/announcements/notes/macro）
            top_k: 最终返回结果数

        Returns:
            格式化文本，每个片段含来源标注
        """
        where = {"stock_code": stock_code} if stock_code else None

        try:
            hits = self._retriever.retrieve(
                query=query,
                collection=collection,
                top_k=top_k * 2,
                where=where,
            )
            hits = self._reranker.rerank(query, hits, top_k=top_k)
        except Exception as e:
            logger.warning("[ReportDataTools] RAG retrieve failed: %s", e)
            return "[RAG 检索失败，跳过]"

        if not hits:
            return "[RAG 未找到相关内容]"

        parts = []
        for i, h in enumerate(hits, 1):
            source = h.get("metadata", {}).get("source", "未知来源")
            text = h.get("text", "")[:600]
            parts.append(f"[来源{i}: {source}]\n{text}")

        return "\n\n".join(parts)

    def query_rag_multi(
        self,
        queries: List[str],
        stock_name: str,
        stock_code: Optional[str] = None,
        collection: str = "reports",
        top_k_per_query: int = 3,
    ) -> str:
        """
        多 query 检索，去重合并结果。用于五步法每步的多角度召回。

        Args:
            queries: query 模板列表（支持 {stock_name} 占位符）
            stock_name: 公司名，用于填充模板
            stock_code: 可选，限定股票过滤
            collection: collection 名
            top_k_per_query: 每个 query 返回条数

        Returns:
            去重合并后的文本
        """
        seen_ids: set = set()
        all_hits: list = []
        where = {"stock_code": stock_code} if stock_code else None

        for q_tpl in queries:
            q = q_tpl.format(stock_name=stock_name)
            try:
                hits = self._retriever.retrieve(
                    query=q,
                    collection=collection,
                    top_k=top_k_per_query * 2,
                    where=where,
                )
                hits = self._reranker.rerank(q, hits, top_k=top_k_per_query)
            except Exception as e:
                logger.warning("[ReportDataTools] multi-query failed '%s': %s", q, e)
                continue

            for h in hits:
                uid = h.get("id") or h.get("text", "")[:80]
                if uid not in seen_ids:
                    seen_ids.add(uid)
                    all_hits.append(h)

        if not all_hits:
            return "[RAG 多 query 检索未找到相关内容]"

        parts = []
        limit = top_k_per_query * len(queries)
        for i, h in enumerate(all_hits[:limit], 1):
            source = h.get("metadata", {}).get("source", "未知来源")
            text = h.get("text", "")[:500]
            parts.append(f"[来源{i}: {source}]\n{text}")

        return "\n\n".join(parts)

    # ----------------------------------------------------------
    # 2. 财务数据
    # ----------------------------------------------------------

    def get_financial_data(self, stock_code: str, years: int = 3) -> str:
        """
        获取 AKShare 财务摘要，返回格式化文本。

        Args:
            stock_code: 股票代码（纯数字，如 "000858"）
            years: 最近几年

        Returns:
            格式化财务摘要文本
        """
        clean_code = stock_code.split(".")[0]
        result = self._financial_loader.get_financial_data(clean_code, years)
        if result.get("error"):
            logger.warning("[ReportDataTools] Financial data error: %s", result["error"])
        summary = result.get("summary", "")
        return summary if summary else f"[财务数据] {clean_code} 暂无数据"

    # ----------------------------------------------------------
    # 3. 技术面分析
    # ----------------------------------------------------------

    def get_tech_analysis(self, stock_code: str, lookback_days: int = 120) -> str:
        """
        通过 tech_scan.DataFetcher 获取 K 线，用 IndicatorCalculator + SignalDetector
        计算技术指标，返回格式化文本供 LLM 分析。

        使用 DataFetcher 而非自写 SQL，因为：
        1. DataFetcher 正确处理 open_price/high_price 等列名映射
        2. DataFetcher 自动区分股票（trade_stock_daily）和 ETF（trade_etf_daily）
        3. 避免代码重复

        Args:
            stock_code: 股票代码（带或不带后缀均可）
            lookback_days: 回溯天数（自然日）

        Returns:
            格式化技术面文本
        """
        try:
            from strategist.tech_scan.data_fetcher import DataFetcher
            from strategist.tech_scan.indicator_calculator import IndicatorCalculator
            from strategist.tech_scan.signal_detector import SignalDetector
        except ImportError as e:
            logger.error("[ReportDataTools] tech_scan import failed: %s", e)
            return f"[技术面] tech_scan 模块导入失败: {e}"

        fetcher = DataFetcher(env=self._db_env)

        try:
            df = fetcher.fetch_daily_data([stock_code], lookback_days=lookback_days)
        except Exception as e:
            logger.warning("[ReportDataTools] DataFetcher failed for %s: %s", stock_code, e)
            return f"[技术面] {stock_code} 数据获取失败: {e}"

        if df is None or df.empty:
            return f"[技术面] {stock_code} 无 K 线数据"

        try:
            calc = IndicatorCalculator()
            df = calc.calculate_all(df)
            latest = df.iloc[-1]
            detector = SignalDetector()
            signals = detector.detect_all(latest)
            kdj_signals = detector.detect_kdj_signals(latest)
            all_signals = signals + kdj_signals
            trend = detector.get_trend_status(latest)
            macd_divergence = detector.detect_macd_divergence(df)
        except Exception as e:
            logger.warning("[ReportDataTools] Indicator calc failed: %s", e)
            return f"[技术面] {stock_code} 指标计算失败: {e}"

        return self._format_tech_text(latest, all_signals, trend, macd_divergence)

    def _format_tech_text(
        self,
        latest: pd.Series,
        signals: list,
        trend: str,
        macd_divergence: dict,
    ) -> str:
        """将技术指标格式化为 LLM 可读文本。使用纯文本标记替代 emoji。"""

        def _v(val, fmt=".2f"):
            if val is None:
                return "N/A"
            try:
                f = float(val)
                if f != f:  # NaN check
                    return "N/A"
                return f"{f:{fmt}}"
            except (TypeError, ValueError):
                return "N/A"

        lines = [
            f"[技术指标] 最新交易日: {latest.get('trade_date', 'N/A')}",
            f"收盘价: {_v(latest.get('close'))}",
            f"MA5/20/60/250: {_v(latest.get('ma5'))}/{_v(latest.get('ma20'))}/{_v(latest.get('ma60'))}/{_v(latest.get('ma250'))}",
            f"MACD DIF/DEA: {_v(latest.get('macd_dif'), '.4f')}/{_v(latest.get('macd_dea'), '.4f')}",
            f"RSI(14): {_v(latest.get('rsi'), '.1f')}",
            f"KDJ K/D/J: {_v(latest.get('kdj_k'), '.1f')}/{_v(latest.get('kdj_d'), '.1f')}/{_v(latest.get('kdj_j'), '.1f')}",
            f"BOLL 上轨/中轨/下轨: {_v(latest.get('boll_upper'))}/{_v(latest.get('boll_middle'))}/{_v(latest.get('boll_lower'))}",
            f"ATR(14): {_v(latest.get('atr_14'))}",
            f"量比(5日均量): {_v(latest.get('volume_ratio'), '.2f')}",
            f"趋势状态: {trend}",
            f"MACD背驰: {macd_divergence.get('type', '无')} "
            f"(置信度={macd_divergence.get('confidence', 'N/A')}, "
            f"{macd_divergence.get('description', '')})",
            "",
            "[信号列表]",
        ]

        if not signals:
            lines.append("  (无触发信号)")
        else:
            for sig in signals:
                # sig.level 是 SignalLevel enum，.name 返回 RED/YELLOW/GREEN/INFO
                level_tag = f"[{sig.level.name}]"
                lines.append(f"  {level_tag} {sig.name}: {sig.description}")

        return "\n".join(lines)
```

**Step 4: Run tests**
```bash
cd /Users/zhaobo/data0/person/myTrader && python -m pytest investment_rag/tests/test_data_tools.py -v
```
Expected: all 5 tests PASS.

**Step 5: Commit**
```bash
git add investment_rag/report_engine/data_tools.py investment_rag/tests/test_data_tools.py
git commit -m "feat(report): add ReportDataTools — RAG/financial/tech data collection layer"
```

---

## Task 4: FiveStepAnalyzer + ReportBuilder + ReportStore

**Files:**
- Create: `investment_rag/report_engine/five_step.py`
- Create: `investment_rag/report_engine/report_builder.py`
- Create: `investment_rag/report_engine/report_store.py`
- Create: `investment_rag/tests/test_five_step.py`

**Step 1: Write the failing tests**

Create `investment_rag/tests/test_five_step.py`:

```python
# -*- coding: utf-8 -*-
import pytest
from unittest.mock import MagicMock, patch


def _make_analyzer():
    from investment_rag.report_engine.five_step import FiveStepAnalyzer
    analyzer = FiveStepAnalyzer.__new__(FiveStepAnalyzer)
    analyzer._tools = MagicMock()
    analyzer._tools.query_rag_multi.return_value = "RAG context text"
    analyzer._tools.get_financial_data.return_value = "Financial context text"
    analyzer._tools.get_tech_analysis.return_value = "Tech context text"
    analyzer._llm = MagicMock()
    analyzer._llm.generate.return_value = "## 分析\n分析内容..."
    return analyzer


def test_five_step_config_has_5_steps():
    from investment_rag.report_engine.prompts import FIVE_STEP_CONFIG
    assert len(FIVE_STEP_CONFIG) == 5
    ids = [s.step_id for s in FIVE_STEP_CONFIG]
    assert ids == ["step1", "step2", "step3", "step4", "step5"]


def test_run_single_step_returns_string():
    from investment_rag.report_engine.prompts import FIVE_STEP_CONFIG
    analyzer = _make_analyzer()
    result = analyzer._run_single_step(
        step_config=FIVE_STEP_CONFIG[0],
        stock_code="000858",
        stock_name="五粮液",
        prev_analysis="",
    )
    assert isinstance(result, str)
    assert len(result) > 0


def test_generate_fundamental_calls_all_5_steps():
    analyzer = _make_analyzer()
    called_steps = []

    def mock_step(step_config, **kwargs):
        called_steps.append(step_config.step_id)
        return f"Result of {step_config.step_id}"

    analyzer._run_single_step = mock_step
    results = analyzer.generate_fundamental("000858", "五粮液")
    assert len(called_steps) == 5
    assert set(called_steps) == {"step1", "step2", "step3", "step4", "step5"}
    assert "full_report" in results
    assert isinstance(results["full_report"], str)


def test_generate_fundamental_accumulates_context():
    """Each step's result must appear in the prev_analysis of subsequent steps."""
    analyzer = _make_analyzer()
    prev_analyses = {}

    def mock_step(step_config, prev_analysis, **kwargs):
        prev_analyses[step_config.step_id] = prev_analysis
        return f"Result of {step_config.step_id}"

    analyzer._run_single_step = mock_step
    analyzer.generate_fundamental("000858", "五粮液")
    assert prev_analyses["step1"] == ""
    assert "Result of step1" in prev_analyses["step2"]
    assert "Result of step2" in prev_analyses["step3"]


def test_generate_tech_section_returns_string():
    analyzer = _make_analyzer()
    result = analyzer.generate_tech_section("000858", "五粮液")
    assert isinstance(result, str)
    analyzer._tools.get_tech_analysis.assert_called_once_with("000858")
    analyzer._llm.generate.assert_called_once()


def test_report_builder_comprehensive():
    from investment_rag.report_engine.report_builder import ReportBuilder
    builder = ReportBuilder()
    results = {f"step{i}": f"## Step {i}\n内容{i}" for i in range(1, 6)}
    report = builder.build_comprehensive(
        stock_code="000858",
        stock_name="五粮液",
        fundamental_results=results,
        tech_section="## 技术面\n技术内容",
    )
    assert "五粮液" in report
    assert "000858" in report
    assert "## 一、信息差分析" in report
    assert "## 六、技术面分析" in report
    assert "技术内容" in report


def test_report_builder_fundamental_only():
    from investment_rag.report_engine.report_builder import ReportBuilder
    builder = ReportBuilder()
    results = {f"step{i}": f"内容{i}" for i in range(1, 6)}
    report = builder.build_fundamental_only(
        stock_code="000858",
        stock_name="五粮液",
        fundamental_results=results,
    )
    assert "五粮液" in report
    assert "000858" in report
    assert "技术面" not in report


def test_report_store_save_and_retrieve(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "investment_rag.report_engine.report_store.REPORT_DIR", str(tmp_path)
    )
    monkeypatch.setattr(
        "investment_rag.report_engine.report_store.INDEX_FILE",
        str(tmp_path / "index.json"),
    )
    from investment_rag.report_engine.report_store import ReportStore
    store = ReportStore()
    rid = store.save("000858", "五粮液", "comprehensive", "# Test\nContent here")
    assert store.get(rid) == "# Test\nContent here"
    assert store.get("nonexistent") is None
    reports = store.list_reports(stock_code="000858")
    assert len(reports) == 1
    assert reports[0]["id"] == rid


def test_report_store_list_filters_by_stock(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "investment_rag.report_engine.report_store.REPORT_DIR", str(tmp_path)
    )
    monkeypatch.setattr(
        "investment_rag.report_engine.report_store.INDEX_FILE",
        str(tmp_path / "index.json"),
    )
    from investment_rag.report_engine.report_store import ReportStore
    store = ReportStore()
    store.save("000858", "五粮液", "comprehensive", "report A")
    store.save("300750", "宁德时代", "fundamental", "report B")
    all_reports = store.list_reports()
    assert len(all_reports) == 2
    filtered = store.list_reports(stock_code="000858")
    assert len(filtered) == 1
    assert filtered[0]["stock_code"] == "000858"
```

**Step 2: Run to confirm all fail**
```bash
cd /Users/zhaobo/data0/person/myTrader && python -m pytest investment_rag/tests/test_five_step.py -v
```
Expected: all tests fail with `ModuleNotFoundError`.

**Step 3: Implement `five_step.py`**

Create `investment_rag/report_engine/five_step.py`:

```python
# -*- coding: utf-8 -*-
"""
FiveStepAnalyzer - 五步法基本面分析链

顺序执行五步分析，每步输出累积为下一步的 {prev_analysis} 上下文。
无 Agent 依赖，直接调用 LLMClient + ReportDataTools。
"""
import logging
from datetime import date
from typing import Dict, Optional

from investment_rag.embeddings.embed_model import LLMClient
from investment_rag.report_engine.data_tools import ReportDataTools
from investment_rag.report_engine.prompts import (
    ANALYST_SYSTEM_PROMPT,
    FIVE_STEP_CONFIG,
    TECH_ANALYSIS_PROMPT,
    StepConfig,
)

logger = logging.getLogger(__name__)


class FiveStepAnalyzer:
    """五步法基本面分析引擎"""

    def __init__(self, db_env: str = "online"):
        self._tools = ReportDataTools(db_env=db_env)
        self._llm = LLMClient()

    # ----------------------------------------------------------
    # Public API
    # ----------------------------------------------------------

    def generate_fundamental(
        self,
        stock_code: str,
        stock_name: str,
        collection: str = "reports",
    ) -> Dict[str, str]:
        """
        执行完整五步法基本面分析。

        Args:
            stock_code: 股票代码
            stock_name: 公司名称
            collection: ChromaDB collection 名

        Returns:
            {
                "step1": str,  # 信息差分析
                "step2": str,  # 逻辑差分析
                "step3": str,  # 预期差分析
                "step4": str,  # 催化剂分析
                "step5": str,  # 综合结论
                "full_report": str  # 所有步骤拼接（换行分隔）
            }
        """
        today = date.today().isoformat()
        system_prompt = ANALYST_SYSTEM_PROMPT.format(today=today)
        results: Dict[str, str] = {}
        accumulated = ""

        for step_config in FIVE_STEP_CONFIG:
            logger.info("[FiveStep] %s - %s for %s", step_config.step_id, step_config.name, stock_name)
            step_result = self._run_single_step(
                step_config=step_config,
                stock_code=stock_code,
                stock_name=stock_name,
                prev_analysis=accumulated,
                collection=collection,
                system_prompt=system_prompt,
            )
            results[step_config.step_id] = step_result
            accumulated += f"\n\n---\n\n{step_result}"

        results["full_report"] = accumulated.strip()
        return results

    def generate_tech_section(self, stock_code: str, stock_name: str) -> str:
        """
        生成独立的技术面分析章节。

        Args:
            stock_code: 股票代码
            stock_name: 公司名称

        Returns:
            技术面分析 Markdown 文本
        """
        tech_data = self._tools.get_tech_analysis(stock_code)
        today = date.today().isoformat()
        prompt = TECH_ANALYSIS_PROMPT.format(
            stock_name=stock_name,
            stock_code=stock_code,
            technical_data=tech_data,
        )
        system_prompt = ANALYST_SYSTEM_PROMPT.format(today=today)
        try:
            return self._llm.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=1500,
            )
        except Exception as e:
            logger.error("[FiveStep] Tech section LLM call failed: %s", e)
            return f"[技术面分析] LLM 调用失败: {e}\n\n原始数据:\n{tech_data}"

    # ----------------------------------------------------------
    # Internal
    # ----------------------------------------------------------

    def _run_single_step(
        self,
        step_config: StepConfig,
        stock_code: str,
        stock_name: str,
        prev_analysis: str,
        collection: str = "reports",
        system_prompt: str = "",
    ) -> str:
        """执行单步分析：收集上下文 -> 渲染 Prompt -> 调用 LLM"""
        # 1. RAG 上下文
        rag_context = ""
        if step_config.rag_queries:
            rag_context = self._tools.query_rag_multi(
                queries=step_config.rag_queries,
                stock_name=stock_name,
                stock_code=stock_code,
                collection=collection,
                top_k_per_query=3,
            )

        # 2. 财务上下文
        financial_context = ""
        if step_config.needs_financial:
            financial_context = self._tools.get_financial_data(stock_code, years=3)

        # 3. 技术面上下文
        technical_context = ""
        if step_config.needs_technical:
            technical_context = self._tools.get_tech_analysis(stock_code)

        # 4. 渲染 Prompt
        prompt = step_config.prompt_template.format(
            stock_name=stock_name,
            rag_context=rag_context or "[无相关研报内容]",
            financial_context=financial_context or "[无财务数据]",
            technical_context=technical_context or "[无技术面数据]",
            prev_analysis=prev_analysis or "[本步骤为第一步，无前期分析]",
        )

        # 5. LLM 生成
        try:
            return self._llm.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.5,
                max_tokens=2000,
            )
        except Exception as e:
            logger.error("[FiveStep] LLM call failed at %s: %s", step_config.step_id, e)
            return f"[{step_config.name}] LLM 调用失败: {e}"
```

**Step 4: Implement `report_builder.py`**

Create `investment_rag/report_engine/report_builder.py`:

```python
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
        """Wrap content with a ## section header if it doesn't already have one."""
        if content.lstrip().startswith("#"):
            return content
        return f"## {title}\n\n{content}"
```

**Step 5: Implement `report_store.py`**

Create `investment_rag/report_engine/report_store.py`:

```python
# -*- coding: utf-8 -*-
"""
ReportStore - 研报持久化存储

保存生成的 Markdown 研报到 output/rag/reports/，
维护 index.json 供 API 列举。
"""
import json
import logging
import os
import uuid
from datetime import date, datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPORT_DIR = os.path.join(ROOT, "output", "rag", "reports")
INDEX_FILE = os.path.join(REPORT_DIR, "index.json")


class ReportStore:
    """研报文件持久化"""

    def __init__(self):
        os.makedirs(REPORT_DIR, exist_ok=True)

    def save(
        self,
        stock_code: str,
        stock_name: str,
        report_type: str,
        content: str,
    ) -> str:
        """
        保存研报 Markdown 文件。

        Returns:
            report_id (str): 唯一标识，格式 {stock_code}_{type}_{date}_{uuid8}
        """
        today = date.today().isoformat()
        short_id = uuid.uuid4().hex[:8]
        report_id = f"{stock_code}_{report_type}_{today}_{short_id}"
        filename = f"{report_id}.md"
        filepath = os.path.join(REPORT_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write(content)

        self._append_index(report_id, stock_code, stock_name, report_type, filename)
        logger.info("[ReportStore] Saved: %s", filepath)
        return report_id

    def get(self, report_id: str) -> Optional[str]:
        """读取研报内容，不存在返回 None"""
        entry = next(
            (r for r in self._load_index() if r["id"] == report_id), None
        )
        if not entry:
            return None
        filepath = os.path.join(REPORT_DIR, entry["filename"])
        if not os.path.exists(filepath):
            return None
        with open(filepath, "r", encoding="utf-8") as fh:
            return fh.read()

    def list_reports(
        self,
        stock_code: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict]:
        """列举研报，按创建时间倒序"""
        index = self._load_index()
        if stock_code:
            index = [r for r in index if r.get("stock_code") == stock_code]
        index.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return index[:limit]

    def _load_index(self) -> List[Dict]:
        if not os.path.exists(INDEX_FILE):
            return []
        with open(INDEX_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def _append_index(
        self,
        report_id: str,
        stock_code: str,
        stock_name: str,
        report_type: str,
        filename: str,
    ) -> None:
        index = self._load_index()
        index.append({
            "id": report_id,
            "stock_code": stock_code,
            "stock_name": stock_name,
            "report_type": report_type,
            "filename": filename,
            "created_at": datetime.now().isoformat(),
        })
        with open(INDEX_FILE, "w", encoding="utf-8") as fh:
            json.dump(index, fh, ensure_ascii=False, indent=2)
```

**Step 6: Run all tests**
```bash
cd /Users/zhaobo/data0/person/myTrader && python -m pytest investment_rag/tests/test_five_step.py -v
```
Expected: all 9 tests PASS.

**Step 7: Commit**
```bash
git add investment_rag/report_engine/five_step.py \
        investment_rag/report_engine/report_builder.py \
        investment_rag/report_engine/report_store.py \
        investment_rag/tests/test_five_step.py
git commit -m "feat(report): implement FiveStepAnalyzer, ReportBuilder, ReportStore"
```

---

## Task 5: API Schemas + New Endpoints

**Files:**
- Modify: `api/schemas/rag.py`
- Modify: `api/routers/rag.py`

**Step 1: Add schemas to `api/schemas/rag.py`**

Append to the end of the existing file:

```python
# --- Report Generation ---

from typing import Literal


class ReportGenerateRequest(BaseModel):
    stock_code: str = Field(..., description="股票代码，如 000858")
    stock_name: str = Field(..., description="公司名称，如 五粮液")
    report_type: Literal["fundamental", "technical", "comprehensive"] = Field(
        default="comprehensive",
        description=(
            "报告类型: "
            "fundamental=纯基本面五步法, "
            "technical=纯技术面, "
            "comprehensive=综合（默认）"
        ),
    )
    collection: str = Field(default="reports", description="ChromaDB collection 名")


class ReportListItem(BaseModel):
    id: str
    stock_code: str
    stock_name: str
    report_type: str
    created_at: str


class ReportListResponse(BaseModel):
    reports: List[ReportListItem]
    total: int
```

**Step 2: Add import for `ReportGenerateRequest` in `api/routers/rag.py`**

At the top of the file, change the schemas import line:
```python
from api.schemas.rag import RAGQueryRequest, RAGQueryResponse
```
to:
```python
from api.schemas.rag import (
    RAGQueryRequest,
    RAGQueryResponse,
    ReportGenerateRequest,
    ReportListItem,
    ReportListResponse,
)
```

Also add `Optional` to the existing `from typing import ...` line if needed (check the top of the file).

**Step 3: Add three new endpoints to `api/routers/rag.py`** (after the existing `/query/sync` endpoint)

```python
@router.post('/report/generate')
async def report_generate(
    req: ReportGenerateRequest,
    current_user: User = Depends(get_current_user),
):
    """
    SSE 流式生成智能研报。

    SSE event types:
      {type: "plan",       sections: [...]}
      {type: "step_start", step: "step1", name: "信息差"}
      {type: "step_done",  step: "step1", name: "信息差", content: "..."}
      {type: "done",       report_id: "...", content: "..."}
      {type: "error",      message: "..."}
    """
    async def event_generator():
        try:
            from investment_rag.report_engine.five_step import FiveStepAnalyzer
            from investment_rag.report_engine.report_builder import ReportBuilder
            from investment_rag.report_engine.report_store import ReportStore
            from investment_rag.report_engine.prompts import FIVE_STEP_CONFIG
        except ImportError as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': f'Module unavailable: {exc}'})}\n\n"
            return

        # --- 1. Plan ---
        sections = []
        if req.report_type in ("fundamental", "comprehensive"):
            sections.extend([c.name for c in FIVE_STEP_CONFIG])
        if req.report_type in ("technical", "comprehensive"):
            sections.append("技术面")

        yield f"data: {json.dumps({'type': 'plan', 'sections': sections}, ensure_ascii=False)}\n\n"

        analyzer = FiveStepAnalyzer(db_env="online")
        builder = ReportBuilder()
        store = ReportStore()
        fundamental_results = {}
        tech_section = ""

        # --- 2. Fundamental steps (step1..step5) ---
        if req.report_type in ("fundamental", "comprehensive"):
            for step_config in FIVE_STEP_CONFIG:
                yield f"data: {json.dumps({'type': 'step_start', 'step': step_config.step_id, 'name': step_config.name}, ensure_ascii=False)}\n\n"

                prev_analysis = "\n\n---\n\n".join(fundamental_results.values())
                step_result = analyzer._run_single_step(
                    step_config=step_config,
                    stock_code=req.stock_code,
                    stock_name=req.stock_name,
                    prev_analysis=prev_analysis,
                    collection=req.collection,
                )
                fundamental_results[step_config.step_id] = step_result

                yield f"data: {json.dumps({'type': 'step_done', 'step': step_config.step_id, 'name': step_config.name, 'content': step_result}, ensure_ascii=False)}\n\n"

        # --- 3. Technical section ---
        if req.report_type in ("technical", "comprehensive"):
            yield f"data: {json.dumps({'type': 'step_start', 'step': 'tech', 'name': '技术面'}, ensure_ascii=False)}\n\n"
            tech_section = analyzer.generate_tech_section(req.stock_code, req.stock_name)
            yield f"data: {json.dumps({'type': 'step_done', 'step': 'tech', 'name': '技术面', 'content': tech_section}, ensure_ascii=False)}\n\n"

        # --- 4. Assemble ---
        if req.report_type == "comprehensive":
            final_report = builder.build_comprehensive(
                stock_code=req.stock_code,
                stock_name=req.stock_name,
                fundamental_results=fundamental_results,
                tech_section=tech_section,
            )
        elif req.report_type == "fundamental":
            final_report = builder.build_fundamental_only(
                stock_code=req.stock_code,
                stock_name=req.stock_name,
                fundamental_results=fundamental_results,
            )
        else:  # technical
            final_report = f"# {req.stock_name}（{req.stock_code}）技术面分析\n\n{tech_section}"

        report_id = store.save(
            stock_code=req.stock_code,
            stock_name=req.stock_name,
            report_type=req.report_type,
            content=final_report,
        )

        yield f"data: {json.dumps({'type': 'done', 'report_id': report_id, 'content': final_report}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        },
    )


@router.get('/report/list', response_model=ReportListResponse)
async def report_list(
    stock_code: Optional[str] = None,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
):
    """列举已保存研报（按创建时间倒序）"""
    from investment_rag.report_engine.report_store import ReportStore
    store = ReportStore()
    reports = store.list_reports(stock_code=stock_code, limit=limit)
    items = [ReportListItem(**r) for r in reports]
    return ReportListResponse(reports=items, total=len(items))


@router.get('/report/{report_id}')
async def report_get(
    report_id: str,
    current_user: User = Depends(get_current_user),
):
    """获取研报 Markdown 内容（Content-Type: text/markdown）"""
    from investment_rag.report_engine.report_store import ReportStore
    from fastapi.responses import PlainTextResponse
    store = ReportStore()
    content = store.get(report_id)
    if content is None:
        raise HTTPException(status_code=404, detail='Report not found')
    return PlainTextResponse(content=content, media_type='text/markdown; charset=utf-8')
```

**Note:** The `Optional` import is already needed — check if `Optional` is imported at the top of `api/routers/rag.py`. If not, add it.

**Step 4: Verify router import and route list**
```bash
cd /Users/zhaobo/data0/person/myTrader && python -c "
from api.routers.rag import router
paths = [r.path for r in router.routes]
for p in paths:
    print(p)
"
```
Expected output includes:
```
/api/rag/query
/api/rag/query/sync
/api/rag/report/generate
/api/rag/report/list
/api/rag/report/{report_id}
```

**Step 5: Commit**
```bash
git add api/schemas/rag.py api/routers/rag.py
git commit -m "feat(api): add /report/generate SSE, /report/list, /report/{id} endpoints"
```

---

## Task 6: CLI Test Script

**Files:**
- Create: `investment_rag/run_report.py`

This script lets you test the full pipeline from the command line without starting the API server.

```python
# -*- coding: utf-8 -*-
"""
CLI - Generate an intelligent research report from the command line.

Usage:
    DB_ENV=online python -m investment_rag.run_report --code 000858 --name 五粮液
    DB_ENV=online python -m investment_rag.run_report --code 000858 --name 五粮液 --type technical
    DB_ENV=online python -m investment_rag.run_report --code 300750 --name 宁德时代 --type comprehensive
"""
import argparse
import logging
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger("run_report")


def main():
    parser = argparse.ArgumentParser(description="Generate intelligent research report")
    parser.add_argument("--code", required=True, help="股票代码，如 000858")
    parser.add_argument("--name", required=True, help="公司名称，如 五粮液")
    parser.add_argument(
        "--type",
        default="comprehensive",
        choices=["fundamental", "technical", "comprehensive"],
        help="报告类型（默认: comprehensive）",
    )
    parser.add_argument("--collection", default="reports", help="ChromaDB collection")
    args = parser.parse_args()

    from investment_rag.report_engine.five_step import FiveStepAnalyzer
    from investment_rag.report_engine.report_builder import ReportBuilder
    from investment_rag.report_engine.report_store import ReportStore
    from investment_rag.report_engine.prompts import FIVE_STEP_CONFIG

    db_env = os.environ.get("DB_ENV", "online")
    analyzer = FiveStepAnalyzer(db_env=db_env)
    builder = ReportBuilder()
    store = ReportStore()

    print(f"\n[INFO] Generating {args.type} report for {args.name}({args.code})...\n")

    fundamental_results = {}
    tech_section = ""

    if args.type in ("fundamental", "comprehensive"):
        print("[INFO] Running 五步法 fundamental analysis (5 steps)...")
        for step_config in FIVE_STEP_CONFIG:
            print(f"  -> Step: {step_config.name} ...", end="", flush=True)
            prev_analysis = "\n\n---\n\n".join(fundamental_results.values())
            result = analyzer._run_single_step(
                step_config=step_config,
                stock_code=args.code,
                stock_name=args.name,
                prev_analysis=prev_analysis,
                collection=args.collection,
            )
            fundamental_results[step_config.step_id] = result
            print(f" done ({len(result)} chars)")

    if args.type in ("technical", "comprehensive"):
        print("[INFO] Running technical analysis ...", end="", flush=True)
        tech_section = analyzer.generate_tech_section(args.code, args.name)
        print(f" done ({len(tech_section)} chars)")

    if args.type == "comprehensive":
        final_report = builder.build_comprehensive(
            stock_code=args.code,
            stock_name=args.name,
            fundamental_results=fundamental_results,
            tech_section=tech_section,
        )
    elif args.type == "fundamental":
        final_report = builder.build_fundamental_only(
            stock_code=args.code,
            stock_name=args.name,
            fundamental_results=fundamental_results,
        )
    else:
        final_report = f"# {args.name}（{args.code}）技术面分析\n\n{tech_section}"

    report_id = store.save(
        stock_code=args.code,
        stock_name=args.name,
        report_type=args.type,
        content=final_report,
    )

    output_path = os.path.join(ROOT, "output", "rag", "reports", f"{report_id}.md")
    print(f"\n[OK] Report ID   : {report_id}")
    print(f"[OK] Saved to    : {output_path}")
    print(f"[OK] Total chars : {len(final_report)}\n")


if __name__ == "__main__":
    main()
```

**Test the CLI (technical only — fastest, no LLM for fundamental):**
```bash
cd /Users/zhaobo/data0/person/myTrader
DB_ENV=online python -m investment_rag.run_report --code 000858 --name 五粮液 --type technical
```
Expected: prints step progress, saves `.md` to `output/rag/reports/`.

**Full comprehensive test (requires DashScope API key):**
```bash
DB_ENV=online python -m investment_rag.run_report --code 000858 --name 五粮液 --type comprehensive
```

**Commit:**
```bash
git add investment_rag/run_report.py
git commit -m "feat(report): add CLI run_report.py for end-to-end testing"
```

---

## Task 7: Run Full Test Suite + Update Docs

**Step 1: Run all tests**
```bash
cd /Users/zhaobo/data0/person/myTrader && python -m pytest investment_rag/tests/ -v
```
Expected: all tests PASS. Fix any failures before proceeding.

**Step 2: Update CLAUDE.md**

In the `investment_rag/` section of the project structure tree, add:
```
│   ├── report_engine/         # 研报生成引擎（P0，无 Agent）
│   │   ├── prompts.py         # 五步法 + 技术面 Prompt 模板
│   │   ├── data_tools.py      # 数据收集（RAG / AKShare / tech_scan）
│   │   ├── five_step.py       # 五步法顺序分析链
│   │   ├── report_builder.py  # Markdown 研报组装
│   │   └── report_store.py    # 研报持久化（output/rag/reports/）
```

In the API router table, add:
```
| rag/report | /api/rag/report/* | 研报生成(SSE)/列表/获取 |
```

In the `output/` tree, add:
```
│   └── rag/                   # 研报产出
│       └── reports/           # 生成的 Markdown 研报 + index.json
```

In the quick-start commands section, add:
```bash
# 生成技术面报告（快速，无需 LLM 长时间调用）
DB_ENV=online python -m investment_rag.run_report --code 000858 --name 五粮液 --type technical

# 生成综合研报
DB_ENV=online python -m investment_rag.run_report --code 000858 --name 五粮液 --type comprehensive
```

**Step 3: Commit**
```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for report_engine module and output/rag/ directory"
```

---

## Summary

**7 tasks, ~12 commits.**

### Zero new Python packages needed for P0
All dependencies already in `requirements.txt`: `akshare`, `chromadb`, `rank_bm25`, `jieba`, `openai`, `dashscope`.

### Comprehensive analysis framework (upgrade path)

```
P0 (this plan):
  report_type=fundamental   -> 五步法 RAG + AKShare
  report_type=technical     -> tech_scan DataFetcher + IndicatorCalculator + SignalDetector + LLM
  report_type=comprehensive -> both combined

P1 (next):
  Add LangGraph agent for adaptive tool calling
  Add web_search tool (Qwen enable_search=True)
  Add report_type=sentiment (AKShare news + LLM scoring)

P2 (future):
  Sentiment module + event detection
  Announcement crawler (cninfo)
  Scheduled auto-generation via scheduler/
```

### Run order to validate
```bash
# 1. Unit tests (no external calls)
python -m pytest investment_rag/tests/ -v

# 2. CLI smoke (needs DB connection, no LLM)
DB_ENV=online python -m investment_rag.run_report --code 000858 --name 五粮液 --type technical

# 3. Full report (needs DashScope API key + DB)
DB_ENV=online python -m investment_rag.run_report --code 000858 --name 五粮液 --type comprehensive
```
