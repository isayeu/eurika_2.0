"""DRILL_SPLIT: исходный монолит для CR-E3 Composer practice.

До split: один файл ~80 LOC с двумя зонами ответственности.
После: split_demo_validators.py + split_demo_formatters.py.
См. docs/CYCLE_REPORT.md §98.
"""
from eurika.polygon.split_demo_validators import (
    validate_non_empty,
    validate_positive,
    validate_range,
)
from eurika.polygon.split_demo_formatters import (
    format_bracketed,
    format_padded,
    format_upper,
)


def polygon_split_demo(s: str, x: int, n: int) -> str:
    """Объединяет validators + formatters — drill для проверки split."""
    if not validate_non_empty(s):
        return ""
    if not validate_range(x, 0, 100):
        return ""
    if not validate_positive(n):
        return ""
    upper = format_upper(s)
    padded = format_padded(n)
    return format_bracketed(f"{upper}:{padded}")
