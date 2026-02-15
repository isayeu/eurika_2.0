# Eurika 2.0 — ROADMAP

Единый план задач. Контракт — в SPEC.md.

---

## Принцип ROADMAP

**Сейчас основная задача — саморазвитие:** анализ и исправление собственного кода, добавление новых функций по запросу. Eurika в первую очередь работает над собой (scan/doctor/fix по своей кодовой базе, доработки по обратной связи). Использование на других проектах — вторично и по мере надобности.

Долгосрочное видение — полноценный агент (звонки, финансы, код по запросу, собственная LLM и т.д.); до этого очень далеко. Ниже: текущее состояние → выполненный план прорыва → следующие шаги (горизонт 2, в фокусе работа над собой) → горизонт 3 (далёкое будущее).

---

## Текущее состояние (v2.6.2)

**Основная задача:** саморазвитие, анализ и исправление собственного кода, добавление новых функций по запросу. Инструмент применяется в первую очередь к своей кодовой базе (eurika).

**Выполнено (включая 3.1, 3.2, v1.2.15):**
- Всё перечисленное в v0.8–v1.2 (pipeline, Smells 2.0, CLI, self-check, History, Patch Engine, Event Engine)
- **Фаза 3.1 (граф как движок):** priority_from_graph, SMELL_TYPE_TO_REFACTOR_KIND, metrics_from_graph, targets_from_graph — patch_plan формируется с опорой на граф
- **Фаза 3.2 (единая модель памяти):** консолидация в `.eurika/` (events.json, history.json, observations.json); learning/feedback — views над EventStore; architect использует recent_events в промпте
- **eurika cycle [path]:** scan → doctor (report + architect) → fix одной командой. Опции: --window, --dry-run, --quiet, --no-llm, --no-clean-imports, --interval
- **Фаза 2.4:** fix/cycle включают remove_unused_import по умолчанию; опция --no-clean-imports

### Оценка зрелости (по review.md, актуальная версия)

| Компонент               | Оценка |
| ----------------------- | ------ |
| Архитектурная структура | 8.5/10 |
| Качество кода           | 8/10   |
| Концепция               | 9/10   |
| Операционность          | 5/10   |
| Продуктовая готовность  | 5/10   |
| Потенциал               | 9.5/10 |

**Диагноз (review):** «Архитектурный аналитик с амбициями автономного агента» — автономным агентом пока не является. Усиливать LLM — преждевременно; усиливать execution — критично. Стратегическое заключение: при вводе Patch Engine, Verify+Rollback, детерминированных refactor-операций и единого Event Engine Eurika станет «автономным архитектурным инструментом»; иначе останется «очень умным архитектурным советником». Долгосрочная цель (вывод в review): полноценный AI-агент, способный к самоусовершенствованию; начало закладываем сейчас.

**План прорыва (путь 2) выполнен:** Patch Engine, Verify, Rollback, Event Engine, CLI 4 режима — реализованы.

---

## План прорыва выполнен

Этапы 1–5 и dogfooding закрыты. Продуктовая 1.0 в смысле плана достигнута.

---

## Следующий горизонт (кратко)

- **Фокус:** работа над собой — регулярный scan/doctor/fix по кодовой базе Eurika, добавление функций по запросу, багфиксы и актуализация документации.
- **Стабилизация:** тесты зелёные, доки соответствуют коду.
- **Фазы 2.2 и 2.3:** выполнены (Knowledge: кэш, наполнение; Orchestrator: run_cycle).
- **Дальше (по review):** фаза 3.1 (граф как движок), фаза 3.2 (единая модель памяти). Опционально: прогоны на других проектах.

---

## Следующие шаги (горизонт 2)

План прорыва выполнен. Ниже — фазы без жёстких сроков, в приоритете саморазвитие и работа над собственной кодовой базой.

### Фаза 2.1 — Саморазвитие и стабилизация (приоритет 1)

**Цель:** закрепить цикл «анализ и исправление собственного кода», добавлять новые функции по запросу, держать тесты и документацию в актуальном состоянии.

