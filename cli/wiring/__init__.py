"""CLI wiring helpers for parser and dispatch setup."""

from .dispatch import dispatch_command
from .parser import build_parser

__all__ = ["build_parser", "dispatch_command"]
