# -*- coding: utf-8 -*-
"""CLI entry point for financial fetcher"""

import argparse
import logging
import sys
import os
import types

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _register_dummy_parent_package():
    """workaround: data_analyst/__init__.py imports xtquant (Windows-only)"""
    if 'data_analyst' not in sys.modules:
        dummy = types.ModuleType('data_analyst')
        dummy.__path__ = [os.path.join(_PROJECT_ROOT, 'data_analyst')]
        dummy.__package__ = 'data_analyst'
        sys.modules['data_analyst'] = dummy


def _load_sibling(name):
    import importlib.util
    full_name = f"data_analyst.financial_fetcher.{name}"
    filepath = os.path.join(_THIS_DIR, f"{name}.py")
    spec = importlib.util.spec_from_file_location(full_name, filepath)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "data_analyst.financial_fetcher"
    sys.modules[full_name] = mod
    spec.loader.exec_module(mod)
    return mod


_register_dummy_parent_package()

# Now load siblings (the actual way to import in this project)
config_mod = _load_sibling("config")
storage_mod = _load_sibling("storage")
fetcher_mod = _load_sibling("fetcher")
report_mod = _load_sibling("report_generator")
cninfo_mod = _load_sibling("cninfo_downloader")
rag_mod = _load_sibling("rag_ingest")

FinancialFetcherConfig = config_mod.FinancialFetcherConfig
FinancialStorage = storage_mod.FinancialStorage
run_fetch = fetcher_mod.run_fetch
generate_markdown = report_mod.generate_markdown
batch_download = cninfo_mod.batch_download
ingest_markdown_files = rag_mod.ingest_markdown_files

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger('financial_fetcher')


def _load_all_stocks(env: str) -> dict:
    """load full A-share stock list from trade_stock_basic, return {code: name}"""
    from config.db import execute_query
    rows = execute_query(
        "SELECT stock_code, stock_name FROM trade_stock_basic ORDER BY stock_code",
        env=env,
    )
    result = {}
    for r in rows:
        raw = r["stock_code"]  # e.g. 000001.SZ
        code = raw.split(".")[0] if "." in raw else raw
        result[code] = r["stock_name"].strip()
    return result


def _load_done_codes(progress_file: str) -> set:
    """read already-fetched stock codes from progress file"""
    if not os.path.exists(progress_file):
        return set()
    done = set()
    with open(progress_file) as f:
        for line in f:
            line = line.strip()
            if line:
                done.add(line)
    return done


def _mark_done(progress_file: str, code: str):
    with open(progress_file, "a") as f:
        f.write(code + "\n")


