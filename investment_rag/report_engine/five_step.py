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
            logger.info(
                "[FiveStep] %s - %s for %s",
                step_config.step_id,
                step_config.name,
                stock_name,
            )
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
