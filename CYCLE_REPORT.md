# Отчёт цикла Eurika — 2025-02-19

## 1. Fix (eurika_fix_report.json)

| Поле | Значение |
|------|----------|
| **modified** | 0 |
| **skipped** | 41 |
| **errors** | 0 |
| **verify** | success |
| **tests** | 183 passed in ~32s |

### Skipped — причины (skipped_reasons)

| Причина | Файлы |
|---------|-------|
| diff already in content | cli/agent_handlers.py, cli/core_handlers.py, cli/orchestrator.py, core/pipeline.py, eurika/api/__init__.py, eurika/evolution/diff.py, eurika/reasoning/architect.py, eurika/reasoning/graph_ops.py, eurika/refactor/*, eurika_cli.py, patch_apply.py, patch_engine_apply_and_verify.py |
| architectural TODO already present | architecture_planner.py, agent_core_arch_review.py |
| split_module: extracted file exists | agent_core.py, action_plan.py |
| extract_class: extracted file exists | code_awareness.py |

### Rescan diff

- **Модули:** 139, без изменений
- **Smells:** bottleneck 4, god_module 7, hub 9
- **Maturity:** low
- **verify_metrics:** success=true, before=46, after=46

---

## 2. Doctor (eurika_doctor_report.json)

| Метрика | Значение |
|---------|----------|
| **Модули** | 139 |
| **Зависимости** | 91 |
| **Циклы** | 0 |
| **Maturity** | low |
| **Risk score** | 46/100 |

### Центральные модули

- project_graph_api.py (fan-in 10, fan-out 1)
- patch_engine.py (fan-in 6, fan-out 5)
- patch_apply.py (fan-in 10, fan-out 0)

### Риски

- god_module @ patch_engine.py (severity 11.00), patch_apply.py (10.00), code_awareness.py (9.00), agent_core.py (7.00)
- bottleneck @ patch_apply.py, agent_core.py

### Architect

- **LLM:** OpenRouter (mistralai/mistral-small-3.2-24b-instruct) — рекомендации с учётом контекста (extract_function, recent refactorings).

### Planned refactorings

41 ops (extract_class=1, refactor_code_smell=35, split_module=5); топ: architecture_planner.py, code_awareness.py, agent_core.py.

---

## 3. Learning (agent learning-summary)

### По виду операции (by_action_kind)

| action | total | success | fail | rate |
|--------|-------|---------|------|------|
| refactor_module | 101 | 97 | 4 | 96% |
| split_module | 176 | 134 | 42 | 76% |
| introduce_facade | 19 | 14 | 5 | 74% |
| remove_unused_import | 17 | 14 | 3 | 82% |
| extract_class | 11 | 7 | 4 | 64% |
| refactor_code_smell | 237 | 137 | 100 | 58% |

### По smell+action

| smell\|action | total | success | fail |
|---------------|-------|---------|------|
| god_module\|split_module | 173 | 134 | 39 |
| long_function\|refactor_code_smell | 167 | 97 | 70 |
| deep_nesting\|refactor_code_smell | 70 | 40 | 30 |
| hub\|split_module | 3 | 0 | 3 |

---

## 4. Recent events (patch/learn)

| type | modified | success |
|------|----------|---------|
| patch | [] | True |
| patch | [3 files] | True |
| learn | [architecture_planner.py, eurika/refactor/extract_function.py, tests/test_extract_function.py] | True |
| patch | [3 files] | False |
| patch | [] | True |

*Цикл 2025-02-19: modified=0, verify ✓, LLM architect.*

---

## 5. Итог

- **Verify:** 183 теста прошли
- **Изменений в этом цикле:** 0 (все операции пропущены)
- **Причины skip:** diff уже в файлах; architectural TODO уже есть; extracted-файлы существуют
- **Система стабильна:** score 46, регрессий нет
- **v2.6.16:** фикс _apply_learning_bump (nonlocal → param/return)
