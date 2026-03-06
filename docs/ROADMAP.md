# Eurika 2.0 — ROADMAP

Единый план задач. Контракт — в SPEC.md.

---

## 1. Принцип и текущая задача

**Основная задача:** саморазвитие — анализ и исправление собственного кода, добавление функций по запросу. Eurika работает над собой (scan/doctor/fix по своей кодовой базе). Использование на других проектах — вторично.

**Долгосрочное видение:** полноценный AI-агент (звонки, финансы, код по запросу); до этого далеко.

---

## 2. Оценка зрелости

| Компонент               | Оценка | Компонент             | Оценка |
| ----------------------- | ------ | --------------------- | ------ |
| Архитектурная структура | 9/10   | Масштабируемость      | 6.5/10 |
| Качество кода           | 8/10   | Чистота структуры     | 5.5/10 |
| Концепция               | 9/10   | Контроль сложности    | 6/10   |
| Операционность          | 5/10   | Тестируемость         | 6/10   |
| Продуктовая готовность  | 7/10   | Продакшн-готовность   | 4/10   |
| Потенциал               | 9.5/10 |                       |        |

**Вывод ревью (2026):** «Функционально мощный, архитектурно нестабильный, структурно перегруженный.» Риски: God CLI, backups в дереве, orchestration без формальной модели. **Стратегия:** усиливать execution — критично; усиливать LLM — преждевременно.

**Review II (2026):** «Стало лучше структурно» — 8.5/10 амбиция, 7/10 архитектура. Ключевая проблема: отсутствие единого Execution Model; комбинаторный рост логики. Рекомендация: **freeze фичей**, ввести MetricVector + EnergyModel, затем ΔEnergy, ExperienceStore, адаптация весов. Подробно: **docs/review.md** §1.

**Review III (2026):** Идея 9/10, Амбиция 10/10, Структурность 7/10, **Стабильность ядра 5/10**, Фокус 6/10. Позиция: Tool ✔ Smart refactor ✔ → переход к Energy-based optimizer. Ключевой совет: **упростить ядро, один автономный цикл идеальным, потом наращивать**. Чего избегать: новые фичи, новые smell, self-rewriting, онлайн-патчинг. docs/review.md §2.

**Обновление (февраль 2026):** Split тяжёлых модулей (task_executor, serve, fix_cycle_impl, core_handlers, chat) — P0.4 выполнен; pipeline_model; test_cycle → test_cycle_report; CR rules (docs, pre-commit, test-api) в .eurika/rules; Qt MVP: hybrid approvals, dashboard, Stop. **Рост:** чистота структуры 4→5.5, контроль сложности 5→6, тестируемость ?→6, продуктовая 6→6.5. **Остаётся:** refactor_code_smell 0%, test_graph_ops/test_api крупные при необходимости, продакшн 4/10.

---

## 3. Выполнено (сводный обзор)

### 3.1 Приоритет 0 (P0) — экспертное ревью

| #   | Действие                         | Статус |
| --- | -------------------------------- | ------ |
| P0.1 | Удалить `.eurika_backups` из дерева | ✅ release_check шаг 0 — предупреждение |
| P0.2 | Вынести orchestration из CLI в application | ✅ eurika/orchestration/; cli — thin re-export |
| P0.3 | Формальная модель pipeline (Input→Plan→Validate→Apply→Verify) | ✅ pipeline_model.PipelineStage; Architecture.md §0.5.1 |
| P0.4 | Лимит размера файлов (400 LOC)   | ✅ self-check FILE SIZE; core_handlers, chat.py; task_executor→helpers/executors/patch; serve→utils/exec/routes; fix_cycle_impl→helpers/apply_approved |
| P0.5 | Архитектурная диаграмма          | ✅ Architecture.md §0.0: Mermaid L0–L6, fix-cycle |

### 3.2 Контуры стабилизации (R1–R5)

- **R1 Structural Hardening:** Layer discipline, domain vs presentation, size budget, public API — ✅
- **R2 Runtime Robustness:** State-модель цикла, fallback-устойчивость, логирование — ✅
- **R3 Quality Gate:** Coverage, edge-case matrix, typing contract — ✅
- **R4 Modular Platform:** Subsystem decomposition, dependency firewall, release hygiene — ✅
- **R5 Strategic Horizon:** Self-guard, risk prediction, @-mentions, plugins — ✅

### 3.3 Фазы развития (кратко)

