from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import torch
from torch.nn.functional import cosine_similarity
from transformers import PreTrainedModel, PreTrainedTokenizerBase

from src.tokenizer import CodeBlock, split_js_file_into_blocks


@dataclass
class FileEmbeddingResult:
    file_path: Path
    blocks: list[CodeBlock]
    block_embeddings: list[torch.Tensor]
    file_embedding: torch.Tensor


def get_block_embedding(
    block_text: str,
    tokenizer: PreTrainedTokenizerBase,
    model: PreTrainedModel,
    max_length: int,
) -> torch.Tensor:
    encoded = tokenizer(
        block_text,
        return_tensors="pt",
        truncation=True,
        max_length=max_length,
    )

    with torch.no_grad():
        outputs = model(**encoded)
        # Use [CLS] representation as the block embedding.
        embedding = outputs.last_hidden_state[:, 0, :].squeeze(0)

    return embedding


def embed_file_blocks(
    file_path: str | Path,
    tokenizer: PreTrainedTokenizerBase,
    model: PreTrainedModel,
    max_length: int = 512,
) -> FileEmbeddingResult:
    path = Path(file_path)
    blocks = split_js_file_into_blocks(path)

    valid_blocks: list[CodeBlock] = []
    block_embeddings: list[torch.Tensor] = []

    for block in blocks:
        if not block.content.strip():
            continue
        block_embedding = get_block_embedding(block.content, tokenizer, model, max_length)
        valid_blocks.append(block)
        block_embeddings.append(block_embedding)

    if not block_embeddings:
        raise ValueError(f"No non-empty blocks found in file: {path}")

    file_embedding = torch.stack(block_embeddings).mean(dim=0)

    return FileEmbeddingResult(
        file_path=path,
        blocks=valid_blocks,
        block_embeddings=block_embeddings,
        file_embedding=file_embedding,
    )


def compute_js_file_similarity(
    file_a: str | Path,
    file_b: str | Path,
    tokenizer: PreTrainedTokenizerBase,
    model: PreTrainedModel,
    max_length: int = 512,
) -> tuple[float, FileEmbeddingResult, FileEmbeddingResult]:
    result_a = embed_file_blocks(file_a, tokenizer, model, max_length)
    result_b = embed_file_blocks(file_b, tokenizer, model, max_length)

    similarity = cosine_similarity(
        result_a.file_embedding.unsqueeze(0),
        result_b.file_embedding.unsqueeze(0),
    ).item()

    return similarity, result_a, result_b
