# -*- coding: utf-8 -*-
"""
银行年报批量处理管道 v2.0

流程：
  17份2025年报PDF
    -> (1) PDF -> Markdown 转换
    -> (2) 银行模板提取 -> MySQL
    -> (3) RAG ingest -> ChromaDB
    -> (4) 逐家打分（v2.0评分卡）
    -> (5) 横向对比表
    -> (6) 汇总研报 + 排名

用法：
  python scripts/batch_bank_report_pipeline.py --stage 1  # 仅转换PDF
  python scripts/batch_bank_report_pipeline.py --stage 2  # 仅提取
  python scripts/batch_bank_report_pipeline.py --all      # 全流程
"""
import sys
import os
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(f"/tmp/bank_report_pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
    ],
)
logger = logging.getLogger(__name__)

# 17家银行（2025年报已下载）
BANK_LIST = [
    ("601998", "中信银行"),
    ("601328", "交通银行"),
    ("601818", "光大银行"),
    ("601166", "兴业银行"),
    ("601288", "农业银行"),
    ("600015", "华夏银行"),
    ("002142", "宁波银行"),
    ("601398", "工商银行"),
    ("000001", "平安银行"),
    ("601939", "建设银行"),
    ("002839", "张家港行"),
    ("600036", "招商银行"),
    ("600016", "民生银行"),
    ("600000", "浦发银行"),
    ("601077", "渝农商行"),
    ("601658", "邮储银行"),
    ("601963", "重庆银行"),
]

PDF_ROOT = Path("/Users/zhaobo/Documents/PDF/投资研究/公司研究/annual_reports")
OUTPUT_DIR = Path(ROOT) / "output" / "bank_reports_2025"

# ============================================================
# Stage 1: PDF -> Markdown 转换
# ============================================================

def stage1_convert_pdf_to_markdown(overwrite: bool = False) -> Dict:
    """批量转换PDF到Markdown（耗时，建议后台运行）"""
    from data_analyst.financial_fetcher.md_converter import MDConverter

    logger.info("=" * 70)
    logger.info("Stage 1: PDF -> Markdown 转换")
    logger.info("=" * 70)

    converter = MDConverter(prefer_mineru=False)
    result = {
        "converted": 0,
        "skipped": 0,
        "failed": 0,
        "files": [],
    }

    for code, name in BANK_LIST:
        pdf_dir = PDF_ROOT / code
        if not pdf_dir.exists():
            logger.warning(f"[{name}] PDF目录不存在: {pdf_dir}")
            continue

        # 找2025年报PDF（文件名包含2025）
        pdf_files = list(pdf_dir.glob(f"*2025*年报.pdf"))
        if not pdf_files:
            logger.warning(f"[{name}] 未找到2025年报PDF")
            continue

        for pdf_file in pdf_files:
            try:
                logger.info(f"[{name}] 转换: {pdf_file.name}")
                md_file = converter.convert(str(pdf_file), output_dir=str(pdf_dir / "md"))
                logger.info(f"  -> {Path(md_file).name} OK")
                result["converted"] += 1
                result["files"].append({"code": code, "name": name, "md": md_file})
            except Exception as e:
                logger.error(f"  -> 转换失败: {e}")
                result["failed"] += 1

    logger.info(f"\n转换完成: {result['converted']} 成功, {result['failed']} 失败\n")
    return result


# ============================================================
# Stage 2: 提取结构化数据 -> MySQL
# ============================================================