| Фаза    | Содержание                                       | Статус |
| ------- | ------------------------------------------------ | ------ |
| 2.1–2.4 | Саморазвитие, Knowledge, Orchestrator, remove_unused_import | ✅     |
| 2.6     | Semi-autonomous (--interval, watch, learning)    | ✅     |
| 2.7     | Agent Runtime (observe→reason→propose→apply→verify→learn) | ✅     |
| 2.8     | Декомпозиция слоёв (L0–L6, dependency guard)    | ✅     |
| 2.9     | LLM в планировании, Knowledge Layer, learning   | ✅     |
| 3.0     | Multi-repo, cross-project memory, team mode     | ✅     |
| 3.1     | Граф как движок (priority, metrics, targets)     | ✅     |
| 3.1-arch | Архитектурная дисциплина (слои, API, file size) | ✅     |
| 3.2     | Единая модель памяти (EventStore)               | ✅     |
| 3.6     | Operability UX (approve per-op, critic, @-mentions, knowledge в Chat, diff view) | ✅     |

### 3.4 План прорыва (этапы 1–5)

- Patch Engine (apply, verify, rollback) — ✅
- Три архитектурные операции + verify stage — ✅
- Event Engine, CLI 4 режима — ✅

### 3.5 Продуктовая готовность 6/10 (B.1–B.6)

README, UI.md, CLI.md, 5-minute onboarding, тесты зелёные — ✅

---

## 4. Активные направления (на выбор)

### 4.1 Направление A — Learning from GitHub

Curated repos (Django, FastAPI) → pattern library → повышение verify_success_rate. **Статус:** 4.1 ✅ — `--light`, `--limit-repos`, лимиты extraction (100 files, 30 entries).

### 4.2 Направление B — Продуктовая готовность 6→7/10

UI.md ✓; README ✓; критерии **B.7–B.14** выполнены. Оценка 7/10 достигнута (март 2026).

| #   | Критерий                         | Описание                                      | Статус |
| --- | -------------------------------- | --------------------------------------------- | ------ |
| B.7 | `release_check.sh` проходит      | ruff, mypy, pytest — без ошибок               | ✅ |
| B.8 | Notes tab в GUI                  | Заметки сохраняются в `.eurika/notes.txt`     | ✅ |
| B.9 | Onboarding ≤ 10 мин              | Новичок: clone → scan/doctor/fix за 10 мин     | ✅ docs/ONBOARDING.md |
| B.10| `.eurika/rules/*` в проекте      | docs.mdc, pre-commit.mdc, test-api.mdc        | ✅ |
| **B.11** | Troubleshooting                 | `docs/TROUBLESHOOTING.md`: типовые ошибки (verify timeout, ModuleNotFoundError, LLM fallback, self_map missing) и решения; ссылка из README/ONBOARDING | ✅ |
| **B.12** | Qt first-run UX                 | При `eurika-qt` без project root — folder picker + подсказка «Выберите проект»; нет пустого экрана | ✅ |
| **B.13** | Dogfooding в ритуале            | DOGFOODING.md + release_check step 9 (smoke); после значимых изменений — прогон `fix --dry-run` и обновление CYCLE_REPORT по необходимости | ✅ |
| **B.14** | Dependency firewall в CI        | EURIKA_STRICT_LAYER_FIREWALL=1 в release_check (шаг 3) — уже включён; явная проверка при PR/merge | ✅ |

**План:** B.11 ✅; B.12 ✅; B.13 ✅. B.14 выполнен.

### 4.3 Направление C — Ритуалы

| Ритуал | Частота |
|--------|---------|
| fix --dry-run | после каждого изменения |
| doctor | раз в день |
| CYCLE_REPORT | раз в 200 циклов |
| scan, report-snapshot | по необходимости |

### 4.4 Qt MVP (eurika_2.0.Qt)

Цели: запуск Qt, folder picker, Commands tab (scan/doctor/fix), live output, Stop, hybrid approvals, dashboard. Стартовый промпт — см. §6.

### 4.5 Текущий фокус (март 2026)

**Принцип:** доказать, что текущий интеллект работает — не добавлять новый.

| Приоритет | Задача | Статус |
|-----------|--------|--------|
| 1 | TODO_AUDIT: prepare, doctor, chat_intent, parser | ✅ all |
| 2 | Dead code: vulture → ruff F401/F841 → ручной обзор | ✅ |
| 3 | 4 теста: CandidateGenerator, Scorer, planner, pipeline | ✅ |
| 4 | 200 циклов, CYCLE_REPORT | ✅ |
| 5 | TODO_AUDIT: full_cycle, operational_metrics, global_memory, graph_ops, remove_unused_import, introduce_facade, diff | ✅ all extracted |

