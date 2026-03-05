# TODO/FIXME Audit (R4 3.2.4)

Список для постепенного закрытия. Собрано: `rg "# TODO|# FIXME|# XXX" --type py -g '!*test*' eurika cli`.

**Дата:** 2026-03-05.

---

## 1. Код — кандидаты на рефакторинг

Маркеры `# TODO (eurika): refactor ...` — предложения по extraction (long_function, deep_nesting). Приоритет по частоте вызовов и критичности.

| Файл | Строка | Тип | Функция/блок |
|------|--------|-----|--------------|
| eurika/orchestration/doctor.py | 217 | long_function | run_doctor_cycle |
| eurika/orchestration/prepare.py | 594 | long_function | prepare_fix_cycle_operations |
| eurika/orchestration/full_cycle.py | 271 | long_function | run_full_cycle |
| eurika/api/chat_intent.py | 584 | long_function | detect_intent |
| eurika/api/chat_rag.py | 112 | deep_nesting | _load_chat_pairs |
| eurika/refactor/fix_import_from_verify.py | 352,355,358,361 | deep_nesting, long_function | _find_failing_file, _find_constant_definition, suggest_fix_import_operations |
| eurika/storage/operational_metrics.py | 69 | long_function | aggregate_operational_metrics |
| eurika/storage/global_memory.py | 139 | deep_nesting | aggregate_global_by_smell_action |
| eurika/reasoning/graph_ops.py | 374 | long_function | priority_from_graph |
| eurika/refactor/remove_unused_import.py | 211 | deep_nesting | _names_imported_under_type_checking |
| eurika/refactor/introduce_facade.py | 100 | long_function | introduce_facade |
| eurika/evolution/diff.py | 473 | long_function | _build_recommended_actions |
| cli/wiring/parser.py | 321 | long_function | _add_product_commands |
| cli/wiring/dispatch.py | ~~73~~ | long_function | ~~dispatch_command~~ ✅ _get_agent_handler extracted |

---

## 2. Структурные TODO (модуль/архитектура)

| Файл | Строка | Описание |
|------|--------|----------|
| eurika/reasoning/planner/core.py | 55 | god_module → split_module |

---

## 3. Не рефакторить (логика/паттерны)

Строки, где `# TODO` — часть логики (проверка diff, генерация маркеров), не кандидаты на закрытие:

- `eurika/api/ops.py` — build_fallback_todo, _is_strong_refactor_code_smell_success (строки с `# TODO` в строках)
- `eurika/reasoning/planner/filter_policy.py` — генерация marker
- `eurika/reasoning/planner_patch_ops.py` — diff output для extract_class
- `eurika/storage/event_views.py`, `global_memory.py` — проверка `"# TODO (eurika)"` в diff

---

## 4. Рекомендации

1. **Высокий приоритет:** doctor.run_doctor_cycle, prepare.prepare_fix_cycle_operations — часто вызываются.
2. **Средний:** chat_intent.detect_intent, fix_import_from_verify — критичный путь.
3. **Низкий:** introduce_facade, diff._build_recommended_actions — реже используются.
4. **planner/core.py** — split_module требует отдельного плана (BOUNDED_EVOLUTION §4).

**Ссылки:** R4_MODULAR_PLATFORM_PLAN.md 3.2.4, RELEASE_CHECKLIST §8, REFACTOR_CODE_SMELL_PLAN.md.
