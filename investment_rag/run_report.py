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
        final_report = f"# {args.name}({args.code}) 技术面分析\n\n{tech_section}"

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
