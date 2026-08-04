"""DRILL_SPLIT: formatters — часть split_demo (CR-E3 Composer practice)."""


def format_upper(s: str) -> str:
    """Return upper case."""
    return s.upper()


def format_padded(n: int, width: int = 4) -> str:
    """Return zero-padded string."""
    return str(n).zfill(width)


def format_bracketed(s: str) -> str:
    """Return [s]."""
    return f"[{s}]"
