#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Download HuggingFace models for local inference.

Usage:
    python scripts/download_models.py --output-dir /data/models
    python scripts/download_models.py --output-dir ~/.cache/mytrader_models  # local dev
"""
import argparse
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

MODELS = {
    "bge-large-zh-v1.5": {
        "repo": "BAAI/bge-large-zh-v1.5",
        "type": "sentence-transformers",
        "description": "Chinese embedding model (1024d)",
    },
    "xlm-roberta-sentiment": {
        "repo": "cardiffnlp/twitter-xlm-roberta-base-sentiment-multilingual",
        "type": "transformers",
        "description": "Multilingual sentiment classification (supports Chinese)",
    },
}


def download_model(name: str, output_dir: Path) -> bool:
    """Download a model to output_dir/name/."""
    info = MODELS[name]
    target = output_dir / name
    target.mkdir(parents=True, exist_ok=True)

    logger.info("=== Downloading %s (%s) ===", name, info["description"])
    logger.info("  Repo: %s", info["repo"])
    logger.info("  Target: %s", target)

    try:
        if info["type"] == "sentence-transformers":
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(info["repo"])
            model.save(str(target))
            logger.info("  Saved sentence-transformers model to %s", target)
        elif info["type"] == "transformers":
            from transformers import AutoModelForSequenceClassification, AutoTokenizer, AutoConfig
            logger.info("  Downloading tokenizer...")
            AutoTokenizer.from_pretrained(info["repo"]).save_pretrained(str(target))
            logger.info("  Downloading model...")
            AutoModelForSequenceClassification.from_pretrained(info["repo"]).save_pretrained(str(target))
            AutoConfig.from_pretrained(info["repo"]).save_pretrained(str(target))
            logger.info("  Saved transformers model to %s", target)

        # Verify
        files = list(target.iterdir())
        logger.info("  Verified: %d files in %s", len(files), target)
        return True

    except Exception as e:
        logger.error("  Failed to download %s: %s", name, e)
        return False


def main():
    parser = argparse.ArgumentParser(description="Download HuggingFace models for myTrader")
    parser.add_argument("--output-dir", required=True, help="Directory to save models")
    parser.add_argument("--model", choices=list(MODELS.keys()), help="Download specific model only")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    models_to_download = [args.model] if args.model else list(MODELS.keys())

    results = {}
    for name in models_to_download:
        results[name] = download_model(name, output_dir)

    logger.info("=== Summary ===")
    for name, ok in results.items():
        status = "OK" if ok else "FAILED"
        logger.info("  %s: %s", name, status)

    if not all(results.values()):
        logger.error("Some downloads failed!")
        sys.exit(1)

    logger.info("All models downloaded to %s", output_dir)


if __name__ == "__main__":
    main()