**Выполнено:** TODO_AUDIT все 14 пунктов; extraction helpers в full_cycle, operational_metrics, global_memory, graph_ops, remove_unused_import, introduce_facade, evolution/diff; last_ts в learning_stats (decay prep).

**Минимальный MVP тестов:** 1 unit CandidateGenerator, 1 unit Scorer, 1 integration planner, 1 pipeline mini repo.

**Отложено:** refactor_code_smell 0% — честная метрика; EnergyModel — контракт есть, реализация позже; production 4/10.

### 4.6 Следующие шаги (приоритизировано)

**Принцип (review III):** упростить ядро, один автономный цикл идеальным, freeze фичей.

| Приоритет | Шаг | Оценка | Зависимости |
|-----------|-----|--------|-------------|
| **P1** | 200 циклов, CYCLE_REPORT | ~6–8 ч | run_cycle_batch с `tail -f .eurika/cycle_batch_report.md`; nohup при фоне |
| **P2** | Очистка `.eurika_backups` | 1 мин | `rm -rf .eurika_backups` перед release |
| **P3** | Ритуал dogfooding после сессии | 5 мин | `eurika fix . --dry-run`; при изменениях — CYCLE_REPORT |
| **P4** | File size >600 LOC (по необходимости) | varies | ✅ chat_intent 515, prepare 544, extract_function 529, architect 528; extract helpers (chat_intent_detectors, prepare_critic, extract_function_ast, architect_helpers) |
| **P5** | EnergyModel как resource constraint | ✅ | EURIKA_ENERGY_CAP; planner_patch_ops truncates по Σ|ΔE|; BOUNDED_EVOLUTION §7 |
| **—** | planner/core split | ✅ | CYCLE_REPORT #129: graph_analysis, actions_proposal; core — thin facade |

**Чего избегать:** новые фичи, новые smell, self-rewriting, онлайн-патчинг (review III).

---

## 5. Cursor Rules (CR) — по тематике

### 5.1 Правила и контекст (CR-A, CR-C, CR-D)

| #     | Шаг                               | Описание                                          | Статус |
| ----- | --------------------------------- | ------------------------------------------------- | ------ |
| CR-A1 | `.eurika/rules/eurika.mdc`        | CLI → orchestration → API → agent; Architecture.md | ✅     |
| CR-A2 | venv и команды в GUI              | .venv, scan/doctor/fix в Commands tab (QProcess); venv.mdc с Commands tab | ✅     |
| CR-A3 | Dependency firewall               | L0–L6; EURIKA_STRICT_LAYER_FIREWALL=1            | ✅     |
| CR-A4 | Qt-контекст (qt_app.mdc)          | PySide6, adapters/ui/services, вкладки, правила для агента | ✅     |
| CR-C1 | Ссылки на документы в промпте    | Architecture, DEPENDENCY_FIREWALL, CLI, API_BOUNDARIES | ✅ .eurika/rules/docs.mdc |
| CR-C2 | Типовые команды проверки          | scan, doctor, fix --dry-run, pytest               | ✅ venv.mdc |
| CR-C3 | Чек-лист перед коммитом           | тесты, ruff, mypy, release_check                  | ✅ .eurika/rules/pre-commit.mdc |
| CR-D1 | Рекомендованные @-ссылки          | @ROADMAP.md, @Architecture.md, @eurika/agent/    | ✅ docs.mdc |
| CR-D2 | Паттерны по типам задач           | рефакторинг → @eurika/agent/; API → @eurika/api/  | ✅ docs.mdc |
| CR-D3 | .cursorignore для артефактов      | build, __pycache__                                | ✅ .cursorignore |

### 5.2 Agent Skills (CR-B)

| #     | Шаг                    | Описание                                    | Статус |
| ----- | ---------------------- | ------------------------------------------- | ------ |
| CR-B1 | Skill «Тест для API»   | GET/POST → test в tests/test_api_serve.py  | ✅ .eurika/rules/test-api.mdc |
| CR-B2 | Skill «Release check»  | Запуск release_check.sh; «прогони release check» | ✅ (chat) |
| CR-B3 | Skill «Сверка ROADMAP» | «проверь фазу X.Y» → roadmap_verify         | ✅     |

### 5.3 Composer и Terminal (CR-E, CR-F)

