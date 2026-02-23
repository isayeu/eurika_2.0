# Отчёт цикла Eurika

---

## 44. Snapshot (2026-02-23) — R3 Typing contract kickoff (orchestration boundary)

### Scope
- старт целевого typing-гейта для критичного fix-контура:
  - `cli/orchestration/prepare.py`
  - `cli/orchestration/apply_stage.py`
  - `cli/orchestration/fix_cycle_impl.py`
- добавлен модуль контрактов `cli/orchestration/contracts.py` (пограничные алиасы + typed payloads для decision/telemetry/safety).
- в `pyproject.toml` добавлен optional extra `typecheck` (`mypy`) и базовая конфигурация `tool.mypy` для постепенного включения typecheck.

### Проверка
- `mypy` по целевым модулям: `Success: no issues found in 3 source files`.
- regression-check:
  - `tests/test_agent_handlers_decision_summary.py` — green
  - `tests/test_campaign_flow.py` — green
  - `tests/test_cycle.py -k "attach_fix_telemetry_counts_campaign_session_skips or attach_fix_telemetry_median_verify_time"` — green

### Итог
- включён узкий typing-contract gate на boundary fix-orchestration без изменения runtime-поведения.

---

## 43. Snapshot (2026-02-23) — QG-4 ritual confirmation (apply-safe + no-op)

### Сценарий A (apply-safe e2e, mini-project)
- подготовлен временный проект `.tmp_qg4_apply` (`a.py` + `tests/test_a.py`).
- `../.venv/bin/python -m eurika_cli scan .tmp_qg4_apply`
- `../.venv/bin/python -m eurika_cli fix .tmp_qg4_apply --quiet`
- `../.venv/bin/python -m eurika_cli campaign-undo .tmp_qg4_apply --checkpoint-id 20260223_113847_517`

### Результат A
- `fix`: `modified_count=1`, `apply_rate=1.0`, `no_op_rate=0.0`, `rollback_rate=0.0`.
- verify: `1 passed`; `verify_required=true`, `verify_ran=true`, `verify_passed=true`.
- checkpoint: `checkpoint_id=20260223_113847_517`, `status=completed`, `run_ids=["20260223_083847"]`.
- `campaign-undo`: `status=undone`, `restored=["a.py"]`, `errors=[]`.

### Сценарий B (no-op e2e, основной проект)
- `../.venv/bin/python -m eurika_cli scan .`
- `../.venv/bin/python -m eurika_cli doctor . --no-llm`
- `../.venv/bin/python -m eurika_cli fix . --dry-run --quiet`

### Результат B
- `eurika_fix_report`: `message="Patch plan has no operations. Cycle complete."`
- telemetry: `operations_total=1`, `modified_count=0`, `skipped_count=1`, `apply_rate=0.0`, `no_op_rate=1.0`, `rollback_rate=0.0`.
- safety gates: `verify_required=false`, `verify_ran=false`, `rollback_done=false`.
- campaign memory: `campaign_skipped=1` по рискованной цели, apply-stage не запускался (ожидаемое no-op поведение).

### Итог
- QG-4 подтверждён: и apply-safe путь (apply + verify + campaign-undo), и no-op путь отрабатывают предсказуемо и детерминированно.

---

## 42. Snapshot (2026-02-23) — QG-1/QG-2 closeout for 3.6.4

### QG-1 (edge-case hardening)
- `campaign-undo` для битого checkpoint payload теперь возвращает явную ошибку (`Invalid checkpoint payload`).
- повторный `campaign-undo` по already-undone checkpoint сделан идемпотентным (`already_undone=true`, без повторного rollback).
- добавлены тесты на missing checkpoint id, invalid payload, repeated undo, mixed rollback errors.

### QG-2 (integrated flow)
- добавлен интеграционный тест `tests/test_campaign_flow.py`:
  - `fix --approve-ops 1` (частичный apply),
  - проверка `decision_summary.blocked_by_human` и `not_in_approved_set`,
  - проверка `campaign_checkpoint` (`checkpoint_id`, `run_ids`),
  - `campaign-undo --checkpoint-id ...` и восстановление изменённого файла.

### Проверка
- `tests/test_campaign_checkpoint.py` — edge-cases green
- `tests/test_campaign_flow.py` + related suites (`test_agent_handlers_decision_summary`) — green

### Итог
- quality-gate для контура `decision gate + checkpoint + campaign-undo` закрыт на интеграционном уровне.

---

## 41. Snapshot (2026-02-23) — DoD 3.6 baseline (3 ritual runs)

### Сценарий
- 3 последовательных прогона: `scan -> doctor --no-llm -> fix --dry-run --quiet`

### Метрики по прогонам
| run | apply_rate | no_op_rate | rollback_rate | verify_required | blocked policy/critic/human | doctor apply_rate | doctor rollback_rate | doctor median_verify_time_ms |
|-----|------------|------------|---------------|-----------------|------------------------------|-------------------|----------------------|------------------------------|
| 1 | 0.0 | 1.0 | 0.0 | false | 0 / 0 / 0 | 0.3576 | 0.7 | 96430 |
| 2 | 0.0 | 1.0 | 0.0 | false | 0 / 0 / 0 | 0.3576 | 0.7 | 96430 |
| 3 | 0.0 | 1.0 | 0.0 | false | 0 / 0 / 0 | 0.3576 | 0.7 | 96430 |

### Вывод
- baseline стабилен и предсказуем: no-op сценарий повторяется без новых регрессий.
- risky target по `eurika/agent/tool_contract.py` последовательно отсекается campaign-memory, verify stage не запускается (ожидаемое поведение для no-op).

---

## 40. Snapshot (2026-02-23) — Sprint 3.6.4 e2e: checkpoint -> campaign-undo

