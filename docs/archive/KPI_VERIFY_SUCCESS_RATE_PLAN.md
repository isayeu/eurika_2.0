# KPI verify_success_rate — план A

**Цель:** рост `verify_success_rate` по `smell|action|target` (apply_rate вторичен). ROADMAP бэклог.

---

## Текущее состояние (snapshot 84)

| smell\|action | total | verify_success | rate |
|---------------|-------|----------------|------|
| extract_block_to_helper | 41 | 2 | 5% |
| remove_unused_import | 13 | 5 | 38% |
| extract_nested_function | 4 | 0 | 0% |
| split_module | 2 | 0 | 0% |

---

## Шаги

### A.1 Planner — verify_success fallback (опционально)

`_success_rate_for_op` использует `success`; merge_learning_stats — `success`/`fail`. Для event_views success = verify_success (кроме TODO-only refactor_code_smell). Логика корректна, изменений не требуется.

### A.2 CLI `eurika learning-kpi [path]` [--polygon]

- Команда выводит KPI блок: by_smell_action с verify_success_rate, top promote/deprioritize.
- `--polygon` — фильтр только по eurika/polygon/ (drill view), секция Polygon drills.
- Использует `get_learning_insights`; формат: таблица + рекомендации (whitelist_candidates, policy_deny_candidates).

### A.3 Policy — dynamic deny из learning

- В `evaluate_operation`: при совпадении op с `policy_deny_candidates` (smell|action|target, rate<0.25, total>=3) — усиливать до deny в auto, review в hybrid.
- Загрузка deny_candidates из `get_learning_insights` при project_root.

### A.4 Context sources — by_target с verify_success_rate

- `build_context_sources`: обогатить `by_target[target]` полями `verify_success_rate`, `verify_success`, `verify_fail` из learning по целевым операциям.
- `_apply_context_priority`: при равном score — учитывать verify_success_rate (targets с низким rate — в конец).

### A.5 CYCLE_REPORT + docs

- Снимок после внедрения; обновить REPORT.md / ROADMAP — KPI flow зафиксирован.

---

## Критерий готовности

- [x] `eurika learning-kpi .` выводит KPI и рекомендации.
- [x] Policy учитывает deny_candidates при evaluate.
- [x] context_sources.by_target содержит verify_success_rate для приоритизации.

**Реализовано:** snapshot 85, CYCLE_REPORT.

---

## KPI 4 — Learning from GitHub для code smells (2026-02-27)

- **DIFF_HINTS:** добавлены (long_function, extract_block_to_helper), (deep_nesting, extract_block_to_helper).
- **REMEDIATION_HINTS:** long_function, deep_nesting в detector.
- **Pattern library:** extract_patterns_from_repos собирает long_function, deep_nesting из CodeAwareness по curated repos.
- **get_code_smell_operations:** OSS hints из pattern_library в description (OSS: Django, FastAPI).
