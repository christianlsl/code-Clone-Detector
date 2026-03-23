from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

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


def split_js_into_blocks(js_code: str) -> list[CodeBlock]:
    """Split JavaScript source code into top-level syntax blocks."""
    parser = _get_js_parser()
    encoded_code = js_code.encode("utf8")
    tree = parser.parse(encoded_code)

    blocks: list[CodeBlock] = []
    last_pos = 0

    for child in tree.root_node.children:
        start_byte = last_pos
        end_byte = child.end_byte
        content = encoded_code[start_byte:end_byte].decode("utf8")

        # Try to extract a name for the block
        name = None
        if child.type in {"function_declaration", "method_definition", "class_declaration"}:
            name_node = child.child_by_field_name("name")
            if name_node:
                name = encoded_code[name_node.start_byte:name_node.end_byte].decode("utf8")
        elif child.type in {"variable_declaration", "lexical_declaration"}:
            # Simplified: look for variable_declarator and get its name
            for sub_child in child.children:
                if sub_child.type == "variable_declarator":
                    name_node = sub_child.child_by_field_name("name")
                    if name_node:
                        name = encoded_code[name_node.start_byte:name_node.end_byte].decode("utf8")
                        break

        blocks.append(
            CodeBlock(
                type=child.type,
                content=content,
                is_function=child.type
                in {"function_declaration", "method_definition", "arrow_function"},
                name=name,
            )
        )
        last_pos = end_byte

    if last_pos < len(encoded_code):
        blocks.append(
            CodeBlock(
                type="trailing",
                content=encoded_code[last_pos:].decode("utf8"),
                is_function=False,
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
    """Get embedding for a single code block using UniXcoder."""
    device = next(model.parameters()).device
    tokens_ids = model.tokenize([block_text], max_length=max_length, mode="<encoder-only>")
    source_ids = torch.tensor(tokens_ids).to(device)

    with torch.no_grad():
        _, embedding = model(source_ids)
        # embedding is the sentence representation from UniXcoder.
        embedding = embedding.squeeze(0)

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

    file_embedding = torch.stack(block_embeddings).mean(dim=0)

    return FileEmbeddingResult(
        file_path=path,
        blocks=valid_blocks,
        block_embeddings=block_embeddings,
        file_embedding=file_embedding,
    )