| # | Задача | Критерий готовности |
|---|--------|----------------------|
| 2.1.1 | Регулярно применять scan/doctor/fix к своей кодовой базе (eurika) | Ритуал по DOGFOODING.md; артефакты и отчёты обновляются; выявленные проблемы фиксируются или попадают в план |
| 2.1.2 | Добавление новых функций по запросу; **багфиксы** по результатам прогонов (напр. Knowledge: явная пустая карта `topic_urls={}` → дефолт только при `topic_urls is None`) | Тесты зелёные; REPORT и CHANGELOG обновлены при изменении возможностей или числа тестов |
| 2.1.3 | Актуализировать документацию при изменении поведения | README, CLI.md, KNOWLEDGE_LAYER.md, ROADMAP соответствуют коду и текущей задаче |
| 2.1.4 | Опционально: полный `eurika fix .` без --dry-run на Eurika (с venv) | ✓ Выполнено: verify 129 passed после багфикса topic_urls |
| 2.1.5 | Опционально: прогоны scan/doctor/fix на других проектах (farm_helper, optweb и т.д.) | ✓ scan + doctor на farm_helper (5 модулей), optweb (38 модулей) — отработали штатно |

**Выход из фазы:** стабильный цикл работы над собой; новые функции и правки вносятся по запросу; известные баги зафиксированы или закрыты.

---

### Фаза 2.2 — Качество Knowledge Layer (приоритет 2, по желанию)

**Цель:** улучшить качество и предсказуемость контента, который подставляется в doctor/architect при работе над собой (и при анализе других проектов); снизить зависимость от доступности внешних URL.

| # | Задача | Критерий готовности |
|---|--------|----------------------|
| 2.2.1 | Чистка HTML в `_fetch_url`: убрать шапку, навбар, футер, лишние блоки | ✓ Удаление script/style; обрезка ведущего boilerplate до What's New/Summary; тест test_fetch_html_cleanup |
| 2.2.2 | Опционально: кэширование сетевых ответов (TTL или файл в .eurika/) | ✓ cache_dir + ttl_seconds (24h); .eurika/knowledge_cache; врач/architect используют кэш; KNOWLEDGE_LAYER.md |
| 2.2.3 | Наполнение `eurika_knowledge.json` и примера в docs по мере надобности | ✓ Добавлены version_migration, security, async_patterns |

**Выход из фазы:** Reference в doctor даёт понятные фрагменты; при отсутствии сети или при частых запусках поведение приемлемое (кэш или только local).

---

### Фаза 2.3 — Orchestrator / единая точка управления (приоритет 3, по необходимости)

**Цель:** при дальнейшем росте числа сценариев — выделить единый фасад цикла (scan → diagnose → plan → patch → verify), чтобы упростить добавление новых режимов и тестирование при работе над собой и по запросу.

| # | Задача | Критерий готовности |
|---|--------|----------------------|
| 2.3.1 | Выделить фасад (например `run_doctor_cycle(path, ...)`, `run_fix_cycle(path, ...)`) в core или отдельный модуль | ✓ cli/orchestrator.py: run_doctor_cycle, run_fix_cycle; doctor и fix вызывают фасад; логика стадий в одном месте |
| 2.3.2 | Опционально: общий «Orchestrator» с конфигурируемыми стадиями (scan → diagnose → plan → patch → verify) | ✓ run_cycle(path, mode=doctor/fix); handlers вызывают run_cycle |

**Выход из фазы:** цикл управляется из одного слоя; проще добавлять новые режимы (например «только scan + report») и тесты на цикл.

---

### Фаза 2.4 — Интеграция remove_unused_import в fix cycle (приоритет: повышение операционности)

**Цель:** `eurika fix` выполняет реальный фикс (clean-imports), а не только append TODO. См. «Причина низкой операционности» выше.

| # | Задача | Критерий готовности |
|---|--------|---------------------|
| 2.4.1 | Добавить handler `remove_unused_import` в patch_apply | ✓ kind="remove_unused_import" вызывает remove_unused_imports, пишет результат |
| 2.4.2 | Генерировать clean-imports ops и препендить к patch_plan в run_fix_cycle | ✓ get_clean_imports_operations + prepend в orchestrator |
| 2.4.3 | Опция --no-clean-imports в fix/cycle | ✓ fix, cycle; флаг отключает clean-imports |
| 2.4.4 | Тест: fix cycle применяет remove_unused_import | ✓ test_fix_cycle_includes_clean_imports, test_fix_no_clean_imports_excludes_clean_ops |

**Выход из фазы:** ✓ `eurika fix .` без --dry-run удаляет unused imports (если есть) как часть цикла; доля реальных фиксов растёт.

---

### Статус рекомендаций review.md §7