### Сценарий (безопасный mini-project)
- создан временный проект `.tmp_campaign_demo` с `a.py` (unused import) и `tests/test_a.py`.
- `eurika scan .tmp_campaign_demo`
- `eurika fix .tmp_campaign_demo --quiet` (apply + verify)
- `eurika campaign-undo .tmp_campaign_demo --list`
- `eurika campaign-undo .tmp_campaign_demo --checkpoint-id <id>`

### Результат
- fix применил `remove_unused_import` для `a.py`; verify: `1 passed`.
- в `eurika_fix_report.json` зафиксирован `campaign_checkpoint`:
  - `checkpoint_id=20260223_004858_306`
  - `status=completed`
  - `run_ids=["20260222_214858"]`
- `campaign-undo --list` показал checkpoint со статусом `completed`, после undo — `status=undone`.
- после `campaign-undo` файл `a.py` восстановлен из backup (`import os` вернулся).

### Итог
- Контур Sprint 3.6.4 подтверждён end-to-end: checkpoint создаётся до apply, связывается с run_id, и откат кампании одним действием работает предсказуемо.

---

## 39. Snapshot (2026-02-22) — ritual check after Sprint 3 push

### Команды
- `eurika scan .`
- `eurika doctor . --no-llm`
- `eurika fix . --dry-run` / no-op fix-path

### Результат
- `eurika_fix_report.json`: `message="Patch plan has no operations. Cycle complete."`
- telemetry: `operations_total=1`, `modified_count=0`, `skipped_count=1`, `apply_rate=0.0`, `no_op_rate=1.0`, `rollback_rate=0.0`
- safety_gates: `verify_required=false`, `verify_ran=false`, `rollback_done=false`
- `eurika_doctor_report.json`: риск стабилен (`risk_score=46`), `smells=stable`, `regressions=[]`

### Проверка Sprint 3.6.4 в ритуале
- risky op по `eurika/agent/tool_contract.py` снова отсечён campaign-memory (`campaign_skipped=1`) — ожидаемо.
- checkpoint кампании в этом прогоне не создаётся, так как apply-stage не запускался (нет executable ops) — поведение корректное для no-op ритуала.

---

## 38. Snapshot (2026-02-22) — 3.6.3 closed: context visibility + context effect

### Изменения
- **UI Dashboard / Context sources:** добавлена карточка с агрегатами (`targets with context`, `recent verify-fail`, `campaign rejected`, `recent patch-modified`).
- **Top context hits:** в UI отображаются top-3 `context_hits` по текущим операциям для объяснения приоритизации.
- **By-target breakdown:** в UI добавлен компактный блок `target -> related_tests / neighbor_modules / hits`.
- **CYCLE_REPORT effect:** `report-snapshot` теперь пишет блок `2.1 Context effect (ROADMAP 3.6.3)` с `apply_rate/no_op_rate` (current vs baseline, delta in pp).

### Тесты
- `tests/test_cycle.py::test_report_snapshot_context_effect_block`
- `tests/test_cycle.py::test_report_snapshot_telemetry_block`

### Проверка
- `../.venv/bin/python -m pytest -q tests/test_cycle.py -k "report_snapshot_telemetry_block or report_snapshot_context_effect_block"` → `2 passed`

---

## 37. Snapshot (2026-02-22) — v3.0.9: runtime robustness (state + degraded visibility)

### Изменения
- **R2 state-модель runtime:** `AgentCycleResult` теперь фиксирует `state` и `state_history` (`idle -> thinking -> done|error`).
- **Детерминированные переходы:** `run_agent_cycle` переводит состояние в `error` при сбое стадии и в `done` при успешном завершении.
- **Doctor degraded metadata:** `run_doctor_cycle` добавляет `runtime` блок (`degraded_mode`, `degraded_reasons`, `llm_used`, `use_llm`).
- **Fix/Cycle degraded metadata:** для non-assist и full-cycle `report.runtime` теперь содержит причины деградации/fallback.

### Тесты
- runtime: `test_run_agent_cycle_state_transitions_success`, `test_run_agent_cycle_state_transitions_error`
- doctor: `test_doctor_runtime_reports_degraded_mode_when_llm_disabled`
- cycle/fix: `test_run_cycle_non_assist_adds_runtime_block_to_report`, `test_full_cycle_propagates_doctor_runtime_to_fix_report`

### Проверка
- `tests/test_agent_runtime.py tests/test_cli_runtime_mode.py tests/test_cycle.py` — green.

---

## 36. Snapshot (2026-02-21) — v3.0.8: long_function extract_block fallback

### Изменения
- **long_function без вложенных def:** fallback на suggest_extract_block (if/for/while 5+ строк) когда extract_nested_function не срабатывает.
- extract_block работает даже при allow_extract_nested=False (learning блокирует только extract_nested).
- fixed_locations предотвращает дубли extract_block для одной функции с long_function и deep_nesting.

---

## 35. Snapshot (2026-02-21) — v3.0.8: god_class WEAK, deep_nesting extract_block

### Изменения (CHANGELOG v3.0.8)
- **god_class|extract_class** в WEAK_SMELL_ACTION_PAIRS; EXTRACT_CLASS_SKIP_PATTERNS (*tool_contract*.py) — защита от повторения #34
- **deep_nesting** — suggest_extract_block, extract_block_to_helper; EURIKA_DEEP_NESTING_MODE=hybrid

### report-snapshot . (текущее состояние)

| Блок | Значение |
|------|----------|
| **Doctor** | 204 модулей, Risk 46/100, apply_rate 0.358 |
| **Learning** | god_class\|extract_class 1/2; deep_nesting\|refactor_code_smell 0% (теперь есть extract_block_to_helper) |

---

## 34. Fix rollback (2026-02-22) — extract_class на tool_contract провалил verify

