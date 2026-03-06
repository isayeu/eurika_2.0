# TODO/FIXME Audit (R4 3.2.4)

Список для постепенного закрытия. Собрано: `rg "# TODO|# FIXME|# XXX" --type py -g '!*test*' eurika cli`.

**Дата:** 2026-03-05.

---

## 1. Код — кандидаты на рефакторинг

Маркеры `# TODO (eurika): refactor ...` — предложения по extraction (long_function, deep_nesting). Приоритет по частоте вызовов и критичности.

| Файл | Строка | Тип | Функция/блок |
|------|--------|-----|--------------|
| eurika/orchestration/doctor.py | ~~217~~ | ~~long_function~~ | ~~run_doctor_cycle~~ ✅ _load_doctor_inputs, _build_doctor_knowledge_provider, _enrich_doctor_output |
| eurika/orchestration/prepare.py | ~~594~~ | ~~long_function~~ | ~~prepare_fix_cycle_operations~~ ✅ _filter_and_policy_operations extracted |
| eurika/orchestration/full_cycle.py | ~~271~~ | ~~long_function~~ | ~~run_full_cycle~~ ✅ _run_full_cycle_scan, _run_full_cycle_doctor, _log_doctor_summary, _merge_doctor_runtime_into_report |
| eurika/api/chat_intent.py | ~~584~~ | ~~long_function~~ | ~~detect_intent~~ ✅ _detect_remember_recall, _detect_create_intent, _detect_delete_intent, _detect_save_intent, _detect_refactor_intent, _detect_run_intent |
| eurika/api/chat_rag.py | ~~112~~ | ~~deep_nesting~~ | ~~_load_chat_pairs~~ ✅ _parse_chat_line, _is_valid_assistant_response |
| eurika/refactor/fix_import_from_verify.py | ~~352,355,358,361~~ | ~~deep_nesting, long_function~~ | ~~_find_failing_file, _find_constant_definition, suggest_fix_import_operations~~ ✅ _extract_file_from_traceback, _extract_file_from_context, _find_name_in_ast_tree, _handle_name_error_ops, _try_redirect_import_ops, _try_create_stub_op |
| eurika/storage/operational_metrics.py | ~~69~~ | ~~long_function~~ | ~~aggregate_operational_metrics~~ ✅ _aggregate_patch_event_counts, _median_int |
| eurika/storage/global_memory.py | ~~139~~ | ~~deep_nesting~~ | ~~aggregate_global_by_smell_action~~ ✅ _process_learn_event |
| eurika/reasoning/graph_ops.py | ~~374~~ | ~~long_function~~ | ~~priority_from_graph~~ ✅ _apply_degree_bonus_to_scores, _sort_and_format_priorities |
| eurika/refactor/remove_unused_import.py | ~~211~~ | ~~deep_nesting~~ | ~~_names_imported_under_type_checking~~ ✅ _names_from_type_checking_block |
| eurika/refactor/introduce_facade.py | ~~100~~ | ~~long_function~~ | ~~introduce_facade~~ ✅ _compute_facade_path_and_module, _build_facade_content |
| eurika/evolution/diff.py | ~~473~~ | ~~long_function~~ | ~~_build_recommended_actions~~ ✅ _build_shift_index, _collect_action_candidates, _format_action_line |
| cli/wiring/parser.py | ~~321~~ | ~~long_function~~ | ~~_add_product_commands~~ ✅ _add_fix_cycle_common_args extracted |
| cli/wiring/dispatch.py | ~~73~~ | long_function | ~~dispatch_command~~ ✅ _get_agent_handler extracted |

---

## 2. Структурные TODO (модуль/архитектура)

| Файл | Строка | Описание |
|------|--------|----------|
| eurika/reasoning/planner/core.py | — | ~~god_module → split_module~~ ✅ CYCLE_REPORT #129: graph_analysis.py (analyze), actions_proposal.py (propose_actions); core — thin facade |

---

## 3. Не рефакторить (логика/паттерны)

Строки, где `# TODO` — часть логики (проверка diff, генерация маркеров), не кандидаты на закрытие:

- `eurika/api/ops.py` — build_fallback_todo, _is_strong_refactor_code_smell_success (строки с `# TODO` в строках)
- `eurika/reasoning/planner/filter_policy.py` — генерация marker
- `eurika/reasoning/planner_patch_ops.py` — diff output для extract_class
- `eurika/storage/event_views.py`, `global_memory.py` — проверка `"# TODO (eurika)"` в diff

---

## 4. Приоритеты (ROADMAP §4.5)

**Порядок (архитектурная логика):**

```
User Input → Intent Detection → Command Parsing → Planner/Executor
```

Intent layer — интерфейс Execution Model. Parser должен быть тонким: intent → handler.
Следовательно: **сначала chat_intent, потом parser.**

1. prepare ✅, doctor ✅, chat_intent ✅, parser ✅
2. Остальные — по мере необходимости
3. planner/core.py split_module — ✅ CYCLE_REPORT #129

**Ссылки:** RELEASE_CHECKLIST §8, API_BOUNDARIES.md.
