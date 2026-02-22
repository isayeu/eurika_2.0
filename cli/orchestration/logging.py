"""Centralized logging helpers for orchestration/runtime paths."""

from __future__ import annotations

import logging
import os
import sys


def _resolve_level() -> int:
    raw = os.environ.get("EURIKA_LOG_LEVEL", "INFO").strip().upper()
    return getattr(logging, raw, logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Return configured logger writing plain messages to stderr."""
    logger = logging.getLogger(f"eurika.{name}")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.propagate = False
    logger.setLevel(_resolve_level())
    return logger

