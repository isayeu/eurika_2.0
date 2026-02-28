# Операционность 5→6 — план D

**Цель:** рост verify_success_rate, переход от 5/10 к 6/10 (по review).

---

## Текущее состояние

| smell\|action | rate | Комментарий |
|---------------|------|-------------|
| remove_unused_import | ~38% | Лучший; реальный фикс (AST) |
| deep_nesting\|extract_block_to_helper | ~13% | 2 success, 13 fail |
| long_function\|extract_block_to_helper | 0% | 26 fail |
| long_function\|extract_nested_function | 0% | 4 fail |

**Блокеры:** campaign memory (verify_fail 2+ → skip), WEAK_SMELL_ACTION_PAIRS (auto: deny).

---

## Стратегия

### 1. Приоритет remove_unused_import
- Уже в prepend (clean_imports); не в WEAK.
- `--allow-low-risk-campaign` / `EURIKA_CAMPAIGN_ALLOW_LOW_RISK=1` — bypass campaign skip для remove_unused_import.
- suggest_policy: при высоком no_op_rate рекомендовать EURIKA_CAMPAIGN_ALLOW_LOW_RISK.

### 2. Накопление success для whitelist
- Цель: 2+ verify_success по target|kind → whitelist candidate.
- `eurika fix . --no-code-smells --allow-low-risk-campaign` — фокус на remove_unused_import.
- `eurika whitelist-draft . --kinds remove_unused_import` — черновик после накопления.

### 3. extract_block_to_helper
- DIFF_HINTS, pattern library, OSS hints — уже добавлены (KPI 4).
- Skip patterns по путям с 0% (eurika/refactor/extract_function.py в HARD_BLOCK).
- Долгосрочно: анализ diagnose_extract_block_failure для точечных правок.

### 4. learning-kpi Next steps
- Блок рекомендаций: «To improve: eurika fix . --no-code-smells --allow-low-risk-campaign».

### 5. Polygon `eurika/polygon.py`
- Сводный полигон для обучения: DRILL_UNUSED_IMPORTS, DRILL_LONG_FUNCTION, DRILL_DEEP_NESTING.
- Намеренные ошибки для fix-циклов; после fix — вернуть для следующего прогона.
- **Verify timeout:** полный pytest может превышать таймаут → verify_fail. Для тренировок: `--verify-cmd "python -m pytest tests/test_clean_imports_cli.py -q"` (обязательно `python -m pytest` — иначе ModuleNotFoundError). См. docs/POLYGON_VERIFY_TIMEOUT.md.

---

## Критерий 6/10

- verify_success_rate по remove_unused_import ≥ 50%;
- или 2+ smell|action|target в whitelist с rate ≥ 60%;
- suggest_policy учитывает no_op_rate.
