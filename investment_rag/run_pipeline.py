# -*- coding: utf-8 -*-
"""
CLI entry point for ingestion pipeline.

Usage:
    # Ingest a single PDF
    python -m investment_rag.run_pipeline --file path/to/report.pdf --collection reports

    # Ingest a directory
    python -m investment_rag.run_pipeline --dir ~/Documents/notes/Finance/Research/01-Sectors --collection reports

    # Ingest default research directory
    python -m investment_rag.run_pipeline --all
"""
import argparse
import logging
import sys

from investment_rag.config import load_config, DEFAULT_CONFIG
from investment_rag.ingest.ingest_pipeline import IngestPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Investment RAG Ingestion Pipeline")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", type=str, help="Single file to ingest")
    group.add_argument("--dir", type=str, help="Directory to ingest (recursive)")
    group.add_argument("--all", action="store_true", help="Ingest default research directory")

    parser.add_argument(
        "--collection", type=str, default="reports",
        choices=["reports", "announcements", "notes", "macro"],
        help="Target collection (default: reports)",
    )

    args = parser.parse_args()

    config = load_config()

    if args.all:
        paths = [config.research_dir]
    elif args.file:
        paths = [args.file]
    else:
        paths = [args.dir]

    logger.info("Starting ingestion into collection '%s'", args.collection)
    pipeline = IngestPipeline(config=config)
    result = pipeline.ingest_paths(paths, args.collection)

    print(f"\nStatus: {result['status']}")
    print(f"Files processed: {result['files_processed']}")
    print(f"Chunks created: {result['chunks_created']}")
    if result['errors']:
        print(f"Errors ({len(result['errors'])}):")
        for err in result['errors']:
            print(f"  - {err}")


if __name__ == "__main__":
    main()
