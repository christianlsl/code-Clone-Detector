from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from transformers import AutoModel, AutoTokenizer

from src.calculate import compute_js_file_similarity


@dataclass
class AppConfig:
    file_a: Path
    file_b: Path
    model_name: str = "microsoft/codebert-base"
    max_length: int = 512


def load_config(config_path: Path) -> AppConfig:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf8") as f:
        raw = yaml.safe_load(f) or {}

    try:
        file_a = Path(raw["file_a"])
        file_b = Path(raw["file_b"])
    except KeyError as e:
        raise KeyError(f"Missing required config key: {e.args[0]}") from e

    return AppConfig(
        file_a=file_a,
        file_b=file_b,
        model_name=raw.get("model_name", "microsoft/codebert-base"),
        max_length=int(raw.get("max_length", 512)),
    )


def main() -> None:
    config = load_config(Path("config.yaml"))

    for file_path in (config.file_a, config.file_b):
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

    tokenizer = AutoTokenizer.from_pretrained(config.model_name)
    model = AutoModel.from_pretrained(config.model_name)
    model.eval()

    similarity, result_a, result_b = compute_js_file_similarity(
        config.file_a,
        config.file_b,
        tokenizer,
        model,
        config.max_length,
    )

    print(f"File A: {result_a.file_path}")
    print(f"  blocks embedded: {len(result_a.blocks)}")
    print(f"  embedding vectors: {len(result_a.block_embeddings)}")
    print(f"File B: {result_b.file_path}")
    print(f"  blocks embedded: {len(result_b.blocks)}")
    print(f"  embedding vectors: {len(result_b.block_embeddings)}")
    print(f"Cosine similarity: {similarity:.6f}")


if __name__ == "__main__":
    main()
