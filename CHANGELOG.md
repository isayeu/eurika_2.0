# Changelog — Eurika 2.0

All notable changes to this project will be documented in this file.

## v2.9.1 — Architect рекомендации «как» (ROADMAP 2.9.1) (2026-02-20)

### Features
- **Architect Recommendation block:** при наличии рисков (god_module, bottleneck, hub, cyclic_dependency) — блок «Recommendation (how to fix)» с конкретными шагами (split modules, introduce facade, decompose, break cycle).
- **Reference block:** отдельный блок «Reference (from documentation)» при наличии Knowledge; рекомендации ссылаются на него.
- **Smell → how mapping:** _SMELL_HOW_MAP, _parse_smell_from_risk, _build_recommendation_how_block в architect.

### Tests
- test_recommendation_how_block_and_parse_smell; test_template_interpret_minimal обновлён.

---

## v2.9.0 — Фаза 2.9 в ROADMAP (углубление цикла) (2026-02-20)

### Docs
- **ROADMAP:** добавлена **Фаза 2.9 — Углубление цикла (LLM + Knowledge + Learning)** — приоритет над 3.0.
- Шаги: 2.9.1 Architect → рекомендации «как»; 2.9.2 LLM в планировании; 2.9.3 Knowledge PEP/RFC; 2.9.4 Обучение в цикле; 2.9.5 Dogfooding.
- Следующий горизонт: текущий приоритет — 2.9 (глубина) перед 3.0 (широта).

---

## v3.0.1 — Multi-Repo Scan (2026-02-20)

### Features (ROADMAP 3.0.1)
- **scan, doctor, fix, cycle:** принимают несколько путей: `eurika scan path1 [path2 ...]`; последовательное выполнение по каждому; при N>1 выводятся заголовки `--- Project N/M: path ---`.
- Parser: `path` nargs="*", default [.]; handler `_paths_from_args` нормализует в список Path.

### Tests
- test_multi_repo_scan: два проекта, scan по обоим, проверка self_map.json.

---

## v2.7.1 — policy: refactor_code_smell in WEAK_SMELL_ACTION_PAIRS (2026-02-20)

### Policy
- **WEAK_SMELL_ACTION_PAIRS:** добавлены `long_function|refactor_code_smell` и `deep_nesting|refactor_code_smell` — по данным learning 0% success; в hybrid требуют manual approval, в auto блокируются; деприоритизированы в плане.

### Docs (2.1.3)
- ROADMAP: «Что по-прежнему не хватает» — Граф и Memory помечены выполненными (Фазы 3.1, 3.2); таблица «Версия 2.1» — замкнутый цикл, Event, Граф, операции обновлены; refactor_code_smell в таблице операций; ссылка review_vs_codebase заменена на WEAK_SMELL_ACTION_PAIRS.
- ROADMAP: добавлена **Фаза 3.0 — Architectural AI Engineer** — дорожная карта с 3.0.1 (multi-repo), 3.0.2 (cross-project memory), 3.0.3 (online knowledge), 3.0.4 (team-mode); критерии готовности, зависимости, DoD.
- eurika_cli/parser: версия 2.7.1.

---

## v2.7.0 — native agent runtime + safety gates + Ollama coding fallback defaults (2026-02-19)

### Features
- Добавлен нативный runtime-цикл с режимами `assist|hybrid|auto` для `fix/cycle/doctor` (policy engine, explainability, session-memory, hybrid approval).
- В отчёт `eurika_fix_report.json` добавлены telemetry и safety gates: `apply_rate`, `no_op_rate`, `rollback_rate`, `verify_duration_ms`, `verify_required`, `verify_ran`, `verify_passed`, `rollback_done`.
- Для edge-cases (`dry-run`, `patch plan has no operations`, `all operations rejected`) telemetry/safety теперь формируются детерминированно.

### LLM/Ollama
- Отключён автозапуск/перезапуск `ollama serve` из Eurika; daemon должен запускаться вручную.
- Дефолт fallback-модели Ollama переключён на coding-профиль: `qwen2.5-coder:7b`.
- Обновлены тесты fallback-веток и контрактов CLI/runtime.

---

## v2.6.16 — architecture_planner: fix _apply_learning_bump nonlocal SyntaxError (2025-02-19)

### Bugfix
- **_apply_learning_bump:** `nonlocal expected_benefit` в standalone-функции вызывал `SyntaxError: no binding for nonlocal 'expected_benefit' found` — nonlocal работает только во вложенных функциях.
- Решение: функция принимает `expected_benefit` как параметр и возвращает обновлённое значение; `_step_to_action` присваивает результат обратно.
- Тесты: 183 passed.

---

## v2.6.15 — extract_nested_function: skip functions with nonlocal/global (2025-02-15)

### Bugfix
- **suggest_extract_nested_function:** пропуск вложенных функций с `nonlocal` или `global` — их извлечение приводит к SyntaxError (no binding for nonlocal).
- Пример: `_apply_learning_bump` в `_step_to_action` использовал `nonlocal expected_benefit`; при извлечении на уровень модуля nonlocal становился невалидным.
- Добавлен `_has_nonlocal_or_global()` check перед добавлением в candidates.

### Tests
- test_suggest_extract_nested_function_skips_when_nonlocal.

---

## v2.6.14 — extract_nested_function: real fix for long_function when nested exists (2025-02-15)

### Real refactor for long_function
- **eurika/refactor/extract_function.py:** new module — moves nested function to module level when it doesn't use parent locals (no closure dependency).
- **get_code_smell_operations:** for long_function, tries suggest_extract_nested_function first; if extractable nested found, creates kind="extract_nested_function" (real fix) instead of refactor_code_smell (TODO).
- **patch_apply:** handler for extract_nested_function — calls extract_nested_function, writes modified content.

### Tests
- tests/test_extract_function.py: suggest, skip when uses parent locals, extract, not found.
- test_apply_extract_nested_function in test_patch_apply.

---

## v2.6.13 — Fix skipped ops: refactor_code_smell when architectural TODO exists (2025-02-15)

### Skip logic fix
- **patch_apply:** marker skip (# TODO: Refactor {target}) only for refactor_module and split_module. refactor_code_smell uses different format — can add long_function/deep_nesting TODOs to files that already have architectural TODO.
- Eurika cycle previously modified=[] because all files had architectural TODOs and we blocked all ops. Now refactor_code_smell ops are applied.

### Debug
- **skipped_reasons:** report includes per-file skip reason (path not found, diff already in content, architectural TODO already present, etc.).

### Tests
- test_apply_patch_plan_refactor_code_smell_not_skipped_by_architectural_todo.

---

## v2.6.12 — py_compile fallback when pytest finds no tests (2025-02-15)

### Verify fallback
- **apply_and_verify:** при pytest returncode 5 ("no tests collected") и verify_cmd=None — fallback на `python -m py_compile` по изменённым .py файлам; если py_compile успешен, rollback не выполняется.
- Проекты без pytest (binance/bbot и др.) — изменения сохраняются при валидном синтаксисе.
- **DOGFOODING.md:** раздел «Проекты без pytest» — варианты verify_cmd, pyproject.toml.

### Tests
- test_apply_and_verify_py_compile_fallback_when_no_tests.

---

## v2.6.11 — Facade protection: exclude patch_engine/patch_apply from split and clean (2025-02-15)

### Problem
Fix cycle repeatedly broke patch_engine: split_module removed re-exports, remove_unused_import deleted facade imports → ImportError on verify → rollback.

### Solution
- **architecture_planner:** FACADE_MODULES = {patch_engine.py, patch_apply.py} — skip split_module/refactor_module for these targets.
- **eurika/api get_clean_imports_operations:** skip facade modules; their imports are re-exports, not unused.
- patch_engine.py, patch_apply.py — critical facades; cycle no longer modifies them destructively.

---

## v2.6.10 — patch_engine/verify_patch extraction, patch_apply _backup_file (2025-02-15)

### patch_engine
- **patch_engine_verify_patch:** выделен verify_patch и _get_verify_cmd с полной поддержкой verify_cmd (override, pyproject.toml).
- **patch_engine_apply_and_verify:** выделен apply_and_verify (orchestration: apply → verify → retry → rollback) — результат split_module в fix cycle.
- patch_engine.py — тонкий фасад: импортирует apply_patch, rollback_patch, verify_patch, apply_and_verify; API без изменений.

### patch_apply
- **_backup_file:** вспомогательная функция — убирает дублирование логики backup в handlers.
- **_try_split_module_chain:** общая логика split_module_by_import → by_class → by_function; убрано дублирование между split_module и refactor_module.
- Все операции используют _backup_file.

---

## v2.6.9 — Code-level smells in fix cycle (long_function, deep_nesting) (2025-02-15)

### Code smells in patch plan

- **get_code_smell_operations:** новый API — сканирует CodeAwareness.find_smells, возвращает ops с kind="refactor_code_smell" для long_function и deep_nesting.
- **Orchestrator:** fix cycle добавляет code_smell ops в patch plan (после clean_imports).
- **patch_apply:** kind="refactor_code_smell" — добавляет TODO-комментарий в файл (default append-diff).
- **--no-code-smells** — опция fix/cycle/watch, исключает refactor_code_smell из плана (аналог --no-clean-imports).
- Подсказки: "consider extracting helper" для long_function, "consider extracting nested block" для deep_nesting.
- Тесты: test_apply_refactor_code_smell_appends_todo, test_get_code_smell_operations_returns_ops_for_long_function, test_fix_no_code_smells_excludes_code_smell_ops.

---

## v2.6.8 — extract_class: module-level constants + fix_import NameError (2025-02-15)

### extract_class: module-level constants
- **extract_class:** при экстракции методов добавляет в extracted-модуль используемые модульные константы (напр. GOALS_FILE).
- _get_module_level_assignments, _names_used_in_node; импорты для констант (Path и др.) подтягиваются автоматически.
- Тест: test_extract_class_includes_module_level_constants.

### fix_import_from_verify: NameError
- **fix_import_from_verify:** обработка NameError (name 'X' is not defined) — поиск определения X в других модулях, добавление в failing file.
- Для goals_goalsystemextracted.py без GOALS_FILE — добавляет `GOALS_FILE = Path('goals.json')` из goals.py.
- Тесты: test_parse_name_error, test_suggest_fix_name_error_adds_constant.

---

## v2.6.7 — fix_import_from_verify: авто-исправление ModuleNotFoundError (2025-02-15)

### fix_import_from_verify

- **Новая операция:** при провале verify (pytest) с ModuleNotFoundError или ImportError Eurika парсит вывод, предлагает fix и применяет его (retry).
- **Стратегии:** 1) перенаправить импорт (если символ найден в другом модуле); 2) создать минимальный stub-модуль (load_*, *_FILE).
- **Интеграция:** apply_and_verify с retry_on_import_error=True (по умолчанию) — после первого verify при импорт-ошибке применяет fix и повторяет verify.
- **Патч-операции:** create_module_stub, fix_import (в patch_apply).
- Тесты: tests/test_fix_import_from_verify.py.
- Прогон на eurika: internal_goals.py создан автоматически, первый verify пройден.