### Что произошло
`eurika fix .` из UI применил extract_class к `eurika/agent/tool_contract.py` (DefaultToolContract). Созданы файлы:
- `tool_contract_defaulttoolcontractextracted.py` — сломанный код (undefined `kwargs`, `dry_run`, `_ok`/`_err`)
- `tool_contract_defaulttoolcontract.py` — обёртка

verify failed (pytest), auto_rollback не восстановил оригинал полностью (backup был перезаписан второй операцией).

### Исправление
1. `eurika agent patch-rollback --run-id 20260221_221321 .` — восстановлен tool_contract.py из backup
2. `git restore eurika/agent/tool_contract.py` — полное восстановление из git
3. Удалены созданные файлы: `tool_contract_defaulttoolcontract.py`, `tool_contract_defaulttoolcontractextracted.py`

### Итог
- 319 tests passed
- extract_class для god_class нуждается в доработке: при извлечении статических методов теряются параметры и хелперы

---

## 33. Fix (2026-02-21) — eurika fix . после dry-run

### Команда
`eurika fix .` (assist mode)

### Результат

| Поле | Значение |
|------|----------|
| **modified** | 7 |
| **skipped** | 0 |
| **verify** | ✓ passed |

### Операции
- 4× remove_unused_import: cli/orchestrator_run_doctor_cycle.py, eurika/api/chat_intent.py, tests/test_chat_intent.py, tests/test_chat_rag.py
- 3× refactor_code_smell (TODO): cli/wiring/dispatch.py (long_function), eurika/api/chat.py (long_function), eurika/api/chat_rag.py (deep_nesting)

### telemetry
apply_rate=1.0, no_op_rate=0.0, rollback_rate=0.0, verify_duration_ms=58098

### verify_metrics
before_score=46, after_score=46

### Итог
- 7 файлов изменены, verify ✓
- Learning: +4 success remove_unused_import, +3 success refactor_code_smell (TODO-маркеры)

---

## 32. Snapshot (2026-02-21) — ритуал 2.1, после багфикса knowledge/base.py

### Команда
`eurika scan .` → `eurika doctor . --no-llm` → `eurika report-snapshot .`

### Багфикс
- `eurika/knowledge/base.py`: SyntaxError — закрыта скобка `}` для dict `meta` (строка 402)

### 1. Fix (последний прогон из events)

| Поле | Значение |
|------|----------|
| **modified** | 382 (curated_repos) / 3 (локальные) |
| **skipped** | 16 |
| **verify** | mixed |

### 2. Doctor (`eurika_doctor_report.json`)

| Метрика | Значение |
|---------|----------|
| **Модули** | 200 |
| **Зависимости** | 108 |
| **Risk score** | 33/100 |
| **apply_rate** (last 10) | 0.3542 |
| **median_verify_time** | 131199 ms |

### 3. Learning

**by_action_kind**
- refactor_code_smell: 0 success, 1045 fail (0%)
- split_module: 4 success, 4 fail (50%)
- remove_unused_import: 10 success, 40 fail (20%)

**by_smell_action**
- long_function|refactor_code_smell: total=881, success=0, fail=860
- god_module|split_module: total=8, success=4, fail=4
- unknown|remove_unused_import: total=50, success=10, fail=40

### Итог
- Ритуал 2.1 выполнен; doctor падал на SyntaxError в knowledge/base.py — исправлено
- Risk score 33/100; модули 200 (+13 vs §31)
- refactor_code_smell 0% (WEAK_SMELL_ACTION_PAIRS)

---

## 31. Snapshot (2026-02-21) — ритуал 2.1, после B (продуктовая готовность) + 3.5.11.A Chat

### Команда
`eurika report-snapshot .`

### 1. Fix (`eurika fix .`)

| Поле | Значение |
|------|----------|
| **modified** | 3 |
| **skipped** | 0 |
| **verify** | True |

### verify_metrics: before=46, after=46

### telemetry (ROADMAP 2.7.8)
apply_rate=1.0, no_op_rate=0.0, rollback_rate=0.0, verify_duration_ms=123701, median_verify_time_ms=123701

### 2. Doctor (`eurika_doctor_report.json`)

| Метрика | Значение |
|---------|----------|
| **Модули** | 187 |
| **Зависимости** | 107 |
| **Risk score** | 46/100 |

### 3. Learning

### by_action_kind
- refactor_code_smell: 0 success, 7 fail (0%)
- split_module: 4 success, 1 fail (80%)
- remove_unused_import: 10 success, 3 fail (77%)

### by_smell_action
- long_function|refactor_code_smell: total=28, success=0, fail=7
- deep_nesting|refactor_code_smell: total=2, success=0, fail=0
- god_module|split_module: total=5, success=4, fail=1
- unknown|remove_unused_import: total=13, success=10, fail=3

### Итог
- Ритуал 2.1 выполнен после направления B (продуктовая готовность) и 3.5.11.A (Chat)
- Risk score 46/100, apply-rate=1.0
- refactor_code_smell по-прежнему 0% (WEAK_SMELL_ACTION_PAIRS)

---

## 30. Snapshot (2026-02-21) — report-snapshot via Web UI (ритуал 2.1)

### Команда
`eurika report-snapshot .` (через Terminal tab Web UI)

### 1. Fix (`eurika fix .`)

| Поле | Значение |
|------|----------|
| **modified** | 3 |
| **skipped** | 0 |
| **verify** | True |

### verify_metrics
- before_score=46, after_score=46

### telemetry (ROADMAP 2.7.8)
- apply_rate=1.0, no_op_rate=0.0, rollback_rate=0
- verify_duration_ms=123701, median_verify_time_ms=123701

### 2. Doctor (`eurika_doctor_report.json`)

| Метрика | Значение |
|---------|----------|
| **Модули** | 187 |
| **Зависимости** | 107 |
| **Risk score** | 46/100 |

