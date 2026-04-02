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


def main():
    parser = argparse.ArgumentParser(description='Financial Data Fetcher')
    parser.add_argument('--code', type=str, help='Single stock code to fetch')
    parser.add_argument('--env', type=str, default='online', choices=['local', 'online'])
    parser.add_argument('--output', type=str, help='Output dir for Markdown')
    parser.add_argument('--download-pdf', action='store_true', help='Download PDF annual reports')
    parser.add_argument('--ingest-rag', action='store_true', help='Ingest Markdown to ChromaDB')
    parser.add_argument('--no-db', action='store_true', help='Skip database writes')

    args = parser.parse_args()
    config = FinancialFetcherConfig()
    if args.env:
        config.db_env = args.env
    if args.output:
        config.output_dir = args.output

    try:
        # 1. fetch structured data
        if not args.no_db:
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
        if args.ingest_rag:
            count = ingest_markdown_files(config.output_dir)
            logger.info(f"RAG ingested: {count} chunks")

        logger.info("Done")

    except Exception as e:
        logger.error(f"Fatal: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
