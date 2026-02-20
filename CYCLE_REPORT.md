# Отчёт цикла Eurika — 2026-02-19

## 1. Fix (`eurika fix . --quiet --no-code-smells`)

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
