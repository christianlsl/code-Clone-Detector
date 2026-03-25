from __future__ import annotations

import itertools
import logging
import os
from pathlib import Path
from typing import Any

import torch
from sklearn.cluster import DBSCAN
from torch.nn.functional import cosine_similarity
from tqdm import tqdm

from src.tokenizer import FileEmbeddingResult, embed_file_blocks
from src.unixcoder import UniXcoder

logger = logging.getLogger(__name__)


def _compare_functions(
    result_a: FileEmbeddingResult,
    result_b: FileEmbeddingResult,
    threshold: float,
) -> list[dict[str, Any]]:
    funcs_a = [
        (block, emb)
        for block, emb in zip(result_a.blocks, result_a.block_embeddings)
        if block.is_function
    ]
    funcs_b = [
        (block, emb)
        for block, emb in zip(result_b.blocks, result_b.block_embeddings)
        if block.is_function
    ]

    similarities: list[dict[str, Any]] = []
    for block_a, emb_a in funcs_a:
        for block_b, emb_b in funcs_b:
            sim = cosine_similarity(emb_a.unsqueeze(0), emb_b.unsqueeze(0)).item()
            if sim >= threshold:
                similarities.append(
                    {
                        "func_a": block_a.content,
                        "name_a": block_a.name,
                        "func_b": block_b.content,
                        "name_b": block_b.name,
                        "similarity": sim,
                    }
                )

    similarities.sort(key=lambda x: x["similarity"], reverse=True)
    return similarities


def detect_clones(
    dir_path: str | Path,
    threshold: float = 0.8,
    dbscan_min_samples: int = 2,
    model_name: str = "microsoft/unixcoder-base",
    model_local_path: str | Path | None = None,
    max_length: int = 512,
) -> list[dict[str, Any]]:
    """Clusters JavaScript files by semantic similarity using DBSCAN."""
    path = Path(dir_path)
    if not path.is_dir():
        raise NotADirectoryError(f"Directory not found: {path}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    logger.info("Using device: %s", device)

    if model_local_path and os.path.exists(model_local_path):
        logger.info("Loading UniXcoder from local path: %s", model_local_path)
        model_path_to_load = str(model_local_path)
    else:
        logger.info("Loading UniXcoder from Hugging Face: %s", model_name)
        model_path_to_load = model_name

    model = UniXcoder(model_path_to_load)

    if model_path_to_load == model_name and model_local_path:
        logger.info("Saving model to local path for future use: %s", model_local_path)
        model.save_pretrained(str(model_local_path))

    model.to(device)
    model.eval()

    js_files = [f for f in path.rglob("*.js") if f.is_file()]
    if not js_files:
        logger.warning("No .js files found in %s", path)
        return []

    logger.info("Found %s .js files. Computing embeddings...", len(js_files))
    results: list[FileEmbeddingResult] = []
    for file_path in tqdm(js_files, desc="Embedding files"):
        try:
            res = embed_file_blocks(file_path, model, max_length)
            results.append(res)
        except ValueError as e:
            logger.warning("Skipping %s: %s", file_path, e)
        except Exception as e:
            logger.error("Error processing %s: %s", file_path, e)

    if not results:
        logger.warning("No valid files were embedded. Clustering skipped.")
        return []

    file_paths = [str(res.file_path) for res in results]
    embedding_matrix = torch.stack([res.file_embedding for res in results]).detach().cpu().numpy()

    eps = max(0.0, 1.0 - threshold)
    logger.info(
        "Clustering %s files using DBSCAN (metric=cosine, eps=%.4f, min_samples=%s)...",
        len(results),
        eps,
        dbscan_min_samples,
    )

    dbscan = DBSCAN(eps=eps, min_samples=dbscan_min_samples, metric="cosine")
    labels = dbscan.fit_predict(embedding_matrix)

    cluster_map: dict[int, list[str]] = {}
    for file_path, label in zip(file_paths, labels):
        label_int = int(label)
        cluster_map.setdefault(label_int, []).append(file_path)

    result_by_path = {str(res.file_path): res for res in results}

    clusters: list[dict[str, Any]] = []
    for label, files in sorted(cluster_map.items(), key=lambda item: item[0]):
        pair_function_analysis: list[dict[str, Any]] = []

        # Analyze function similarity only inside non-noise clusters with at least 2 files.
        if label != -1 and len(files) >= 2:
            for file_a, file_b in itertools.combinations(files, 2):
                result_a = result_by_path[file_a]
                result_b = result_by_path[file_b]
                file_similarity = cosine_similarity(
                    result_a.file_embedding.unsqueeze(0),
                    result_b.file_embedding.unsqueeze(0),
                ).item()
                func_similarities = _compare_functions(result_a, result_b, threshold)
                pair_function_analysis.append(
                    {
                        "file_a": file_a,
                        "file_b": file_b,
                        "total_similarity": file_similarity,
                        "function_similarities": func_similarities,
                    }
                )

            pair_function_analysis.sort(
                key=lambda x: x["total_similarity"],
                reverse=True,
            )

        clusters.append(
            {
                "cluster_id": label,
                "cluster_type": "noise" if label == -1 else "cluster",
                "size": len(files),
                "files": files,
                "pair_function_analysis": pair_function_analysis,
            }
        )

    normal_cluster_count = sum(1 for c in clusters if c["cluster_id"] != -1)
    noise_count = next((c["size"] for c in clusters if c["cluster_id"] == -1), 0)
    logger.info(
        "DBSCAN finished. Found %s clusters and %s noise files.",
        normal_cluster_count,
        noise_count,
    )
    return clusters