def _run_all(config: FinancialFetcherConfig, workers: int = 3):
    """fetch all A-share stocks with parallel workers and resume support"""
    import concurrent.futures
    import threading

    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    progress_dir = os.path.join(ROOT, 'output', 'financial_fetcher')
    os.makedirs(progress_dir, exist_ok=True)
    progress_file = os.path.join(progress_dir, 'progress.txt')
    failed_file = os.path.join(progress_dir, 'failed.txt')

    all_stocks = _load_all_stocks(config.db_env)
    done_codes = _load_done_codes(progress_file)
    pending = {k: v for k, v in all_stocks.items() if k not in done_codes}

    logger.info(f"Total: {len(all_stocks)}, done: {len(done_codes)}, pending: {len(pending)}, workers: {workers}")

    # init tables once before parallel workers start
    FinancialStorage(env=config.db_env).init_tables()

    lock = threading.Lock()
    counter = {"done": len(done_codes), "fail": 0}

    def fetch_one(item):
        code, name = item
        try:
            run_fetch(config, stock_codes={code: name}, skip_init=True)
            with lock:
                _mark_done(progress_file, code)
                counter["done"] += 1
                logger.info(f"[{counter['done']}/{len(all_stocks)}] {name}({code}) done")
        except Exception as e:
            with lock:
                counter["fail"] += 1
                with open(failed_file, "a") as f:
                    f.write(f"{code}\t{name}\t{e}\n")
            logger.error(f"[FAIL] {name}({code}): {e}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        executor.map(fetch_one, pending.items())

    logger.info(f"All done. success={counter['done']}, fail={counter['fail']}")
    logger.info(f"Progress: {progress_file}")
    if counter["fail"]:
        logger.info(f"Failed list: {failed_file}")


def main():
    parser = argparse.ArgumentParser(description='Financial Data Fetcher')
    parser.add_argument('--code', type=str, help='Single stock code to fetch')
    parser.add_argument('--all', action='store_true', help='Fetch all A-share stocks from trade_stock_basic')
    parser.add_argument('--env', type=str, default='online', choices=['local', 'online'])
    parser.add_argument('--output', type=str, help='Output dir for Markdown')
    parser.add_argument('--download-pdf', action='store_true', help='Download PDF annual reports')
    parser.add_argument('--ingest-rag', action='store_true', help='Ingest Markdown + PDF text to ChromaDB')
    parser.add_argument('--ingest-pdf', action='store_true', help='Ingest PDF annual reports to ChromaDB (extract text first)')
    parser.add_argument('--no-db', action='store_true', help='Skip database writes')
    parser.add_argument('--workers', type=int, default=3, help='Parallel workers for --all mode (default 3)')

    args = parser.parse_args()
    config = FinancialFetcherConfig()
    if args.env:
        config.db_env = args.env
    if args.output:
        config.output_dir = args.output

    try:
        # 1. fetch structured data
        if not args.no_db:
            if args.all:
                _run_all(config, workers=args.workers)
            else:
                stats = run_fetch(config, single_code=args.code)
                logger.info(f"Fetch stats: {stats}")

        # 2. generate markdown
        storage = FinancialStorage(env=config.db_env)
        targets = {args.code: config.watch_list.get(args.code, args.code)} if args.code else config.watch_list
        for code, name in targets.items():
            path = generate_markdown(code, name, storage, config.output_dir)
            if path:
                logger.info(f"Report: {path}")

        # 3. download PDF
        if args.download_pdf:
            paths = batch_download(
                targets,
                ann_types=["年报"],
                start_year=2023,
            )
            logger.info(f"PDF downloaded: {len(paths)}")

        # 4. RAG ingest
        if args.ingest_rag or args.ingest_pdf:
            from investment_rag.embeddings.embed_model import EmbeddingClient
            from investment_rag.store.chroma_client import ChromaClient
            ec = EmbeddingClient()
            cc = ChromaClient()
            collection_name = "financials"
            total = 0

            if args.ingest_rag:
                count = ingest_markdown_files(
                    config.output_dir, collection_name, ec, cc,
                )
                total += count
                logger.info(f"Markdown RAG: {count} chunks")

            if args.ingest_pdf:
                import re as _re
                pdf_root = "/Users/zhaobo/Documents/PDF资料/投资研究/公司研究/annual_reports"
                pdf_dir = config.pdf_dir if hasattr(config, 'pdf_dir') else pdf_root
                for code_dir in sorted(os.listdir(pdf_dir)):
                    code_path = os.path.join(pdf_dir, code_dir)
                    if not os.path.isdir(code_path):
                        continue
                    for fname in sorted(os.listdir(code_path)):
                        if not fname.endswith(".txt"):
                            continue
                        # Guess stock info from filename
                        m = _re.match(r'(.+?)_(\d{6})_(\d{4})_', fname)
                        if not m:
                            continue
                        stock_name = m.group(1)
                        stock_code = m.group(2)
                        report_year = m.group(3)
                        txt_path = os.path.join(code_path, fname)
                        n = rag_mod.ingest_pdf_text(
                            pdf_path=txt_path,
                            stock_code=stock_code,
                            stock_name=stock_name,
                            report_year=report_year,
                            collection_name=collection_name,
                            embed_client=ec,
                            chroma_client=cc,
                        )
                        total += n
                        logger.info(f"PDF RAG: {stock_name}({stock_code}) {report_year} -> {n} chunks")

            logger.info(f"RAG total: {total} chunks ingested into '{collection_name}'")

        logger.info("Done")

    except Exception as e:
        logger.error(f"Fatal: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
