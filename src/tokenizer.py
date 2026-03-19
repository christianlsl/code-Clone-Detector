from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from tree_sitter import Language, Parser
import tree_sitter_javascript as tsjs


@dataclass
class CodeBlock:
    type: str
    content: str
    is_function: bool


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

        blocks.append(
            CodeBlock(
                type=child.type,
                content=content,
                is_function=child.type
                in {"function_declaration", "method_definition", "arrow_function"},
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
