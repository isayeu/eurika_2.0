"""DRILL_DEEP_NESTING: вложенные if с return в каждой ветке.

- polygon_deep_nesting: return в каждой ветке — suggest_extract_block пропускает.
- polygon_deep_nesting_extractable: внутренний блок 5+ строк без return — extractable.
"""


def polygon_deep_nesting(x: int) -> str:
    """Вложенные if с return в каждой ветке."""
    if x > 0:
        if x > 1:
            if x > 2:
                if x > 3:
                    return "deep"
                return "mid"
            return "shallow"
        return "tiny"
    return "zero"


def polygon_deep_nesting_extractable(x: int) -> int:
    """Вложенные if с extractable блоком (5+ строк, без return)."""
    result = 0
    if x > 0:
        if x > 1:
            if x > 2:
                if x > 3:
                    if x > 4:
                        a = x + 1
                        b = a * 2
                        c = b + x
                        d = c * 2
                        result = d
    return result
