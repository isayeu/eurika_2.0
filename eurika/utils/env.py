"""Environment variable utilities (L0)."""

from __future__ import annotations

import os


def env_bool(name: str, default: bool = False) -> bool:
    """Parse env var as boolean; \"1\", \"true\", \"yes\" (case-insensitive) -> True."""
    fallback = "1" if default else "0"
    val = os.environ.get(name, fallback).strip().lower()
    return val in ("1", "true", "yes")
