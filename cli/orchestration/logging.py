"""Centralized logging helpers for orchestration/runtime paths (R2)."""

from __future__ import annotations

import logging
import os
import sys

_configured = False


def _resolve_level() -> int:
    raw = os.environ.get("EURIKA_LOG_LEVEL", "").strip().upper()
    if raw:
        return getattr(logging, raw, logging.INFO)
    return logging.INFO


def configure_cli_logging(*, quiet: bool = False, verbose: bool = False) -> None:
    """Set eurika.* logger levels from CLI flags. R2: --quiet/--verbose override env."""
    global _configured
    env_level = _resolve_level()
    if verbose:
        level = logging.DEBUG
    elif quiet:
        level = logging.WARNING
    else:
        level = env_level
    root = logging.getLogger("eurika")
    root.setLevel(level)
    if not root.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(h)
        root.propagate = False
    for child in ("orchestration", "reasoning", "api"):
        logging.getLogger(f"eurika.{child}").setLevel(level)
    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return configured logger writing plain messages to stderr."""
    logger = logging.getLogger(f"eurika.{name}")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.propagate = False
    if not _configured:
        logger.setLevel(_resolve_level())
    return logger

