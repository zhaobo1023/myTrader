# -*- coding: utf-8 -*-
"""
OnePagerAnalyzer - 一页纸深度公司研究报告生成器 v2

数据驱动架构：
1. OnePagerDataCollector 从 DB 提取所有可用数据，预计算派生指标
2. RAG 检索补充研报/公告上下文
3. LLM 只负责"解读和判断"，不做任何计算
4. 缺失数据明确标注，不允许 LLM 凭记忆填充
"""
import logging
from datetime import date
from typing import Dict, Optional, Callable

from investment_rag.embeddings.embed_model import LLMClient
from investment_rag.report_engine.one_pager_data import OnePagerDataCollector
from investment_rag.report_engine.prompts import (
    ONE_PAGER_SYSTEM_PROMPT,
    ONE_PAGER_STEPS,
    ONE_PAGER_RAG_QUERIES,
    OnePagerStepConfig,
)

logger = logging.getLogger(__name__)


class OnePagerAnalyzer:
    """一页纸深度研究报告引擎 v2 - 数据驱动"""

    def __init__(self, db_env: str = "online"):
        self._data_collector = OnePagerDataCollector(db_env=db_env)
        self._llm = LLMClient()
        self._db_env = db_env

        # RAG retriever (lazy init, may not be available)
        self._rag_tools = None

    def _get_rag_tools(self):
        """Lazy-init RAG tools (heavy imports)."""
        if self._rag_tools is None:
            try:
                from investment_rag.report_engine.data_tools import ReportDataTools
                self._rag_tools = ReportDataTools(db_env=self._db_env)
            except Exception as e:
                logger.warning("[OnePager] RAG tools init failed: %s", e)
        return self._rag_tools

    def generate(
        self,
        stock_code: str,
        stock_name: str,
        collection: str = "reports",
        on_step_start: Optional[Callable[[str, str], None]] = None,
        on_step_done: Optional[Callable[[str, str, str], None]] = None,
    ) -> Dict[str, str]:
        """
        生成完整的一页纸研究报告。

        流程：
        1. [数据采集] OnePagerDataCollector 从 DB 提取 13 个数据块
        2. [RAG检索] 补充研报/公告上下文
        3. [LLM Part1] 上半页 A-E（结构判断）
        4. [LLM Part2] 下半页 F-I（投资判断）
        5. [组装] 标题头 + Part1 + Part2
        """
        today = date.today()
        system_prompt = ONE_PAGER_SYSTEM_PROMPT.format(today=today.isoformat())
        results: Dict[str, str] = {}

        # Step 0: Collect all DB data
        logger.info("[OnePager] Collecting data for %s (%s)", stock_name, stock_code)
        data_blocks = self._data_collector.collect(stock_code, stock_name)

        # Step 0.5: RAG context
        rag_context = self._fetch_rag_context(stock_code, stock_name, collection)
        data_blocks["rag_context"] = rag_context

        # Extract price from data blocks for header
        price_str = self._extract_price(data_blocks.get("valuation_snapshot", ""))

        for step_config in ONE_PAGER_STEPS:
            step_id = step_config.step_id
            step_name = step_config.name

            if on_step_start:
                on_step_start(step_id, step_name)

            logger.info("[OnePager] %s - %s for %s", step_id, step_name, stock_name)

            prompt = self._build_prompt(
                step_config=step_config,
                stock_code=stock_code,
                stock_name=stock_name,
                data_blocks=data_blocks,
                part1_result=results.get("part1", ""),
            )

            try:
                content = self._llm.generate(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    temperature=0.4,
                    max_tokens=3000,
                )
            except Exception as e:
                logger.error("[OnePager] LLM call failed at %s: %s", step_id, e)
                content = f"[{step_name}] LLM 调用失败: {e}"

            results[step_id] = content

            if on_step_done:
                on_step_done(step_id, step_name, content)

        # Assemble full report
        header = (
            f"# {stock_name} | 一页纸深度研究\n\n"
            f"**市场**：A股  **股票代码**：{stock_code}  "
            f"**分析日期**：{today.isoformat()}  **价格**：{price_str}（最新收盘）"
        )
        results["full_report"] = (
            header + "\n\n"
            + results.get("part1", "")
            + "\n\n---\n\n"
            + results.get("part2", "")
        )

        return results

    def _fetch_rag_context(
        self, stock_code: str, stock_name: str, collection: str
    ) -> str:
        """Fetch RAG context from ChromaDB.

        Queries both the passed collection (e.g. 'reports') and
        'annual_reports' (year report PDFs), merging results.
        """
        tools = self._get_rag_tools()
        if tools is None:
            return "[无研报检索服务]"

        parts = []
        bare = stock_code.split(".")[0] if "." in stock_code else stock_code

        # Query primary collection (sell-side reports / announcements)
        try:
            text = tools.query_rag_multi(
                queries=ONE_PAGER_RAG_QUERIES,
                stock_name=stock_name,
                stock_code=bare,
                collection=collection,
                top_k_per_query=3,
            )
            if text and "no relevant content" not in text and "检索失败" not in text:
                parts.append(f"[研报/公告]\n{text}")
        except Exception as e:
            logger.warning("[OnePager] RAG fetch (primary) failed: %s", e)

        # Query annual_reports collection (PDF-extracted annual reports)
        try:
            annual_text = tools.query_rag_multi(
                queries=ONE_PAGER_RAG_QUERIES,
                stock_name=stock_name,
                stock_code=bare,
                collection="annual_reports",
                top_k_per_query=3,
            )
            if annual_text and "no relevant content" not in annual_text and "检索失败" not in annual_text:
                parts.append(f"[年度报告原文]\n{annual_text}")
        except Exception as e:
            logger.warning("[OnePager] RAG fetch (annual_reports) failed: %s", e)

        if not parts:
            return "[无研报及年报检索结果]"
        return "\n\n".join(parts)

    def _build_prompt(
        self,
        step_config: OnePagerStepConfig,
        stock_code: str,
        stock_name: str,
        data_blocks: Dict[str, str],
        part1_result: str,
    ) -> str:
        """Render prompt template with all data blocks."""
        kwargs = {
            "stock_name": stock_name,
            "stock_code": stock_code,
            # All data blocks - mapped to prompt slots
            "company_profile": data_blocks.get("company_profile", "[无公司信息]"),
            "financial_summary": data_blocks.get("financial_summary", "[无利润表数据]"),
            "balance_sheet": data_blocks.get("balance_sheet", "[无资产负债表数据]"),
            "valuation_snapshot": data_blocks.get("valuation_snapshot", "[无估值数据]"),
            "growth_analysis": data_blocks.get("growth_analysis", "[无增长趋势数据]"),
            "roe_decomposition": data_blocks.get("roe_decomposition", "[无ROE数据]"),
            "dividend_analysis": data_blocks.get("dividend_analysis", "[无分红数据]"),
            "quality_factors": data_blocks.get("quality_factors", "[无质量因子数据]"),
            "rps_momentum": data_blocks.get("rps_momentum", "[无RPS数据]"),
            "rag_context": data_blocks.get("rag_context", "[无研报检索结果]"),
            "price_technical": data_blocks.get("price_technical", "[无技术面数据]"),
            "valuation_verdict": data_blocks.get("valuation_verdict", "[无估值判断数据]"),
            "cashflow_analysis": data_blocks.get("cashflow_analysis", "[无现金流数据]"),
            # 银行专项数据：有数据时加标题，无数据时传空字符串（prompt 中占位符直接消失）
            "bank_indicators_block": (
                "**[D14] 银行专项指标（NPL/拨备/CAR/NIM/逾期明细/利润明细，预计算）**：\n"
                + data_blocks["bank_indicators"]
                if data_blocks.get("bank_indicators")
                else ""
            ),
        }

        if step_config.needs_part1:
            summary = part1_result[:2500]
            if len(part1_result) > 2500:
                for sep in ["\n###", "\n---", "\n\n"]:
                    last_pos = summary.rfind(sep)
                    if last_pos > 1200:
                        summary = summary[:last_pos]
                        break
                summary += "\n[... 上半页后续省略 ...]"
            kwargs["part1_summary"] = summary

        return step_config.prompt_template.format(**kwargs)

    @staticmethod
    def _extract_price(valuation_text: str) -> str:
        """Extract latest close price from valuation snapshot text."""
        for line in valuation_text.split("\n"):
            if "收盘价" in line:
                # Format: **最新收盘价**: 67.00元
                parts = line.split(":")
                if len(parts) >= 2:
                    val = parts[-1].strip().rstrip("元").strip()
                    try:
                        float(val)
                        return val + "元"
                    except ValueError:
                        pass
        return "--"
