from __future__ import annotations

import itertools
import json
import logging
import os
import pickle
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


def save_embeddings(
    results: list[FileEmbeddingResult],
    embedding_dir: Path,
    prefix: str = "embeddings",
) -> Path:
    """Save embeddings to directory with separate files for metadata and embeddings."""
    embedding_dir = Path(embedding_dir)
    embedding_dir.mkdir(parents=True, exist_ok=True)
    
    # Save metadata (file paths, blocks, etc.) as JSON
    metadata: list[dict[str, Any]] = []
    embeddings_list: list[dict[str, Any]] = []
    
    for result in results:
        # Metadata for this file
        file_metadata = {
            "file_path": str(result.file_path),
            "blocks": [
                {
                    "type": block.type,
                    "content": block.content,
                    "is_function": block.is_function,
                    "name": block.name,
                }
                for block in result.blocks
            ],
        }
        metadata.append(file_metadata)
        
        # Save embeddings as tensors
        embeddings_dict = {
            "file_path": str(result.file_path),
            "file_embedding": result.file_embedding.cpu().numpy().tolist(),
            "block_embeddings": [emb.cpu().numpy().tolist() for emb in result.block_embeddings],
        }
        embeddings_list.append(embeddings_dict)
    
    # Save metadata
    metadata_file = embedding_dir / f"{prefix}_metadata.json"
    with metadata_file.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    # Save embeddings as pickle (more efficient for numpy arrays)
    embeddings_file = embedding_dir / f"{prefix}_embeddings.pkl"
    with embeddings_file.open("wb") as f:
        pickle.dump(embeddings_list, f)
    
    logger.info(f"Embeddings saved to {embedding_dir} with prefix: {prefix}")
    return embedding_dir


def load_embeddings(
    embedding_dir: Path,
    prefix: str = "embeddings",
) -> list[FileEmbeddingResult]:
    """Load embeddings from directory."""
    embedding_dir = Path(embedding_dir)
    
    # Load metadata
    metadata_file = embedding_dir / f"{prefix}_metadata.json"
    with metadata_file.open("r", encoding="utf-8") as f:
        metadata = json.load(f)
    
    # Load embeddings
    embeddings_file = embedding_dir / f"{prefix}_embeddings.pkl"
    with embeddings_file.open("rb") as f:
        embeddings_list = pickle.load(f)
    
    # Reconstruct FileEmbeddingResult objects
    from src.tokenizer import CodeBlock
    
    results: list[FileEmbeddingResult] = []
    for meta, emb_data in zip(metadata, embeddings_list):
        file_path = Path(meta["file_path"])
        blocks = [
            CodeBlock(
                type=block["type"],
                content=block["content"],
                is_function=block["is_function"],
                name=block["name"],
            )
            for block in meta["blocks"]
        ]
        
        file_embedding = torch.tensor(emb_data["file_embedding"])
        block_embeddings = [torch.tensor(emb) for emb in emb_data["block_embeddings"]]
        
        result = FileEmbeddingResult(
            file_path=file_path,
            blocks=blocks,
            block_embeddings=block_embeddings,
            file_embedding=file_embedding,
        )
        results.append(result)
    
    logger.info(f"Loaded {len(results)} embeddings from {embedding_dir}")
    return results


def compare_embeddings(
    embedding_dir: Path,
    threshold: float = 0.8,
    dbscan_min_samples: int = 2,
) -> list[dict[str, Any]]:
    """Load embeddings from directory and perform clustering comparison."""
    embedding_dir = Path(embedding_dir)
    
    # Find all embedding files in directory
    embedding_files = sorted(embedding_dir.glob("*_embeddings.pkl"))
    
    if not embedding_files:
        logger.warning(f"No embedding files found in {embedding_dir}")
        return []
    
    logger.info(f"Found {len(embedding_files)} embedding files to compare")
    
    all_results: list[FileEmbeddingResult] = []
    
    # Load all embeddings
    for embedding_file in embedding_files:
        prefix = embedding_file.name.replace("_embeddings.pkl", "")
        try:
            results = load_embeddings(embedding_dir, prefix=prefix)
            all_results.extend(results)
        except Exception as e:
            logger.warning(f"Failed to load embeddings with prefix {prefix}: {e}")
    
    if not all_results:
        logger.warning("No valid embeddings loaded for comparison")
        return []
    
    logger.info(f"Loaded total {len(all_results)} files from embeddings")
    
    # Perform clustering on all loaded embeddings
    file_paths = [str(res.file_path) for res in all_results]
    
    eps = max(0.0, 1.0 - threshold)
    logger.info(
        "Clustering %s files using DBSCAN (metric=precomputed, eps=%.4f, min_samples=%s)...",
        len(all_results),
        eps,
        dbscan_min_samples,
    )
    
    pair_cache: dict[tuple[int, int], tuple[float, list[dict[str, Any]]]] = {}
    distance_matrix = np.zeros((len(all_results), len(all_results)), dtype=np.float32)
    
    for i in range(len(all_results)):
        for j in range(i + 1, len(all_results)):
            aggregate, matches = _aggregate_function_similarity(
                all_results[i],
                all_results[j],
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
    
    path_to_index = {str(res.file_path): idx for idx, res in enumerate(all_results)}
    
    clusters: list[dict[str, Any]] = []
    for label, files in sorted(cluster_map.items(), key=lambda item: item[0]):
        pair_function_analysis: list[dict[str, Any]] = []
        
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
    files_list: list[str | Path],
    threshold: float = 0.8,
    dbscan_min_samples: int = 2,
    model_name: str = "microsoft/unixcoder-base",
    model_local_path: str | Path | None = None,
    max_length: int = 768,
    save_embeddings_dir: Path | str | None = None,
    embedding_prefix: str = "embeddings",
) -> tuple[list[dict[str, Any]], list[FileEmbeddingResult]]:
    """
    Clusters JavaScript files by semantic similarity using DBSCAN.
    
    Returns:
        tuple of (clusters, results) where clusters is the clustering result
        and results is the list of FileEmbeddingResult objects.
    """
    js_files = [Path(f) for f in files_list if Path(f).is_file()]
    if not js_files:
        logger.warning("No valid files found in the provided list.")
        return [], []

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
        return [], []

    # Save embeddings if requested
    if save_embeddings_dir:
        save_embeddings(results, Path(save_embeddings_dir), prefix=embedding_prefix)

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
    return clusters, results