| Пункт review | Статус | Примечание |
|--------------|--------|------------|
| 1. Event Engine | ✓ | eurika/storage/event_engine.py, ProjectMemory.events |
| 2. Усилить execution | ✓ | apply_patch, verify_patch, rollback_patch, auto_rollback |
| 3. Verify stage обязательный | ✓ | verify после patch, откат при провале |
| 4. Граф как операционный инструмент | ✓ | Фаза 3.1: приоритеты, триггеры, метрики, targets_from_graph |
| 5. Центральный orchestrator | ✓ | run_cycle(path, mode=doctor/fix), cli/orchestrator.py |

---

### Фаза 3.1 — Граф как движок (по review §7.4, §3.3)

**Цель:** граф не только анализирует, но определяет приоритет рефакторинга, триггерит операции, служит базой метрик (источник приоритетов, триггер операций, база метрик).

| # | Шаг | Задача | Критерий готовности |
|---|-----|--------|----------------------|
| 3.1.1 | Приоритизация из графа | Функция `priority_from_graph(graph, smells)` → упорядоченный список модулей для рефакторинга (по degree, severity, fan-in/fan-out) | ✓ graph_ops.priority_from_graph; get_patch_plan использует; тесты test_priority_from_graph_* |
| 3.1.2 | Триггер операций по типам smell | По god_module/hub/bottleneck в графе — автоматически маппинг в split_module / introduce_facade в patch_plan | ✓ graph_ops.SMELL_TYPE_TO_REFACTOR_KIND, refactor_kind_for_smells(); planner использует; hub→split_module; тесты |
| 3.1.3 | Граф как база метрик | health_score, risk_score, centrality — вычисляются из графа; влияют на verify_metrics и evolution | ✓ graph_ops.metrics_from_graph, centrality_from_graph; history и orchestrator используют; тесты |
| 3.1.4 | Инициация операций графом | Граф не только «рекомендует», но передаёт в patch_plan конкретные цели (target_file, kind) из своей структуры | ✓ targets_from_graph; build_patch_plan использует graph.nodes/edges; introduce_facade params от suggest_facade_candidates; тесты |

**Выход из фазы:** граф — стратегический слой; patch_plan формируется с опорой на граф, а не только на эвристики.

---

### Фаза 3.2 — Единая модель памяти (по review §3.2)

**Цель:** память как система знаний, а не набор разрозненных файлов; единая модель события; Event — первичная сущность.

| # | Шаг | Задача | Критерий готовности |
|---|-----|--------|----------------------|
| 3.2.1 | Консолидация storage | Learning, feedback, events — единый ProjectMemory; один формат сериализации (JSONL или структурированный JSON) | ✓ Все артефакты в project_root/.eurika/: events.json, learning.json, feedback.json, observations.json, history.json; миграция из legacy путей |
| 3.2.2 | Event как первичная сущность | Решение (Decision), действие (Action), результат (Result) записываются как Event; логи и история — проекции EventStore | ✓ LearningView, FeedbackView — views над EventStore; append пишет type=learn/feedback; aggregate_* читают из events.by_type() |
| 3.2.3 | Контекст для architect | Из EventStore извлекать последние патчи, результаты verify для подстановки в architect/LLM | ✓ EventStore.recent_events; _format_recent_events; architect использует recent_events в prompt (template + LLM); handle_architect, run_doctor_cycle передают |

**Выход из фазы:** memory концептуально единая; тормоз эволюции (раздробленность) снят.

---

### Горизонт 3 — Roadmap до 3.0 (по обновлённому review.md)

**Версионирование:** major.minor берётся из фазы ROADMAP (2.1, 2.3, 2.6, 3.0); patch — инкремент внутри фазы. pyproject.toml и eurika_cli следуют этой схеме.

**Направление (без жёстких дат):** движение к архитектурному AI-инженеру. Фундамент (Patch Engine, Verify, Event Engine, Orchestrator) заложен; фазы 3.1 и 3.2 реализованы.

| Версия | Цель | Содержание |
|--------|------|-------------|
| **v2.1** | Execution Milestone | Orchestrator ✓; PatchEngine v1 ✓; Verify ✓; Rollback ✓; 3 детермин. операции ✓. |
| **v2.3** | Stability Phase | Метрики; priority engine ✓; CI-ready ✓ (CLI.md § CI/CD); CLI doctor/fix/explain ✓. |
| **v2.6** | Semi-Autonomous Agent | auto-run ✓; continuous monitoring ✓; performance-based improvement ✓; event-based learning ✓. |
| **v3.0** | Architectural AI Engineer | multi-repo; cross-project memory; online knowledge; team-mode. |

### Фаза 2.6 — Semi-Autonomous Agent (по review.md §v2.6)