| #     | Шаг                         | Описание                                        | Статус |
| ----- | ---------------------------- | ----------------------------------------------- | ------ |
| CR-E1 | Сценарии для Composer        | split модуля, вынос domain vs presentation      | ✅ composer-scenarios.mdc |
| CR-E2 | Шаблон промпта Composer      | контекст + план 3–7 шагов + критерии            | ✅ composer-scenarios.mdc |
| CR-E3 | Практика: крупный рефакторинг в Composer | один пример в CYCLE_REPORT                | ✅ polygon split_demo §98 |
| CR-F1 | Команды для агента           | eurika serve, pytest, release_check.sh           | ✅ release_check в GUI (Quality) |
| CR-F2 | Паттерн «изменение → проверка» | pytest по модулю после правок                 | ✅ change-verify-pattern.mdc |
| CR-F3 | Интерпретация ошибок         | Ruff → __all__/импорт; mypy → type hint         | ✅ change-verify-pattern.mdc |

### 5.4 Chat intents config (CR-G)

| #     | Шаг                    | Описание                                          | Статус |
| ----- | ---------------------- | ------------------------------------------------- | ------ |
| CR-G1 | chat_intents.yaml      | Паттерны, emit, intent_hints; match_direct_intent | ✅     |
| CR-G2 | Векторная память       | Embeddings для fuzzy match (опционально)          | ✅ EURIKA_USE_VECTOR_INTENT=1 |
| CR-G3 | PyTorch-классификатор  | Только при 100+ интентов (опционально)            | —      |

---

## 5.5 v3.0 Architecture (review 2026)

**Проблема:** «8/10 по амбиции, 6/10 по архитектурной чистоте». Рост без упрощения.

### Этап 1 — Чистка
- [x] Убрать/изолировать `*_extracted.py` в `eurika/extraction_sandbox/` (action_plan_extracted, agent_core_extracted, code_awareness_extracted, code_awareness_codeawarenessextracted)
- [x] Упростить planner до одного ядра (eurika/reasoning/planner/: types, heuristics, analysis, actions, llm_adapter; shims для совместимости)
- [x] Исключить runtime-мусор из релиза (MANIFEST.in + .gitignore: `.eurika_backups`, `.coverage`, `.pytest_cache`, `*_report.json`)

### Этап 2 — Модель
- [x] Доменные модели: `ArchitectureModel`, `RefactorAction`, `RiskReport`, `SmellReport`
- [x] Architecture Scoring Model (cohesion, coupling, complexity, modularity)
- [x] Refactor Simulation Engine (`simulate_patch` перед apply)

### Этап 3 — Безопасность
- [x] risk-based patching (`risk_report_from_plan`, RiskReport в report)
- [x] simulation-first apply (`simulate_patch` перед `apply_and_verify`; abort при errors)
- [x] regression detection: semantic — `enrich_report_with_rescan` (before/after score, rollback при metrics_worsened); performance — placeholder

### 5.6 Консолидация planner (по ревью) ✅

**Было:** planner_rules, planner_actions, planner_analysis, planner_patch_ops, planner_llm; architecture_planner_build_action_plan, architecture_planner_build_patch_plan.

**Структура:**
```
eurika/reasoning/planner/
    core.py          # analyze, detect_smells, propose_actions (фасад)
    heuristics.py    # правила, scoring
    actions.py       # patch ops
    llm_adapter.py   # Ollama/LiteLLM
    types.py, analysis.py, models.py
```

Shim-файлы удалены — импорты из eurika.reasoning.planner.*. architecture_planner: один build-модуль (build_plan, build_action_plan, build_patch_plan).
- [x] action_plan.py → eurika/reasoning/action_plan.py (L3); action_plan_api удалён.

### 5.7 Execution Model (review 2026 II)

**Источник:** docs/review.md. Цель: формальная execution-модель вместо хаотичного роста.

**Порядок (жёсткий):** нельзя начинать с learning или глубокого рефакторинга planner — сначала MetricVector + EnergyModel.

