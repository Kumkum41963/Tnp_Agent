"""
Loguru configuration for structured, human-readable logging.
All log output goes to stderr; a run-scoped context binder is provided.
"""
from __future__ import annotations

import sys
from typing import Any

from loguru import logger


def configure_logging(log_level: str = "INFO") -> None:
    """Configure Loguru sinks. Call once at application startup."""
    logger.remove()  # Remove default handler
    logger.add(
        sys.stderr,
        level=log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
            "{message}"
        ),
        backtrace=True,
        diagnose=True,
        colorize=True,
    )


def get_run_logger(run_id: str) -> Any:
    """
    Return a logger bound with the run_id context field.
    Use this inside pipeline nodes so every log line carries the run ID.
    """
    return logger.bind(run_id=run_id)
