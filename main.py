from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Any
import shutil
import tempfile

from src.app_config import load_config
from src.clone_detection import detect_clones
from src.logging_utils import setup_logging

logger = logging.getLogger(__name__)


def run_clone_detection_on_files(files: list[Path], config: Any) -> list[dict[str, Any]]:
    if not files:
        return []

    # temporary directory to hold copies of files for detect_clones since it expects a directory
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir_path = Path(temp_dir)
        for i, f in enumerate(files):
            if f.exists():
                dest = temp_dir_path / f"{i}_{f.name}"
                shutil.copy2(f, dest)

        logger.info(f"Starting clone detection on {len(files)} files.")
        start_time = time.time()
        
        clusters = detect_clones(
            dir_path=temp_dir_path,
            threshold=config.similarity_threshold,
            dbscan_min_samples=config.dbscan_min_samples,
            model_name=config.model_name,
            model_local_path=config.model_local_path,
            max_length=config.max_length,
        )

    duration = time.time() - start_time
    logger.info(f"Clone detection completed in {duration:.2f}s.")
    return clusters


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

    clusters = detect_clones(
        dir_path=dir_path,
        threshold=config.similarity_threshold,
        dbscan_min_samples=config.dbscan_min_samples,
        model_name=config.model_name,
        model_local_path=config.model_local_path,
        max_length=config.max_length,
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
            project_results["PAGE_results"] = run_clone_detection_on_files(page_files, config)
            has_run = True
            
        if service_files:
            logger.info(f"Processing SERVICE files for project {project_name}")
            project_results["SERVICE_results"] = run_clone_detection_on_files(service_files, config)
            has_run = True

        if has_run:
            out_file = output_dir / f"{project_name}_results.json"
            with out_file.open("w", encoding="utf-8") as f:
                json.dump(project_results, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved merged project results to {out_file}")


def main() -> None:
    parser = argparse.ArgumentParser(description="UniXcoder-based Code Clone Detector")
    parser.add_argument("dir_path", type=str, help="Path to the directory containing JavaScript files or projects")
    parser.add_argument("--config", type=str, default="config.yaml", help="Path to config file")
    parser.add_argument("--mode", type=int, choices=[0, 1], default=0,
                        help="Mode 0: Parse projects dir for PAGE/SERVICE. Mode 1: Original dir processing")
    args = parser.parse_args()

    if args.mode == 1:
        run_mode_1(args.dir_path, args.config)
    else:
        run_mode_0(args.dir_path, args.config)


if __name__ == "__main__":
    main()