| #   | Этап                    | Действие | Статус |
| --- | ----------------------- | -------- | ------ |
| 0   | Freeze фичей            | 1–2 итерации без новых возможностей, AI, risk-расширений | ✅ завершён |
| 1   | MetricVector             | Фиксированная размерность (complexity, coupling, cohesion, instability, layering_violations, entropy). Не dict. | ✅ eurika/analysis/metric_vector.py |
| 2   | EnergyModel              | Energy = W · MetricVector. Линейная формула, веса пока фиксированы | ✅ eurika/analysis/energy_model.py |
| 3   | Planner на ΔEnergy       | Ранжировать candidates по delta = E_before - E_after; Score = Delta - Risk | ✅ energy_ranking.rank_operations_by_energy (heuristic) |
| 4   | ExecutionContext         | snapshot_before, candidates, selected, simulated_snapshot, snapshot_after, delta_score | ✅ eurika/reasoning/execution_context.py |
| 5   | ArchitectureSnapshot     | graph + metrics + smells — единая модель состояния | ✅ planner.models.ArchitectureSnapshot |
| 6   | ExperienceStore          | Запись outcome без изменения весов | ✅ eurika/storage/experience_store.py |
| 7   | Weight adaptation        | Медленно, bounded, с откатом | ✅ weight_store, EURIKA_WEIGHT_ADAPTATION=1 |

**Принцип:** AI = оптимизация в пространстве состояний. Без строгого MetricVector — сложный инструмент, не AI.

**Эволюция (по review):** v2.x rule-based → v3.0 energy-based → v3.5 adaptive weights → v4.0 meta-strategy.

**Freeze (этап 0, завершён):** стабилизация пройдена. Разморозка — можно приступать к следующей фазе.

**Целевая структура (v3.x):**
```
core/           models, execution_context
analysis/       graph, metrics, smells
planning/       planner_engine, candidate_generator, scoring, risk_model
simulation/     simulator
execution/      patch_executor, verifier
evaluation/     delta_evaluator
storage/        state_store, event_log, learning_store (dumb persistence)
```

### 5.8 Сводка review (для нового ревью)

**Источник:** docs/review.md. Извлечённые рекомендации и антипаттерны.

**Проблемы (что следить):**

| Проблема | Описание | Статус |
|----------|----------|--------|
| Смешение абстракций | В одном модуле: domain, orchestration, LLM, risk, mutation | Частично: hints_provider, filter_policy вынесены |
| Planner = God Engine | Анализ, решение, LLM, риск, patch, симуляция в planner | Частично: engine 4 шага; LLM в hints_provider |
| Нет жёсткой доменной модели | smells, graph, patches как dict | ArchitectureSnapshot, ExecutionContext есть; dict ещё в patch_plan |
| Нет явного pipeline | Нет одного orchestrator над всем | orchestration есть; ExecutionContext частично в prepare |
| Storage умный | event/session/campaign/learning + логика | Упрощение к State/Event/Learning — в плане |
| planner→storage→learning→planner | Скрытая циклическая зависимость | Избегать: storage = write-only |

**Принципы (review):**

1. **Planner** — чистая decision-машина: collect_facts → generate → rank → output. Не мутирует, не пишет, не применяет. LLM — отдельный сервис (injectable).
2. **Storage** — dumb persistence: StateStore, EventLog, LearningStore. Без вызовов planner, без решений, без изменения graph.
3. **ExecutionContext** — единый контекст; только Orchestrator мутирует. Все сервисы — чистые.
4. **Score Delta:** `delta = score(after) - score(before)`; planner ранжирует по delta. Без этого — rule-engine, не AI.
5. **SimulationEngine** — отдельно; Planner только вызывает `simulate(snapshot, action)`.
6. **Порядок миграции:** MetricVector → EnergyModel → ΔEnergy → ExperienceStore → Weight adaptation. Не learning сначала, не перестройка planner до MetricVector.

**Целевое разделение слоёв:**

| Слой | Ответственность |
|------|-----------------|
| analysis | только анализ |
| planning | только выбор действий |
| simulation | только dry-run |
| execution | только применение |
| evaluation | только сравнение before/after |
| storage | dumb persistence (только запись) |

**Эволюция (v2.x → v4.0):** rule-based → energy-based → adaptive weights → meta-strategy.

**Угроза:** добавление фич без execution-модели → потеря управляемости через 2–3 версии.

**Storage 3 слоя (review):** StateStore (save/load snapshot), EventLog (append-only), LearningStore (record_outcome, get_statistics). Никакой логики внутри.

**Соответствие Planner 4 компонента (текущее → целевое):**

| Целевое | Текущая реализация |
|--------|---------------------|
| planner_engine | `run_patch_plan` — оркестрирует 4 шага |
| candidate_generator | `generate_candidates` → build_patch_operations |
| scoring | `rank_candidates` → energy_ranking.rank_operations_by_energy |
| risk_model | `risk_report_from_plan` в planner.models |