---

## v2.6.6 — Configurable verify command (2025-02-15)

### fix/cycle: --verify-cmd

- **patch_engine:** verify_patch и apply_and_verify принимают `verify_cmd` — переопределение команды верификации.
- **Приоритет:** `--verify-cmd` > `[tool.eurika] verify_cmd` в pyproject.toml > pytest -q.
- **CLI:** `eurika fix . --verify-cmd "python manage.py test"`, `eurika cycle . --verify-cmd "..."`.
- Для проектов без pytest (Django, unittest и т.д.) — настраиваемая verify.
- Тесты: test_verify_patch_custom_cmd, test_verify_patch_pyproject_verify_cmd.
- CLI.md обновлён.

---

## v2.6.5 — Dogfooding: code_awareness cycle (2025-02-15)

### Cycle artifacts

- **code_awareness:** split_module + extract_class (CodeAwarenessExtracted, code_awareness_extracted).
- bottleneck: 7 → 6.
- Дополнительные циклы: clean-imports, мелкие правки в extracted-модулях.

---

## v2.6.4 — split_module: повышение операционности (2025-02-15)

### split_module

- **split_module_by_function:** новый fallback — экстракция standalone top-level функций в отдельный модуль.
- **split_module_by_import:** при пустом params.imports_from — inference stems из AST модуля.
- **Relax extraction:** defs с несколькими импортами из imports_from теперь экстрагируются (assign to stem cluster).
- **Module-level constants:** _module_level_names() — не экстрагировать defs, использующие модульные константы (избежание NameError после extract).
- Цепочка: split_module_by_import → split_module_by_class → split_module_by_function.
- Тесты: test_apply_split_module_by_function_fallback, test_apply_split_module_extracts_when_def_uses_multiple_imports, test_apply_split_module_by_function_skips_when_uses_module_constant.

### Cycle artifacts (dogfooding)

- Добавлены артефакты успешного цикла: extracted-модули (agent_core, action_plan, patch_apply, orchestrator, agent_handlers, patch_engine, runtime_scan), фасады (action_plan_api, code_awareness_api).

### extract_class: imports for type hints

- **extract_class:** собирает используемые импорты (включая type hints в сигнатурах) и добавляет их в extracted-модуль.
- Фикс NameError при методах с `path: Path` и др.
- Тест: test_apply_extract_class_includes_type_hint_imports.

### refactor_module (ROADMAP: реальный фикс вместо TODO)

- **patch_apply:** kind="refactor_module" теперь пробует split_module chain (by_import → by_class → by_function) до fallback на append diff.
- Тест: test_apply_refactor_module_produces_real_split.

### Git

- self_map.json исключён из tracking (уже в .gitignore).

---

## v2.6.2 — watch + performance-based filter (ROADMAP 2.6.2, 2.6.3) (2025-02-15)

### eurika watch [path]

- **2.6.2:** команда `eurika watch .` — мониторинг .py файлов (polling по mtime), при изменении запускает fix.
- Опции: `--poll SEC` (интервал опроса, default 5), `--quiet`, `--no-clean-imports`, `--window`.
- Ctrl+C для остановки.

### Performance-based improvement (2.6.3)

- **architecture_planner:** при learning_stats — операции с success_rate < 0.25 и total >= 3 исключаются из плана.
- Тест: test_build_patch_plan_filters_low_success_rate_ops.

---

## v2.6.1 — Auto-run mode, версии по ROADMAP (2025-02-15)

**Версии следуют ROADMAP:** major.minor = фаза (2.1, 2.3, 2.6, 3.0), patch = инкремент в фазе.

### eurika fix / eurika cycle --interval SEC

- **--interval SEC:** повторять цикл каждые SEC секунд (0 = один раз). Остановка: Ctrl+C.
- Реализует часть v2.6 «auto-run mode» (review.md).
- CLI.md обновлён.

---

## v1.2.22 — Фикс обрезки описаний и architect max_tokens (2025-02-15)

### explain: Planned operations

- **cli/core_handlers:** описания операций в `eurika explain` обрезаются по границе слова (max 200 символов), а не посередине фразы.
- Раньше: `desc[:80]` давал обрывы вида «Refactor module ac»; теперь — полная фраза до последнего пробела.
- **eurika explain --window N:** опция для окна истории patch-plan (по умолчанию 5). CLI.md, DOGFOODING обновлены.
- **README, CLI.md:** напоминание — для LLM (doctor, architect, cycle) запускать через venv из `/mnt/storage/project/` (иначе только шаблон architect).
- **Прогоны на других проектах:** scan + doctor проверены на farm_helper (5 модулей), optweb (38 модулей) — отработали штатно.

### architect

- **eurika/reasoning/architect.py:** `max_tokens` увеличен с 150 до 350 — ответы LLM (в т.ч. «Key Actions») не обрываются на полуфразе.

---

## v1.2.21 — introduce_facade: реальный handler для bottleneck (2025-02-15)

### introduce_facade

- **eurika/refactor/introduce_facade.py** — создаёт `{stem}_api.py`, реэкспортирующий публичные символы bottleneck. Уменьшает прямой fan-in.
- **patch_apply:** handler `kind="introduce_facade"` — вызывает introduce_facade, создаёт новый файл. Раньше был только append TODO.
- **Тесты:** test_apply_introduce_facade, test_apply_introduce_facade_skips_when_api_exists.
- **Повышение операционности:** bottleneck теперь даёт реальный фикс (фасад), а не TODO.

---

## v1.2.20 — CI-ready: документация и тест exit code (2025-02-15)

### CI/CD

- **CLI.md:** новая секция «CI/CD» — рекомендуемые команды (`eurika fix . --quiet`, `--dry-run --quiet`, `eurika cycle . --quiet --no-llm`), семантика exit code (0/1).
- **README:** добавлена строка про CI.
- **Тест:** test_fix_quiet_exit_code_success — проверка, что fix --quiet возвращает 0 при успехе.

---

## v1.2.19 — Дедупликация modified, EurikaOrchestrator (2025-02-15)

### Изменения

- **patch_apply:** список `modified` в отчёте дедуплицируется (один файл, несколько операций — одна запись).
- **EurikaOrchestrator:** формальный класс в cli/orchestrator.py (review.md Part 1); делегирует run_cycle; OOP-интерфейс для цикла.
- **Тесты:** test_apply_patch_plan_dedupes_modified, test_eurika_orchestrator_run.

---

## v1.2.18 — ROADMAP по обновлённому review (2025-02-15)

### Обновление по review.md

- **ROADMAP:** Горизонт 3 переписан как Roadmap до 3.0 (v2.1 Execution Milestone, v2.3 Stability, v2.6 Semi-Autonomous, v3.0 AI Engineer).
- **review_vs_codebase.md:** добавлена секция «Обновление review» — сопоставление Orchestrator Core design и roadmap v2.1–v3.0 с текущим кодом.
- **LLM:** зафиксировано — усиливать только после 2.1; в 3.0 — smarter planner, adaptive refactor, historical memory.
- **Orchestrator:** отмечено, что cli/orchestrator.py реализует цикл; EurikaOrchestrator (core/) — опциональный следующий шаг; режимы: хирургическая интеграция или новая архитектура.

---

## v1.2.17 — Интеграция remove_unused_import в fix cycle (ROADMAP 2.4) (2025-02-15)

### Fix cycle включает clean-imports

- **eurika fix**, **eurika cycle** по умолчанию добавляют операции `remove_unused_import` в план (файлы с неиспользуемыми импортами).
- **patch_apply:** handler `kind="remove_unused_import"` — вызывает `remove_unused_imports`, применяет результат.
- **eurika.api.get_clean_imports_operations(project_root)** — возвращает список ops для patch_plan.
- **--no-clean-imports** — опция fix/cycle, отключает добавление clean-imports.
- **ROADMAP:** блок «Причина низкой операционности (TODO vs реальные фиксы)»; фаза 2.4 реализована.
- **Тесты:** test_apply_remove_unused_import, test_fix_cycle_includes_clean_imports_ops, test_fix_no_clean_imports_excludes_clean_ops.

