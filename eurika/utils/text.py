"""Text/string utilities (L0)."""

import re

_ANSI_STRIP_RE = re.compile(
    r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|"
    r"\x1b[PX^_][^\x1b]*\x1b\\",
    re.DOTALL,
)


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences (e.g. from ollama CLI spinner)."""
    return _ANSI_STRIP_RE.sub("", text or "")


def contains_stripped(content: str, needle: str) -> bool:
    """True if needle (stripped) is non-empty and a substring of content."""
    s = needle.strip()
    return bool(s) and s in content