**Соответствие Storage 3 слоя (текущее → целевое):**

| Целевое | Текущая реализация |
|--------|---------------------|
| EventLog | `event_engine` (EventStore) — append-only events |
| LearningStore | `LearningView` + `ExperienceStore.record_outcome`, `get_statistics` |
| StateStore | save_checkpoint / load_checkpoint / snapshot_from_checkpoint — eurika/storage/state_store.py; persistence в .eurika/state/ |

**Стратегия тестирования (review):** Level 1 — unit CandidateGenerator/Scorer/RiskModel; Level 2 — simulation без FS; Level 3 — planner integration (mocked); Level 4 — full pipeline (мини-репо с cycle).

**Жёсткий совет (review):** Не добавлять новые фичи, пока planner не станет чистым, storage не станет тупым, snapshot не станет единым источником правды.

---

### 5.9 Review III — автономность и цикл (2026)

**Источник:** docs/review.md §1–§3.

**Соответствие:** MetricVector, EnergyModel, State (ExecutionContext, ArchitectureSnapshot) уже есть (§5.7, §6.0.1). Review III п. «нет формального пространства состояний» — частично закрыт. **Замкнутость цикла:** delta_score → patch event, learn event; record_outcome(delta_energy). Остаётся: bounded evolution, самокоррекция решений.

**Шкала зрелости (где мы):**

| Уровень | Статус |
|---------|--------|
| Tool | ✔ |
| Smart refactor engine | ✔ |
| Energy-based optimizer | ⏳ |
| Adaptive AI system | ⏳ |
| Autonomous cognitive architect | 🚧 |

Переход между 2 и 3.

**Минимальный замкнутый цикл автономии (обязателен):**

```python
while True:
    goal = select_goal()
    plan = build_plan(goal)
    result = execute(plan)
    evaluation = evaluate(result)
    update_memory(evaluation)
```

Без этого цикла — не автономность. Eurika: scan→doctor→plan→patch→verify есть; **замкнутость:** delta_score в patch event и learn event (output), record_outcome(delta_energy=ctx.delta_score) — evaluation persist для следующего цикла.

**Направления развития:**

1. **Стабильное ядро** — один железобетонный цикл, потом наращивать.
2. **Настоящая память** — short/long term, failure log; приоритет целей, забывание, конфликт целей. **Failure log:** view над EventLog (learn, result=False); get_recent_failures читает из events. Один источник истины (ARCHITECTURE_MEMORY_REVIEW).

   **Формализация STM/LTM (review §2):**

   | Тип | Роль | Реализация | Scope |
   |-----|------|------------|-------|
   | **STM** | Контекст текущего цикла | ExecutionContext (snapshot_before/after, candidates, simulation_result, delta_score); SessionMemory (verify_success/fail в сессии) | один fix cycle |
   | **LTM** | Агрегаты и история | EventLog (events.json), LearningStore (learning_stats, get_merged_learning_stats), ArchitectureHistory, failure log, StateStore checkpoints, weights | все циклы |
   | **Failure log** | Провалы для самокоррекции | view над EventLog, get_recent_failures | bounded по limit |

   **Формализация:** docs/MEMORY.md — EventLog, FailureLog, LearningStore (минимальный контракт).

   **Остаётся (будущее):** приоритет целей, забывание (decay), конфликт целей, явное изменение стратегии.

   **Следующие шаги (приоритизировано):**
   1. Приоритет целей — ✅ Architecture.md §3.4 (targets_from_graph, priority_from_graph, prioritized_smell_actions).
   2. Забывание — ✅ bounded retention + decay v1.2: priority_decay (failure_penalty, freshness_bonus, archive); Step 3 recovery (success cancels failure); Step 4 forgetting (time-weighted). Полигон: eurika/polygon/decay_polygon.py, tests/test_decay_dynamics.py.
   3. Конфликт целей / изменение стратегии — ✅ meta_controller при деградации (skip_adaptation, learning_rate_scale); явные named стратегии — позже.

3. **Самокоррекция** — анализ *решений* (почему план провалился, какая гипотеза не сработала), не только кода. failure_reason в patch/learn events; architect получает failure в recent_events; planner deprioritize: get_recent_failures → sort_and_reindex_by_learning(recent_failures=...) — ops с metrics_worsened/simulation_errors/verify_failed идут последними.

**Чего не делать сейчас:** онлайн-патчинг, self-rewriting modules, автоматическое изменение архитектуры, 50 новых классов.