### Причина низкой операционности (review)

- Зафиксировано в ROADMAP: patch часто = append TODO, а не код. Путь к повышению — расширять реальные handlers; clean-imports — первый шаг.

---

## v1.2.16 — Актуализация ROADMAP и документации (2025-02-15)

### Обновления

- **ROADMAP:** текущее состояние v1.2.15; review §7 пункт 4 (граф) отмечен выполненным; фазы 3.1, 3.2 отражены.
- **README, CLI.md:** команда `eurika cycle`; артефакты в `.eurika/`; learning/feedback — views над events.
- **eurika --version:** 1.2.15.

---

## v1.2.15 — Команда cycle, пояснение --no-llm (2025-02-15)

### eurika cycle — полный ритуал одной командой

- **eurika cycle .** — scan → doctor (report + architect) → fix. Один вызов вместо трёх.
- Опции: --window, --dry-run, --quiet, --no-llm (architect без API ключа).

### --no-llm

- Используется для детерминированного шаблонного вывода architect (без OPENAI_API_KEY).
- Применение: CI, окружения без сети, ускорение. С LLM architect даёт более развёрнутые рекомендации.

---

## v1.2.14 — Контекст для architect (ROADMAP 3.2.3) (2025-02-15)

### Architect использует последние события в промпте

- **EventStore.recent_events(limit, types)** — последние N событий, фильтр по типам (patch, learn).
- **eurika/api.get_recent_events(project_root, limit, types)** — единая точка доступа.
- **architect**: `_format_recent_events`, параметр `recent_events` в `interpret_architecture`; блок «Recent actions» в template и LLM prompt.
- **handle_architect**, **run_doctor_cycle** — передают `recent_events` в architect.
- Тесты: test_event_store_recent_events, test_architect_includes_recent_events, test_format_recent_events.

---

## v1.2.13 — Event как первичная сущность (ROADMAP 3.2.2) (2025-02-15)

### Learning и feedback — views над EventStore

- **eurika/storage/event_views.py** — LearningView, FeedbackView: append → events.append_event(type="learn"|"feedback"); all() и aggregate_* выводят из events.by_type().
- **ProjectMemory.learning / .feedback** возвращают views вместо LearningStore/FeedbackStore.
- Автомиграция: при первом append/all legacy learning.json/feedback.json переносятся в events и удаляются.
- Типы событий: добавлен "feedback".

---

## v1.2.12 — Консолидация storage (ROADMAP 3.2.1) (2025-02-14)

### Единый каталог хранения .eurika/

- **eurika/storage/paths.py** — STORAGE_DIR, storage_path(), migrate_if_needed(), ensure_storage_dir().
- Все артефакты памяти в `project_root/.eurika/`: events.json, learning.json, feedback.json, observations.json, history.json.
- **ProjectMemory** и **event_engine** используют consolidated paths.
- Автомиграция: при первом доступе файлы из legacy путей (eurika_events.json, architecture_*.json и т.п.) копируются в .eurika/.
- Тесты: test_migration_from_legacy_path (feedback, learning, observations, events).

---

## v1.2.11 — Инициация операций графом (ROADMAP 3.1.4) (2025-02-14)

### Граф передаёт цели в patch_plan

- **graph_ops.targets_from_graph(graph, smells, ...)** — список целей (name, kind, reasons) из graph.nodes; фильтр по наличию в графе.
- **build_patch_plan** при наличии graph использует targets_from_graph; params для split_module и introduce_facade строятся из graph.edges (suggest_god_module_split_hint, suggest_facade_candidates).
- Тест test_targets_from_graph.

---

## v1.2.10 — Граф как база метрик (ROADMAP 3.1.3) (2025-02-14)

### Граф как единый источник метрик

- **graph_ops.metrics_from_graph(graph, smells, trends)** — risk_score, health level и centrality из графа; делегирует compute_health, добавляет centrality_from_graph.
- **graph_ops.centrality_from_graph(graph)** — max_degree, top_by_degree.
- **history.append** использует metrics_from_graph вместо compute_health напрямую.
- **orchestrator** verify_metrics использует metrics_from_graph для before/after.
- Тесты: test_centrality_from_graph, test_metrics_from_graph.

---

## v1.2.9 — Триггер операций по типам smell (ROADMAP 3.1.2) (2025-02-14)

### Граф как движок — smell_type → refactor_kind

- **graph_ops.SMELL_TYPE_TO_REFACTOR_KIND, refactor_kind_for_smells()** — канонический маппинг smell_type → refactor_kind: god_module→split_module, hub→split_module, bottleneck→introduce_facade, cyclic_dependency→break_cycle.
- **architecture_planner** использует refactor_kind_for_smells вместо _decide_step_kind; hub теперь триггерит split_module (раньше refactor_module).
- **DIFF_HINTS** добавлены для (hub, split_module).
- Тесты: test_refactor_kind_for_smells, test_smell_type_to_refactor_kind_canonical, test_build_patch_plan_hub_produces_split_module.

---

## v1.2.8 — Learning при skip, рефакторинг runtime_scan (2025-02-14)

### Исправление Learning при modified=[]

- **orchestrator, agent_handlers:** при `modified=[]` (все операции пропущены) не вызывается `memory.learning.append`. Исключено завышение success rate для не применённых операций.
- Тест `test_learning_not_appended_when_all_skipped`.

### Рефакторинг runtime_scan → ProjectMemory.record_scan

- **ProjectMemory.record_scan(observation)** — вынос записи scan observation и event в storage.
- **runtime_scan:** вызов `memory.record_scan(observation)` вместо inline-логики; удалены дубликаты TODO.

---

## v1.2.7 — Приоритизация из графа (ROADMAP 3.1.1) (2025-02-14)

### Граф как движок — приоритизация модулей

- **priority_from_graph(graph, smells, summary_risks, top_n)** в `eurika.reasoning.graph_ops`: возвращает упорядоченный список модулей для рефакторинга, комбинируя severity из smells, degree (fan-in + fan-out), бонусы для god_module/hub (fan-out) и bottleneck (fan-in), плюс summary_risks. ROADMAP 3.1.1.
- **get_patch_plan** использует `priority_from_graph` вместо ручного подсчёта scores; patch_plan сортирует операции по приоритету из графа.
- Тесты: `test_priority_from_graph_orders_by_severity_and_degree`, `test_priority_from_graph_includes_summary_risks`.

---

## v1.2.6 — Сохранение отчётов doctor и fix --dry-run (2025-02-14)

### Стабилизация — прогон тестов, doctor, fix --dry-run

- **pytest:** полный прогон — 126 passed.
- **eurika doctor . --no-llm:** выполнен успешно; вывод содержит блок Reference из Knowledge Layer.
- **eurika fix . --dry-run:** выполнен успешно; patch_plan с 8 операциями (split_module, introduce_facade), файлы не изменены.
- **ROADMAP, REPORT:** «Следующий горизонт» уточнён — Knowledge Layer отмечен реализованным; дальше стабилизация, использование, опционально наполнение кэша и ReleaseNotes.

### Синхронизация с обновлённым review.md

- **review.md** обновлён: концептуальный разбор (аналитик vs агент), таблица оценок (архитектурная структура, качество кода, концепция, операционность, продуктовая готовность, потенциал), стратегическое заключение (Patch Engine, Verify, Event Engine → автономный инструмент), вывод — долгосрочно Eurika как AI-агент с самоусовершенствованием.
- **REPORT.md:** таблица зрелости приведена к формулировкам review; добавлен блок «В ответ на review реализовано» и отсылка к долгосрочной цели из review.
- **ROADMAP.md:** оценка зрелости и диагноз переписаны по актуальному review; зафиксировано выполнение плана прорыва и долгосрочная цель (AI-агент).
- **Architecture.md:** блок «Оценка по review.md и направление 2.1» обновлён: кратко актуальный диагноз и вывод review; 2.1 отмечен выполненным.

### Общий Orchestrator run_cycle (фаза 2.3.2)

- **run_cycle(path, mode="doctor"|"fix", ...)** — единая точка входа. Handlers doctor и fix вызывают run_cycle вместо run_doctor_cycle/run_fix_cycle. Неизвестный mode возвращает {"error": "Unknown mode: ..."}. Тест test_run_cycle_single_entry_point.

### Цикл 2.1, обновление REPORT

- Выполнен scan → doctor → fix --dry-run; REPORT обновлён (фазы 2.2, 2.3.1 выполнены; 131 passed).

### Наполнение eurika_knowledge.json (фаза 2.2.3)

- Добавлены темы: `version_migration` (Python/deps upgrade), `security` (vulnerable deps, deprecated), `async_patterns` (async/await). Обновлены `eurika_knowledge.json` и `docs/eurika_knowledge.example.json`. KNOWLEDGE_LAYER обновлён.

### Кэш сетевых ответов Knowledge (фаза 2.2.2)

- **OfficialDocsProvider, ReleaseNotesProvider:** поддержка `cache_dir` и `ttl_seconds` (по умолчанию 24h). При `eurika doctor` и `eurika architect` ответы сохраняются в `path/.eurika/knowledge_cache/`; при повторном запуске без сети или в пределах TTL используется кэш. `.eurika/` добавлен в .gitignore. Тест `test_official_docs_provider_uses_cache`. Документация в KNOWLEDGE_LAYER.md.

