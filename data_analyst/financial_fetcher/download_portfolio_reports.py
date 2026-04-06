"""
批量下载持仓股最近3年年报和季报（巨潮资讯）

用法：
    python data_analyst/financial_fetcher/download_portfolio_reports.py
    python data_analyst/financial_fetcher/download_portfolio_reports.py --dry-run
    python data_analyst/financial_fetcher/download_portfolio_reports.py --start-year 2022

报告类型：年报 / 一季报 / 半年报 / 三季报
输出目录：/Users/zhaobo/Documents/PDF资料/投资研究/公司研究/annual_reports/{stock_code}/
"""

import sys
import os
import time
import logging
import argparse
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/tmp/portfolio_reports_download.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("portfolio_reports")

# ETF code prefixes to skip (no financial reports)
ETF_PREFIXES = ("159", "510", "511", "512", "513", "515", "516", "517", "518", "588")

ANN_TYPES = ["年报", "一季报", "半年报", "三季报"]


def get_portfolio_stocks(portfolio_path: str) -> dict:
    """
    Parse portfolio file and return {code: name} for non-ETF A-shares.
    """
    from strategist.tech_scan.portfolio_parser import PortfolioParser

    parser = PortfolioParser(portfolio_path)
    positions = parser.parse()

    watch_list = {}
    skipped_etf = []

    for pos in positions:
        code_bare = pos.code.split(".")[0]  # strip .SH / .SZ suffix
        if any(code_bare.startswith(p) for p in ETF_PREFIXES):
            skipped_etf.append(f"{code_bare}({pos.name})")
            continue
        watch_list[code_bare] = pos.name

    if skipped_etf:
        logger.info(f"Skipped ETFs: {', '.join(skipped_etf)}")

    return watch_list


def run_download(watch_list: dict, start_year: int, dry_run: bool = False,
                 interval: float = 2.0):
    """
    Search and download all report types for each stock.
    Returns (downloaded, skipped, failed) counts.
    """
    from data_analyst.financial_fetcher.cninfo_downloader import (
        search_announcements, download_pdf, PDF_DIR
    )

    downloaded = 0
    skipped = 0
    failed = 0
    start_date = f"{start_year}-01-01"

    total_stocks = len(watch_list)
    for idx, (code, name) in enumerate(watch_list.items(), 1):
        logger.info(f"[{idx}/{total_stocks}] ===== {name}({code}) =====")
        out_dir = PDF_DIR / code

        for ann_type in ANN_TYPES:
            anns = search_announcements(code, name, ann_type, start_date)
            logger.info(f"  {ann_type}: found {len(anns)} reports")

            for ann in anns:
                logger.info(f"    {ann['date']}  {ann['title']}")
                if dry_run:
                    skipped += 1
                    continue

                path = download_pdf(ann, out_dir, overwrite=False)
                if path:
                    # download_pdf returns path even when skipped (file exists)
                    if "(already exists)" in str(path) or ann.get("_skipped"):
                        skipped += 1
                    else:
                        downloaded += 1
                else:
                    failed += 1
                time.sleep(interval)

    return downloaded, skipped, failed


def main():
    parser = argparse.ArgumentParser(description="Download portfolio annual/quarterly reports")
    parser.add_argument("--start-year", type=int, default=2022,
                        help="Start year for report search (default: 2022)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Search only, do not download")
    parser.add_argument("--interval", type=float, default=2.0,
                        help="Sleep seconds between downloads (default: 2.0)")
    parser.add_argument(
        "--portfolio",
        default="/Users/zhaobo/Documents/notes/Finance/Positions/00-Current-Portfolio-Audit.md",
        help="Path to portfolio Markdown file",
    )
    args = parser.parse_args()

    logger.info(f"Portfolio: {args.portfolio}")
    logger.info(f"Start year: {args.start_year}  |  Dry run: {args.dry_run}")

    watch_list = get_portfolio_stocks(args.portfolio)
    logger.info(f"Non-ETF A-shares: {len(watch_list)}")
    for code, name in watch_list.items():
        logger.info(f"  {code}  {name}")

    logger.info(f"\nReport types: {ANN_TYPES}")
    logger.info("Starting download..." if not args.dry_run else "DRY RUN - search only")

    downloaded, skipped, failed = run_download(
        watch_list,
        start_year=args.start_year,
        dry_run=args.dry_run,
        interval=args.interval,
    )

    if args.dry_run:
        logger.info(f"\n[DRY RUN DONE] total announcements found: {downloaded + skipped}")
    else:
        logger.info(
            f"\n[DONE] downloaded={downloaded}  skipped(exists)={skipped}  failed={failed}"
        )
        from data_analyst.financial_fetcher.cninfo_downloader import PDF_DIR
        logger.info(f"Files saved to: {PDF_DIR}")


if __name__ == "__main__":
    main()
