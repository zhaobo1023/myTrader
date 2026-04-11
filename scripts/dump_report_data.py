# -*- coding: utf-8 -*-
"""
Dump all data contexts for each step of the five-step analysis.
Does NOT call LLM - only collects data and renders prompts.
Output: one file per step with the full rendered prompt.
"""
import os
import sys
import json
import logging

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

from datetime import date
from investment_rag.report_engine.data_tools import ReportDataTools
from investment_rag.report_engine.industry_config import get_industry_config, IndustryAnalysisConfig
from investment_rag.report_engine.prompts import (
    ANALYST_SYSTEM_PROMPT,
    FIVE_STEP_CONFIG,
)

STOCK_CODE = "600015"
STOCK_NAME = "华夏银行"
DB_ENV = os.environ.get("DB_ENV", "online")
COLLECTION = "reports"

OUTPUT_DIR = os.path.join(ROOT, "output", "rag", "debug_prompts")
os.makedirs(OUTPUT_DIR, exist_ok=True)


def main():
    tools = ReportDataTools(db_env=DB_ENV)
    industry_config = get_industry_config(STOCK_CODE, db_env=DB_ENV)

    today = date.today().isoformat()
    system_prompt = ANALYST_SYSTEM_PROMPT.format(today=today)

    # Save system prompt
    with open(os.path.join(OUTPUT_DIR, "00_system_prompt.txt"), "w") as f:
        f.write(system_prompt)

    print(f"\n[INFO] Industry config: {industry_config.industry_name}")
    print(f"[INFO] Output dir: {OUTPUT_DIR}\n")

    # Collect all data contexts once
    print("[DATA] Collecting RAG contexts...")
    rag_contexts = {}
    for sc in FIVE_STEP_CONFIG:
        all_rag_queries = list(sc.rag_queries)
        if sc.step_id in ("step1", "step2", "step4") and industry_config.extra_rag_queries:
            all_rag_queries = all_rag_queries + industry_config.extra_rag_queries
        if all_rag_queries:
            rag_contexts[sc.step_id] = tools.query_rag_multi(
                queries=all_rag_queries,
                stock_name=STOCK_NAME,
                stock_code=STOCK_CODE,
                collection=COLLECTION,
                top_k_per_query=3,
            )
        else:
            rag_contexts[sc.step_id] = "[无RAG查询]"

    print("[DATA] Collecting financial data...")
    financial_context = tools.get_financial_data(STOCK_CODE, years=3)

    print("[DATA] Collecting bank indicators...")
    bank_indicators = tools.get_bank_indicators(STOCK_CODE)

    print("[DATA] Collecting overdue loan detail...")
    overdue_detail = tools.get_overdue_loan_detail(STOCK_CODE)

    print("[DATA] Collecting income detail...")
    income_detail = tools.get_income_detail(STOCK_CODE)

    print("[DATA] Collecting non-recurring items...")
    non_recurring = tools.get_non_recurring_items(STOCK_CODE)

    print("[DATA] Collecting bank cross section...")
    bank_cross_section = tools.get_bank_cross_section()

    print("[DATA] Collecting tech analysis...")
    tech_analysis = tools.get_tech_analysis(STOCK_CODE)

    print("[DATA] Collecting valuation snapshot...")
    valuation_context = tools.get_valuation_snapshot(STOCK_CODE)

    print("[DATA] Collecting expected return...")
    expected_return = tools.get_expected_return_context(STOCK_CODE)

    print("[DATA] Collecting consensus forecast...")
    consensus_forecast = tools.get_consensus_forecast(STOCK_CODE)

    print("[DATA] Collecting core financials...")
    core_financials = tools.get_core_financials(STOCK_CODE)

    print("[DATA] Collecting dividend analysis...")
    dividend_analysis = tools.get_dividend_analysis(STOCK_CODE)

    # Save all raw data
    raw_data = {
        "financial_context": financial_context,
        "core_financials": core_financials,
        "bank_indicators": bank_indicators,
        "overdue_detail": overdue_detail,
        "income_detail": income_detail,
        "non_recurring": non_recurring,
        "bank_cross_section": bank_cross_section,
        "tech_analysis": tech_analysis,
        "valuation_context": valuation_context,
        "expected_return": expected_return,
        "consensus_forecast": consensus_forecast,
        "dividend_analysis": dividend_analysis,
    }
    with open(os.path.join(OUTPUT_DIR, "00_raw_data.txt"), "w") as f:
        for k, v in raw_data.items():
            f.write(f"{'='*60}\n[{k}]\n{'='*60}\n{v}\n\n")

    # Build industry_extra_data for step1 (same logic as five_step.py)
    industry_extra_data_step1 = bank_indicators
    _no_data = ("无年报", "查询失败", "DB模块未加载")
    if overdue_detail and not any(s in overdue_detail for s in _no_data):
        industry_extra_data_step1 += "\n\n" + overdue_detail
    if income_detail and not any(s in income_detail for s in _no_data):
        industry_extra_data_step1 += "\n\n" + income_detail
    if non_recurring and not any(s in non_recurring for s in _no_data):
        industry_extra_data_step1 += "\n\n" + non_recurring

    # Render each step prompt
    prev_analysis = ""
    for sc in FIVE_STEP_CONFIG:
        # Determine data for this step
        rag = rag_contexts.get(sc.step_id, "[无RAG]")
        fin = financial_context if sc.needs_financial else ""
        tech = tech_analysis if sc.needs_technical else ""
        # Step2 also needs valuation anchor to prevent PB hallucination
        val = valuation_context if (sc.needs_valuation or sc.step_id == "step2") else ""
        exp_ret = expected_return if sc.needs_valuation else ""
        cons = consensus_forecast if sc.needs_valuation and sc.step_id == "step3" else ""

        # Industry extra data
        ind_extra = ""
        bcs = ""
        if industry_config.needs_bank_indicators:
            if sc.step_id == "step1":
                ind_extra = industry_extra_data_step1
            elif sc.step_id in ("step2", "step3"):
                bcs = bank_cross_section

        prompt = sc.prompt_template.format(
            stock_name=STOCK_NAME,
            industry_name=industry_config.industry_name,
            rag_context=rag or "[无相关研报内容]",
            financial_context=fin or "[无财务数据]",
            industry_extra_data=ind_extra or "[无行业专项数据]",
            technical_context=tech or "[无技术面数据]",
            prev_analysis=prev_analysis or "[本步骤为第一步，无前期分析]",
            valuation_context=val or "[无估值历史数据]",
            expected_return_context=exp_ret or "[无预期回报数据]",
            consensus_forecast_context=cons or "[无一致预期数据]",
            bank_cross_section=bcs or "[无行业对标数据]",
            step1_focus_areas=industry_config.step1_focus_areas,
            moat_dimensions=industry_config.moat_dimensions,
            valuation_note=industry_config.valuation_note,
            risk_dimensions=industry_config.risk_dimensions,
        )

        fname = os.path.join(OUTPUT_DIR, f"{sc.step_id}_prompt.txt")
        with open(fname, "w") as f:
            f.write(prompt)
        print(f"  [OK] {sc.step_id}: {len(prompt)} chars -> {fname}")

        # For subsequent steps, use placeholder prev_analysis
        prev_analysis = f"[{sc.name}的分析结果将在此处填入，当前为数据导出模式]"

    print(f"\n[DONE] All prompts saved to {OUTPUT_DIR}/")
    print("Now read 00_raw_data.txt for the full data context.")


if __name__ == "__main__":
    main()
