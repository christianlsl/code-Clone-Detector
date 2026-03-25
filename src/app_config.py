from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class AppConfig:
    log_path: Path
    output_path: Path
    model_local_path: Path
    similarity_threshold: float = 0.8
    dbscan_min_samples: int = 2
    model_name: str = "microsoft/unixcoder-base"
    max_length: int = 512


def load_config(config_path: Path) -> AppConfig:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf8") as f:
        raw = yaml.safe_load(f) or {}

    log_path = Path(raw.get("log_path", "logs/process.log"))
    output_path = Path(raw.get("output_path", "output/results.json"))
    model_local_path = Path(raw.get("model_local_path", "models/unixcoder-base"))

    return AppConfig(
        log_path=log_path,
        output_path=output_path,
        model_local_path=model_local_path,
        similarity_threshold=float(raw.get("similarity_threshold", 0.8)),
        dbscan_min_samples=int(raw.get("dbscan_min_samples", 2)),
        model_name=raw.get("model_name", "microsoft/unixcoder-base"),
        max_length=int(raw.get("max_length", 512)),
    )
