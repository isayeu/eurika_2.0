"""DRILL_EXTRACTABLE_BLOCK: extract_block_to_helper — блок if с 5+ строками без return."""

def _extracted_block_14(x):
    a = x + 1
    b = a * 2
    c = b + x
    d = c * 2
    return d

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
                        result = _extracted_block_14(x)
    return result