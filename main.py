from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any

from src.app_config import load_config
from src.clone_detection import detect_clones
from src.logging_utils import setup_logging

logger = logging.getLogger(__name__)


def run_clone_detection(dir_path: str | Path, config_path: str | Path = "config.yaml") -> list[dict[str, Any]]:
    """
    Higher-level interface to run the clone detection process.
    Handles config loading, logging setup, and result saving.
    """
    config = load_config(Path(config_path))
    setup_logging(config.log_path)
    
    start_time = time.time()
    logger.info(f"Starting clone detection for directory: {dir_path}")

    dir_path = Path(dir_path)
    if not dir_path.is_dir():
        logger.error(f"Directory not found: {dir_path}")
        return []

    clusters = detect_clones(
        dir_path=dir_path,
        threshold=config.similarity_threshold,
        dbscan_min_samples=config.dbscan_min_samples,
        model_name=config.model_name,
        model_local_path=config.model_local_path,
        max_length=config.max_length,
    )

    # Save output
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    with config.output_path.open("w", encoding="utf-8") as f:
        json.dump({
            "config": {
                "dir_path": str(dir_path),
                "threshold": config.similarity_threshold,
                "dbscan_min_samples": config.dbscan_min_samples,
                "model_name": config.model_name,
                "max_length": config.max_length
            },
            "results": clusters
        }, f, indent=2, ensure_ascii=False)
    
    end_time = time.time()
    duration = end_time - start_time
    logger.info(f"Results saved to {config.output_path}")
    logger.info(f"Clone detection completed in {duration:.2f} seconds.")
    return clusters


def main() -> None:
    parser = argparse.ArgumentParser(description="UniXcoder-based Code Clone Detector")
    parser.add_argument("dir_path", type=str, help="Path to the directory containing JavaScript files")
    parser.add_argument("--config", type=str, default="config.yaml", help="Path to config file")
    args = parser.parse_args()

    run_clone_detection(args.dir_path, args.config)


if __name__ == "__main__":
    main()
