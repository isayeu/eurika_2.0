# Отчёт цикла Eurika — 2026-02-19

## 1. Fix (`eurika fix . --quiet --no-code-smells`)

| Поле | Значение |
|------|----------|
| **modified** | 0 |
| **skipped** | 1 |
| **errors** | 0 |
| **verify** | success |
| **tests** | 187 passed in ~30s |

### Skipped — причины (`skipped_reasons`)

| Причина | Файлы |
|---------|-------|
| extract_class: extracted file exists | code_awareness.py |

### Rescan diff

- **Модули:** 139, без изменений
- **Smells:** bottleneck 4, god_module 7, hub 9
- **Maturity:** low
- **verify_metrics:** success=true, before=46, after=46

---

## 2. Doctor (`eurika_doctor_report.json`)

| Метрика | Значение |
|---------|----------|
| **Модули** | 139 |
| **Зависимости** | 91 |
| **Циклы** | 0 |
| **Maturity** | low |
| **Risk score** | 46/100 |

### Центральные модули

- patch_engine.py (fan-in 6, fan-out 5)
- project_graph_api.py (fan-in 10, fan-out 1)
- patch_apply.py (fan-in 10, fan-out 0)

### Риски

- god_module @ patch_engine.py (severity 11.00), patch_apply.py (10.00), code_awareness.py (9.00), agent_core.py (7.00)
- bottleneck @ patch_apply.py (10.00)

### Architect

- **LLM:** fallback на template (`Connection error` при попытке LLM).

### Planned refactorings

- 1 op (`extract_class=1`), top target: `code_awareness.py`.

---

## 3. Learning (`agent learning-summary`)

### По виду операции (`by_action_kind`)

| action | total | success | fail | rate |
|--------|-------|---------|------|------|
| remove_unused_import | 20 | 16 | 4 | 80% |
| split_module | 120 | 74 | 46 | 62% |
| introduce_facade | 4 | 2 | 2 | 50% |
| extract_class | 16 | 10 | 6 | 62% |
| refactor_code_smell | 411 | 241 | 170 | 59% |
| extract_nested_function | 1 | 0 | 1 | 0% |

### По smell+action

| smell\|action | total | success | fail |
|---------------|-------|---------|------|
| god_module\|split_module | 117 | 74 | 43 |
| long_function\|refactor_code_smell | 284 | 167 | 117 |
| deep_nesting\|refactor_code_smell | 127 | 74 | 53 |
| hub\|split_module | 3 | 0 | 3 |
| long_function\|extract_nested_function | 1 | 0 | 1 |

---

## 4. Recent events (patch/learn, из doctor context)

| type | modified | success |
|------|----------|---------|
| patch | 1 file | True |
| learn | [cli/orchestrator.py] | True |
| patch | 0 files | True |
| patch | 1 file | True |
| learn | [eurika/api/__init__.py] | True |

---

## 5. Итог

- **Verify:** 187 тестов прошли
- **Изменений в контрольном fix:** 0
- **Skip шум резко снижен:** осталась 1 причина (`extract_class: extracted file exists`)
- **Система стабильна:** score 46, регрессий нет
- **Фокус дальше:** повышать долю реальных apply и улучшать fallback-policy для слабых пар learning
