from __future__ import annotations

import itertools
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np
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
    top_k: int = 5,
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

    if not funcs_a or not funcs_b:
        return []

    candidates: list[tuple[float, int, int]] = []
    for i, (block_a, emb_a) in enumerate(funcs_a):
        for j, (block_b, emb_b) in enumerate(funcs_b):
            sim = cosine_similarity(emb_a.unsqueeze(0), emb_b.unsqueeze(0)).item()
            candidates.append((sim, i, j))

    candidates.sort(key=lambda x: x[0], reverse=True)

    used_a: set[int] = set()
    used_b: set[int] = set()
    matches: list[dict[str, Any]] = []

    for sim, i, j in candidates:
        if i in used_a or j in used_b:
            continue
        used_a.add(i)
        used_b.add(j)

        block_a = funcs_a[i][0]
        block_b = funcs_b[j][0]
        matches.append(
            {
                "func_a": block_a.content,
                "name_a": block_a.name,
                "func_b": block_b.content,
                "name_b": block_b.name,
                "similarity": sim,
                "above_threshold": sim >= threshold,
            }
        )
        if len(matches) >= top_k:
            break

    return matches


def _aggregate_function_similarity(
    result_a: FileEmbeddingResult,
    result_b: FileEmbeddingResult,
    threshold: float,
    top_k: int = 5,
) -> tuple[float, list[dict[str, Any]]]:
    matches = _compare_functions(result_a, result_b, threshold, top_k=top_k)
    if matches:
        aggregate = float(np.mean([match["similarity"] for match in matches]))
        return aggregate, matches

    # Fallback for files with no extractable functions; keep this low-weighted
    # so boilerplate imports/requires do not dominate clustering.
    file_level = cosine_similarity(
        result_a.file_embedding.unsqueeze(0),
        result_b.file_embedding.unsqueeze(0),
    ).item()
    return max(0.0, min(1.0, 0.35 * file_level)), []


def detect_clones(
    dir_path: str | Path,
    threshold: float = 0.8,
    dbscan_min_samples: int = 2,
    model_name: str = "microsoft/unixcoder-base",
    model_local_path: str | Path | None = None,
    max_length: int = 768,
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

    safe_max_length = min(max(8, int(max_length)), 1023)
    if safe_max_length != max_length:
        logger.warning("Adjusted max_length from %s to %s to fit model constraints.", max_length, safe_max_length)

    logger.info("Found %s .js files. Computing embeddings...", len(js_files))
    results: list[FileEmbeddingResult] = []
    for file_path in tqdm(js_files, desc="Embedding files"):
        try:
            res = embed_file_blocks(file_path, model, safe_max_length)
            results.append(res)
        except ValueError as e:
            logger.warning("Skipping %s: %s", file_path, e)
        except Exception as e:
            logger.error("Error processing %s: %s", file_path, e)

    if not results:
        logger.warning("No valid files were embedded. Clustering skipped.")
        return []

    file_paths = [str(res.file_path) for res in results]

    eps = max(0.0, 1.0 - threshold)
    logger.info(
        "Clustering %s files using DBSCAN (metric=precomputed, eps=%.4f, min_samples=%s)...",
        len(results),
        eps,
        dbscan_min_samples,
    )

    pair_cache: dict[tuple[int, int], tuple[float, list[dict[str, Any]]]] = {}
    distance_matrix = np.zeros((len(results), len(results)), dtype=np.float32)
    for i in range(len(results)):
        for j in range(i + 1, len(results)):
            aggregate, matches = _aggregate_function_similarity(
                results[i],
                results[j],
                threshold=threshold,
                top_k=5,
            )
            pair_cache[(i, j)] = (aggregate, matches)
            distance = max(0.0, min(1.0, 1.0 - aggregate))
            distance_matrix[i, j] = distance
            distance_matrix[j, i] = distance

    dbscan = DBSCAN(eps=eps, min_samples=dbscan_min_samples, metric="precomputed")
    labels = dbscan.fit_predict(distance_matrix)

    cluster_map: dict[int, list[str]] = {}
    for file_path, label in zip(file_paths, labels):
        label_int = int(label)
        cluster_map.setdefault(label_int, []).append(file_path)

    path_to_index = {str(res.file_path): idx for idx, res in enumerate(results)}

    clusters: list[dict[str, Any]] = []
    for label, files in sorted(cluster_map.items(), key=lambda item: item[0]):
        pair_function_analysis: list[dict[str, Any]] = []

        # Analyze function similarity only inside non-noise clusters with at least 2 files.
        if label != -1 and len(files) >= 2:
            for file_a, file_b in itertools.combinations(files, 2):
                idx_a = path_to_index[file_a]
                idx_b = path_to_index[file_b]
                cache_key = (idx_a, idx_b) if idx_a < idx_b else (idx_b, idx_a)
                file_similarity, func_similarities = pair_cache[cache_key]
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
