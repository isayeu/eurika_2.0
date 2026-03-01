"""DRILL_EXTRACTABLE_BLOCK: extract_block_to_helper — блок if с 5+ строками без return."""


def polygon_extractable_block(x: int) -> int:
    """Внутренний блок if (5+ строк) без return — подходит для suggest_extract_block.

    Нужно depth > 4 (5+ вложенных if) чтобы CodeAwareness пометил deep_nesting.
    """
    result = 0
    if x > 0:
        if x < 10:
            if x > 1:
                if x < 9:
                    if True:
                        a = x + 1
                        b = a * 2
                        c = b + x
                        d = c * 2
                        result = d
    return result