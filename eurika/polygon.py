"""Eurika training polygon — intentional issues for KPI learning cycles.

Сводный полигон для накопления verify_success. Запуск:
  eurika fix . --no-code-smells --allow-low-risk-campaign   (только remove_unused_import)
  eurika fix . --allow-low-risk-campaign                    (включая extract_block_to_helper по whitelist)

Для теста Approvals diff view (3.6.7): eurika fix . --team-mode --no-code-smells
  → Load plan в Qt → выбрать строку eurika/polygon.py → diff preview.

Секции (drills):
  - DRILL_UNUSED_IMPORTS: remove_unused_import — добавить неиспользуемые импорты, fix удалит
  - DRILL_EXTRACTABLE_BLOCK: extract_block_to_helper — блок if с 5+ строками без return
  - DRILL_LONG_FUNCTION: long_function (сложный случай, 0% пока)
  - DRILL_DEEP_NESTING: deep_nesting (сложный случай, ~13%)
"""
from pathlib import Path


def polygon_imports_ok() -> Path:
    """DRILL_UNUSED_IMPORTS: после fix остаётся только Path."""
    return Path(".")


def polygon_extractable_block(x: int) -> int:
    """DRILL_EXTRACTABLE_BLOCK: deep_nesting|extract_block_to_helper.

    Внутренний блок if (5+ строк) без return — подходит для suggest_extract_block.
    Цель: накопить verify_success для extract_block_to_helper (rate ~13%).
    """
    result = 0
    if x > 0:
        if x < 10:
            a = x + 1
            b = a * 2
            c = b + x
            d = c * 2
            result = d
    return result


def polygon_long_function() -> int:
    """DRILL_LONG_FUNCTION: длинная функция без extractable block (0% пока).

    Плоский список присваиваний — suggest_extract_block не находит блок if/for/while.
    """
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
    """DRILL_DEEP_NESTING: вложенные if с return в каждой ветке.

    suggest_extract_block пропускает блоки с return — этот случай не extractable.
    """
    if x > 0:
        if x > 1:
            if x > 2:
                if x > 3:
                    return "deep"
                return "mid"
            return "shallow"
        return "tiny"
    return "zero"
