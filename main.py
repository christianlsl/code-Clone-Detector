from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any

from src.app_config import load_config
from src.clone_detection import detect_clones, compare_embeddings
from src.logging_utils import setup_logging

logger = logging.getLogger(__name__)


def run_mode_1(dir_path: str | Path, config_path: str | Path = "config.yaml") -> list[dict[str, Any]]:
    """ Original mode 1 """
    config = load_config(Path(config_path))
    setup_logging(config.log_path)
    
    start_time = time.time()
    logger.info(f"[Mode 1] Starting clone detection for directory: {dir_path}")

    dir_path = Path(dir_path)
    if not dir_path.is_dir():
        logger.error(f"Directory not found: {dir_path}")
        return []

    # Extract all .js files
    js_files = list(dir_path.rglob("*.js"))

    # Generate embedding prefix based on directory name
    embedding_prefix = dir_path.name or "mode1"

    clusters, results = detect_clones(
        files_list=js_files,
        threshold=config.similarity_threshold,
        dbscan_min_samples=config.dbscan_min_samples,
        model_name=config.model_name,
        model_local_path=config.model_local_path,
        max_length=config.max_length,
        save_embeddings_dir=config.embedding_path,
        embedding_prefix=embedding_prefix,
    )

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
    logger.info(f"Results saved to {config.output_path}")
    logger.info(f"Embeddings saved to {config.embedding_path}")
    logger.info(f"Clone detection completed in {end_time - start_time:.2f} seconds.")
    return clusters


def run_mode_0(dir_path: str | Path, config_path: str | Path = "config.yaml") -> None:
    """ Default mode 0 """
    config = load_config(Path(config_path))
    setup_logging(config.log_path)
    
    root_path = Path(dir_path)
    if not root_path.is_dir():
        logger.error(f"Directory not found: {root_path}")
        return

    logger.info(f"[Mode 0] Starting batch clone detection on projects in: {root_path}")
    for project_dir in root_path.iterdir():

        if not project_dir.is_dir():
            continue
            
        project_name = project_dir.name
        modules_dir = project_dir / "modules"
        logger.info(f"Processing project: {project_name}")

        if not modules_dir.is_dir():
            continue

        page_files = []
        service_files = []

        for module_dir in modules_dir.iterdir():
            if not module_dir.is_dir():
                continue
            
            general_work_dir = module_dir / "general_work"
            if not general_work_dir.is_dir():
                continue
                
            page_script_dir = general_work_dir / "PAGE" / "script"
            service_dir = general_work_dir / "SERVICE"
            
            if page_script_dir.is_dir():
                page_files.extend(list(page_script_dir.rglob("*.js")))
                
            if service_dir.is_dir():
                # includes subdirectories like SERVICE/api/*.js and SERVICE/utils/*.js
                service_files.extend(list(service_dir.rglob("*.js")))

        output_dir = Path("output")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        project_results = {
            "config": {
                "threshold": config.similarity_threshold,
                "dbscan_min_samples": config.dbscan_min_samples,
                "model_name": config.model_name,
                "max_length": config.max_length
            },
            "PAGE_results": [],
            "SERVICE_results": []
        }
        
        has_run = False
        
        if page_files:
            logger.info(f"Processing PAGE files for project {project_name}")
            start_time = time.time()
            clusters, _ = detect_clones(
                files_list=page_files,
                threshold=config.similarity_threshold,
                dbscan_min_samples=config.dbscan_min_samples,
                model_name=config.model_name,
                model_local_path=config.model_local_path,
                max_length=config.max_length,
                save_embeddings_dir=config.embedding_path,
                embedding_prefix=f"{project_name}_page",
            )
            duration = time.time() - start_time
            logger.info(f"Clone detection for PAGE completed in {duration:.2f}s.")
            project_results["PAGE_results"] = clusters
            has_run = True
            
        if service_files:
            logger.info(f"Processing SERVICE files for project {project_name}")
            start_time = time.time()
            clusters, _ = detect_clones(
                files_list=service_files,
                threshold=config.similarity_threshold,
                dbscan_min_samples=config.dbscan_min_samples,
                model_name=config.model_name,
                model_local_path=config.model_local_path,
                max_length=config.max_length,
                save_embeddings_dir=config.embedding_path,
                embedding_prefix=f"{project_name}_service",
            )
            duration = time.time() - start_time
            logger.info(f"Clone detection for SERVICE completed in {duration:.2f}s.")
            project_results["SERVICE_results"] = clusters
            has_run = True

        if has_run:
            out_file = output_dir / f"{project_name}_results.json"
            with out_file.open("w", encoding="utf-8") as f:
                json.dump(project_results, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved merged project results to {out_file}")
            logger.info(f"Embeddings saved to {config.embedding_path}")


def run_compare(embedding_dir: str | Path, config_path: str | Path = "config.yaml") -> None:
    """Compare embeddings loaded from directory."""
    config = load_config(Path(config_path))
    setup_logging(config.log_path)
    
    embedding_dir = Path(embedding_dir)
    logger.info(f"[Compare Mode] Loading embeddings from: {embedding_dir}")
    
    start_time = time.time()
    clusters = compare_embeddings(
        embedding_dir=embedding_dir,
        threshold=config.similarity_threshold,
        dbscan_min_samples=config.dbscan_min_samples,
    )
    
    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    with config.output_path.open("w", encoding="utf-8") as f:
        json.dump({
            "config": {
                "embedding_dir": str(embedding_dir),
                "threshold": config.similarity_threshold,
                "dbscan_min_samples": config.dbscan_min_samples,
                "model_name": config.model_name,
                "max_length": config.max_length
            },
            "results": clusters
        }, f, indent=2, ensure_ascii=False)
    
    end_time = time.time()
    logger.info(f"Compare results saved to {config.output_path}")
    logger.info(f"Compare completed in {end_time - start_time:.2f} seconds.")


def main() -> None:
    parser = argparse.ArgumentParser(description="UniXcoder-based Code Clone Detector")
    parser.add_argument("dir_path", type=str, help="Path to the directory containing JavaScript files or projects")
    parser.add_argument("--config", type=str, default="config.yaml", help="Path to config file")
    parser.add_argument("--mode", type=int, choices=[0, 1, 2], default=0,
                        help="Mode 0: Parse projects dir for PAGE/SERVICE. Mode 1: Original dir processing. Mode 2: Compare embeddings from directory")
    args = parser.parse_args()

    if args.mode == 2:
        run_compare(args.dir_path, args.config)
    elif args.mode == 1:
        run_mode_1(args.dir_path, args.config)
    else:
        run_mode_0(args.dir_path, args.config)


if __name__ == "__main__":
    main()