def stage2_extract_and_save(md_files: List[Dict] = None) -> Dict:
    """从Markdown提取结构化数据并保存到MySQL"""
    from data_analyst.financial_fetcher.annual_report_extractor import AnnualReportExtractor

    logger.info("=" * 70)
    logger.info("Stage 2: 提取结构化数据 -> MySQL")
    logger.info("=" * 70)

    extractor = AnnualReportExtractor(db_env="online")
    result = {
        "extracted": 0,
        "failed": 0,
        "records": [],
    }

    # 如果没有提供md_files，从磁盘扫描
    if not md_files:
        md_files = []
        for code, name in BANK_LIST:
            md_dir = PDF_ROOT / code / "md"
            md_list = list(md_dir.glob("*2025*年报.md"))
            for md in md_list:
                md_files.append({"code": code, "name": name, "md": str(md)})

    for item in md_files:
        code, name, md_path = item["code"], item["name"], item["md"]
        try:
            logger.info(f"[{name}] 提取: {Path(md_path).name}")
            result_dict = extractor.process_md(md_path, industry="bank", save=True)
            logger.info(f"  -> 提取成功: income/overdue/cashflow")
            result["extracted"] += 1
            result["records"].append({
                "code": code,
                "name": name,
                "md": md_path,
                "extracted_keys": list(result_dict.keys()),
            })
        except Exception as e:
            logger.error(f"  -> 提取失败: {e}")
            result["failed"] += 1

    logger.info(f"\n提取完成: {result['extracted']} 成功, {result['failed']} 失败\n")
    return result


# ============================================================
# Stage 3: RAG 向量化
# ============================================================

def stage3_ingest_to_rag(md_files: List[Dict] = None) -> Dict:
    """向量化markdown文件到ChromaDB"""
    from investment_rag.ingest.ingest_pipeline import IngestPipeline, DEFAULT_CONFIG

    logger.info("=" * 70)
    logger.info("Stage 3: RAG 向量化 -> ChromaDB")
    logger.info("=" * 70)

    pipeline = IngestPipeline(config=DEFAULT_CONFIG)

    # 如果没有提供md_files，从磁盘扫描
    if not md_files:
        md_files = []
        for code, name in BANK_LIST:
            md_dir = PDF_ROOT / code / "md"
            md_list = list(md_dir.glob("*2025*年报.md"))
            for md in md_list:
                md_files.append({"code": code, "name": name, "md": str(md)})

    result = {
        "ingested": 0,
        "chunks": 0,
        "failed": 0,
    }

    md_paths = [item["md"] for item in md_files]
    try:
        logger.info(f"向量化 {len(md_paths)} 个文件...")
        ingest_result = pipeline.ingest_paths(md_paths, collection="annual_reports_2025")
        result["ingested"] = ingest_result.get("files_processed", 0)
        result["chunks"] = ingest_result.get("total_chunks", 0)
        result["failed"] = ingest_result.get("errors", 0)
        logger.info(f"向量化完成: {result['ingested']} 文件, {result['chunks']} chunks\n")
    except Exception as e:
        logger.error(f"向量化失败: {e}\n")
        result["failed"] = len(md_paths)

    return result


# ============================================================
# Stage 4: 逐家打分
# ============================================================

def stage4_score_all_banks() -> Dict:
    """使用BankScoreCard v2.0评分"""
    from investment_rag.report_engine.bank_scorecard import BankScoreCard

    logger.info("=" * 70)
    logger.info("Stage 4: 逐家打分（v2.0评分卡）")
    logger.info("=" * 70)

    scorecard = BankScoreCard(db_env="online")
    result = {
        "scored": 0,
        "failed": 0,
        "scores": [],
    }

    for code, name in BANK_LIST:
        try:
            logger.info(f"[{name}] 评分...")
            score_result = scorecard.score(code, name)
            result["scored"] += 1
            result["scores"].append({
                "code": code,
                "name": name,
                "total_score": round(score_result.total_score, 2),
                "rating": score_result.rating,
                "dim_scores": {
                    d.name: round(d.dim_raw, 2)
                    for d in score_result.dim_scores
                },
            })
            logger.info(f"  -> {score_result.total_score:.1f}/100 ({score_result.rating})")
        except Exception as e:
            logger.error(f"  -> 评分失败: {e}")
            result["failed"] += 1

    # 按总分排序
    result["scores"].sort(key=lambda x: x["total_score"], reverse=True)

    logger.info(f"\n评分完成: {result['scored']} 家成功, {result['failed']} 家失败\n")
    return result


