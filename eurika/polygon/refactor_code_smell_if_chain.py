"""DRILL_REFACTOR_CODE_SMELL_IF_CHAIN: long_function с if/elif цепочкой, каждый блок 1–2 строки.

return в каждой ветке — suggest_extract_block пропускает (_block_has_control_flow_exit).
Нет вложенных def. Вариант для LLM: объединить ветки в match/case или extract lookup dict.
"""


def polygon_refactor_code_smell_if_chain(score: int) -> str:
    """55+ строк: длинная if/elif цепочка, каждая ветка с return — не extractable."""
    if score < 0:
        return "negative"
    elif score == 0:
        return "zero"
    elif score == 1:
        return "one"
    elif score == 2:
        return "two"
    elif score == 3:
        return "three"
    elif score == 4:
        return "four"
    elif score == 5:
        return "five"
    elif score == 6:
        return "six"
    elif score == 7:
        return "seven"
    elif score == 8:
        return "eight"
    elif score == 9:
        return "nine"
    elif score == 10:
        return "ten"
    elif score < 20:
        return "teens"
    elif score < 30:
        return "twenties"
    elif score < 40:
        return "thirties"
    elif score < 50:
        return "forties"
    elif score < 60:
        return "fifties"
    elif score < 70:
        return "sixties"
    elif score < 80:
        return "seventies"
    elif score < 90:
        return "eighties"
    elif score < 100:
        return "nineties"
    # Padding to exceed MAX_FUNCTION_LINES (50) for long_function
    _ = 1
    __ = 2
    ___ = 3
    ____ = 4
    _____ = 5
    ______ = 6
    _______ = 7
    ________ = 8
    _________ = 9
    __________ = 10
    return "hundred_plus"