**Цель:** Eurika сама предлагает изменения. Минимальная автономность: повтор по расписанию, реакция на изменения, обучение на результатах.

| # | Шаг | Задача | Критерий готовности |
|---|-----|--------|----------------------|
| 2.6.1 | Auto-run mode | Повторять fix/cycle по интервалу | ✓ `eurika fix . --interval SEC`, `eurika cycle . --interval SEC`; Ctrl+C для остановки; v2.6.1 |
| 2.6.2 | Continuous monitoring | Запуск цикла при изменении файлов (watch) | ✓ `eurika watch [path]` — polling .py mtimes, --poll N; триггер fix при изменении; v2.6.2 |
| 2.6.3 | Performance-based improvement | Адаптация плана по success rate | ✓ Пропуск ops с success_rate < 0.25 при total >= 3; тест test_build_patch_plan_filters_low_success_rate_ops |
| 2.6.4 | Event-based learning | Обучение на событиях patch/verify | ✓ LearningView над EventStore; patch_plan использует learning_stats для сортировки; aggregate_by_smell_action |

**Выход из фазы:** ✓ Eurika может работать в фоне (--interval) или реагировать на изменения (`eurika watch`); план учитывает прошлые успехи.

**LLM — только после 2.1.** Orchestrator: cli/orchestrator.py ✓; EurikaOrchestrator (core/) — опционально.

**Детальный дизайн (review.md):** Часть 1 — Orchestrator Core (EurikaOrchestrator, PatchOperation, принципы LLM=стратег / PatchEngine=исполнитель); Часть 2 — roadmap до 3.0; варианты — хирургическая интеграция или новая архитектура.

---

## Стратегия выхода в 1.0

| Версия | Фокус |
|--------|-------|
| v0.5 | стабилизация pipeline ✓ |
| v0.6 | history + diff ✓ |
| v0.7 | CLI UX ✓ |
| v0.8 | smells 2.0 ✓ |
| v0.9 | layout skeleton + eurika.* imports + документация ✓ |
| v1.0 | релиз ✓ |

---

## 1. Архитектурная целостность