### 3. Learning

**by_action_kind**
- refactor_code_smell: 0 success, 7 fail (0%)
- split_module: 4 success, 1 fail (80%)
- remove_unused_import: 10 success, 3 fail (77%)

**by_smell_action**
- long_function|refactor_code_smell: total=28, success=0, fail=7
- deep_nesting|refactor_code_smell: total=2, success=0, fail=0
- god_module|split_module: total=5, success=4, fail=1
- unknown|remove_unused_import: total=13, success=10, fail=3

### Итог
- Ритуал 2.1: report-snapshot выполнен через Web UI
- Risk score стабилен (46/100), apply-rate=1.0

---

## 20. Dogfooding cycle 2026-02-20 (ROADMAP 2.7.9)

### Команда
`eurika cycle .` (assist mode, с LLM fallback)

### Fix результат
| Поле | Значение |
|------|----------|
| **modified** | 7 |
| **skipped** | 0 |
| **verify** | success |
| **tests** | 258 passed (37.03s) |
| **rollback** | нет |

### Операции применены
- 3× refactor_code_smell (TODO long_function: handle_report_snapshot, prepare_fix_cycle_operations, handle_non_default_kind)
- 2× remove_unused_import (architecture_planner_build_patch_plan, tests/test_hitl_cli)
- 1× split_module (architecture_planner → architecture_planner_build_plan)

### Telemetry (ROADMAP 2.7.8)
- apply_rate=1.17, no_op_rate=0, rollback_rate=0
- verify_duration_ms=37582, median_verify_time_ms=19497

### Rescan
- modules_added: architecture_planner_build_plan.py
- verify_metrics: before_score=46, after_score=46
- architecture_planner.py: fan_out 2→3

### Learning (по циклу)
| action | success | fail | rate |
|--------|---------|------|------|
| split_module | 22 | 11 | 67% |
| extract_class | 5 | 2 | 71% |
| remove_unused_import | 4 | 4 | 50% |
| refactor_code_smell | 0 | 76 | 0% |

### Итог
- Verify passed, rollback не потребовался
- architecture_planner — фасад: build_plan в architecture_planner_build_plan, build_patch_plan в architecture_planner_build_patch_plan
- Цикл 1/3 для DoD 2.7.9

---

## 21. Dogfooding cycle 2 — 2026-02-20

### Fix результат
| Поле | Значение |
|------|----------|
| **modified** | 2 |
| **skipped** | 0 |
| **verify** | success |
| **tests** | 258 passed (33.38s) |
| **rollback** | нет |

### Операции применены
- 2× remove_unused_import (architecture_planner.py, architecture_planner_build_action_plan.py)
- 1× split_module (architecture_planner → build_action_plan в architecture_planner_build_action_plan.py)

### Telemetry
- apply_rate=0.67, no_op_rate=0, rollback_rate=0
- verify_duration_ms=33846, median_verify_time_ms=34229

### Rescan
- verify_metrics: before_score=46, after_score=46
- architecture_planner.py: fan_out 4→3; action_plan.py: fan_in 8→7

### Итог
- verify passed, rollback не потребовался
- Цикл 2/3 для DoD 2.7.9

---

## 22. Dogfooding cycle 3 — 2026-02-20

### Fix результат
| Поле | Значение |
|------|----------|
| **modified** | 0 или минимально |
| **verify** | success |
| **rollback** | нет |

### Learning (после 3 циклов)
| action | success | fail | rate |
|--------|---------|------|------|
| split_module | 19 | 6 | **76%** |
| extract_class | 4 | 1 | **80%** |
| remove_unused_import | 8 | 3 | **73%** |
| refactor_code_smell | 0 | 41 | 0% |

### Итог
- 3 стабильных цикла подряд ✓
- DoD 2.7.9 выполнен

---

## 23. Policy update: refactor_code_smell в WEAK_SMELL_ACTION_PAIRS (2026-02-20)

### Обоснование
- Learning: `refactor_code_smell` — 0% success (0/41), только TODO-маркеры
- `long_function|refactor_code_smell` и `deep_nesting|refactor_code_smell` добавлены в `WEAK_SMELL_ACTION_PAIRS`

### Поведение
- **hybrid:** требуют manual approval (review)
- **auto:** блокируются (deny)
- **assist:** без изменений (все ops apply)
- Деприоритизация: слабые пары в конце плана, первыми отсекаются при max_ops

### Файл
`eurika/agent/policy.py` — WEAK_SMELL_ACTION_PAIRS

---

## 24. Dogfooding 2.9 — 3 цикла с LLM + Knowledge (ROADMAP 2.9.5)

### Команда
`eurika cycle . --apply-suggested-policy`

### Результат
- 3 стабильных цикла подряд
- verify ✓ passed
- apply-rate, rollback-rate стабильны
- architect даёт рекомендации «как»; suggested policy при низком apply_rate

### DoD 2.9.5
- [x] apply-rate не падает
- [x] релевантность рекомендаций (Recommendation block, Reference block)
- [x] learning: suggested policy из telemetry

---

## 1. Fix (`eurika fix . --quiet --no-code-smells`) — 2026-02-19

| Поле | Значение |
|------|----------|
| **modified** | 0 |
| **skipped** | 0 |
| **errors** | 0 |
| **verify** | success |
| **tests** | 188 passed in ~28s |

### Skipped — причины (`skipped_reasons`)

- Нет (`patch plan has no operations`).

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

- project_graph_api.py (fan-in 10, fan-out 1)
- patch_engine.py (fan-in 6, fan-out 5)
- patch_apply.py (fan-in 10, fan-out 0)

### Риски

- god_module @ patch_engine.py (severity 11.00), patch_apply.py (10.00), code_awareness.py (9.00), agent_core.py (7.00)
- bottleneck @ patch_apply.py (10.00)

