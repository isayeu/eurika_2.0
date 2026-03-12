# TODO/FIXME Audit (R4)

**Статус:** Все 14 пунктов закрыты (CYCLE_REPORT #126, март 2026).

---

## 1. Рефакторинг (выполнено)

| Модуль | Было | Стало |
|--------|------|-------|
| doctor.py | long_function | _load_doctor_inputs, _build_doctor_knowledge_provider, _enrich_doctor_output |
| prepare.py | long_function | _filter_and_policy_operations |
| full_cycle.py | long_function | _run_full_cycle_scan, _run_full_cycle_doctor, _log_doctor_summary |
| chat_intent.py | long_function | _detect_* extraction |
| chat_rag.py | deep_nesting | _parse_chat_line, _is_valid_assistant_response |
| fix_import_from_verify.py | deep_nesting, long_function | _extract_*, _find_*, _handle_*, _try_* |
| operational_metrics.py | long_function | _aggregate_patch_event_counts, _median_int |
| global_memory.py | deep_nesting | _process_learn_event |
| graph_ops.py | long_function | _apply_degree_bonus_to_scores, _sort_and_format_priorities |
| remove_unused_import.py | deep_nesting | _names_from_type_checking_block |
| introduce_facade.py | long_function | _compute_facade_path_and_module, _build_facade_content |
| evolution/diff.py | long_function | _build_shift_index, _collect_action_candidates, _format_action_line |
| parser.py | long_function | _add_fix_cycle_common_args |
| dispatch.py | long_function | _get_agent_handler |

---

## 2. planner/core split

✅ CYCLE_REPORT #129: graph_analysis.py, actions_proposal.py; core — thin facade.

---

## 3. Не рефакторить

- ops.py — build_fallback_todo, _is_strong_refactor_code_smell_success
- filter_policy.py — генерация marker
- planner_patch_ops.py — diff output
- event_views.py, global_memory.py — проверка "# TODO (eurika)" в diff

---

## 4. Ссылки

ROADMAP §4.5, RELEASE_CHECKLIST §8, API_BOUNDARIES.md, REVIEW_2026_IV_ANALYSIS.