# ============================================================
# Stage 5: 横向对比表
# ============================================================

def stage5_comparison_table(scores: List[Dict]) -> str:
    """生成横向对比Markdown表"""
    logger.info("=" * 70)
    logger.info("Stage 5: 横向对比表")
    logger.info("=" * 70)

    lines = [
        "# 17家银行2025年报评分对比",
        "",
        f"评分时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 总分排名",
        "",
        "| 排名 | 银行 | 代码 | 总分 | 评级 | 资产质量 | 盈利 | 利润质量 | 净资产 | 资本 | 估值 | 股息 |",
        "|------|------|------|------|------|---------|------|---------|--------|------|------|------|",
    ]

    for rank, item in enumerate(scores, 1):
        dims = item["dim_scores"]
        line = (
            f"| {rank} | {item['name']:6} | {item['code']} | "
            f"{item['total_score']:5.1f} | {item['rating']:8} | "
            f"{dims.get('资产质量', 0):.1f} | {dims.get('盈利能力', 0):.1f} | "
            f"{dims.get('利润质量', 0):.1f} | {dims.get('净资产质量', 0):.1f} | "
            f"{dims.get('资本充足率', 0):.1f} | {dims.get('估值安全边际', 0):.1f} | "
            f"{dims.get('股息回报', 0):.1f} |"
        )
        lines.append(line)

    # 分析统计
    lines += [
        "",
        "## 分析统计",
        "",
    ]

    ratings = {}
    for item in scores:
        r = item["rating"]
        ratings[r] = ratings.get(r, 0) + 1

    lines.append("### 评级分布")
    for rating in ["强烈推荐", "推荐", "中性偏推荐", "中性", "回避", "强烈回避"]:
        count = ratings.get(rating, 0)
        if count > 0:
            lines.append(f"- {rating}: {count}家")

    # 维度最高分
    lines += [
        "",
        "### 各维度最高分",
        "",
    ]
    dim_names = ["资产质量", "盈利能力", "利润质量", "净资产质量", "资本充足率", "估值安全边际", "股息回报"]
    for dim in dim_names:
        best_bank = max(scores, key=lambda x: x["dim_scores"].get(dim, 0))
        best_score = best_bank["dim_scores"].get(dim, 0)
        lines.append(f"- **{dim}**: {best_bank['name']} ({best_score:.1f})")

    table_text = "\n".join(lines)
    logger.info(f"\n对比表生成完成\n")
    return table_text


# ============================================================
# Stage 6: 汇总研报
# ============================================================