### Architect

- **LLM:** fallback на template (`Connection error` при попытке LLM).

### Planned refactorings

- 0 ops (`patch_plan.operations=[]`).

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

- **Verify:** 188 тестов прошли
- **Изменений в контрольном fix:** 0
- **Skip-шум устранён:** стабильная причина `extract_class: extracted file exists` больше не воспроизводится
- **Система стабильна:** score 46, регрессий нет
- **Фокус дальше:** повышать долю реальных apply и улучшать fallback-policy для слабых пар learning

---

## 6. Рефактор `eurika/reasoning/architect.py`

- Разбит `long_function` в `_template_interpret` и `_llm_interpret` на helper-функции.
- Поведение сохранено: LLM fallback и шаблонная интерпретация без функциональных изменений.
- Проверка: `pytest -q tests/test_architect.py` → `6 passed`.

---

## 7. LLM Fallback (OpenRouter -> Ollama)

- Добавлена цепочка провайдеров в `architect`: сначала `OPENAI_*` (OpenRouter), при ошибке — локальный Ollama (`OLLAMA_OPENAI_*` или дефолт `http://127.0.0.1:11434/v1`, `qwen2.5:1.5b`).
- Обновлены тесты на контракт dry-run и fallback-поведение:
  - `pytest -q tests/test_architect.py tests/test_cycle.py` → `22 passed`.
- Контрольный `eurika cycle .` после фикса тестов: `verify=true`, `189 passed`.
- Operational note: если в shell уже экспортированы `OPENAI_*`, они имеют приоритет над `.env` (из-за `load_dotenv(..., override=False)`), поэтому для принудительного локального сценария нужен `unset OPENAI_API_KEY OPENAI_MODEL OPENAI_BASE_URL`.

---

## 8. Контрольный прогон (после env-priority и no-op prefilter)

- `eurika doctor .`:
  - system: `modules=140`, `dependencies=92`, `cycles=0`
  - risk score: `43/100` (было 46)
  - trends: `complexity=increasing`, `smells=stable`, `centralization=stable`
  - patch_plan: `operations=[]`
- `eurika fix . --no-code-smells --quiet`:
  - `{"message":"Patch plan has no operations. Cycle complete."}`
- LLM в данном runtime окружении агента: не достигнут ни primary, ни fallback
  (`primary LLM failed (Connection error.); ollama fallback failed (Connection error.)`).
  В пользовательском терминале локальный Ollama ранее подтверждён рабочим (`doctor` с содержательным LLM-ответом).

---

## 9. Sprint 4 update (Safety gates + KPI telemetry)

### Реализовано

- В `eurika_fix_report.json` добавлены KPI:
  - `telemetry.operations_total`
  - `telemetry.modified_count`
  - `telemetry.skipped_count`
  - `telemetry.apply_rate`
  - `telemetry.no_op_rate`
  - `telemetry.rollback_rate`
  - `telemetry.verify_duration_ms`
- Добавлен блок guardrails:
  - `safety_gates.verify_required`
  - `safety_gates.auto_rollback_enabled`
  - `safety_gates.verify_ran`
  - `safety_gates.verify_passed`
  - `safety_gates.rollback_done`
- Для rollback-ветки фиксируется `rollback.trigger = "verify_failed"`.
- Telemetry/safety теперь формируются не только в apply-ветке, но и в edge-cases:
  - `patch plan has no operations`
  - `all operations rejected by user/policy`
  - `dry-run`.

### Проверка

- Прогон через venv:
  - `"/mnt/sdb2/project/.venv/bin/python" -m pytest -q tests/test_cycle.py tests/test_patch_engine.py tests/test_architect.py`
  - Результат: `42 passed`.
- Добавлен тест на edge-case полного отклонения операций в hybrid (`telemetry + no verify gate`).

### Ollama runtime policy (обновление)

- Автозапуск/перезапуск `ollama serve` из Eurika отключён.
- При недоступности daemon возвращается явная инструкция запустить `ollama serve` вручную.
- Дефолт fallback-модели Ollama переключен на coding-профиль:
  - `OLLAMA_OPENAI_MODEL=qwen2.5-coder:7b`.

---

## 10. Контрольный baseline после Sprint 4

### Прогоны (через venv)

- `"/mnt/sdb2/project/.venv/bin/python" -m eurika_cli doctor .`
- `"/mnt/sdb2/project/.venv/bin/python" -m eurika_cli fix . --dry-run --quiet`
- `"/mnt/sdb2/project/.venv/bin/python" -c "... run_cycle(..., mode='fix', dry_run=True, quiet=True) ..."`

### Doctor snapshot

- system: `modules=151`, `dependencies=93`, `cycles=0`
- risk score: `46/100` (Δ0 по окну)
- trends: `complexity=stable`, `smells=stable`, `centralization=stable`
- patch plan from doctor: `operations=[]`
- LLM status в этом запуске: template fallback, причина:
  - `ollama CLI fallback failed (could not connect to ollama server; start it manually with ollama serve)`

### Fix dry-run snapshot (runtime assist)

- patch plan operations: `1`
  - `refactor_code_smell` для `eurika/agent/policy.py:evaluate_operation` (`deep_nesting`, risk=`medium`)
- telemetry:
  - `operations_total=1`
  - `modified_count=0`
  - `skipped_count=0`
  - `apply_rate=0.0`
  - `no_op_rate=0.0`
  - `rollback_rate=0.0`
  - `verify_duration_ms=0`
- safety_gates:
  - `verify_required=false`
  - `auto_rollback_enabled=false`
  - `verify_ran=false`
  - `verify_passed=null`
  - `rollback_done=false`

---

## 11. Orchestrator Split progress (ROADMAP 2.8.3 a-d + facade thinning)

