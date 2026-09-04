"""DRILL_REFACTOR_CODE_SMELL: long_function без extractable block/nested (REFACTOR_CODE_SMELL_PLAN Phase 2).

Длинная функция (>50 строк) с последовательными присваиваниями — нет вложенных def,
нет if/for/while блоков 3+ строк. extract_nested и suggest_extract_block возвращают None.
Fallback: refactor_code_smell (TODO при emit_todo) или skip. Целевой кейс для LLM-powered extract.
"""


def _compute_intermediate_values(seed: int):
    a = seed + 1
    b = a * 2
    c = b + seed
    d = c * 2
    e = d + a
    f = e * 2
    g = f + b
    h = g * 2
    i = h + c
    j = i * 2
    return a, b, c, d, e, f, g, h, i, j


def _sum_intermediates(values: tuple) -> int:
    """Offline LLM-shaped extract for C.14 propose (no live LLM required)."""
    a, b, c, d, e, f, g, h, i, j = values
    return a + b + c + d + e + f + g + h + i + j


def polygon_refactor_code_smell_drill(seed: int) -> int:
    """55+ строк последовательного кода. Нет extractable nested/block — refactor_code_smell fallback."""
    values = _compute_intermediate_values(seed)
    # Padding to exceed MAX_FUNCTION_LINES (50)
    _1 = 1
    _2 = 2
    _3 = 3
    _4 = 4
    _5 = 5
    _6 = 6
    _7 = 7
    _8 = 8
    _9 = 9
    _10 = 10
    _11 = 11
    _12 = 12
    _13 = 13
    _14 = 14
    _15 = 15
    _16 = 16
    _17 = 17
    _18 = 18
    _19 = 19
    _20 = 20
    _21 = 21
    _22 = 22
    _23 = 23
    _24 = 24
    _25 = 25
    _26 = 26
    _27 = 27
    _28 = 28
    _29 = 29
    _30 = 30
    _31 = 31
    _32 = 32
    _33 = 33
    _34 = 34
    _35 = 35
    _36 = 36
    _37 = 37
    return _sum_intermediates(values) + _1
