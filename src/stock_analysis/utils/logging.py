# src/stock_analysis/utils/logging.py
"""Logging configuration module.

Provides unified logging configuration functionality.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# This module is already being used elsewhere
try:
    from .paths import OUTPUTS_DIR
except Exception:
    # Fallback, don't crash again due to path module issues
    OUTPUTS_DIR = Path.cwd() / "outputs"

__all__ = ["setup_logging", "get_logger", "StrategyLogger"]

_DEFAULT_FMT = "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
_DEFAULT_DATEFMT = "%Y-%m-%d %H:%M:%S"


def _ensure_outputs_dir() -> Path:
    try:
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        # Worst case fallback to current directory
        return Path.cwd()
    return OUTPUTS_DIR


def setup_logging(
    name: str, filename: str | None = None, level: int = logging.INFO
) -> logging.Logger:
    """Set up logging configuration.

    Args:
        name: Logger name
        filename: Optional log file name
        level: Log level, defaults to logging.INFO

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Use directly if already configured, avoid duplicate handlers
    if getattr(logger, "_configured", False):
        return logger

    formatter = logging.Formatter(_DEFAULT_FMT, datefmt=_DEFAULT_DATEFMT)

    # Create console handler
    sh = logging.StreamHandler(stream=sys.stdout)
    sh.setLevel(level)
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    # Create file handler
    if filename:
        out_dir = _ensure_outputs_dir()
        fh_path = out_dir / filename
        fh = logging.FileHandler(fh_path, encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    logger._configured = True  # type: ignore[attr-defined]
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get logger for backward compatibility.

    Only configures console output if no filename provided.
    For file output, call setup_logging(name, 'xxx.log') first.

    Args:
        name: Logger name

    Returns:
        Logger instance
    """
    return setup_logging(name, filename=None)


class StrategyLogger:
    """
    Small wrapper for backtest strategies: can use logging or fallback to print.
    """

    def __init__(
        self,
        use_logging: bool = True,
        logger_name: str = "strategy",
        level: int | None = None,
    ):
        self.use_logging = use_logging
        if use_logging:
            # Ensure at least console output; let upper layer decide file output
            self.logger = setup_logging(
                logger_name, level=level if level is not None else logging.INFO
            )
        else:
            self.logger = None

    def log(self, txt: str, dt=None) -> None:
        if self.use_logging and self.logger:
            if dt is not None:
                self.logger.info(f"{dt} - {txt}")
            else:
                self.logger.info(txt)
        else:
            prefix = f"{dt} - " if dt is not None else ""
            print(prefix + txt)