### Артефакты в .gitignore

- `self_map.json`, `eurika_knowledge.json` добавлены; все runtime-артефакты (self_map, doctor/fix отчёты, backups) — в .gitignore. DOGFOODING: блок «Артефакты и Git».

### Orchestrator / фасад циклов (фаза 2.3.1)

- **cli/orchestrator.py:** единая точка управления циклами: `run_doctor_cycle(path, window, no_llm)` и `run_fix_cycle(path, window, dry_run, quiet)`. Логика стадий (scan → diagnose → plan → patch → verify) собрана в одном модуле; doctor и fix вызывают фасад, handlers остаются тонкими (I/O и вывод). Подбор тем Knowledge вынесен в `_knowledge_topics_from_env_or_summary` в orchestrator, используется doctor и architect.

### Knowledge: чистка HTML в _fetch_url (фаза 2.2.1)

- В **OfficialDocsProvider** и **ReleaseNotesProvider** при загрузке страниц: удаляются блоки `<script>...</script>` и `<style>...</style>`; после снятия тегов обрезается ведущий boilerplate (Python X documentation, Skip to main content, Navigation и т.п.) до первого осмысленного блока (What's New in Python, Summary и т.д.). Фрагменты в Reference без мусора в начале. Добавлен тест `test_fetch_html_cleanup`.

### Knowledge: явная пустая карта topic_urls (багфикс)

- **OfficialDocsProvider, ReleaseNotesProvider:** при передаче `topic_urls={}` использовался дефолтный allow-list (`topic_urls or DEFAULT`), из‑за чего тесты test_*_topic_not_in_map падали при наличии сети. Исправлено: дефолт только при `topic_urls is None`; явная пустая карта `{}` даёт пустой результат по любой теме. Verify при `eurika fix` после этого проходит.

### ROADMAP — переписан с учётом основной задачи (саморазвитие)

- **ROADMAP.md:** добавлен блок «Принцип ROADMAP»: основная задача сейчас — саморазвитие, анализ и исправление собственного кода, добавление функций по запросу; работа в первую очередь над собой; долгосрок — полноценный агент (очень далеко). «Следующий горизонт» и фаза 2.1 переформулированы: фокус на работе над собой (scan/doctor/fix по eurika, функции по запросу, стабилизация); прогоны на других проектах и полный fix на Eurika — опционально. Фазы 2.2–2.3 и горизонт 3 приведены в соответствие с этой логикой. Заголовок упрощён до «ROADMAP» (без «до v1.0»).
- **REPORT.md:** формулировка «Следующий горизонт» обновлена под новую фазу 2.1.

### REPORT, ROADMAP — основная задача (сейчас)

- **REPORT.md:** добавлен пункт «Основная задача (сейчас)»: саморазвитие, анализ и исправление собственного кода, добавление новых функций по запросу; Eurika в первую очередь работает над собой.
- **ROADMAP.md:** в «Текущее состояние» добавлена формулировка основной задачи; использование на других проектах указано как вторичное.

### ROADMAP, REPORT — видение полноценного агента (далёкое будущее)

- **ROADMAP.md (Горизонт 3):** направление сформулировано как «Полноценный агент (далёкое будущее)»: универсальный агент — звонки, финансы, код по запросу, собственная LLM и т.д.; проекты pphone, mind_games, binance, eurika, farm_helper, pytorch приведены как примеры диапазона областей, не как исчерпывающий список.
- **REPORT.md:** блок переименован в «Видение (далёкое будущее)»; акцент на агенте с разными способностями; примеры проектов — иллюстрация областей.

### ROADMAP — следующие шаги (горизонт 2 и 3)

- **ROADMAP.md:** добавлен блок «Следующие шаги (горизонт 2 и далее)» с приоритизированными фазами без жёстких сроков. **Фаза 2.1** — стабилизация и использование (прогоны на проектах, багфиксы, актуализация доков). **Фаза 2.2** — качество Knowledge Layer (чистка HTML в _fetch_url, опционально кэширование сетевых ответов, наполнение кэша). **Фаза 2.3** — Orchestrator / единая точка управления циклом (фасад run_doctor_cycle / run_fix_cycle). **Горизонт 3** — долгосрок по review: граф как движок, единая модель памяти, самоусовершенствование. Таблицы с задачами и критериями готовности по каждой фазе.
- **REPORT.md:** «Следующий горизонт» переведён на отсылку к ROADMAP § Следующие шаги.

### Knowledge Layer — тема python_3_12 по умолчанию

- **Теми по умолчанию:** в `_knowledge_topics_from_env_or_summary` добавлена тема `python_3_12` (вместе с `python`). Без env в Reference попадают фрагменты из OfficialDocs и ReleaseNotes по What's New 3.12 (при доступной сети).
- **tests/test_cycle.py:** test_knowledge_topics_derived_from_summary обновлён — ожидается `["python", "python_3_12"]` и наличие `python_3_12` в остальных кейсах.
- **docs/KNOWLEDGE_LAYER.md:** уточнено описание тем по умолчанию.

### Knowledge Layer — CompositeKnowledgeProvider, doctor/architect используют сеть

- **CompositeKnowledgeProvider:** объединяет несколько провайдеров; по каждой теме запрашивает всех и склеивает фрагменты, добавляя к заголовку префикс источника `[source]`.
- **doctor и architect:** вместо одного LocalKnowledgeProvider передаётся Composite из Local + OfficialDocsProvider + ReleaseNotesProvider. В блоке Reference появляются фрагменты из локального кэша и (при доступной сети и теме из allow-list) из официальной документации и release notes.
- **eurika.knowledge:** экспорт CompositeKnowledgeProvider. Тест test_composite_knowledge_provider_merges_fragments.
- **docs/KNOWLEDGE_LAYER.md:** обновлено описание интеграции (Composite, три провайдера).

### Knowledge Layer — ReleaseNotesProvider с curated URL (сеть)

- **ReleaseNotesProvider:** реализован запрос по allow-list `RELEASE_NOTES_TOPIC_URLS` (python_3_12, python_3_11 → What's New), по образцу OfficialDocsProvider; stdlib urllib, timeout 5 с. Конструктор принимает опциональные `topic_urls` и `timeout`.
- **tests/test_knowledge.py:** тесты `test_release_notes_provider_topic_not_in_map`, `test_release_notes_provider_unknown_topic_returns_empty`, `test_release_notes_provider_fetch_mocked`.
- **docs/KNOWLEDGE_LAYER.md:** описание ReleaseNotesProvider обновлено.

### Knowledge Layer — OfficialDocsProvider с curated URL (сеть)

- **OfficialDocsProvider:** реализован запрос по фиксированному allow-list: `OFFICIAL_DOCS_TOPIC_URLS` (topic → url), по умолчанию python_3_12 и python_3_11 (What's New). Используется только stdlib `urllib.request`, таймаут 5 с; HTML упрощается до текста (strip tags), один фрагмент до 8000 символов. При отсутствии темы в списке или ошибке сети возвращается пустой ответ.
- **tests/test_knowledge.py:** тесты `test_official_docs_provider_topic_not_in_map`, `test_official_docs_provider_fetch_mocked` (мок urlopen).
- **docs/KNOWLEDGE_LAYER.md:** обновлено описание OfficialDocsProvider.

### Knowledge Layer — подбор тем по диагнозу, несколько тем

- **interpret_architecture:** параметр `knowledge_topic` может быть строкой или списком строк; при списке запрашиваются все темы и фрагменты объединяются.
- **doctor и architect:** темы по умолчанию выводятся из summary: базовая `python`; при `system.cycles > 0` добавляется `cyclic_imports`; при наличии в risks слов god_module/hub/bottleneck — `architecture_refactor`. Функция `_knowledge_topics_from_env_or_summary` в cli/core_handlers; при заданной переменной `EURIKA_KNOWLEDGE_TOPIC` (через запятую для нескольких тем) используется она.
- **docs/KNOWLEDGE_LAYER.md:** обновлено описание интеграции (подбор тем по диагнозу, несколько тем).
- **tests/test_cycle.py:** тест `test_knowledge_topics_derived_from_summary` — проверка вывода тем по summary и по env.

### Knowledge Layer — наполнение кэша

- В **eurika_knowledge.json** и **docs/eurika_knowledge.example.json** добавлены темы: **deprecated_api** (release notes, replacement APIs), **typing** (PEP 484, mypy/pyright, 3.12 generics), **cyclic_imports** (TYPE_CHECKING, отдельный модуль для общих типов). Тема по умолчанию для doctor — `python`; при необходимости задайте `EURIKA_KNOWLEDGE_TOPIC=typing` или `cyclic_imports` и т.д.
- **docs/KNOWLEDGE_LAYER.md:** в описании примера перечислены все темы.

### Dogfooding: eurika_knowledge.json в корне, DOGFOODING

- **eurika_knowledge.json** в корне проекта (содержимое как в docs/eurika_knowledge.example.json): при `eurika doctor .` вывод архитектора включает блок Reference из Knowledge Layer.
- **DOGFOODING.md:** комментарий в шаге doctor про eurika_knowledge.json; новая секция «Knowledge Layer (doctor)»; в результатах прогона — упоминание Reference при наличии кэша.
- **REPORT.md:** количество тестов обновлено (123 passed).

### Knowledge Layer — README, интеграционный тест (после 1.0)

- **README.md:** в описании `eurika doctor` добавлено упоминание опционального `eurika_knowledge.json` и `EURIKA_KNOWLEDGE_TOPIC`; в списке документации уточнён пункт про docs/KNOWLEDGE_LAYER.md и пример eurika_knowledge.example.json.
- **tests/test_cycle.py:** интеграционный тест `test_doctor_includes_knowledge_when_cache_present` — при наличии eurika_knowledge.json (тема python) вывод `eurika doctor --no-llm` содержит «Reference» и контент из кэша. Вспомогательная функция `_minimal_self_map`.

### Knowledge Layer — REPORT, ROADMAP, пример кэша (после 1.0)

- **REPORT.md:** блок «Следующий горизонт» обновлён — Knowledge Layer с интеграцией doctor/architect и eurika_knowledge.json отражён как выполненный начальный этап.
- **ROADMAP.md:** в «Следующий горизонт» добавлен пункт про начальную реализацию Knowledge Layer; следующий шаг — наполнение кэша и опционально сетевые провайдеры.
- **docs/eurika_knowledge.example.json:** пример файла кэша (темы python, python_3_12, architecture_refactor) для копирования в корень проекта.
- **docs/KNOWLEDGE_LAYER.md:** ссылка на пример в разделе про формат кэша.

### Knowledge Layer — интеграция в architect, StaticAnalyzer, док (после 1.0)

- **StaticAnalyzerProvider:** заглушка (source `static_analyzer`), экспорт из `eurika.knowledge`. Тест `test_static_analyzer_provider_stub`.
- **Интеграция в architect:** `interpret_architecture(..., knowledge_provider=..., knowledge_topic=...)`. При передаче провайдера и темы вызывается `query(topic)`; фрагменты форматируются (`_format_knowledge_fragments`) и подставляются в промпт LLM и в шаблонный вывод (блок «Reference»). Обратная совместимость: параметры опциональны.
- **doctor и architect:** в `handle_doctor` и `handle_architect` передаётся `LocalKnowledgeProvider(path / "eurika_knowledge.json")` и тема из env `EURIKA_KNOWLEDGE_TOPIC` (по умолчанию `python`). При наличии файла кэша фрагменты по теме попадают в вывод архитектора.
- **docs/KNOWLEDGE_LAYER.md:** раздел «Реализация» — интеграция с doctor/architect; формат `eurika_knowledge.json` (структура `topics`, нормализация ключа).
- **tests/test_architect.py:** `test_interpret_architecture_with_knowledge` — проверка появления «Reference» и контента фрагмента при передаче провайдера с кэшем.

### Knowledge Layer — кэш Local и заглушки провайдеров (после 1.0)

- **LocalKnowledgeProvider:** загрузка кэша из JSON (`cache_path`). Формат: `{"topics": {"topic_id": [{"title": "...", "content": "..."}, ...]}}`. Нормализация темы в ключ (`_topic_key`: lowercase, пробелы → `_`). При отсутствии файла или ошибке парсинга — пустой ответ.
- **OfficialDocsProvider, ReleaseNotesProvider:** добавлены как заглушки (без сетевых вызовов): `query(topic)` возвращает `StructuredKnowledge` с соответствующим `source` и пустыми `fragments`.
- **eurika.knowledge:** экспорт `OfficialDocsProvider`, `ReleaseNotesProvider` из пакета.
- **tests/test_knowledge.py:** тесты загрузки кэша (`test_local_knowledge_provider_loads_cache`), отсутствия кэша, заглушек OfficialDocs/ReleaseNotes (всего 7 тестов).

### Knowledge Layer — проектирование и скелет (после 1.0)

- **docs/KNOWLEDGE_LAYER.md:** контракт Knowledge Provider, провайдеры (Local, OfficialDocs, ReleaseNotes, StaticAnalyzer), схема интеграции с LLM и Patch engine, источники по review.md.
- **eurika.knowledge:** пакет с `KnowledgeProvider` (ABC), `StructuredKnowledge` (topic, source, fragments, meta), `LocalKnowledgeProvider` (заглушка, пустой ответ). Без сетевых вызовов.
- **tests/test_knowledge.py:** тесты контракта и LocalKnowledgeProvider.

### Полный цикл fix на Eurika и fix --dry-run на других проектах

- **farm_helper, optweb:** выполнены **fix --dry-run** (успешно, план строится).
- **Eurika:** выполнен **eurika fix .** (без --dry-run) с venv: scan → plan → apply (часть операций skipped) → **verify (pytest 113 passed)** → rescan → **verify_metrics (46→46)**. Откат не потребовался.
- **REPORT.md:** в «Проверка стабильности» добавлены полный fix на Eurika и fix --dry-run на farm_helper/optweb.

### Стабилизация: тесты и проверка на других проектах

- **Тесты:** 113 passed (pytest с venv).
- **farm_helper, optweb (с правами на запись):** полный **scan** (артефакты в каталогах проектов) и **doctor --no-llm** выполнены успешно. farm_helper: 5 модулей, risk 80; optweb: 38 модулей, risk 80.
- **DOGFOODING.md:** секция «Использование на других проектах» (проекты в `/mnt/storage/project`, примеры команд).

### Управляющие документы: план прорыва выполнен

- **REPORT.md:** «Выполнено» приведено в соответствие с планом прорыва (Patch Engine, Verify, Event Engine, CLI 4, dogfooding); диагноз обновлён; блок «Следующий горизонт» — стабилизация, использование на других проектах, Knowledge Layer.
- **ROADMAP.md:** блок «Следующий шаг» заменён на «План прорыва выполнен» и «Следующий горизонт» (стабилизация, использование, опционально fix без dry-run, Knowledge Layer).

### Dogfooding (ROADMAP)

- Прогнан полный цикл на проекте Eurika с venv: **/mnt/storage/project/venv/bin/python** — scan → doctor (с LLM) → fix --dry-run (успешно).
- **DOGFOODING.md:** путь к venv `/mnt/storage/project/venv` (без него LLM не работает); примеры с `$PY -m eurika_cli` и `source …/venv/bin/activate`.

### CLI — 4 продуктовых режима (ROADMAP этап 5)

- **eurika_cli.py:** разбивка на _add_product_commands (scan, doctor, fix, explain) и _add_other_commands; продуктовые команды регистрируются первыми — в usage и help они идут первыми.
- **handle_help:** блок «Product (4 modes):» — только scan, doctor, fix, explain; «Other» и «Advanced (eurika agent …)» для остальных. Версия в help обновлена до v1.2.6.
- **epilog:** «Product (4 modes): scan | doctor | fix | explain».

### Event Engine (ROADMAP этап 4)

- **eurika/storage/event_engine.py:** единая точка входа **event_engine(project_root)** → EventStore; контракт Event { type, input, action, result, timestamp } (action в сериализации = output).
- **eurika/storage/events.py:** Event.to_dict() добавляет поле `action` (равно output); Event.from_dict() принимает `action` как синоним `output`.
- **eurika/storage/memory.py:** ProjectMemory.events получает хранилище через event_engine(project_root).
- **eurika/storage:** экспорт Event, EventStore, event_engine из __init__.py.
- **Тесты:** test_event_engine_entry_point, test_event_to_dict_includes_action, test_event_from_dict_accepts_action.

### Фиксация Knowledge Layer в документах (по обновлённому review.md)

- **ROADMAP.md:** раздел «После 1.0 — Knowledge Layer» — порядок (сначала детерминизм, потом Knowledge layer), контракт Knowledge Provider, ссылка на review.md.
- **Architecture.md:** подраздел «Knowledge Layer / онлайн-слой (после 1.0)» — абстракция, схема LLM → Knowledge → Patch → Verify.
- **REPORT.md:** в таблице документов у review.md и ROADMAP указано про Knowledge Layer.

### Verify Stage — метрики и откат при ухудшении (ROADMAP этап 3)

- **handle_agent_cycle:** после успешного pytest и rescan сравниваются health score (compute_health) до и после патча. Если after_score < before_score, выполняется **rollback_patch** и в отчёт добавляются **verify_metrics** (success: false, before_score, after_score) и **rollback** (reason: "metrics_worsened"). Сообщение в stderr: «Metrics worsened (health X → Y); changes rolled back.»
- **Этап 2 в ROADMAP** отмечен выполненным (три операции уже в коде).

### Patch Engine — целевой API и автооткат (ROADMAP этап 1)

- **patch_engine.py:** добавлены явные операции **apply_patch(project_root, plan, backup=...)** (только применение), **verify_patch(project_root, timeout=...)** (pytest), **rollback_patch(project_root, run_id=None)** (восстановление из бэкапа). **rollback** оставлен как алиас для rollback_patch.
- **apply_and_verify:** параметр **auto_rollback=True** (по умолчанию): при провале verify автоматически вызывается rollback_patch; в отчёт добавляется ключ **rollback** (done, run_id, restored, errors).
- **cli/agent_handlers:** цикл fix вызывает apply_and_verify(..., auto_rollback=True); при провале verify выводится «Tests failed; changes rolled back automatically.» если откат выполнен.
- **Тесты:** test_apply_patch_only, test_verify_patch_returns_dict, test_rollback_patch_same_as_rollback, test_apply_and_verify_auto_rollback_on_failure; test_apply_and_verify_modifies_files дополнен проходящим pytest в tmp_path.

### Синхронизация управляющих документов (review + ROADMAP)

- **REPORT.md:** обновлён под оценку зрелости из review.md, диагноз, следующий шаг (прорыв вглубь), таблица документов.
- **README.md:** добавлен блок «Текущий фокус»; описание Patch Engine приведено к целевым apply/verify/rollback; список документации обновлён.
- **SPEC.md:** добавлен раздел «Текущий фокус» — операционный прорыв, без расширения reasoning.
- **Architecture.md:** оценка 2.1 переформулирована как целевое состояние; Patch Engine и память — текущее состояние и цель (event_engine, целевой API).
- **CLI.md:** в рекомендуемый цикл добавлена цель Verify (перескан + откат); целевое упрощение до 4 режимов (ROADMAP этап 5).
- **ROADMAP.md** (ранее): оценка зрелости, «что не хватает», план прорыва (этапы 1–5), стратегический вывод.

### doctor: сохранение в eurika_doctor_report.json

- **handle_doctor:** отчёт (summary, history, architect, patch_plan) сохраняется в `eurika_doctor_report.json` в корне проекта по умолчанию.
- По аналогии с `eurika fix` → `eurika_fix_report.json`.

### fix --dry-run: сохранение в eurika_fix_report.json

- **handle_agent_cycle:** при `--dry-run` сохраняется `eurika_fix_report.json` с ключами `dry_run: true` и `patch_plan`.

---

## v1.2.4 — Увеличение доли успешно применяемых патчей (2025-02-14)

### split_module: fallback split_module_by_class

- **eurika.refactor.split_module:** `split_module_by_class()` — извлечение крупнейшего self-contained класса (≥3 методов, без ссылок на другие top-level defs) в новый модуль, когда split_module_by_import возвращает None.
- **patch_apply:** для split_module сначала пробует import-based split, при провале — class-based.
- Тест: test_apply_split_module_by_class_fallback.

### Приоритеты: топ-8 вместо топ-5

- **architecture_planner:** priorities[:8] — agent_core_arch_review (с god_class) чаще попадает в план, extract_class может примениться.

### Post-fix: исправления после split_module_by_class

- **agent_core_arch_review_archreviewagentcore:** исправлен баг `store.aggregate_by_action_kind()` → `memory.learning.aggregate_by_action_kind()` (NameError при пустом aggregate_by_smell_action).
- **agent_core_arch_review.py:** упрощён до чистого фасада (реэкспорт ArchReviewAgentCore), удалены лишние импорты, добавлен `__all__`.
- **Регрессия:** eurika scan + fix --dry-run на optweb (38 модулей, Django) — проходит без ошибок.

---

## v1.2.5 — Architect/Explain связка с patch-plan (ROADMAP §7)

### Пункт 7: подсказки архитектора связаны с patch-plan и explain

- **eurika.api:** `get_patch_plan(project_root, window)` — строит PatchPlan из диагностики.
- **eurika architect:** получает patch_plan и передаёт в LLM/шаблон; выводит «Planned refactorings: N ops (kinds); top targets».
- **eurika explain:** секция «Planned operations (from patch-plan)» — операции, затрагивающие модуль.
- **LLM prompt:** при OPENAI_API_KEY в prompt добавлен блок с planned operations.
- **architecture_planner:** импорт graph_ops перенесён внутрь build_patch_plan (устранён circular import).
- Тесты: test_template_interpret_with_patch_plan, test_get_patch_plan_*.

---

## v1.2.3 — AST-based extract_class (2025-02-14)

### god_class: детекция и автофикс через extract_class

- **eurika.refactor.extract_class:** `suggest_extract_class(file_path, min_methods=6)` — находит классы с ≥6 методами и предлагает extractable (без self.attr) методы.
- **architecture_planner:** при god_module вызывается suggest_extract_class; при успехе добавляется op extract_class.
- **eurika.smells.detector:** REMEDIATION_HINTS["god_class"] — hint для extract_class.
- Тесты: test_suggest_extract_class_*, test_build_patch_plan_god_module_with_god_class_produces_extract_class.

### extract_class: извлечение методов в новый класс

- **eurika.refactor.extract_class:** извлечение методов, не использующих self, в новый класс (в отдельный файл). Методы становятся @staticmethod.
- **patch_apply:** обработка kind=extract_class с params.target_class и params.methods_to_extract.
- Тесты: test_apply_extract_class, test_apply_extract_class_skips_when_methods_use_self.

### split_module: fallback на TODO

- **patch_apply:** когда split_module_by_import возвращает None (нет экстрагируемых defs), fallback — append diff (TODO-подсказки) вместо полного skip.

### fix: сохранение отчёта по умолчанию

- **handle_agent_cycle:** отчёт fix (modified, skipped, rescan_diff, verify) сохраняется в `eurika_fix_report.json` в корне проекта.

## v1.2.2 — AST-based split_module (2025-02-14)

### split_module: фактическая экстракция

- **eurika.refactor.split_module:** AST-based split — выделяет функции/классы, которые используют только один из imports_from, в новый модуль `*_extracted.py`.
- **patch_apply:** обработка kind=split_module с params.imports_from — вызывает split_module_by_import вместо append TODO.
- Тесты: test_apply_split_module, test_apply_split_module_skips_when_no_extractable.

## v1.2.1 — clean-imports: TYPE_CHECKING и __all__ (2025-02-14)

### remove_unused_import: сохранение нужных импортов

- **`if TYPE_CHECKING:`** — импорты внутри блока считаются используемыми (аннотации часто строки при `from __future__ import annotations`).
- **`__all__`** — имена из `__all__ = [...]` считаются используемыми (реэкспорты фасадов).
- Тесты: test_keep_imports_under_type_checking, test_keep_imports_in_all.

## v1.2.0 — Стабилизация и продуктовый CLI (2025-02-14)

### split_module: отдельный kind для god_module

- **architecture_planner:** для god_module создаётся `kind=split_module` вместо `refactor_module`; params: `imports_from`, `imported_by` из suggest_god_module_split_hint.
- **Тест:** test_build_patch_plan_god_module_produces_split_module.

### bottleneck: exemption *_api.py

- **eurika.smells.models.detect_bottlenecks:** модули `*_api.py` исключены — фасады по конвенции имеют высокий fan-in, это ожидаемо.
- **Тест:** test_bottleneck_exempts_facade_api.

### Продуктовый CLI

- **eurika** (без аргументов) — выводит краткий обзор; product commands (scan, doctor, fix, clean-imports) в приоритете.
- **--version, -V** — вывод версии.
- **handle_help:** продуктовая структура — 4 команды сверху, «Other», «Advanced (agent)».
- **CLI.md:** обновлён обзор (eurika без args, --version).

### Документация

- **review.md:** добавлена секция «Обновление по ревью (v1.1.x)» — таблица реализации пунктов ревью, обновлённые оценки.

### Стабилизация

- Проверка на внешних проектах (farm_helper, rozygrysh, eurika, optweb).
- venv exclusion устраняет зависание на проектах с зависимостями.

## v1.1.1 — god_module и clean-imports для фасадов (2025-02-14)

### scan: exclude venv, .venv, node_modules

- **CodeAwareness.scan_python_files:** каталоги `venv`, `.venv`, `node_modules`, `.git` исключены из сканирования — ускоряет анализ проектов с зависимостями.
- **Тест:** test_scan_excludes_venv_and_node_modules.

### clean-imports: skip *_api.py

- **handle_clean_imports:** файлы `*_api.py` пропускаются (как `__init__.py`) — фасады реэкспортируют импорты через `__all__`, AST не видит использование имён из строк.
- **Тест:** test_clean_imports_skips_api_facades.

### Ослабление god_module

- **eurika.smells.models.detect_god_modules:** модули `*_api.py` полностью исключены из детекции god_module — фасады по конвенции имеют высокий fan-in, это ожидаемо, а не smell.
- **Тест:** test_god_module_exempts_facade_api.

## v1.1.0 — Полировка и Killer-feature (2025-02-14)

### Защита от дубликатов TODO

- **patch_apply:** при append diff проверка маркера `# TODO: Refactor {target_file}` — если уже есть, skip (предотвращает дубли при варьировании graph hints).
- **Тест:** test_apply_patch_plan_skips_when_marker_exists.

### Remove Unused Imports (Killer-feature: dead code)

- **eurika.refactor.remove_unused_import:** AST-based removal of unused imports.
- **eurika clean-imports [path]:** CLI command; dry-run by default, `--apply` to write. Skips __init__.py (re-exports).
- **Тесты:** tests/test_remove_unused_import.py.

### Killer UX (eurika fix)

- **Человекочитаемая сводка:** после `eurika fix` (и `--dry-run`) выводится блок «--- Eurika fix complete ---» с: Modified N file(s), Operations (по kind), Verify ✓/✗. При remove_cyclic_import — строка «Broke N cyclic dependency(ies)».
- **Шаги:** Step 1 scan, 2 diagnose, 3 plan/patch, 4 verify. Однострочный контекст «scan → diagnose → plan → patch → verify».

### Remove Cyclic Import (ROADMAP 2.1 — архитектурные операции)

- **eurika.refactor.remove_import:** AST-based удаление импорта из Python-файла.
- **PatchOperation.params:** опциональное поле для remove_cyclic_import: `{"target_module": str}`.
- **build_patch_plan:** при cyclic_dependency + graph + self_map создаёт remove_cyclic_import вместо TODO-блока; resolve_module_for_edge находит модуль для разрыва.
- **patch_apply:** обработка kind=remove_cyclic_import — вызывает remove_import_from_file вместо append.
- **Тесты:** tests/test_remove_import.py, tests/test_patch_apply_remove_import.py, test_build_patch_plan_creates_remove_cyclic_import_when_cycle.

### Граф как инструмент (ROADMAP 2.1 / review.md)

- **eurika.reasoning.graph_ops:** модуль графовых операций для планирования патчей:
  - `suggest_cycle_break_edge(graph, cycle_nodes)` — предложение ребра (src, dst) для разрыва цикла (эвристика: наименьший fan-in dst).
  - `suggest_facade_candidates(graph, bottleneck_node)` — callers bottleneck'а (кандидаты для facade).
  - `suggest_god_module_split_hint(graph, god_node)` — imports_from / imported_by для hints по разбиению.
  - `graph_hints_for_smell(graph, smell_type, nodes)` — конкретные hints по типу smell.
- **architecture_planner.build_patch_plan:** новый параметр `graph: Optional[ProjectGraph]`; при наличии — diff hints обогащаются graph-derived предложениями.
- **ArchReviewAgentCore:** `_load_structure` возвращает (summary, smells, graph); graph передаётся в `_build_patch_plan`.
- **Тесты:** `tests/test_graph_ops.py` (11 тестов: graph_ops + интеграция с build_patch_plan).

### Patch Engine (ROADMAP 2.1 / review.md)

- **Модуль `patch_engine.py`:** единый фасад для применение плана и верификации.
  - **apply_and_verify(project_root, plan, backup=..., verify=..., verify_timeout=120)** — вызов patch_apply.apply_patch_plan + при verify запуск pytest; возвращает отчёт с modified, run_id, verify (success, returncode, stdout, stderr).
  - **rollback(project_root, run_id=None)** — восстановление из `.eurika_backups` (аналог restore_backup).
  - **list_backups(project_root)** — список run_id.
- **cli/agent_handlers:** цикл fix и команда patch-apply с --verify переведены на patch_engine.apply_and_verify; patch-rollback использует patch_engine.rollback. Удалён прямой вызов subprocess pytest из handlers.
- **Тесты:** `tests/test_patch_engine.py` (6 тестов: apply_and_verify с verify и без, rollback по run_id и latest, list_backups).

### Единая модель Event (ROADMAP 2.1 / review.md)

- **eurika.storage.events:** модель **Event** (type, input, output, result, timestamp) и **EventStore** (append_event, all(), by_type()); хранение в `eurika_events.json` (до MAX_EVENTS записей).
- **ProjectMemory.events** — доступ к единому логу событий.
- Запись событий: при **scan** (runtime_scan) — type=scan, output=summary (files, total_lines, smells_count); при **patch** (handle_agent_cycle, handle_agent_patch_apply с --verify) — type=patch, output=modified/run_id/verify_success, result=verify_success.
- **Тесты:** `tests/test_storage_events.py` (Event roundtrip, EventStore append/all/by_type, ProjectMemory.events).

---

## v1.0.0 — Релиз

Первый стабильный релиз. Все пункты ROADMAP разделов 1–6 выполнены.

### Входит в v1.0

- **Ядро:** pipeline (scan → graph → smells → summary → history → diff → report), ArchitectureSnapshot, core/cli handlers
- **Пакет eurika/:** реализация в eurika.smells (detector, models, health, advisor, summary), eurika.analysis.metrics, eurika.evolution (history, diff); плоские модули — реэкспорты
- **History engine:** version, git_commit, risk_score, diff metrics, smell history, регрессии
- **Smell engine:** severity_to_level, remediation_hints, корреляция с history
- **Diff engine:** structural diff, centrality shifts, recommended actions, bottleneck modules
- **CLI:** eurika scan, arch-summary, arch-history, history, report, arch-diff, self-check, explain, **serve**
- **JSON API:** eurika.api (get_summary, get_history, get_diff), `eurika serve` — HTTP GET /api/summary, /api/history, /api/diff
- **Документация:** README, Architecture.md, ROADMAP.md, CHANGELOG, CLI.md, THEORY.md

Раздел 7 (мини-AI) запланирован после v1.0.

### Мини-AI слой (ROADMAP §7)

- **eurika.reasoning.architect**: `interpret_architecture(summary, history, use_llm=True)` — короткая интерпретация "архитектор проекта" (2–4 предложения). По умолчанию шаблонная; при `OPENAI_API_KEY` опционально вызывается LLM, при ошибке — откат на шаблон с сообщением в stderr.
- **Поддержка OpenRouter:** переменные `OPENAI_BASE_URL` (например `https://openrouter.ai/api/v1`) и `OPENAI_MODEL` (например `mistralai/mistral-small-3.2-24b-instruct`). Без них используется стандартный OpenAI (модель по умолчанию `gpt-4o-mini`).
- **Загрузка .env:** при установленном `python-dotenv` CLI загружает `.env` из текущего каталога; ключ и URL можно не экспортировать вручную. Опциональная зависимость: `pip install eurika[env]`.
- **eurika architect [path]** — команда CLI: загружает summary и history через eurika.api, выводит интерпретацию. Флаги: `--window N`, `--no-llm` (только шаблон).
- Тесты: `tests/test_architect.py` (_template_interpret, interpret_architecture с use_llm=False).

### Полировка CLI (v1.0)

- **--json** для `report`, `arch-summary`, `arch-history`, `history`, `arch-diff` — вывод в JSON (machine-readable) вместо текста. Для `report --json` — объект с ключами `summary` и `history`.
- **--window** для `report`, `arch-history`, `history` — размер окна истории (по умолчанию 5).
- **Единые сообщения об ошибках:** префикс `eurika:`, короткие формулировки (path does not exist, not a directory, old/new self_map not found, module required, ambiguous module).
- **Справка:** заголовок обновлён до v1.0, добавлена строка про использование `--json` с report/history/arch-summary/arch-diff.

---

## v0.9.x — Migration to eurika/* (target layout)

Реализация перенесена из плоских модулей в пакет `eurika/`; плоские файлы оставлены как реэкспорты для обратной совместимости.

### Перенесённая реализация

- **eurika.smells.detector** — из `architecture_diagnostics.py` (detect_architecture_smells, severity_to_level, get_remediation_hint, REMEDIATION_HINTS)
- **eurika.smells.models** — из `architecture_smells.py` (ArchSmell, detect_smells, detect_cycle_smells, detect_god_modules, detect_bottlenecks, detect_hubs)
- **eurika.smells.health** — из `architecture_health.py` (compute_health, health_summary)
- **eurika.smells.advisor** — из `architecture_advisor.py` (build_recommendations)
- **eurika.smells.summary** — из `architecture_summary.py` (build_summary, summary_to_text, SummarySection)
- **eurika.analysis.metrics** — из `graph_analysis.py` (summarize_graph)
- **eurika.evolution.history** — из `architecture_history.py` (ArchitectureHistory, HistoryPoint, trend, evolution_report, detect_regressions)
- **eurika.evolution.diff** — из `architecture_diff.py` (ArchSnapshot, build_snapshot, diff_snapshots, diff_architecture_snapshots, diff_to_text, main_cli)

### Фасады (реэкспорт плоских модулей)

- `eurika.analysis`: graph, scanner, self_map, topology, cycles
- `eurika.evolution`: history, diff (реализация в пакете; плоские architecture_history, architecture_diff — реэкспорты)
- `eurika.reporting`: text, markdown
- `eurika.core`: pipeline, snapshot

### Документация

- REPORT.md, ROADMAP.md, Architecture.md приведены в соответствие с текущим состоянием миграции.

### JSON API (ROADMAP §2.3)

- **eurika.api**: модуль с функциями `get_summary(project_root)`, `get_history(project_root, window)`, `get_diff(old_self_map, new_self_map)` — возвращают JSON-сериализуемые dict для summary, history, diff.
- **eurika serve**: команда CLI запускает HTTP-сервер (stdlib); GET `/api/summary`, `/api/history?window=5`, `/api/diff?old=...&new=...`; по умолчанию порт 8765, хост 127.0.0.1.
- Тесты: `tests/test_api.py` (get_summary/get_history/get_diff и json.dumps).

### Стабилизация после миграции

- Добавлены тесты, явно использующие API из пакета: `tests/test_evolution_diff.py` (build_snapshot, diff_snapshots, diff_to_text из eurika.evolution.diff), в `test_architecture_history.py` — test_evolution_report_from_eurika_evolution_history (evolution_report из eurika.evolution.history).

---

## v0.8.2 — Smells × History

- `ArchitectureHistory.evolution_report(window)` дополнился секцией **Smell history (window)**:
  - Показывает дельты по типам smells между первой и последней точкой окна:
    - `god_module: 1 → 3 (Δ 2)`
    - `bottleneck: 0 → 2 (Δ 2)`
    - `hub: 1 → 1 (Δ 0)`
- Это даёт быстрый обзор, какие классы архитектурных проблем растут/падают во времени.

---

## v0.8.1 — Diff metrics in history

- `ArchitectureHistory.evolution_report(window)` теперь показывает явные дельты (Δ) между oldest и newest в окне:
  - Modules, Dependencies, Cycles, Total smells, Max degree, Risk score (если доступен).
- Пример блока:

  - `Modules: 51 → 54 (Δ 3)`
  - `Dependencies: 94 → 102 (Δ 8)`
  - `Total smells: 6 → 8 (Δ 2)`

---

## v0.8.0 — Smells 2.0

### Severity level

- `architecture_diagnostics.severity_to_level(severity: float)` → `low` | `medium` | `high` | `critical`
- Thresholds: <5 low, <12 medium, <20 high, ≥20 critical

### Remediation hints

- `REMEDIATION_HINTS` — dict по типам smell (god_module, bottleneck, hub, cyclic_dependency)
- `get_remediation_hint(smell_type)` — подсказка «что делать»
- Отчёты (text + markdown) показывают level и hint для каждого smell

### Tests

- `tests/test_architecture_diagnostics.py` — severity_to_level, get_remediation_hint

---

## Documentation reform (post-v0.7)

**Объединение управляющих документов:**

- **SPEC.md** — единый контракт; объединены SPEC v0.1 + drafts v0.2–v0.4 + AGENT_DESIGN
- **ROADMAP.md** — единый roadmap; объединены TODO + TASKS
- **REPORT.md** — сокращён до краткого статуса
- **docs/archive/** — V01_MINIMAL_PROPOSAL, AUDIT, eurika_v_1, AGENT_DESIGN_v0.2, SPEC_v0.2/3/4_draft
- Удалены: TODO.md, TASKS.md (содержимое в ROADMAP)

---

## v0.7.0 — CLI UX (color, ASCII, markdown)

### Report UX layer (`report/ux.py`)

- **Color output** — ANSI codes, TTY-aware via `should_use_color(force=None)`; `--color` / `--no-color` for scan and self-check
- **ASCII mini-charts** — `ascii_bar(value, max_val, width)` → `[████░░░░░░] 40/100`; used for health score and risk score in evolution report
- **Markdown export** — `--format markdown` / `-f markdown` for scan and self-check; `format_observation_md()` and `_render_architecture_report_md()` produce markdown reports

### CLI options

- **eurika scan** — `--format {text|markdown}`, `--color`, `--no-color`
- **eurika self-check** — same options

### Package layout

- `report.py` removed; `report/` package with `report/ux.py` (format_observation, format_observation_md, health_summary_enhanced, ascii_bar, should_use_color)

---

## v0.6.0 — History Engine + Documentation

### Documentation (§6)

- **README.md** — обновлён: pipeline, History v0.6, ссылки на CLI.md, THEORY.md
- **Architecture.md** — обновлён: pipeline layout, ArchitectureSnapshot, evolution path v0.5/v0.6
- **CLI.md** — новый: полный справочник команд с примерами
- **THEORY.md** — новый: идеология, принципы, self-analysis ritual

### History model (v0.6)

- **HistoryPoint**: version (from pyproject.toml), git_commit (optional), risk_score (0–100)
- **Version**: read from `[project] version` in pyproject.toml
- **Git hash**: optional short hash if `.git` exists; omitted when no git
- **Risk score**: computed via `compute_health()`, stored per history point; shown in evolution report

### Regression detection

- Per-type smell growth: god_module, bottleneck, hub tracked separately in `detect_regressions()`
- evolution_report shows Version, Git (if present), Risk score for latest snapshot

---

## v0.5.0 — Core Pipeline Stabilization

### Pipeline & ArchitectureSnapshot

- `core/pipeline.py` — `run_full_analysis(path)` → ArchitectureSnapshot; `build_snapshot_from_self_map(path)` для arch-diff
- `core/snapshot.py` — ArchitectureSnapshot (graph, smells, summary, history, diff)
- `render_full_architecture_report(snapshot)` — рендеринг полного отчёта из snapshot
- `run_full_analysis(update_artifacts=False)` — read-only режим для arch-summary

### Унификация через pipeline

- `runtime_scan.run_scan` — использует `run_full_analysis` + `render_full_architecture_report`
- `arch-summary` — через `run_full_analysis(update_artifacts=False)`
- `arch-diff` — через `build_snapshot_from_self_map` + `diff_architecture_snapshots`
- `eurika agent cycle` rescan_diff — через `build_snapshot_from_self_map` + `diff_architecture_snapshots`

### Self-analysis ritual

- `eurika self-check [path]` — ритуал самоанализа; Eurika анализирует свою архитектуру

### CLI refactor

- `cli/handlers.py` — все command handlers (handle_scan, handle_self_check, handle_arch_*, handle_agent_*)
- `eurika_cli.py` — только parser + dispatch (~250 строк вместо ~1000)

### Architecture Diff

- `architecture_diff.diff_architecture_snapshots(old, new: ArchitectureSnapshot)` — единый формат
- `_build_graph_and_summary_from_self_map(self_map_path)` в architecture_pipeline — общая логика для path и file
- ArchSnapshot сохранён для обратной совместимости (standalone `python architecture_diff.py`)

---

## v0.3.0 — Action Layer, Patch Apply, Learning Loop

### Action Plan + Executor

- `action_plan.py` — Action, ActionPlan (type, target, description, risk, expected_benefit)
- `executor_sandbox.py` — ExecutorSandbox.dry_run(plan), ExecutorSandbox.execute(plan, backup); execute converts ActionPlan to patch and calls apply_patch_plan; JSONL logging
- CLI: `eurika agent action-apply [path]` [--no-backup] — build ActionPlan and execute (append TODO per action)
- `architecture_planner.py` — build_action_plan, build_patch_plan, PlanStep → Action mapping
- CLI: `eurika agent action-dry-run`, `eurika agent action-simulate`

### Patch Plan + Apply

- `patch_plan.py` — PatchOperation, PatchPlan; smell_type for (smell_type, action_kind) learning
- `patch_apply.py` — apply_patch_plan with dry_run, backup, run_id; skip if diff already in file
- `.eurika_backups/<run_id>/` — per-run backups; list_backups, restore_backup
- CLI: `eurika agent patch-plan` [-o FILE], `patch-apply` [--apply] [--verify] [--no-backup], `patch-rollback` [--run-id] [--list]
- Tailored diff hints per (smell_type, action_kind): god_module, bottleneck, hub, cyclic_dependency

### Learning Loop

- `architecture_learning.py` — LearningStore, aggregate_by_action_kind, aggregate_by_smell_action
- Records after patch-apply --apply --verify; planner uses past success rates for expected_benefit bump
- **Patch plan ordering**: when building patch plan, operations are sorted by (smell_type, action_kind) success rate (LearningStore.aggregate_by_smell_action); higher success first
- CLI: `eurika agent learning-summary` — by_action_kind + by_smell_action

### Cycle

- `eurika agent cycle` — scan → arch-review → patch-apply --apply --verify
- Rollback hint on test failure (with run_id)
- `eurika agent cycle --dry-run` — scan → arch-review → patch-plan only (no apply/verify)
- **Rescan after apply**: on verify success, runs scan again and compares architecture before/after;
  report includes `rescan_diff` (structures, smells, maturity, centrality_shifts)
- **Cycle --quiet** (`-q`): suppress scan/arch output; only final report JSON to stdout
- **SPEC v0.4 draft**: `SPEC_v0.4_draft.md` — action/patch/learning/rescan layer, CLI, safety

### Tests

- `tests/test_cycle.py` — cycle --dry-run integration tests; full cycle with apply + rescan_diff + rollback on tmp project
- `tests/test_executor_sandbox.py` — ExecutorSandbox dry_run and execute

### Misc

- `code_awareness.py` — exclude `.eurika_backups` from scan; refactored extract_imports, find_duplicates

---

## v0.1.0 — Architecture Awareness Engine

First release-ready version focused on **observation-only** architecture analysis
of Eurika's own codebase.

### Core

- `eurika_cli.py` — CLI entrypoint with:
  - `scan` (full pipeline),
  - `arch-summary` / `arch-history` / `arch-diff`,
  - experimental AgentCore helpers:
    - `agent arch-review`
    - `agent arch-evolution`
    - `agent prioritize-modules`
    - `agent feedback-summary`.
- `runtime_scan.py` — orchestration of a full scan:
  - code awareness,
  - self-introspection (`self_map.json`),
  - architecture smells,
  - architecture summary,
  - recommendations,
  - history + trends,
  - observation memory.

### Analysis

- `code_awareness.py` — file system scan, AST analysis, smells, duplicates.
- `project_graph.py` — project-only import graph.
- `graph_analysis.py` — graph summary (nodes, edges, cycles, metrics).
- `architecture_smells.py` — detection of `god_module`, `hub`, `bottleneck`, cycles.
- `architecture_summary.py` — реэкспорт из `eurika.smells.summary`; high-level system portrait (central modules, risks, maturity).
- `architecture_advisor.py` — heuristics from smells to refactoring recommendations.
- `architecture_history.py` — architecture history + trends + dynamic maturity.
- `architecture_diff.py` — diff between two architecture snapshots.

### Storage

- `observation_memory.py` — append-only observation history (`eurika_observations.json`).
- `architecture_history.json` — persisted architecture history.

### Tests

- `tests/` — minimal pytest suite for:
  - `ProjectGraph`,
  - architecture smells/advisor,
  - graph analysis,
  - architecture history,
  - end-to-end `runtime_scan.run_scan` on a tiny project.

### Agent stack (frozen for v0.1)

- `agent_core.py`, `agent_runtime.py`, `reasoner_dummy.py`, `selector.py`,
  `executor_sandbox.py` — kept as design artefacts, **not used** in v0.1 runtime.
- `agent_core_arch_review.py` — thin, experimental AgentCore-style layer for:
  - `arch_review` (explain_risk + summarize_evolution),
  - `arch_evolution_query` (summarize_evolution only),
  built strictly on top of v0.1 artifacts (`self_map`, summary, history, observations).
- `architecture_feedback.py` — append-only storage for manual feedback about AgentCore
  proposals (`architecture_feedback.json`), used for simple statistics only.

