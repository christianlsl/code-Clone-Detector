from __future__ import annotations

from pathlib import Path

import torch
from torch.nn.functional import cosine_similarity

from src.tokenizer import FileEmbeddingResult, embed_file_blocks
from src.unixcoder import UniXcoder


def compute_js_file_similarity(
    file_a: str | Path,
    file_b: str | Path,
    model: UniXcoder,
    max_length: int = 512,
) -> tuple[float, FileEmbeddingResult, FileEmbeddingResult]:
    """Compute cosine similarity between two JavaScript files using UniXcoder embeddings."""
    result_a = embed_file_blocks(file_a, model, max_length)
    result_b = embed_file_blocks(file_b, model, max_length)

    similarity = cosine_similarity(
        result_a.file_embedding.unsqueeze(0),
        result_b.file_embedding.unsqueeze(0),
    ).item()

    return similarity, result_a, result_b
