"""DRILL_SPLIT: validators — часть split_demo (CR-E3 Composer practice)."""


def validate_non_empty(s: str) -> bool:
    """Check string is non-empty."""
    return bool(s and s.strip())


def validate_range(x: int, lo: int, hi: int) -> bool:
    """Check x in [lo, hi]."""
    return lo <= x <= hi


def validate_positive(n: int) -> bool:
    """Check n > 0."""
    return n > 0
