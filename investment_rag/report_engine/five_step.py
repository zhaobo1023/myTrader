# -*- coding: utf-8 -*-
"""
FiveStepAnalyzer - 五步法基本面分析链 v2.0

v2.0 改进：
- 上下文传递由全文累积改为结构化摘要（每步限100字要点）
- 新增执行摘要生成（200字决策速览卡片）
- 每步 max_tokens 根据输出要求差异化设置
"""
import logging
from datetime import date
from typing import Dict, Optional

from investment_rag.embeddings.embed_model import LLMClient
from investment_rag.report_engine.data_tools import ReportDataTools
from investment_rag.report_engine.industry_config import (
    IndustryAnalysisConfig,
    DEFAULT_CONFIG,
    get_industry_config,
)
from investment_rag.report_engine.prompts import (
    ANALYST_SYSTEM_PROMPT,
    EXECUTIVE_SUMMARY_PROMPT,
    FIVE_STEP_CONFIG,
    TECH_ANALYSIS_PROMPT,
    StepConfig,
)

logger = logging.getLogger(__name__)

# 每步的 max_tokens 差异化设置（v2.0 各步输出精简后降低 token 上限）
_STEP_MAX_TOKENS = {
    "step1": 1500,   # 3个发现 + 数据局限
    "step2": 1200,   # 逻辑链 + 护城河
    "step3": 1200,   # 估值隐含假设 + 修正窗口
    "step4": 800,    # 纯表格
    "step5": 1200,   # 数据卡片 + 预期回报量化分解
}

# 摘要生成 prompt（内部使用，不暴露给外部）
_SUMMARIZE_PROMPT = """请将以下分析内容压缩为要点摘要，每个步骤限100字以内。
只保留关键数据点和核心结论，去掉所有展开论述。
用简洁的条目格式输出，每个步骤一个条目。

原始内容：
{content}

输出格式：
- [步骤名]：[100字以内的要点摘要]
"""


