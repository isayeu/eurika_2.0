"""Eurika training polygon — intentional issues for learning cycles.

Сводный полигон для накопления verify_success: сюда вкладываются
разные ошибки и ситуации для eurika fix . --no-code-smells --allow-low-risk-campaign.

Секции (drills):
  - DRILL_UNUSED_IMPORTS: remove_unused_import
  - DRILL_LONG_FUNCTION: long_function (extract_block_to_helper, 0% пока)
  - DRILL_DEEP_NESTING: deep_nesting (extract_block_to_helper, ~13%)
"""
from pathlib import Path
def polygon_imports_ok() -> Path:
    """После fix: остаётся только Path."""
    return Path('.')

def polygon_long_function() -> int:
    """Намеренно длинная функция для будущих циклов extract_block_to_helper."""
    a = 1
    b = 2
    c = 3
    d = 4
    e = 5
    f = 6
    g = 7
    h = 8
    i = 9
    j = 10
    return a + b + c + d + e + f + g + h + i + j

def polygon_deep_nesting(x: int) -> str:
    """Глубокая вложенность для extract_block_to_helper."""
    if x > 0:
        if x > 1:
            if x > 2:
                if x > 3:
                    return 'deep'
                return 'mid'
            return 'shallow'
        return 'tiny'
    return 'zero'