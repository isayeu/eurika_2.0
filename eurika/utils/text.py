"""Text/string utilities (L0)."""


def contains_stripped(content: str, needle: str) -> bool:
    """True if needle (stripped) is non-empty and a substring of content."""
    s = needle.strip()
    return bool(s) and s in content