**Bounded evolution (review §1):** EURIKA_MAX_OPS_PER_CYCLE (default 12) — cap операций за fix cycle; 0 = без лимита. **Доказательство адаптации ✓** (100 циклов, CYCLE_REPORT #123). **Следующий целевой вектор:** bounded evolution → часть execution model; EnergyModel → resource constraint (energy budget, caps) — контракт §7 в docs/BOUNDED_EVOLUTION.md ✓. Реализация — по мере пробелов.

**Прогресс (Review III):** зрелость +40%, цели +60%, стратегия +70%, формализация +20%. Формализация отстаёт — нормально.

**Рекомендация:** долгая игра (вариант 3) — эволюция от простого ядра. Только с самоограничением.

---

## 6. Открытый бэклог (следующие шаги)

### 6.0 Продуктовая готовность 7/10 (B.11–B.14 выполнены)

- [x] **B.11** Создать `docs/TROUBLESHOOTING.md`: verify timeout, ModuleNotFoundError, LLM fallback, self_map missing; ссылка из README/ONBOARDING ✅
- [x] **B.12** Qt first-run: при запуске без project root — folder picker + подсказка; нет пустого экрана ✅
- [x] **B.13** Dogfooding ритуал: зафиксировать в ROADMAP/DOGFOODING; после значимых изменений — fix --dry-run, при необходимости обновить CYCLE_REPORT ✅

### 6.0.1 Execution Model — интеграция ExecutionContext в fix-cycle (review §1–3)

- [x] **Этап A:** Внедрить ExecutionContext в prepare; snapshot_before из ArchitectureSnapshot.from_core_snapshot ✅
- [x] **Этап B:** RiskReport в context (prepare) — risk_report_from_plan(patch_plan) → context.risk_report
- [x] **Этап C:** snapshot_after, delta_score в context (apply_stage) — _update_execution_context_after_rescan; delta_score в eurika_fix_report.json
- [x] **Этап D:** SimulationResult в context — simulation_result = SimulationResult.from_simulate_dict(simulation) сразу после simulate_patch
- [x] **Этап E:** planner через context.snapshot_before — ctx строится до diagnose, передаётся в agent; _structure_from_snapshot при наличии snapshot
- [x] **DeltaEvaluator:** eurika/evaluation/delta_evaluator.py — compute_delta(before, after, metrics_fn) → verify_metrics
- [x] **Review соответствие:** Planner 4 компонента и Storage 3 слоя — маппинг задокументирован в §5.8
- [x] **StateStore:** eurika/storage/state_store.py — save_checkpoint, load_checkpoint, snapshot_from_checkpoint; prepare сохраняет "latest" при build context
- [x] **STM/LTM формализация:** маппинг в §5.9 (ExecutionContext=STM, EventLog/LearningStore/ArchitectureHistory/failure_log/StateStore/weights=LTM)

### 6.1 Структура и размер файлов

- ~~Разбить `eurika/api/task_executor.py` (767 LOC), `eurika/api/serve.py` (598)~~ ✅ P0.4: task_executor → helpers, types, executors, patch; serve → utils, exec, routes_get, routes_post
- ~~Разбить `eurika/orchestration/fix_cycle_impl.py` (586)~~ ✅ fix_cycle_helpers, fix_cycle_apply_approved
- ~~test_cycle.py~~ → test_cycle_report.py (report-snapshot, telemetry, whitelist-draft) ✅
- ~~test_cycle.py~~ → test_cycle.py, test_cycle_doctor.py, test_cycle_fix_apply.py ✅
- ~~test_chat_api.py~~ → test_chat_api.py, test_chat_api_handlers.py ✅
- ~~test_api_serve.py~~ → test_api_serve.py, test_api_serve_post.py ✅

### 6.2 Qt и UI

- CR-A2: Commands tab — scan/doctor/fix в GUI (QProcess) ✅
- CR-A4: qt_app.mdc с правилами для агента ✅
- Live output + Stop/Cancel ✅
- Hybrid approvals: Load plan, approve/reject per row, Save, apply-approved ✅ (Save feedback: "X approved, Y rejected")
- Dashboard: Summary, risks, SELF-GUARD, Ops, History sub-tab, Run scan button ✅
- Quality: Ruff, Mypy, Release check (CR-F1) ✅
- Dark theme: View → Dark theme; сохранение в qt_settings.json ✅

### 6.3 Операционность

- KPI: `verify_success_rate` по smell|action|target (prioritized_smell_actions ✅)
- refactor_code_smell — archive/REFACTOR_CODE_SMELL_PLAN.md (Phase 1–4 ✅; Phase E: policy adjust при rate≥25% ✅)

### 6.4 Архитектура (L3↛L5)

- architect → report: DI (template_formatter), LayerException удалён ✅

### 6.5 Cursor Rules (незакрытые)

- ~~CR-B1, CR-C1, CR-C2, CR-C3, CR-D3~~ ✅
- CR-D1–CR-D2: @-ссылки, паттерны по типам задач ✅
- ~~CR-E, CR-F: Composer и Terminal~~ ✅ composer-scenarios, change-verify-pattern, CR-E3 polygon split_demo

### 6.6 Multi-repo и Learning

- ~~3.0.1: eurika_fix_report_aggregated.json при fix/cycle [path1 path2 ...]~~ ✅ test_multi_repo_fix_aggregated_report
- 3.0.5: расширение Learning from GitHub (pattern library, OSS examples) — GET /api/pattern_library ✅

### 6.7 Execution Model (по review 2026 II)

- §5.7 этапы 1–7: MetricVector, EnergyModel, ΔEnergy, ExecutionContext, ArchitectureSnapshot, ExperienceStore, Weight adaptation — ✅
- **v4.0 meta-controller:** переключение стратегий при деградации — ✅ `eurika/cognition/meta_controller.py`; `EURIKA_META_CONTROLLER=1` при `EURIKA_WEIGHT_ADAPTATION=1`.
- **GET /api/metrics:** MetricVector + Energy для текущего состояния — ✅ `eurika.api.get_metrics`; для dashboard, delta tracking.

---

## 7. Стартовый промпт для Qt (eurika_2.0.Qt)

```
Контекст: Работаем в форке eurika_2.0.Qt. Цель — desktop-first UX на Qt без ломки ядра Eurika.
Роль: senior Python/Qt инженер. Практичные, инкрементальные шаги. Совместимость с CLI/API.

Главные цели MVP:
1) Запуск Qt, выбор project root через folder picker
2) Вкладка запуска: scan, doctor, fix, cycle, explain
3) Live output + Stop/Cancel
4) Hybrid approvals (pending plan, approve/reject, apply-approved)
5) Dashboard (summary/history/risks) через JSON API

Ограничения: thin Qt shell поверх API/CLI; тест/сценарий на каждое изменение; без big-bang.
Технологии: Python 3.12+, PySide6; qt_app/, adapters/, services/, ui/.
Критерий: eurika scan запускается из UI, вывод виден, процесс завершается/останавливается.
```

---

## 8. Причина низкой операционности (5/10)

**Цикл fix:** patch часто = append TODO, а не изменение кода. refactor_code_smell — 0% success; в WEAK_SMELL_ACTION_PAIRS (hybrid: review, auto: deny).

| Операция             | Результат                                |
| -------------------- | ---------------------------------------- |
| remove_unused_import | ✅ Реальный фикс                         |
| remove_cyclic_import | ✅ Реальный фикс                         |
| introduce_facade     | ✅ Реальный фикс                         |
| extract_class        | ✅ Реальный; в WEAK (hybrid)             |
| split_module         | ✅ Часто реальный                       |
| refactor_code_smell  | TODO-маркер или extract_block (гибрид)  |

**Для повышения:** интернет, LLM, pattern library, curated repos (3.0.5). Pattern library: до 3 OSS snippets в LLM extract prompt, snippet до 800 символов; curated_repos.light + flask.

---

## 9. Зависимости (v3.0.13+)

**libcst**, **litellm**, **rich**, **pydantic**, **watchdog**, **ruff**, **structlog**, **ollama**. См. docs/DEPENDENCIES.md.

---

## 10. Главное правило

> Если модуль нельзя чётко протестировать — он не готов к существованию.

---

## 11. Архив (кратко)

- **v0.5–v1.0:** pipeline, history, CLI, smells 2.0, JSON API — ✅
- **Чеклист v1.0:** разделы 1–6 выполнены — ✅
- **Этапы v0.1–v0.7:** AgentCore, FeedbackStore, Action plan, patch apply, learning — ✅
- **Knowledge Layer:** ✅ контракт docs/KNOWLEDGE_LAYER.md; eurika.api.get_knowledge; GET /api/knowledge?topic=...; ONBOARDING опциональный eurika_knowledge.json