def stage6_summary_report(scores: List[Dict], comparison_table: str) -> str:
    """生成汇总研报"""
    logger.info("=" * 70)
    logger.info("Stage 6: 汇总研报")
    logger.info("=" * 70)

    # 分类统计
    strong_buy = [s for s in scores if s["rating"] in ["强烈推荐", "推荐"]]
    neutral = [s for s in scores if s["rating"] in ["中性", "中性偏推荐"]]
    avoid = [s for s in scores if s["rating"] in ["回避", "强烈回避"]]

    lines = [
        "# 2025年银行年报综合研报",
        "",
        f"分析日期: {datetime.now().strftime('%Y-%m-%d')}",
        "分析对象: 17家A股上市银行2025年年报",
        "评分框架: 逆向工程f大权重 (v2.0改进版)",
        "",
        "## 核心观点",
        "",
        f"- **推荐关注**: {len(strong_buy)}家（强烈推荐/推荐）",
        f"- **中性评级**: {len(neutral)}家",
        f"- **规避风险**: {len(avoid)}家",
        "",
    ]

    if strong_buy:
        lines += [
            "## 推荐关注（排名靠前）",
            "",
        ]
        for item in strong_buy[:3]:
            dims = item["dim_scores"]
            strongest = max(dims.items(), key=lambda x: x[1])
            lines.append(f"### {item['name']} ({item['code']})")
            lines.append(f"- 总分: **{item['total_score']:.1f}** | 评级: **{item['rating']}**")
            lines.append(f"- 核心优势: {strongest[0]} ({strongest[1]:.1f}/5.0)")
            lines.append("")

    if avoid:
        lines += [
            "## 规避风险（排名靠后）",
            "",
        ]
        for item in avoid[:3]:
            dims = item["dim_scores"]
            weakest = min(dims.items(), key=lambda x: x[1])
            lines.append(f"### {item['name']} ({item['code']})")
            lines.append(f"- 总分: **{item['total_score']:.1f}** | 评级: **{item['rating']}**")
            lines.append(f"- 核心风险: {weakest[0]} ({weakest[1]:.1f}/5.0)")
            lines.append("")

    lines += [
        "## 详细对比表",
        "",
        comparison_table,
        "",
        "## 评分方法论",
        "",
        "基于对f大17家银行年报点评的逆向工程，调整后的权重：",
        "- D1 资产质量 (25%): NPL2趋势核心，f大最关注的质量指标",
        "- D2 盈利能力 (10%): 大幅降权，f大认为利润易被调节",
        "- D3 利润质量 (15%): 拨备释放、剪刀差分析",
        "- D4 净资产质量 (20%): 大幅上调，第一驱动力",
        "- D5 资本充足率 (10%): 降权，相对不被重视",
        "- D6 估值安全边际 (10%): PB历史分位",
        "- D7 股息回报 (10%): 新增独立维度，分红率与增速",
        "",
    ]

    summary = "\n".join(lines)
    logger.info(f"\n汇总研报生成完成\n")
    return summary


# ============================================================
# 主流程
# ============================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="银行年报批量处理管道")
    parser.add_argument("--stage", type=int, choices=[1, 2, 3, 4, 5, 6],
                        help="运行指定阶段")
    parser.add_argument("--all", action="store_true",
                        help="运行全流程")
    parser.add_argument("--skip-convert", action="store_true",
                        help="跳过PDF转换（假设已转换）")
    parser.add_argument("--skip-extract", action="store_true",
                        help="跳过数据提取（假设已提取）")

    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 运行流程
    stage1_result = None
    stage2_result = None
    stage3_result = None
    stage4_result = None

    try:
        if args.all or args.stage == 1:
            if not args.skip_convert:
                stage1_result = stage1_convert_pdf_to_markdown()

        if args.all or args.stage == 2:
            if not args.skip_extract:
                stage2_result = stage2_extract_and_save(stage1_result.get("files") if stage1_result else None)

        if args.all or args.stage == 3:
            stage3_result = stage3_ingest_to_rag()

        if args.all or args.stage == 4 or args.stage == 5 or args.stage == 6:
            stage4_result = stage4_score_all_banks()

        if args.all or args.stage == 5 or args.stage == 6:
            comparison_table = stage5_comparison_table(stage4_result["scores"])

        if args.all or args.stage == 6:
            summary_report = stage6_summary_report(stage4_result["scores"], comparison_table)

            # 保存报告
            report_path = OUTPUT_DIR / f"bank_report_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            report_path.write_text(summary_report, encoding="utf-8")
            logger.info(f"汇总研报已保存: {report_path}")

            # 也保存对比表
            table_path = OUTPUT_DIR / f"bank_comparison_table_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
            table_path.write_text(f"# 银行对比表\n\n{comparison_table}", encoding="utf-8")
            logger.info(f"对比表已保存: {table_path}")

            # 保存评分数据
            scores_path = OUTPUT_DIR / f"bank_scores_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            scores_path.write_text(json.dumps(stage4_result["scores"], ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"评分数据已保存: {scores_path}")

        logger.info("\n" + "=" * 70)
        logger.info("PIPELINE 执行完成")
        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"\nPIPELINE 执行失败: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
