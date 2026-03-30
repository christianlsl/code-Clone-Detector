from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterator

import torch
from tree_sitter import Language, Parser
import tree_sitter_javascript as tsjs

from src.unixcoder import UniXcoder


@dataclass
class CodeBlock:
    type: str
    content: str
    is_function: bool
    name: str | None = None


@dataclass
class FileEmbeddingResult:
    file_path: Path
    blocks: list[CodeBlock]
    block_embeddings: list[torch.Tensor]
    file_embedding: torch.Tensor


@lru_cache(maxsize=1)
def _get_js_parser() -> Parser:
    js_language = Language(tsjs.language())
    return Parser(js_language)


FUNCTION_NODE_TYPES = {
    "function_declaration",
    "function_expression",
    "arrow_function",
    "method_definition",
    "generator_function_declaration",
}


def _iter_nodes(node) -> Iterator:
    yield node
    for child in node.children:
        yield from _iter_nodes(child)


def _decode_node_text(encoded_code: bytes, node) -> str:
    return encoded_code[node.start_byte:node.end_byte].decode("utf8")


def _is_require_declaration(node, encoded_code: bytes) -> bool:
    if node.type not in {"variable_declaration", "lexical_declaration"}:
        return False
    return "require(" in _decode_node_text(encoded_code, node)


def _extract_function_name(node, encoded_code: bytes) -> str | None:
    name_node = node.child_by_field_name("name")
    if name_node:
        return _decode_node_text(encoded_code, name_node)

    parent = node.parent
    if not parent:
        return None

    # Object property functions, e.g. key: function() {} or key: () => {}
    if parent.type == "pair":
        key_node = parent.child_by_field_name("key")
        if key_node:
            return _decode_node_text(encoded_code, key_node)

    # Variable assignments, e.g. const foo = () => {}
    if parent.type == "variable_declarator":
        var_name_node = parent.child_by_field_name("name")
        if var_name_node:
            return _decode_node_text(encoded_code, var_name_node)

    # Assignment expressions, e.g. foo.bar = function() {}
    if parent.type == "assignment_expression":
        left_node = parent.child_by_field_name("left")
        if left_node:
            return _decode_node_text(encoded_code, left_node)

    return None


def _block_weight(block: CodeBlock) -> float:
    if block.is_function:
        return 1.0
    if block.type == "import_statement":
        return 0.2
    if block.type in {"variable_declaration", "lexical_declaration"} and "require(" in block.content:
        return 0.25
    return 0.6


def split_js_into_blocks(js_code: str) -> list[CodeBlock]:
    """Split JavaScript source code into weighted semantic blocks.

    Function-like nodes are collected recursively so that object-property
    functions and nested function expressions are not missed.
    """
    parser = _get_js_parser()
    encoded_code = js_code.encode("utf8")
    tree = parser.parse(encoded_code)

    blocks: list[CodeBlock] = []

    # Keep lightweight context blocks for imports/requires and down-weight later.
    for child in tree.root_node.children:
        if child.type == "import_statement" or _is_require_declaration(child, encoded_code):
            blocks.append(
                CodeBlock(
                    type=child.type,
                    content=_decode_node_text(encoded_code, child),
                    is_function=False,
                    name=None,
                )
            )

    # Recursively extract functions from the entire syntax tree.
    for node in _iter_nodes(tree.root_node):
        if node.type not in FUNCTION_NODE_TYPES:
            continue
        content = _decode_node_text(encoded_code, node)
        if not content.strip():
            continue
        blocks.append(
            CodeBlock(
                type=node.type,
                content=content,
                is_function=True,
                name=_extract_function_name(node, encoded_code),
            )
        )

    if not blocks:
        blocks.append(
            CodeBlock(
                type="program",
                content=js_code,
                is_function=False,
                name=None,
            )
        )

    return blocks


def split_js_file_into_blocks(file_path: str | Path) -> list[CodeBlock]:
    """Read a JavaScript file and split it into top-level syntax blocks."""
    path = Path(file_path)
    js_code = path.read_text(encoding="utf8")
    return split_js_into_blocks(js_code)


def get_block_embedding(
    block_text: str,
    model: UniXcoder,
    max_length: int,
) -> torch.Tensor:
    """Get embedding for a block, chunking long inputs then mean-pooling."""
    device = next(model.parameters()).device
    token_budget = max(32, max_length - 4)
    tokens = model.tokenizer.tokenize(block_text)

    if len(tokens) <= token_budget:
        texts = [block_text]
    else:
        token_chunks = [
            tokens[i:i + token_budget]
            for i in range(0, len(tokens), token_budget)
        ]
        texts = [model.tokenizer.convert_tokens_to_string(chunk) for chunk in token_chunks]

    tokens_ids = model.tokenize(texts, max_length=max_length, mode="<encoder-only>")
    source_ids = torch.tensor(tokens_ids).to(device)

    with torch.no_grad():
        _, embedding = model(source_ids)
        embedding = embedding.mean(dim=0)

    return embedding


def embed_file_blocks(
    file_path: str | Path,
    model: UniXcoder,
    max_length: int = 512,
) -> FileEmbeddingResult:
    """Split a file into blocks and get embeddings for each block."""
    path = Path(file_path)
    blocks = split_js_file_into_blocks(path)

    valid_blocks: list[CodeBlock] = []
    block_embeddings: list[torch.Tensor] = []

    for block in blocks:
        if not block.content.strip():
            continue
        block_embedding = get_block_embedding(block.content, model, max_length)
        valid_blocks.append(block)
        block_embeddings.append(block_embedding)

    if not block_embeddings:
        raise ValueError(f"No non-empty blocks found in file: {path}")

    weights = torch.tensor([_block_weight(block) for block in valid_blocks], device=block_embeddings[0].device)
    normalized_weights = weights / weights.sum()
    file_embedding = (torch.stack(block_embeddings) * normalized_weights.unsqueeze(1)).sum(dim=0)

    return FileEmbeddingResult(
        file_path=path,
        blocks=valid_blocks,
        block_embeddings=block_embeddings,
        file_embedding=file_embedding,
    )
