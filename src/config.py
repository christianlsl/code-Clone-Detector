"""Configuration management for clone detection."""

import yaml
from pathlib import Path
from typing import Dict, Any


class Config:
    """Load and manage configuration from YAML file."""

    def __init__(self, config_file: str = "config.yaml"):
        """
        Initialize configuration from YAML file.

        Args:
            config_file: Path to config.yaml file
        """
        self.config_file = Path(config_file)
        if not self.config_file.exists():
            raise FileNotFoundError(f"Config file not found: {config_file}")
        
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load YAML configuration file."""
        with open(self.config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config or {}
    
    @property
    def data_path(self) -> Path:
        """Get data path for JS files."""
        return Path(self.config.get('data_path', './testcases'))
    
    @property
    def output_path(self) -> Path:
        """Get output path for results."""
        return Path(self.config.get('output_path', './output'))
    
    @property
    def log_path(self) -> Path:
        """Get log path."""
        return Path(self.config.get('log_path', './logs'))
    
    def to_dict(self) -> Dict[str, Any]:
        """Return configuration as dictionary."""
        return self.config.copy()