- [x] Pipeline: scan → graph → smells → summary → history → diff → report
- [x] ArchitectureSnapshot как единый объект
- [x] core/pipeline.py, cli/handlers.py
- [x] Скелет eurika/ + фасады + импорты среднего слоя (analysis, smells.rules, evolution, reporting, self_map, topology)
- [x] Перенос реализации в eurika/*: smells (detector, models, health, advisor), analysis.metrics; плоские файлы — реэкспорты
- [x] architecture_summary → eurika.smells.summary (реализация в пакете, плоский — реэкспорт)
- [x] evolution (history, diff) → eurika.evolution.history, eurika.evolution.diff (реализация в пакете, плоские — реэкспорты; architecture_diff.py сохраняет CLI)

---

## 2. Architecture History Engine

### 2.1 Модель данных
- [x] version (pyproject.toml)
- [x] git_commit (опционально)
- [x] diff metrics (дельты, не только абсолюты)

### 2.2 Регрессии
- [x] god_module, bottleneck, hub — отдельно
- [x] risk score (0–100)

### 2.3 Будущее
- [x] JSON API под future UI: `eurika.api` (get_summary, get_history, get_diff), `eurika serve` (GET /api/summary, /api/history, /api/diff)

---

## 3. Smell Engine

- [x] Уровень серьёзности: low / medium / high / critical (severity_to_level)
- [x] Remediation hints (что делать) — REMEDIATION_HINTS, get_remediation_hint
- [x] Корреляция со history — Smell history (per-type counts in evolution_report)

---

## 4. Architecture Diff Engine

- [x] Топ-модули по росту fan-in
- [x] Модули, ставшие bottleneck
- [x] Деградация maturity
- [x] Блок "Recommended actions: refactor X, split Y, isolate Z"

---

## 5. CLI

### 5.1 Команды
- [x] eurika scan ., arch-summary, arch-history, arch-diff, self-check
- [x] eurika history (алиас arch-history)
- [x] eurika report (summary + evolution report)
- [x] eurika explain module.py
- [x] eurika serve [path] (JSON API для UI)

### 5.2 UX
- [x] Цветной вывод (--color / --no-color)
- [x] ASCII charts (health score, risk score)
- [x] Markdown (--format markdown)

---

## 6. Документация

- [x] README, Architecture, CLI.md, THEORY.md

---

## Чеклист перед v1.0 (выполнен)

- [x] Разделы 1–6 ROADMAP выполнены (архитектура, history, smells, diff, CLI, документация)
- [x] JSON API и eurika serve реализованы
- [x] Версия обновлена на 1.0.0, CHANGELOG v1.0.0 записан

---

## 7. Мини-AI слой (после v1.0)

- [x] Интерпретация архитектуры: `eurika architect [path]` — шаблонная сводка + опционально LLM (OPENAI_API_KEY; поддержка OpenRouter через OPENAI_BASE_URL, OPENAI_MODEL); ответ в стиле "архитектор проекта"
- [x] Генерация рефакторинг-плана (эвристики): `eurika suggest-plan [path]` и `eurika.reasoning.refactor_plan.suggest_refactor_plan` — из summary/risks или из build_recommendations; LLM — в перспективе
- [x] Расширение: подсказки архитектора связаны с patch-plan и explain (ROADMAP §7)

---

## Этапы v0.1–v0.7 (выполнены)

- **0–8**: Заморозка контракта, аудит, core, memory, reasoning loop, code awareness, sandbox, feedback, freeze
- **A–C**: AgentCore (arch-review, arch-evolution), FeedbackStore, SPEC v0.2
- **D**: Prioritize modules
- **E–H**: Action plan, patch apply, learning loop, cycle
- **I–J**: Pipeline, ArchitectureSnapshot, self-check
- **K–L**: History v0.6 (version, git, risk_score), документация §6, CLI v0.7
- **M**: Smells v0.8 (severity_level, remediation_hints)

---

## Продукт 1.0 (по review.md)

Ориентир: *«Архитектурный инженер-практик»* — не только анализ, но и понятные действия. Риск: «умный, но бесполезный»; противодействие — замкнутый цикл и один чёткий сценарий.

### Цель продукта

- **Eurika = автономный архитектурный ревьюер и рефакторинг-ассистент:** анализирует → находит проблемы → формирует план → предлагает патчи (и при желании применяет с verify).

### TODO до продуктовой 1.0

- [x] **Консолидация памяти:** единый контракт — `eurika.storage.ProjectMemory(project_root)`. Довести до единого Event Engine — см. Этап 4 плана прорыва.
- [x] **Замкнутый цикл (скелет):** поток `eurika fix` = scan → diagnose → plan → patch → verify → learn есть; довести verify + rollback и полноценный Patch Engine — этапы 1, 3.
- [ ] **Killer-feature (цель):** remove_cyclic_import, remove unused imports, split oversized module; eurika fix с verify и откатом при провале — этапы 1–2, 3.
- [x] **CLI режимы есть:** scan, doctor, fix, explain. Упростить до 4 режимов без dev-команд — этап 5.

### Уже есть (не дублировать)

- Pipeline scan → graph → smells → summary → history → diff → report.
- patch-apply, --verify, learning loop, architecture_history, evolution_report.
- `eurika architect` (интерпретация), `eurika explain`, JSON API, self-check.

---

## Что по-прежнему не хватает (по review.md)

- ~~**Нет полноценного операционного цикла**~~ — **выполнено:** Scan → Diagnose → Plan → Patch → Verify → Log; apply_and_verify, auto_rollback, run_cycle.
- **Граф недоиспользован:** строится и анализируется, но не генерирует архитектурные действия, не определяет приоритет рефакторинга, не запускает автоматические операции — аналитический слой, а не движок. → **Фаза 3.1** (подробные шаги выше).
- **Memory концептуально раздроблена:** Event Engine есть, но логи, история, feedback хранятся по-разному. Нужна консолидация. → **Фаза 3.2** (подробные шаги выше).

### Причина низкой операционности (5/10): TODO vs реальные фиксы

Цикл fix формально завершён, но **patch часто = append TODO-комментарий**, а не изменение кода. Детальный анализ — **review_vs_codebase.md**.

| Операция | Результат |
|----------|-----------|
| remove_cyclic_import | ✓ Реальный фикс (AST) |
| remove_unused_import | ✓ Реальный фикс (в fix cycle по умолчанию, фаза 2.4) |
| introduce_facade | ✓ Реальный фикс (создаёт {stem}_api.py) |
| extract_class | ✓ Реальный фикс |
| split_module (успех) | ✓ Реальный фикс |
| refactor_module | ❌ Append TODO |
| split_module (fallback) | ❌ Append TODO |

**Приоритет:** расширять handlers (split_module fallback → реальный split по мере возможностей).

---

## Версия 2.1 — инженерный инструмент (целевое состояние)

Цель: 2.0 → «инженерный инструмент» (конкретная польза, автофиксы, стабильный CLI). Путь инженерный, не академический.

| Элемент | Статус | Задача |
|--------|--------|--------|
| **Patch Engine** | ✓ | `patch_engine.py`: **apply_patch**, **verify_patch**, **rollback_patch**; apply_and_verify(..., **auto_rollback=True**) при провале verify откатывает изменения |
| **Verify stage** | ✓ | После patch: перескан, сравнение health score; при ухудшении — откат (verify_metrics + rollback reason) |
| **Замкнутый цикл** | есть скелет | `eurika fix` = scan → diagnose → plan → patch → verify → learn (полноценно замкнуть) |
| **Единая модель Event** | частично | event_engine есть; консолидация learning/feedback в единую память → **Фаза 3.2** |
| **Граф как движок** | нет | Граф должен определять priority рефакторинга и запускать автоматические операции → **Фаза 3.1** |
| **Архитектурные операции** | частично | 1) Remove unused imports 2) Detect and break cyclic imports 3) Split oversized module (по LOC) — создать реальную ценность |

Детальный разбор — в **review.md**.

---

## План прорыва (этапы по review.md)

### Этап 1 — Patch Engine (критично)
- [x] Создать/дополнить `patch_engine.py`: **apply_patch(plan)**, **verify_patch()**, **rollback_patch()**; **apply_and_verify(..., auto_rollback=True)** при провале verify откатывает изменения.

### Этап 2 — Три архитектурные операции
- [x] Remove unused imports (`eurika clean-imports`, eurika.refactor.remove_unused_import)
- [x] Detect and break cyclic imports (remove_cyclic_import в patch plan + patch_apply)
- [x] Split oversized module (split_module по god_module: import-based + class-based)

### Этап 3 — Verify Stage
- [x] После patch: пересканировать, сравнить health (risk_score); если after_score < before_score — откат и report["verify_metrics"], report["rollback"]["reason"] = "metrics_worsened".

### Этап 4 — Упростить Memory → Event Engine
- [x] `eurika/storage/event_engine.py` — единая точка входа `event_engine(project_root)` → EventStore; Event { type, input, output/action, result, timestamp }; ProjectMemory.events использует event_engine; сериализация с полем `action` (review).

### Этап 5 — Упростить CLI
- [x] Четыре продуктовых режима первыми: `eurika scan .`, `eurika doctor .`, `eurika fix .`, `eurika explain file.py`; остальные команды в блоке «Other», agent — «Advanced». Help и usage выводят 4 режима как Product.

### Dogfooding
- [x] Провести полный цикл на самом проекте Eurika: scan → doctor → fix --dry-run. Инструкция — **DOGFOODING.md** (в т.ч. про venv для verify).

---

## Стратегический вывод (по review.md)

> Доказать, что можешь сделать инструмент, который **меняет код** — а не только анализирует его.

Продуктовая 1.0 в полном смысле = после выполнения этапов 1–5 (Patch Engine, 3 автофикса, Verify, Event Engine, CLI 4 режима) и dogfooding.

---

## После 1.0 — Knowledge Layer (по review.md)

Онлайн-ресурсы и внешний knowledge имеют смысл **только после** детерминированного ядра (Patch Engine, Verify, rollback). Иначе — хаос и потеря воспроизводимости.

**Порядок введения (review.md § 9):**
1. Patch Engine, Verify, детерминированные операции — **сначала** (этапы 1–3 выполнены).
2. Knowledge layer, external validation, adaptive learning — **потом**.

**Контракт:** не «LLM + поиск в интернете», а **Knowledge Provider Layer** — абстракция `KnowledgeProvider.query(topic) -> StructuredKnowledge`. Источники: официальная документация, release notes, PEP/RFC, статик-анализаторы; не «всё подряд». Схема: LLM → гипотеза → Knowledge layer (проверка по curated источникам) → LLM уточняет план → Patch engine → Verify.

**Проектирование:** **docs/KNOWLEDGE_LAYER.md** — контракт, провайдеры, схема интеграции. **eurika.knowledge** — скелет: `KnowledgeProvider`, `StructuredKnowledge`, `LocalKnowledgeProvider` (заглушка); тесты в `tests/test_knowledge.py`. Детально — **review.md** (блок «Онлайн-ресурсы / Knowledge Layer»).

---

## Главное правило

> Если модуль нельзя чётко протестировать — он не готов к существованию.