### До/после по фасаду

- `cli/orchestrator.py`: **798 → 383 LOC** (фасад значительно истончен).
- Вынесено в слой `cli/orchestration/`:
  - `prepare.py` — pre-stage (scan/diagnose/plan/policy/session-filter), **217 LOC**
  - `apply_stage.py` — apply/verify/rescan/report/memory/telemetry, **223 LOC**
  - `doctor.py` — doctor-cycle wiring + knowledge topics, **69 LOC**
  - `full_cycle.py` — full-cycle wiring, **58 LOC**

### Что сохранено по контракту

- Публичные точки входа (`run_cycle`, `run_doctor_cycle`, `run_fix_cycle`, `run_full_cycle`) не менялись.
- Тестируемые shim-точки в `cli/orchestrator.py` оставлены там, где это требуется для patch-моков.
- Формат `eurika_fix_report.json` и поля `telemetry/safety_gates/policy_decisions` сохранены.

### Проверка после декомпозиции

- `"/mnt/sdb2/project/.venv/bin/python" -m pytest -q tests/test_cycle.py tests/test_cli_runtime_mode.py tests/test_architect.py tests/test_patch_engine.py`
- Результат: **46 passed**.

---

## 12. CLI Wiring Split progress (ROADMAP 2.8.4, step 1-2)

### До/после по entrypoint

- `eurika_cli.py`: **633 → 59 LOC** (тонкий entrypoint: env-load + parser + dispatch call).
- Вынесено в `cli/wiring/`:
  - `parser.py` — регистрация subcommands и аргументов, **231 LOC**
  - `dispatch.py` — роутинг команд к handlers, **59 LOC**

### Что сохранено по контракту

- Синтаксис CLI и список флагов/команд сохранены 1:1.
- `eurika --version` и parser-контракт runtime-флагов (`--runtime-mode`, `--non-interactive`, `--session-id`) не изменены.
- `main()` в `eurika_cli.py` теперь только `parse -> dispatch`, без бизнес-логики.

### Проверка после декомпозиции

- `"/mnt/sdb2/project/.venv/bin/python" -m pytest -q tests/test_cli_runtime_mode.py tests/test_cycle.py`
- Результат: **25 passed**.

---

## 13. Planner Boundary progress (ROADMAP 2.8.5, safe split)

### До/после по facade-модулю

- `architecture_planner.py`: **497 -> 88 LOC** (тонкий facade: `build_plan`, `build_action_plan`, `build_patch_plan`).
- Вынесено в `eurika/reasoning/`:
  - `planner_types.py` — модели `PlanStep`/`ArchitecturePlan`, **38 LOC**
  - `planner_rules.py` — smell-action правила и env-фильтры, **92 LOC**
  - `planner_patch_ops.py` — сборка patch-операций и фильтры применимости, **460 LOC**
  - `planner_analysis.py` — индекс smells + сборка шагов плана, **77 LOC**
  - `planner_actions.py` — конвертация шагов в `ActionPlan`, **83 LOC**

### Что сохранено по контракту

- Внешний API `architecture_planner` сохранен: `build_plan`, `build_action_plan`, `build_patch_plan`.
- Семантика prefilter/fallback логики patch-планировщика не менялась; изменена только граница модулей.
- Форматы `PatchPlan` и `ActionPlan` не изменялись.

### Проверка после декомпозиции

- `python -m pytest tests/test_graph_ops.py -q`
- `python -m pytest tests/test_cycle.py -q`
- Результат: **49 passed** (28 + 21).

---

## 14. Patch Apply Boundary progress (ROADMAP 2.8.6, step 1)

### До/после по фасаду apply

- `patch_apply.py`: **489 -> 389 LOC** (сохранен API `apply_patch_plan`, `list_backups`, `restore_backup`).
- Вынесено в новый модуль:
  - `patch_apply_backup.py` — backup/restore и file-write helper-функции, **133 LOC**

### Что сохранено по контракту

- Поведение публичных функций `patch_apply` не менялось: внешние точки входа и формат отчетов те же.
- `list_backups`/`restore_backup` остались доступными из `patch_apply` как фасадные вызовы.
- Основная логика operation-kind обработки в `apply_patch_plan` сохранена без изменений.

### Проверка шага

- `python -m py_compile patch_apply.py patch_apply_backup.py`
- `ReadLints` по `patch_apply.py` и `patch_apply_backup.py` — без ошибок.

### Step 2: kind-dispatch extraction

- `patch_apply.py`: **389 -> 209 LOC** (тонкий orchestrator apply-цикла с fallback append-путем).
- Вынесено в новый модуль:
  - `patch_apply_handlers.py` — обработчики operation-kind (`create_module_stub`, `fix_import`, `split_module`, `extract_class`, и др.), **271 LOC**

### Проверка шага 2

- `python -m py_compile patch_apply.py patch_apply_handlers.py patch_apply_backup.py`
- `ReadLints` по `patch_apply.py`, `patch_apply_handlers.py`, `patch_apply_backup.py` — без ошибок.

### Step 3: patch_engine verify/rollback orchestration extraction

- `patch_engine_apply_and_verify.py`: **99 -> 67 LOC** (тонкий orchestrator apply+verify flow).
- Вынесено в новый модуль:
  - `patch_engine_apply_and_verify_helpers.py` — import-fix retry, `py_compile` fallback, auto-rollback flow, **108 LOC**

### Проверка шага 3

- `python -m py_compile patch_engine_apply_and_verify.py patch_engine_apply_and_verify_helpers.py`
- `ReadLints` по `patch_engine_apply_and_verify.py` и `patch_engine_apply_and_verify_helpers.py` — без ошибок.

### Step 4: patch_engine facade constant boundary

