# Память — минимальная формализация (Review III)

Три хранилища для автономного цикла. Без сложной иерархии.

---

## 1. EventLog

| Атрибут | Значение |
|--------|----------|
| **Реализация** | `EventStore` (eurika/storage/event_engine, events.py) |
| **Файл** | `.eurika/events.json` |
| **Контракт** | append-only; `append_event(type, input, output, result)`; `by_type(t)`, `recent_events(limit, types)` |
| **Типы событий** | `scan`, `patch`, `learn`, `feedback` |
| **Роль** | Первичный журнал: что произошло за все циклы |

**Точка входа:** `ProjectMemory(project_root).events` или `event_engine(project_root)`.

---

## 2. FailureLog

| Атрибут | Значение |
|--------|----------|
| **Реализация** | Bounded view над EventLog (learn, result=False) |
| **Файл** | Нет отдельного. Данные в `.eurika/events.json` |
| **Контракт** | `get_recent_failures`, `get_recent_failures_enriched`, `get_recent_failed_plan_hashes` |
| **Обогащение** | goal_id, plan_hash, confidence в output learn event (ARCHITECTURE_MEMORY_REVIEW §2) |
| **Ограничение** | Bounded по limit при чтении |
| **Роль** | Провалы для самокоррекции; planner deprioritize; decay failure_penalty |

**Один источник истины:** все outcomes в EventLog. FailureLog = projection.

---

## 3. LearningStore

| Атрибут | Значение |
|--------|----------|
| **Реализация** | `LearningView` (event_views) — view над EventStore type=learn |
| **Запись** | `record_outcome(project_root, modules, operations, risks, verify_success)` → memory.learning.append |
| **Чтение** | `aggregate_by_action_kind()`, `aggregate_by_smell_action()`, `get_merged_learning_stats(root)` |
| **Роль** | Агрегаты success/fail по (smell_type, action_kind); planner сортирует ops по learning_stats |

**Точка входа:** `ProjectMemory(project_root).learning`; `eurika.storage.record_outcome`; `get_merged_learning_stats` (global_memory).

---

## Связи

```
record_outcome (apply_stage)
    ├── memory.learning.append → EventLog (type=learn, result, output.failure_reason)
    └── append_learn_to_global (опционально)

get_recent_failures → EventLog (learn, result=False) — bounded view
get_merged_learning_stats → LearningView.aggregate_* + global_memory
```

---

## STM (краткосрочная память)

ExecutionContext — контекст текущего fix-cycle. Не сохраняется в LTM.

| Поле | Роль |
|------|------|
| snapshot_before/after, delta_score | Состояние до/после |
| current_goal | Текущая цель (опционально) |
| attempt_count | Попытки в сессии |
| session_failures | Провалы в сессии |

---

## Операционность pattern library

Pattern library (OSS hints в diff) полезна **только** когда learning loop реально меняет поведение. Иначе — статический каталог.

| Условие | Поведение |
|---------|-----------|
| success_rate < 0.25, total ≥ 3 | OSS hints = 0 (не усиливать провальные стратегии) |
| success_rate ≥ 0.25 или total < 3 | OSS hints до 3 (по умолчанию) |

**Реализация:** `build_hints_and_params(learning_stats=...)` → `_oss_hint_limit_for_smell_action`.

---

## Влияние памяти на planner

Planner читает enriched failures и меняет поведение (не только сортировку):

| Сигнал | Действие |
|--------|----------|
| `(kind, plan_hash)` в failed pairs | Deprioritize: ops в конец при повторе плана |
| `kind` failed 2+ раз (любой plan) | `apply_failure_based_fallback` → swap kind (напр. split_module → refactor_module) |
| `plan_hash` failed | Reverse ops order (стратегическая вариация) |

**Функции:** `get_recent_failed_kind_plan_pairs`, `get_kind_plan_failure_counts`, `apply_failure_based_fallback`, `sort_and_reindex_by_learning(failed_kind_plan_pairs=..., kind_plan_counts=...)`.

---

## Ссылки

- **ARCHITECTURE_MEMORY_REVIEW.md** — честный разбор, двойная истина, план
- **ROADMAP.md** §5.8 — STM/LTM маппинг
- **Architecture.md** §0.9 — Execution Model
- **EXECUTION_MODEL_PLAN.md** — аудит стабильного ядра
