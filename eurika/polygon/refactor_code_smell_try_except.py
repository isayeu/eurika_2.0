"""DRILL_REFACTOR_CODE_SMELL_TRY_EXCEPT: long_function — try/except с return в ветках.

Блок try содержит return — suggest_extract_block пропускает. Нет extractable блока.
Вариант для LLM: extract логику до try или разбить на шаги.
"""


def polygon_refactor_code_smell_try_except(data: list) -> int:
    """55+ строк: длинный try/except с return в каждой ветке."""
    try:
        if not data:
            return 0
        if len(data) == 1:
            return data[0]
        if len(data) == 2:
            return data[0] + data[1]
        if len(data) == 3:
            return data[0] + data[1] + data[2]
        if len(data) == 4:
            return data[0] + data[1] + data[2] + data[3]
        if len(data) == 5:
            return sum(data[:5])
        if len(data) == 6:
            return sum(data[:6])
        if len(data) == 7:
            return sum(data[:7])
        if len(data) == 8:
            return sum(data[:8])
        if len(data) == 9:
            return sum(data[:9])
        if len(data) == 10:
            return sum(data[:10])
        if len(data) < 20:
            return sum(data[:20])
        if len(data) < 30:
            return sum(data[:30])
        if len(data) < 40:
            return sum(data[:40])
        if len(data) < 50:
            return sum(data[:50])
        return sum(data)
    except TypeError:
        return -1
    except ValueError:
        return -2
    except IndexError:
        return -3
    except KeyError:
        return -4
    except AttributeError:
        return -5
    except RuntimeError:
        return -6
    except OSError:
        return -7
    except MemoryError:
        return -8
    except Exception:
        return -9
