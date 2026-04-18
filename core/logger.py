"""
English-only structured logging for the open-source backend.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    name: str = "dataevolver",
) -> logging.Logger:
    """Configure root logger for the API process; idempotent for repeated calls."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_path, encoding="utf-8")
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(formatter)
    logger.addHandler(sh)
    return logger


class LoggerService:
    """Thin wrapper around a named logger (compatible with future subsystem use)."""

    def __init__(self, log_level: str = "INFO", log_file: Optional[str] = None) -> None:
        self._logger = setup_logging(level=log_level, log_file=log_file)

    def get_logger(self, name: str = "dataevolver") -> logging.Logger:
        return logging.getLogger(name)
