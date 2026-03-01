# R2 Fallback Audit

Каталог fallback-путей для предсказуемого завершения цикла при недоступности внешних зависимостей.
Критерий: *при недоступности LLM/knowledge/network цикл завершается детерминированно (degraded mode или early exit).*

---

## 1. Doctor cycle (`run_doctor_cycle`)

| Зависимость | Fallback | degraded_mode | Код |
|-------------|----------|---------------|-----|
| `get_summary` error | Early exit, `degraded_reasons: ["summary_unavailable"]` | ✓ | doctor.py:134–144 |
| Architect LLM unavailable | Template text, `degraded_reasons: ["llm_unavailable:..."]` | ✓ | architect.py:503–531 |
| `--no-llm` | Template, `degraded_reasons: ["llm_disabled"]` | ✓ | architect.py |
| Knowledge fetch failure | Empty snippet, cycle continues | ✓ | architect docstring |

---

## 2. Fix cycle (`run_fix_cycle`, `prepare_fix_cycle_operations`)

| Зависимость | Fallback | Код |
|-------------|----------|-----|
| Scan fail | Early exit, return_code=1 | prepare.py:460–465 |
| Diagnose fail | Early exit, result.output | prepare.py:467–469 |
| Empty patch_plan (no suggest_patch_plan) | Prepend clean_imports + code_smells | prepare.py:473–478 |
| `build_context_sources` Exception | `context_sources={}`, cycle continues | prepare.py:501–509 |
| patch_plan None after prepare | Early exit, "Internal error: missing patch plan" | fix_cycle_impl.py:421–435 |

---

## 3. Architect (`interpret_architecture_with_meta`)

| Цепочка | Fallback |
|---------|----------|
| Primary (OpenAI/OpenRouter) | → Ollama HTTP |
| Ollama HTTP fail | → Ollama CLI `ollama run` |
| All fail | Return (None, reason), meta.degraded_mode=True |

---

## 4. Full cycle (`run_full_cycle`)

| Зависимость | Fallback |
|-------------|----------|
| `run_scan` != 0 | Early exit, degraded_reasons: ["scan_failed"] |
| Doctor `data.get("error")` | Early exit, degraded_reasons: ["doctor_error"] |

---

## 5. Agent runtime (`run_agent_cycle`)

| Stage exception | Fallback |
|-----------------|----------|
| observe/reason/propose/apply/verify raise | state=ERROR, stage_outputs[stage].status="error" |

Тест: `test_agent_runtime_stage_exception_sets_error_state`.

---

## 6. Edge-case tests (R3)

- `test_get_summary_empty_self_map_returns_error`
- `test_architect_empty_summary_completes` (degraded_mode, llm_disabled)
- `test_cycle_state_empty_project_returns_done_or_error`
- `test_agent_runtime_stage_exception_sets_error_state`
- `test_build_patch_operations_empty_input_returns_list`

---

## Вывод

Критические пути (doctor, fix, full cycle) имеют детерминированный degraded mode или early exit при сбоях внешних зависимостей. Knowledge resolution failures дают пустой snippet; architect при LLM unavailable возвращает template.