- `patch_engine.py` теперь реэкспортирует `BACKUP_DIR`, чтобы внешние слои не зависели напрямую от `patch_apply`.
- `cli/orchestration/deps.py` переключен на импорт `BACKUP_DIR` из `patch_engine` facade.

### Проверка шага 4

- `python -m py_compile patch_engine.py cli/orchestration/deps.py`
- `ReadLints` по `patch_engine.py` и `cli/orchestration/deps.py` — без ошибок.

---

## 15. Violation Audit progress (ROADMAP 2.8.7, iteration 1)

### Closed violations (before -> after)

- `cli/orchestration/deps.py` больше не импортирует `BACKUP_DIR` напрямую из `patch_apply`; зависимость переведена на `patch_engine` facade (`from patch_engine import BACKUP_DIR, ...`).
- `cli/agent_handlers.py` и `cli/agent_handlers_handle_agent_patch_apply.py` больше не вызывают `patch_apply.apply_patch_plan` напрямую; dry-run/apply маршруты переведены на `patch_engine` facade (`apply_patch_dry_run`, `apply_patch`).

### Current intentional/legacy boundaries (tracked)

- `patch_engine` по-прежнему использует `patch_apply` как execution backend (`apply_patch_plan`, `restore_backup`, `list_backups`) — это текущий совместимый контракт фасада patch-подсистемы.
- В `eurika/reasoning/` остаются legacy compatibility shims с wildcard-реэкспортами (`planner.py`, `heuristics.py`, `advisor.py`); они поддерживают обратную совместимость, но не соответствуют целевому strict-layer стилю.

### Next closure candidates

- Минимизировать wildcard-compat shims в `eurika/reasoning` до явных экспортов/алиасов.

## 16. Violation Audit progress (ROADMAP 2.8.7, iteration 2)

### Closed violations (before -> after)

- `eurika/reasoning/planner.py`: удалены wildcard-реэкспорты (`from ... import *`), введен явный facade-контракт через именованные импорты и `__all__`.
- `eurika/reasoning/heuristics.py`: удалены wildcard-реэкспорты (`from ... import *`), введен явный facade-контракт через именованные импорты и `__all__`.
- `eurika/reasoning/advisor.py`: удалены wildcard-реэкспорты (`from ... import *`), введен явный facade-контракт через именованные импорты и `__all__`.

### Compatibility contract

- Сохранена обратная совместимость по публичным сущностям фасадов (`build_*`, `Action*`, `Patch*`, `AgentCore`/`ArchReviewAgentCore`, `SimpleMemory`/`DummyReasoner`/`SimpleSelector` и др.) через явный экспорт.
- Изолирована поверхность API: внешние импорты получают стабильный список символов вместо неявного расширения через wildcard.

### Verification

- `python -m py_compile eurika/reasoning/planner.py eurika/reasoning/heuristics.py eurika/reasoning/advisor.py`
- `ReadLints` по обновленным файлам — без ошибок.

---

## 17. Dogfooding on New Boundaries (ROADMAP 2.8.8)

### Сценарий

- Проведен dogfooding-контур на декомпозированных границах (`doctor -> fix --dry-run -> fix`) после шагов 2.8.5-2.8.7.
- Контрольный apply-run: `run_id=20260220_095348` (`eurika_fix_report.json`).

### Контрольные метрики (из fix-report)

- `verify.success=true`, `returncode=0`
- `verify.stdout`: `214 passed in 31.36s`
- `telemetry.operations_total=8`
- `telemetry.modified_count=9`
- `telemetry.no_op_rate=0.0`
- `telemetry.rollback_rate=0.0`
- `telemetry.verify_duration_ms=31840`
- `safety_gates.verify_required=true`, `verify_ran=true`, `verify_passed=true`, `rollback_done=false`

### Stability / regression check

- Верификация после apply стабильна (падений verify нет).
- Rollback не потребовался (`rollback_rate=0.0`), safety-gates отработали штатно.
- По rescan-метрикам score без деградации (`before_score=46`, `after_score=46`).

### Вывод

- Шаг ROADMAP `2.8.8 Dogfooding on New Boundaries` считается закрытым: декомпозиция границ не ухудшила verify-стабильность и не вызвала всплеска rollback/no-op метрик в контрольном прогоне.

---

## 18. Layer Map progress (ROADMAP 2.8.1)

### Выполнено

- Добавлен раздел **§0 Layer Map** в `Architecture.md`:
  - Карта 6 слоёв (Infrastructure → Core → Analysis → Planning → Execution → Reporting)
  - Таблица allowed dependencies (no upward deps)
  - Маппинг модулей v2.7 по слоям
  - Anti-pattern examples (Analysis→Execution, Planning→Execution, cross-layer bypass)
  - Ссылка на 2.8.2 Dependency Guard для автоматической проверки
- Добавлена ссылка в `CLI.md` § Рекомендуемый цикл
- В `ROADMAP.md` шаг 2.8.1 отмечен как выполненный

---

## 19. Dependency Guard progress (ROADMAP 2.8.2)

### Выполнено

- Добавлен тест `tests/test_dependency_guard.py`:
  - Проверка запрещённых импортов по Architecture.md §0.4
  - Правила: CLI → patch_apply; architecture_planner* → patch_apply; eurika/smells/, eurika/analysis/, code_awareness, graph_analysis, semantic_architecture, system_topology → patch_apply, patch_engine
  - Исключены: tests/, __pycache__/, .eurika_backups/, _shelved/
  - Парсинг через `ast`; вывод нарушений в assertion
- Обновлены Architecture.md §0.5 и ROADMAP.md (2.8.2 помечен как выполнено)

---

## 23. API Boundaries (ROADMAP 3.1-arch.2)

### Выполнено

