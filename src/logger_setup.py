"""Logger setup and configuration."""

import logging
from pathlib import Path
from typing import Optional


def setup_logger(
    name: str,
    log_path: Optional[Path] = None,
    level: int = logging.INFO
) -> logging.Logger:
    """
    Setup logger with file and console handlers.

    Args:
        name: Logger name
        log_path: Path to log directory
        level: Logging level

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # File handler
    if log_path:
        log_path = Path(log_path)
        log_path.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_path / f'{name}.log')
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger
