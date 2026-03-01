# R3 Edge-Case Matrix

Формализованные edge-cases для CI (ROADMAP R3).

## Матрица

| Категория | Сценарий | Тест | Ожидание |
|-----------|----------|------|----------|
| Пустой вход | self_map.json отсутствует | `test_get_summary_empty_self_map_returns_error` | error dict, no crash |
| Пустой вход | Минимальный self_map | `test_get_summary_minimal_valid_returns_summary` | summary с system |
| Пустой вход | Пустой summary в architect | `test_architect_empty_summary_completes` | template, degraded_mode |
| Пустой вход | Пустая operation kind в policy | `test_policy_empty_operation_kind_defaults_medium_risk` | allow/review, не crash |
| Model/network error | Stage raises в runtime | `test_agent_runtime_stage_exception_sets_error_state` | ERROR state, no propagation |
| Memory | events append + read | `test_memory_events_append_and_read` | persist, all() returns |
| Cycle | Пустой проект (no self_map) | `test_cycle_state_empty_project_returns_done_or_error` | state=error, predictable |
| Огромный вход | 500 модулей в build_summary | `test_build_summary_huge_graph_no_overflow` | completes, modules=500 |
| Planning | empty summary/smells в build_patch_operations | `test_build_patch_operations_empty_input_returns_list` | [], no crash |
| R2 Fallback | build_context_sources raises | `test_prepare_context_sources_exception_continues` | context_sources={}, no crash |

## Запуск

```bash
pytest tests/edge_cases/ -v
# или
pytest -m edge_case -v
```