class FiveStepAnalyzer:
    """五步法基本面分析引擎 v2.0"""

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
        industry_config: Optional[IndustryAnalysisConfig] = None,
    ) -> Dict[str, str]:
        """
        执行完整五步法基本面分析。

        Returns:
            {
                "step1": str,  # 财报关键发现
                "step2": str,  # 驱动逻辑与护城河
                "step3": str,  # 估值与预期偏差
                "step4": str,  # 催化剂时间表
                "step5": str,  # 风险与操作建议
                "executive_summary": str,  # 执行摘要
                "full_report": str  # 所有步骤拼接
            }
        """
        today = date.today().isoformat()
        system_prompt = ANALYST_SYSTEM_PROMPT.format(today=today)
        results: Dict[str, str] = {}
        # 存储每步的原始输出，用于生成摘要
        step_outputs: Dict[str, str] = {}

        # 行业配置：优先使用传入的配置，否则自动路由
        if industry_config is None:
            industry_config = get_industry_config(stock_code, db_env=self._tools._db_env)
        logger.info(
            "[FiveStep] Industry routing: %s -> %s",
            stock_code,
            industry_config.industry_name,
        )

        for step_config in FIVE_STEP_CONFIG:
            logger.info(
                "[FiveStep] %s - %s for %s",
                step_config.step_id,
                step_config.name,
                stock_name,
            )
            # 为当前步骤生成前步摘要（v2.0：摘要而非全文）
            prev_summary = self._build_prev_summary(step_config.step_id, step_outputs)

            step_result = self._run_single_step(
                step_config=step_config,
                stock_code=stock_code,
                stock_name=stock_name,
                prev_analysis=prev_summary,
                collection=collection,
                system_prompt=system_prompt,
                industry_config=industry_config,
            )
            results[step_config.step_id] = step_result
            step_outputs[step_config.step_id] = step_result

        # 拼接完整报告
        full_parts = []
        for sc in FIVE_STEP_CONFIG:
            full_parts.append(results.get(sc.step_id, ""))
        results["full_report"] = "\n\n---\n\n".join(full_parts)

        # 生成执行摘要（v2.0 新增）
        results["executive_summary"] = self._generate_executive_summary(
            stock_code=stock_code,
            stock_name=stock_name,
            full_analysis=results["full_report"],
            system_prompt=system_prompt,
        )

        return results

    def generate_tech_section(self, stock_code: str, stock_name: str) -> str:
        """生成独立的技术面分析章节。"""
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
    # Internal - 前步摘要构建
    # ----------------------------------------------------------

    def _build_prev_summary(
        self, current_step_id: str, step_outputs: Dict[str, str]
    ) -> str:
        """
        为当前步骤构建前步要点摘要。

        v2.0 策略：
        - step1: 无前步（返回空）
        - step2: Step1 的 3 个发现标题 + 关键数据（不含展开论述）
        - step3: Step1 要点 + Step2 要点
        - step4: Step1-3 要点
        - step5: Step1-4 要点
        """
        if current_step_id == "step1":
            return ""

        step_names = {
            "step1": "财报关键发现",
            "step2": "驱动逻辑与护城河",
            "step3": "估值与预期偏差",
            "step4": "催化剂时间表",
            "step5": "风险与操作建议",
        }

        # 确定需要哪些前步
        step_order = ["step1", "step2", "step3", "step4", "step5"]
        current_idx = step_order.index(current_step_id)
        prev_steps = step_order[:current_idx]

        summaries = []
        for sid in prev_steps:
            content = step_outputs.get(sid, "")
            if content:
                # 提取摘要：取前300字符作为要点（简单截断策略）
                # 这比调用 LLM 做摘要更快且更可靠
                truncated = content[:300].strip()
                if len(content) > 300:
                    # 在最后一个完整句子处截断
                    for sep in ["。", "\n", "；", "，"]:
                        last_pos = truncated.rfind(sep)
                        if last_pos > 150:
                            truncated = truncated[:last_pos + 1]
                            break
                    truncated += " [...]"
                summaries.append(f"**{step_names.get(sid, sid)}要点**：\n{truncated}")

        if not summaries:
            return "[本步骤为第一步，无前期分析]"

        return "\n\n".join(summaries)

    # ----------------------------------------------------------
    # Internal - 执行摘要生成
    # ----------------------------------------------------------

    def _generate_executive_summary(
        self,
        stock_code: str,
        stock_name: str,
        full_analysis: str,
        system_prompt: str,
    ) -> str:
        """生成执行摘要（200字决策速览卡片）。"""
        # 截取完整分析的前3000字符以控制 token 消耗
        analysis_for_summary = full_analysis[:3000]
        if len(full_analysis) > 3000:
            analysis_for_summary += "\n[... 后续分析已省略 ...]"

        prompt = EXECUTIVE_SUMMARY_PROMPT.format(
            stock_name=stock_name,
            stock_code=stock_code,
            full_analysis=analysis_for_summary,
        )
        try:
            return self._llm.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=500,
            )
        except Exception as e:
            logger.error("[FiveStep] Executive summary LLM call failed: %s", e)
            return "[执行摘要生成失败]"

    # ----------------------------------------------------------
    # Internal - 单步执行
    # ----------------------------------------------------------

    def _run_single_step(
        self,
        step_config: StepConfig,
        stock_code: str,
        stock_name: str,
        prev_analysis: str,
        collection: str = "reports",
        system_prompt: str = "",
        industry_config: Optional[IndustryAnalysisConfig] = None,
    ) -> str:
        """执行单步分析：收集上下文 -> 渲染 Prompt -> 调用 LLM"""
        if industry_config is None:
            industry_config = DEFAULT_CONFIG

        # 1. RAG 上下文（通用查询 + 行业专属查询合并）
        rag_context = ""
        all_rag_queries = list(step_config.rag_queries)
        # 仅 step1/step2/step4 追加行业专属 RAG（避免 step3/step5 重复）
        if step_config.step_id in ("step1", "step2", "step4") and industry_config.extra_rag_queries:
            all_rag_queries = all_rag_queries + industry_config.extra_rag_queries
        if all_rag_queries:
            rag_context = self._tools.query_rag_multi(
                queries=all_rag_queries,
                stock_name=stock_name,
                stock_code=stock_code,
                collection=collection,
                top_k_per_query=3,
            )

        # 2. 财务上下文
        financial_context = ""
        if step_config.needs_financial:
            financial_context = self._tools.get_financial_data(stock_code, years=3)
            # 追加核心财务数据（绝对金额，防止LLM幻觉）
            core_financials = self._tools.get_core_financials(stock_code)
            _no_data_core = ("无数据", "查询失败", "DB模块未加载")
            if core_financials and not any(s in core_financials for s in _no_data_core):
                financial_context += "\n\n" + core_financials

        # 3. 行业专项数据（银行指标等）
        industry_extra_data = ""
        bank_cross_section = ""
        if industry_config.needs_bank_indicators:
            if step_config.step_id == "step1":
                # 基础银行指标 + 年报提取的精确数据（逾期贷款、公允价值变动、一次性损益）
                industry_extra_data = self._tools.get_bank_indicators(stock_code)
                overdue_detail = self._tools.get_overdue_loan_detail(stock_code)
                income_detail = self._tools.get_income_detail(stock_code)
                non_recurring = self._tools.get_non_recurring_items(stock_code)
                # Only append if data was actually retrieved (failure strings contain "失败" or "无年报")
                _no_data = ("无年报", "查询失败", "DB模块未加载")
                if overdue_detail and not any(s in overdue_detail for s in _no_data):
                    industry_extra_data += "\n\n" + overdue_detail
                if income_detail and not any(s in income_detail for s in _no_data):
                    industry_extra_data += "\n\n" + income_detail
                if non_recurring and not any(s in non_recurring for s in _no_data):
                    industry_extra_data += "\n\n" + non_recurring
            elif step_config.step_id in ("step2", "step3"):
                # Step2 / Step3 注入银行对标表用于护城河和估值对标
                bank_cross_section = self._tools.get_bank_cross_section()

        # 4. 技术面上下文
        technical_context = ""
        if step_config.needs_technical:
            technical_context = self._tools.get_tech_analysis(stock_code)

        # 5. 估值历史分位数上下文
        valuation_context = ""
        expected_return_context = ""
        consensus_forecast_context = ""
        # Step2 也需要估值锚定数据（防止LLM用训练记忆编造PB/PE）
        if step_config.needs_valuation or step_config.step_id == "step2":
            valuation_context = self._tools.get_valuation_snapshot(stock_code)
        if step_config.needs_valuation:
            expected_return_context = self._tools.get_expected_return_context(stock_code)
            # Step3 额外注入一致预期 + 分红数据（用于估值和股息率分析）
            if step_config.step_id == "step3":
                consensus_forecast_context = self._tools.get_consensus_forecast(stock_code)
                dividend_analysis = self._tools.get_dividend_analysis(stock_code)
                _no_data_div = ("无分红", "查询失败", "DB模块未加载")
                if dividend_analysis and not any(s in dividend_analysis for s in _no_data_div):
                    valuation_context += "\n\n" + dividend_analysis

        # 7. 渲染 Prompt（包含行业差异化槽位）
        prompt = step_config.prompt_template.format(
            stock_name=stock_name,
            industry_name=industry_config.industry_name,
            rag_context=rag_context or "[无相关研报内容]",
            financial_context=financial_context or "[无财务数据]",
            industry_extra_data=industry_extra_data or "[无行业专项数据]",
            technical_context=technical_context or "[无技术面数据]",
            prev_analysis=prev_analysis or "[本步骤为第一步，无前期分析]",
            valuation_context=valuation_context or "[无估值历史数据]",
            expected_return_context=expected_return_context or "[无预期回报数据]",
            consensus_forecast_context=consensus_forecast_context or "[无一致预期数据]",
            bank_cross_section=bank_cross_section or "[无行业对标数据]",
            step1_focus_areas=industry_config.step1_focus_areas,
            moat_dimensions=industry_config.moat_dimensions,
            valuation_note=industry_config.valuation_note,
            risk_dimensions=industry_config.risk_dimensions,
        )

        # 8. LLM 生成（v2.0：差异化 max_tokens）
        max_tokens = _STEP_MAX_TOKENS.get(step_config.step_id, 1500)
        try:
            return self._llm.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.5,
                max_tokens=max_tokens,
            )
        except Exception as e:
            logger.error("[FiveStep] LLM call failed at %s: %s", step_config.step_id, e)
            return f"[{step_config.name}] LLM 调用失败: {e}"
