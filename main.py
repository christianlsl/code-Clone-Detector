from __future__ import annotations

import argparse
import itertools
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
import yaml
from torch.nn.functional import cosine_similarity
from tqdm import tqdm

from src.tokenizer import CodeBlock, FileEmbeddingResult, embed_file_blocks
from src.unixcoder import UniXcoder

logger = logging.getLogger(__name__)


@dataclass
class AppConfig:
    log_path: Path
    output_path: Path
    model_local_path: Path
    similarity_threshold: float = 0.8
    model_name: str = "microsoft/unixcoder-base"
    max_length: int = 512


def setup_logging(log_path: Path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )


def load_config(config_path: Path) -> AppConfig:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf8") as f:
        raw = yaml.safe_load(f) or {}

    try:
        log_path = Path(raw.get("log_path", "logs/process.log"))
        output_path = Path(raw.get("output_path", "output/results.json"))
        model_local_path = Path(raw.get("model_local_path", "models/unixcoder-base"))
    except KeyError as e:
        raise KeyError(f"Missing required config key: {e.args[0]}") from e

    return AppConfig(
        log_path=log_path,
        output_path=output_path,
        model_local_path=model_local_path,
        similarity_threshold=float(raw.get("similarity_threshold", 0.8)),
        model_name=raw.get("model_name", "microsoft/unixcoder-base"),
        max_length=int(raw.get("max_length", 512)),
    )


def compare_functions(result_a: FileEmbeddingResult, result_b: FileEmbeddingResult, threshold: float = 0.8) -> list[tuple[CodeBlock, CodeBlock, float]]:
    funcs_a = [(block, emb) for block, emb in zip(result_a.blocks, result_a.block_embeddings) if block.is_function]
    funcs_b = [(block, emb) for block, emb in zip(result_b.blocks, result_b.block_embeddings) if block.is_function]

    similarities = []
    for (block_a, emb_a) in funcs_a:
        for (block_b, emb_b) in funcs_b:
            sim = cosine_similarity(emb_a.unsqueeze(0), emb_b.unsqueeze(0)).item()
            if sim >= threshold:
                similarities.append((block_a, block_b, sim))

    similarities.sort(key=lambda x: x[2], reverse=True)
    return similarities


def detect_clones(
    dir_path: str | Path,
    threshold: float = 0.8,
    model_name: str = "microsoft/unixcoder-base",
    model_local_path: str | Path | None = None,
    max_length: int = 512
) -> list[dict[str, Any]]:
    """
    Finds groups of similar JavaScript files in a directory and compares their functions.
    """
    path = Path(dir_path)
    if not path.is_dir():
        raise NotADirectoryError(f"Directory not found: {path}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info(f"Using device: {device}")
    
    # Logic to load from local or download
    if model_local_path and os.path.exists(model_local_path):
        logger.info(f"Loading UniXcoder from local path: {model_local_path}")
        model_path_to_load = str(model_local_path)
    else:
        logger.info(f"Loading UniXcoder from Hugging Face: {model_name}")
        model_path_to_load = model_name

    model = UniXcoder(model_path_to_load)
    
    # Save if it was loaded from Hugging Face
    if model_path_to_load == model_name and model_local_path:
        logger.info(f"Saving model to local path for future use: {model_local_path}")
        model.save_pretrained(str(model_local_path))

    model.to(device)
    model.eval()

    js_files = [f for f in path.rglob("*.js") if f.is_file()]
    if not js_files:
        logger.warning(f"No .js files found in {path}")
        return []

    logger.info(f"Found {len(js_files)} .js files. Computing embeddings...")
    results: list[FileEmbeddingResult] = []
    for f in tqdm(js_files, desc="Embedding files"):
        try:
            res = embed_file_blocks(f, model, max_length)
            results.append(res)
        except ValueError as e:
            logger.warning(f"Skipping {f}: {e}")
        except Exception as e:
            logger.error(f"Error processing {f}: {e}")

    similar_pairs = []
    logger.info(f"Comparing {len(results)} files for clones (threshold: {threshold})...")
    
    total_pairs = len(results) * (len(results) - 1) // 2
    for res_a, res_b in tqdm(itertools.combinations(results, 2), total=total_pairs, desc="Comparing files"):
        sim = cosine_similarity(res_a.file_embedding.unsqueeze(0), res_b.file_embedding.unsqueeze(0)).item()
        if sim >= threshold:
            func_sims = compare_functions(res_a, res_b, threshold)
            similar_pairs.append({
                "file_a": str(res_a.file_path),
                "file_b": str(res_b.file_path),
                "total_similarity": sim,
                "function_similarities": [
                    {
                        "func_a": f_a.content,
                        "name_a": f_a.name,
                        "func_b": f_b.content,
                        "name_b": f_b.name,
                        "similarity": f_sim
                    }
                    for f_a, f_b, f_sim in func_sims
                ]
            })

    # Sort pairs by total similarity descending
    similar_pairs.sort(key=lambda x: x["total_similarity"], reverse=True)
    logger.info(f"Found {len(similar_pairs)} similar pairs above threshold.")
    return similar_pairs


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

    similar_pairs = detect_clones(
        dir_path=dir_path,
        threshold=config.similarity_threshold,
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
                "model_name": config.model_name,
                "max_length": config.max_length
            },
            "results": similar_pairs
        }, f, indent=2, ensure_ascii=False)
    
    end_time = time.time()
    duration = end_time - start_time
    logger.info(f"Results saved to {config.output_path}")
    logger.info(f"Clone detection completed in {duration:.2f} seconds.")
    return similar_pairs


def main() -> None:
    parser = argparse.ArgumentParser(description="UniXcoder-based Code Clone Detector")
    parser.add_argument("dir_path", type=str, help="Path to the directory containing JavaScript files")
    parser.add_argument("--config", type=str, default="config.yaml", help="Path to config file")
    args = parser.parse_args()

    run_clone_detection(args.dir_path, args.config)


if __name__ == "__main__":
    main()