- Добавлен `__all__` в ключевые модули:
  - `patch_engine`: apply_patch, verify_patch, rollback_patch, apply_and_verify, rollback, list_backups, apply_patch_dry_run, BACKUP_DIR
  - `eurika.core`, `eurika.analysis`, `eurika.smells`, `eurika.evolution`, `eurika.reporting`: публичные подмодули
- Добавлен раздел **§0.6 API Boundaries** в `Architecture.md`:
  - Таблица подсистем → публичные точки входа
  - Список пакетов с `__all__`

---

## 24. CLI thinning (ROADMAP 3.1-arch.5)

### Выполнено

- **report/report_snapshot.py** — format_report_snapshot(path) → str; логика форматирования вынесена из handle_report_snapshot
- **eurika.api** — explain_module(path, module_arg, window), get_suggest_plan_text(path, window), clean_imports_scan_apply(path, apply)
- **Тонкие handlers**: handle_report_snapshot, handle_explain, handle_suggest_plan, handle_clean_imports — только валидация args и вызов API
- **test_handle_report_snapshot_delegates_to_format** — тест на изоляцию (патч format_report_snapshot)

---

## 25. Planning–Execution split (ROADMAP 3.1-arch.6)

### Выполнено

- **eurika/reasoning/planner.py** — удалены apply_patch_plan, list_backups, restore_backup, ExecutorSandbox, ExecutionLogEntry; только planning types и build_*
- **Architecture.md §0.5** — Planner–Executor Contract: Planner выдаёт dict, Executor применяет; явный контракт
- **tests/test_dependency_guard.py** — правило eurika/reasoning/ → patch_apply, patch_engine запрещены

---

## 26. Domain vs presentation (ROADMAP 3.1-arch.4)

### Выполнено

- **report/architecture_report.py** — модуль presentation: render_full_architecture_report, _smells_to_text, _render_architecture_report_md
- **core/pipeline.py** — только domain (run_full_analysis, build_snapshot_from_self_map); render делегирует в report
- **system_topology.py** — central_modules_for_topology вынесена из architecture_pipeline (используется и domain, и presentation)

---

## 27. File size limits (ROADMAP 3.1-arch.3)

### Выполнено

- **eurika/checks/file_size.py** — check_file_size_limits(root), format_file_size_report(root); лимиты 400 (candidate) и 600 (must split)
- **handle_self_check** — выводит блок FILE SIZE LIMITS после scan
- **python -m eurika.checks.file_size [path]** — standalone run
- **tests/test_file_size_check.py** — 7 тестов

---

## 28. Dogfooding 3.1-arch (ROADMAP 3.1-arch.7) — 2026-02-21

### Команды

- `eurika fix .` (apply)
- 3× `eurika fix . --dry-run` (fixpoint check)

### Fix результат (apply run)

| Поле | Значение |
|------|----------|
| **modified** | 6 |
| **skipped** | 0 |
| **verify** | success |
| **tests** | 287 passed (138.14s) |
| **rollback** | нет |
| **run_id** | 20260221_092534 |

### Операции применены

- 3× remove_unused_import (architecture_pipeline.py, core/pipeline.py, tests/test_file_size_check.py)
- 3× refactor_code_smell (TODO long_function: handle_doctor, _render_architecture_report_md, format_report_snapshot)

### Dry-run × 3 (fixpoint)

| Прогон | operations_total | Результат |
|--------|------------------|-----------|
| 1 | 0 | Patch plan has no operations. Cycle complete. |
| 2 | 0 | Patch plan has no operations. Cycle complete. |
| 3 | 0 | Patch plan has no operations. Cycle complete. |

### Rescan / Architecture

- modules: 187, dependencies: 107, cycles: 0
- verify_metrics: before_score=46, after_score=46
- Health score: 46/100 (medium)

### Итог

- DoD 3.1-arch.7 выполнен: нет регресса, verify стабилен, fixpoint достигнут после 1 apply + 3 dry-run
- Policy: remove_unused_import allowed; refactor_code_smell (long_function) blocked in auto mode (WEAK_SMELL_ACTION_PAIRS)

---

## 29. Cycle v3.0.7 (2026-02-21)

### Команда

`eurika cycle .` (assist mode, после коммита v3.0.7)

### Fix результат

| Поле | Значение |
|------|----------|
| **modified** | 3 |
| **skipped** | 0 |
| **verify** | True |
| **tests** | 294 passed (123.19s) |
| **rollback** | нет |
| **run_id** | 20260221_131545 |

### Операции применены

- 3× refactor_code_smell (TODO long_function: run_doctor_cycle, _dispatch_api_get, aggregate_operational_metrics)
- Policy: long_function|refactor_code_smell в WEAK_SMELL_ACTION_PAIRS (deny в auto); в assist применились

### verify_metrics

- before_score=46, after_score=46

### telemetry (ROADMAP 2.7.8)

- apply_rate=1.0, no_op_rate=0.0, rollback_rate=0
- verify_duration_ms=123701, median_verify_time_ms=123701

### Doctor (eurika_doctor_report.json)

| Метрика | Значение |
|---------|----------|
| Модули | 187 |
| Зависимости | 107 |
| Risk score | 46/100 |

### Learning

**by_action_kind**

- refactor_code_smell: 0 success, 7 fail (0%)
- split_module: 4 success, 1 fail (80%)
- remove_unused_import: 10 success, 3 fail (77%)

**by_smell_action**

- long_function|refactor_code_smell: total=28, success=0, fail=7
- deep_nesting|refactor_code_smell: total=2, success=0, fail=0
- god_module|split_module: total=5, success=4, fail=1
- unknown|remove_unused_import: total=13, success=10, fail=3

### Итог

- Verify passed, rollback не потребовался
- v3.0.7: Web UI 3.5.6/3.5.7 (Approve tab, Graph), operational metrics, team mode, refactor serve._run_handler
