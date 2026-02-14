# Changelog — Eurika 2.0

All notable changes to this project will be documented in this file.

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

