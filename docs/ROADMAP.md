# Eurika 2.0 — ROADMAP

Единый план задач. Контракт — в SPEC.md.

---

## Принцип ROADMAP

**Сейчас основная задача — саморазвитие:** анализ и исправление собственного кода, добавление новых функций по запросу. Eurika в первую очередь работает над собой (scan/doctor/fix по своей кодовой базе, доработки по обратной связи). Использование на других проектах — вторично и по мере надобности.

Долгосрочное видение — полноценный агент (звонки, финансы, код по запросу, собственная LLM и т.д.); до этого очень далеко. Ниже: текущее состояние → выполненный план прорыва → следующие шаги (горизонт 2, в фокусе работа над собой) → горизонт 3 (далёкое будущее).

---

## Текущее состояние (v3.0.x, актуальная ветка)

**Основная задача:** саморазвитие, анализ и исправление собственного кода, добавление новых функций по запросу. Инструмент применяется в первую очередь к своей кодовой базе (eurika).

**Выполнено (включая 3.1, 3.2 и последние рефакторинги цикла):**

- Всё перечисленное в v0.8–v1.2 (pipeline, Smells 2.0, CLI, self-check, History, Patch Engine, Event Engine)
- **Фаза 3.1 (граф как движок):** priority_from_graph, SMELL_TYPE_TO_REFACTOR_KIND, metrics_from_graph, targets_from_graph — patch_plan формируется с опорой на граф
- **Фаза 3.2 (единая модель памяти):** консолидация в `.eurika/` (events.json, history.json, observations.json); learning/feedback — views над EventStore; architect использует recent_events в промпте
- **eurika cycle [path]:** scan → doctor (report + architect) → fix одной командой. Опции: --window, --dry-run, --quiet, --no-llm, --no-clean-imports, --no-code-smells, --interval
- **Фаза 2.4:** fix/cycle включают remove_unused_import по умолчанию; опция --no-clean-imports
- **v2.6.9:** fix/cycle включают refactor_code_smell (long_function, deep_nesting) по умолчанию; опция --no-code-smells
- **Стабилизация execution-policy:** learning-gate для `long_function|extract_nested_function`, env-policy `EURIKA_DISABLE_SMELL_ACTIONS` (например `hub|split_module`)
- **Снижение сложности ядра цикла:** декомпозиция `build_patch_plan`, `get_code_smell_operations`, `run_fix_cycle`, `handle_explain` на stage/helper-функции с сохранением поведения

### Оценка зрелости (по review.md, актуальная версия)


| Компонент               | Оценка |
| ----------------------- | ------ |
| Архитектурная структура | 8.5/10 |
| Качество кода           | 8/10   |
| Концепция               | 9/10   |
| Операционность          | 5/10   |
| Продуктовая готовность  | 6/10   |
| Потенциал               | 9.5/10 |


**Диагноз (review):** «Архитектурный аналитик с амбициями автономного агента» — автономным агентом пока не является. Усиливать LLM — преждевременно; усиливать execution — критично. Стратегическое заключение: при вводе Patch Engine, Verify+Rollback, детерминированных refactor-операций и единого Event Engine Eurika станет «автономным архитектурным инструментом»; иначе останется «очень умным архитектурным советником». Долгосрочная цель (вывод в review): полноценный AI-агент, способный к самоусовершенствованию; начало закладываем сейчас.

**План прорыва (путь 2) выполнен:** Patch Engine, Verify, Rollback, Event Engine, CLI 4 режима — реализованы.

---

## План прорыва выполнен

Этапы 1–5 закрыты. Продуктовая 1.0 в смысле плана достигнута.

---

## Следующий горизонт (кратко)

- **Состояние v3.0.x:** фазы 2.1–2.9, 3.0, 3.1, 3.1-arch, 3.2 выполнены. Текущий интерфейсный фокус — Qt shell (`qt_app`, `eurika-qt`).
- **Фокус:** работа над собой — регулярный scan/doctor/fix, добавление функций по запросу, багфиксы, актуализация документации.
- **Стабилизация:** тесты зелёные, доки соответствуют коду.
- **Операционность 5/10:** refactor_code_smell 0% success (в WEAK_SMELL_ACTION_PAIRS); extract_block_to_helper работает в guarded-режиме (hybrid: review, auto: deny, target-aware/whitelist); для повышения — допустимо использовать интернет и LLM (промпты, pattern library, curated repos).
- **Дальше:** см. «Следующий фокус» и новый активный бэклог ниже.

### Расширения зависимостей (v3.0.13+)

Установлены и интегрируются: **libcst** (refactor), **litellm** (architect LLM), **rich** (CLI UX), **pydantic**, **watchdog**, **ruff**, **structlog**, **ollama**. См. **docs/DEPENDENCIES.md**.

### Следующий фокус

Три направления на выбор:

### Стартовый промпт для чата в `eurika_2.0.Qt`

Использовать при старте нового чата в проекте Qt-форка (скопировать целиком):

```text
Контекст:
- Работаем в форке: /home/lena/project/eurika_2.0.Qt
- Базовый web-проект eurika_2.0 заморожен как эталон.
- Цель: desktop-first UX на Qt без ломки ядра Eurika.

Твоя роль:
- Ты senior Python/Qt инженер.
- Предлагай только практичные, инкрементальные шаги с быстрым feedback loop.
- Сохраняй совместимость с текущим CLI/API ядром Eurika, если это явно не отменено.

Главные цели MVP (по порядку):
1) Запуск Qt-приложения и выбор project root через нативный folder picker.
2) Вкладка/панель запуска core-команд: scan, doctor, fix, cycle, explain.
3) Отображение live output процесса + кнопка Stop/Cancel.
4) Блок hybrid approvals (pending plan, approve/reject, apply-approved).
5) Минимальный dashboard (summary/history/risks) через существующий JSON API.

Ограничения:
- Не переписывать ядро Eurika без необходимости.
- Сначала thin Qt shell поверх существующего API/CLI, потом углубление.
- Каждое изменение должно сопровождаться проверкой (тест/ручной сценарий).
- Избегать big-bang рефакторинга.

Формат работы:
- Сначала короткий план на 3–7 шагов.
- Затем выполняй по шагам: код -> проверка -> краткий отчёт.
- Если есть архитектурная развилка, предложи 2 варианта с trade-offs и рекомендуй один.

Технические предпочтения:
- Python 3.12+ (или актуальная версия проекта), PySide6 (предпочтительно) или PyQt6.
- Ясная структура: qt_app/, adapters/, services/, ui/.
- Конфиг project root и пользовательские настройки хранить отдельно от ядра.

Критерий готовности ближайшей итерации:
- Приложение стартует, папка проекта выбирается нативно, команда `eurika scan` запускается из UI,
  вывод виден в окне, процесс корректно завершается/останавливается.
```


| Направление                            | Описание                                                                                               | Быстрота  |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------ | --------- |
| **A. 3.0.5 Learning from GitHub**      | Curated repos (Django, FastAPI) → pattern library → повышение verify_success_rate по action-kind       | Долго     |
| **B. Продуктовая готовность (5→6/10)** | UI.md ✓; README (getting started, примеры); критерии готовности в ROADMAP; venv-нейтральные инструкции | Быстро    |
| **C. Ритуал 2.1**                      | Регулярно: scan, doctor, report-snapshot; обновлять CYCLE_REPORT; без новых фич                        | Постоянно |


### Критерии продуктовой готовности 6/10 (направление B)


| #   | Критерий                                                                                          | Статус                                                 |
| --- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| B.1 | README: быстрый старт без привязки к конкретному venv-пути                                        | ✓ venv: `pip install -e ".[test]"`; инструкции generic |
| B.2 | README: все 4 продуктовые команды с примерами (scan, doctor, fix --dry-run, serve)                | ✓                                                      |
| B.3 | UI.md: полный список вкладок + описание Chat                                                      | ✓                                                      |
| B.4 | CLI.md: раздел CI/CD и рекомендуемый цикл                                                         | ✓                                                      |
| B.5 | Новый пользователь может за 5 минут: install → scan → doctor → fix --dry-run без чтения 10 файлов | ✓ README/UI/CLI покрывают сценарий 5-minute onboarding |
| B.6 | Тесты зелёные, CYCLE_REPORT актуален                                                              | ✓ ритуалы #61–#64 зафиксированы                        |


**Цель:** пользователь клонирует репо, читает README и через 5 минут понимает, что делает Eurika и как её запустить.

---

### Новый вектор из обновлённого review (логическая интеграция)

Ниже — не «перенос пунктов 1:1», а встраивание рекомендаций в текущую логику ROADMAP:
сначала структурная стабилизация ядра, затем защитные контуры, потом модульная платформа и только после этого — расширение интеллектуальности.

#### Контур R1 — Structural Hardening (ближайший приоритет)

**Цель:** закрепить архитектурный контракт и убрать источники непредсказуемости перед новыми фичами.


| Поток                  | Что делаем                                                                                                               | Критерий готовности                                                                      |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| Layer discipline       | Перепроверка и донастройка карты слоёв (allowed deps + no-upward imports) по факту текущих модулей                       | ✅ 2026-02: SMELL_TO_KNOWLEDGE_TOPICS → eurika.knowledge; 0 violations; self-check LAYER DISCIPLINE блок |
| Domain vs Presentation | Убираем форматирование отчётов/markdown из domain-кода; domain возвращает структуры, rendering только в reporting/UI/CLI | ✅ 2026-02: explain_module, get_suggest_plan_text перенесены в report/; eurika.api — только структуры |
| Size budget            | Жёстко применяем бюджет размера файлов (>400 warning, >600 split required) в self-check/ритуале                          | ✅ self-check выводит FILE SIZE LIMITS; 2026-02: eurika.api/__init__.py разбит на architecture, learning_api, team_api, diff_api, explain_api (697→185 LOC) |
| Public subsystem API   | Для ключевых подсистем оставляем 1-2 публичные точки входа, остальное private                                            | ✅ Architecture.md §0.7; Knowledge добавлен в таблицу                                    |


#### Контур R2 — Runtime Robustness (после R1)

**Цель:** сделать runtime-поведение наблюдаемым и устойчивым в ошибочных сценариях.


| Поток                        | Что делаем                                                                                  | Критерий готовности                                                  |
| ---------------------------- | ------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| Явная state-модель цикла     | Ввести формальное состояние выполнения runtime (idle/thinking/error/done) и тесты переходов | ✅ AgentRuntimeState, CycleState; test_agent_runtime, test_cycle_state, test_agent_runtime_stage_exception_sets_error_state |
| Fallback-устойчивость        | Аудит fallback-путей (LLM/knowledge/runtime) с обязательным детерминированным degraded mode | ✅ R2_FALLBACK_AUDIT; degraded_mode/degraded_reasons; doctor/fix/full_cycle early exit; тесты pass |
| Централизованное логирование | Привести runtime/CLI к единому logging-контуру (уровни, verbose/debug режимы)               | ✅ LOGGING_R2; cli/orchestration/logging.py; --quiet/--verbose; orchestration без print |


#### Контур R3 — Quality Gate (параллельно R1/R2)

**Цель:** поднять доверие к изменениям через жёсткий quality gate.


| Поток                    | Что делаем                                                                              | Критерий готовности                                                    |
| ------------------------ | --------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Coverage критичного ядра | Приоритетно покрывать тестами runtime/policy/memory/planning contracts                  | ✅ CI: pytest --cov=eurika --cov=cli; runtime 97%, policy 76%, events 89%, cycle_state 100%; рост итеративно |
| Edge-case matrix         | Формализовать edge-cases: пустой/огромный вход, model/network error, memory write error | ✅ docs/EDGE_CASE_MATRIX.md; tests/edge_cases/; CI job pytest -m edge_case; 10 тестов |
| Typing contract          | Усилить type-hints на границах подсистем; mypy как optional-gate                        | ✅ docs/TYPING_CONTRACT.md; CI mypy step (optional); pyproject overrides 45+ модулей; 0 errors |


#### Контур R4 — Modular Platform (после R1–R3)

**Цель:** подготовить Eurika к масштабированию без архитектурного долга.

Детальный план: **docs/R4_MODULAR_PLATFORM_PLAN.md**

| Поток                   | Что делаем                                                                                     | Критерий готовности                                |
| ----------------------- | ---------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| Subsystem decomposition | Укрепить пакетную изоляцию (core/analysis/planning/execution/reporting) и контракты между ними | ✅ SubsystemBypassRule, API_BOUNDARIES.md; test_subsystem_imports_via_public_api; 1 exception (architecture_planner) |
| Dependency firewall     | Автотест графа зависимостей как контракт архитектуры                                           | ✅ ImportRule/LayerRule/SubsystemBypassRule; CI step EURIKA_STRICT_LAYER_FIREWALL=1; 7 тестов |
| Release hygiene         | Перед релизами: dead code cleanup, TODO hygiene, lint/type/test, clean-start check             | ✅ scripts/release_check.sh; CI job release-hygiene; RELEASE_CHECKLIST.md (пункты 1–10) |

Реализовано: `scripts/release_check.sh`, `docs/RELEASE_CHECKLIST.md`, `docs/DEPENDENCY_FIREWALL.md`, `docs/API_BOUNDARIES.md`; CI с job `release-hygiene`; SubsystemBypassRule, рефакторинг через фасады. Миграция architecture_planner отложена (circular import).


#### Контур R5 — Strategic Horizon (дальний)

**Цель:** самонаблюдение, предиктивная аналитика, расширяемость. Детальный план: **docs/R5_STRATEGIC_HORIZON_PLAN.md**.

##### R5.1 Self-guard / Meta-architecture

Критерий: Eurika сама детектирует деградацию архитектуры и даёт алерты.

| # | Шаг | Задача | Критерий готовности |
|---|-----|--------|---------------------|
| R5.1.1 | Агрегированный SELF-GUARD | Единый блок в `eurika self-check`: layer + file_size + subsystem | ✅ PASS/FAIL по всем guard-проверкам |
| R5.1.2 | Флаг --strict | `eurika self-check . --strict` → exit 1 при нарушениях | ✅ --strict/--fail-on-guard |
| R5.1.3 | Complexity budget alarms | Пороги god_module >8, bottleneck >5; алерт при превышении | ✅ self_guard.py, блок в self-check |
| R5.1.4 | Centralization trend alarm | При centralization=increasing в history — предупреждение | ✅ evolution.history, alarm в self-check |
| R5.1.5 | SELF-GUARD в Qt Dashboard | Блок с итогом guard-проверок в GUI | ✅ Qt Dashboard |

##### R5.2 Intelligence upgrade

Критерий: более точные рекомендации и предикция рисков.

| # | Шаг | Задача | Критерий готовности |
|---|-----|--------|---------------------|
| R5.2.1 | Risk prediction | Оценка «вероятность регрессии» для модуля (history + smells) | ✅ get_risk_prediction, /api/risk_prediction |
| R5.2.2 | Recommendation engine | Учёт learning stats, past success rate в приоритизации | ✅ prioritized_smell_actions, context_sources |
| R5.2.3 | Контекстные подсказки | @-mentions в chat → фокус на модулях/smells | ✅ parse_mentions, scope-контекст, Focus module/smell |

##### R5.3 Extensibility

Критерий: подключение внешних анализаторов через единый контракт.

| # | Шаг | Задача | Критерий готовности |
|---|-----|--------|---------------------|
| R5.3.1 | Plugin interface | `AnalyzerPlugin` protocol: `analyze(path) -> List[ArchSmell]` | ✅ eurika/plugins/, protocol |
| R5.3.2 | Регистрация плагинов | `.eurika/plugins.toml` или `pyproject [tool.eurika.plugins]` | ✅ load_plugins, docs/R5_PLUGIN_INTERFACE.md |
| R5.3.3 | Агрегация результатов | Eurika + плагины → объединённый отчёт | ✅ detect_smells_with_plugins, GET /api/smells_with_plugins |
| R5.3.4 | Пример плагина | Тестовый пример callable | ✅ tests/fixtures/eurika_plugin_example.py |

**Порядок выполнения:** Фаза A (Self-guard) → Фаза B (Intelligence) → Фаза C (Extensibility). Основные критерии R5 закрыты.

---

## Следующие шаги (горизонт 2)

План прорыва выполнен. Ниже — фазы без жёстких сроков, в приоритете саморазвитие и работа над собственной кодовой базой.

**Фазы по возрастанию:** 2.1 → 2.2 → 2.3 → 2.4 → 2.6 → 2.7 → 2.8 → 2.9 → 3.0 (3.0.5) → 3.1 → 3.1-arch → 3.2

---

### Активный бэклог (после закрытия предыдущего)

**Закрыто:**

- Повысить долю реальных apply в `eurika fix` — _drop_noop_append_ops в prepare
- WEAK_SMELL_ACTION_PAIRS, _deprioritize_weak_pairs
- refactor_code_smell в WEAK_SMELL_ACTION_PAIRS (hybrid: review, auto: deny)
- god_class|extract_class в WEAK_SMELL_ACTION_PAIRS + EXTRACT_CLASS_SKIP_PATTERNS (*tool_contract*.py) — защита от повторных ошибок (CYCLE_REPORT #34)
- extract_block_to_helper в WEAK_SMELL_ACTION_PAIRS (hybrid: review, auto: deny) + target-aware policy по verify_fail history
- operation whitelist: `.eurika/operation_whitelist.json` для controlled rollout safe targets (CYCLE_REPORT #74)
- report-snapshot
- Малые рефакторинги + тесты для топ-long/deep функций
- R3 Typing contract (iterative): целевой mypy-gate расширен до `CLI entry -> orchestration -> API surface -> agent/storage/event-memory/facade -> learning/knowledge -> reasoning -> runtime/tool-contract -> evolution -> smells/core -> analysis/reporting -> checks/utils/storage-sidecar` (80 модулей), подтверждён финальным consolidate-ритуалом (full mypy + targeted regression-pack) и step-7..step-16 валидацией (CYCLE_REPORT #50, #51, #52, #53, #54, #55, #56, #57, #58, #59, #60, #61)
- Ритуал 2.1: `eurika report-snapshot .` (post R3 typing) выполнен и зафиксирован в CYCLE_REPORT #62
- Full cycle + snapshot ritual (post R3 typing) выполнен: no-op без verify-step, risk_score=46, context effect зафиксирован (CYCLE_REPORT #63)
- UI.md обновлён (CLI, serve, вкладки, run-cycle/terminal/approve/chat)
- README обновлён под продуктовый onboarding: venv-нейтральный quick start + базовые команды `scan/doctor/fix --dry-run/serve` (CYCLE_REPORT #64)
- B. Продуктовая готовность закрыт до 6/10: критерии B.1–B.6 выполнены (ROADMAP + CYCLE_REPORT #65)
- Uplift refactor/extract action-kind (phase 1+2): outcome-семантика `not_applied|verify_fail|verify_success`, hardening extract-функций, детальная skip-диагностика (CYCLE_REPORT #66)

**Закрыто (CYCLE_REPORT #67, #68):**

- long_function|extract_nested_function: extract with params (1–3 parent vars), verify_success в controlled scenario
- refactor_code_smell — по умолчанию не эмитить; `EURIKA_EMIT_CODE_SMELL_TODO=1` для TODO-маркеров
- deep_nesting — EURIKA_DEEP_NESTING_MODE=heuristic|hybrid|llm|skip, suggest_extract_block + extract_block_to_helper (guarded path: weak+target-aware+whitelist)
- long_function fallback — suggest_extract_block (if/for/while 5+ строк) когда extract_nested_function не срабатывает

**Новый бэклог (следующие шаги):**

- KPI-фокус: `verify_success_rate` по `smell|action|target` (apply_rate вторичен) — ✅ prioritized_smell_actions в context_sources, Dashboard
- 3.6.5 @-mentions: ✅ выполнено

**Update (2026-03-01, v3.0.26):**

- 3.0.1 Multi-repo: eurika_fix_report_aggregated.json при fix/cycle [path1 path2 ...]
- prioritized_smell_actions в get_learning_insights, context_sources, Qt Dashboard (Learning insights)
- CI: pytest --cov=eurika --cov=cli

**Update (2026-02-27, Qt/chat hardening + doc sync v3.0.12):**

- Doc sync: pyproject 3.0.12, README/UI/MIGRATION/CHANGELOG/CYCLE_REPORT/REPORT приведены в соответствие с Qt-first этапом.
- 3.6.5 @-mentions: parse_mentions (@module, @smell); interpret_task подставляет target из @module при refactor; _build_chat_context обогащается scope (Focus module/smell, risks по scope); тесты.
- Qt runtime hardening: корректный `closeEvent` в `MainWindow` с shutdown для `QProcess` (`terminate` → `wait` → `kill`) и остановкой health-timer.
- Stability gate окружения: Qt smoke переведён в изолированный `subprocess`; для нестабильного teardown на Python 3.14 введена рекомендация запускать smoke на 3.12/3.13 (через `EURIKA_QT_SMOKE_PYTHON`).
- Chat actions hardening: добавлены e2e-сценарии `add/remove tab` по цепочке `interpret -> pending_plan -> применяй -> verify`, чтобы закрыть регрессию класса "удали -> добавь".
- Operability 3.6 KPI: добавлен controlled whitelist seed (`operation_whitelist.controlled.json`) для 1–2 action-kind с безопасным rollout.
- UI sync: model controls закреплены на отдельной вкладке `Models`, chat-вкладка оставлена фокусной для диалога/goal-view.

### Пакет 3.6 — Operability UX (практики из Cursor)

**Цель:** повысить долю реальных и безопасных применений в `eurika fix` за счёт управляемого apply-процесса и лучшего контекста для планировщика.

| #     | Шаг                                | Задача                                                                                           | Критерий готовности                                                                                   |
| ----- | ---------------------------------- | ------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------- |
| 3.6.1 | Approve per operation              | Подтверждение/отклонение по операциям (а не только whole-plan): risk, reason, target, diff-hint | ✅ per-op approve/reject; --apply-approved, --approve-ops; team_mode, hybrid, Qt Approvals |
| 3.6.2 | Critic pass before apply           | Перед применением прогонять критический check плана (imports/API/tests impact)                  | ✅ _run_critic_pass, critic_verdict allow/review/deny; deny не проходит в auto; critic_decisions в report |
| 3.6.3 | Semantic context for planner       | Подмешивать в planner семантически релевантные модули/тесты/историю фейлов                       | ✅ Выполнено: context sources в planner/report/UI; в report-snapshot есть блок "Context effect" (apply/no-op delta) |
| 3.6.4 | Session checkpoint + campaign undo | Снимок состояния перед серией apply; откат всей кампании одним действием                         | ✅ Выполнено: pre-apply checkpoint, `campaign-undo`, e2e rollback кампании (checkpoint -> run_id -> undo) |
| 3.6.5 | @-mentions / scoped context       | Парсинг @module, @smell в чате; обогащение контекста; target из @module при refactor           | ✅ parse_mentions; примеры: @patch_engine.py, @code_awareness.py, @god_module (scan/doctor) |
| 3.6.6 | Knowledge в Chat и Planner        | eurika_knowledge + pattern_library + (опционально) PEP/docs в Chat prompt; Knowledge в planner LLM hints | ✅ Chat: _knowledge_topics_for_chat, _fetch_knowledge_for_chat; Planner: _fetch_knowledge_for_planner_hints в ask_ollama_split_hints |
| 3.6.7 | Approvals diff view               | Полноценный diff preview в Qt Approvals: API preview_operation для single-file ops; панель unified diff при выборе строки | ✅ API preview_operation; POST /api/operation_preview; Qt: diff panel по клику на op |
| 3.6.8 | Chat понимание и обучение         | Eurika понимает намерения (не шаблоны); tool calls (git, eurika CLI); обучение из чата при уточнениях | ✅ Phase 1–4: git tools, system prompt, feedback UI, few-shot из feedback |

**DoD пакета 3.6:** рост `apply_rate`, снижение `rollback_rate`, снижение доли TODO/no-op операций.

**Статус спринтов:**

- Спринт 1 (3.6.1 + 3.6.2): ✅ decision gate, critic pass, per-op approve/reject, decision summary
- Спринт 2 (3.6.3): ✅ context_sources в planner/report/UI, report-snapshot "Context effect"
- Спринт 3 (3.6.4): ✅ pre-apply checkpoint, campaign-undo, e2e rollback; R3 Quality Gate закрыт

---

#### 3.6.1–3.6.2 — Approve per operation + Critic pass (Спринт 1)

**Scope:** управляемое применение операций + pre-apply safety фильтр.

| Трек | Что делаем | Артефакты |
| ---- | ---------- | --------- |
| T1. Contract | Ввести/расширить структуру operation approval: `approved/rejected/pending`, reason, reviewer, timestamp; унифицировать формат pending/approved плана | ✅ approval_state, team_decision, approved_by, rejection_reason; payload created_at; load принимает team_decision ИЛИ approval_state |
| T2. CLI/UX | Добавить per-op workflow в CLI: показать операции с индексами/risk и поддержать approve/reject по индексам; сохранить существующий `--apply-approved` сценарий | ✅ --approve-ops, --reject-ops (1-based); hybrid prompt [idx/N] kind→target risk=X [a]/[r]/[A]/[R]; decision_summary; --apply-approved |
| T3. Apply pipeline | На этапе apply исполнять только approved ops; rejected пропускать с явной причиной в отчёте; pending не запускать в auto | ✅ _filter_executable_operations; operation_results+skipped_reason; skipped_reasons в report; pending/rejected не выполняются |
| T4. Critic pass | Перед apply запускать critic для каждой операции: imports/API surface/test impact, verdict `allow/review/deny` | ✅ _run_critic_pass; critic_verdict, critic_reason; deny блокирует в _filter_executable; critic_decisions в report |
| T5. Reporting | Включить в `eurika_fix_report.json` breakdown по операциям: approval_state, critic_verdict, applied/skipped reason | ✅ operation_results (approval_state, critic_verdict, applied, skipped_reason); decision_summary; critic_decisions |
| T6. Tests | Добавить unit/integration тесты: approve subset, reject high-risk, deny from critic, mixed plan apply | ✅ test_fix_cycle_approve_ops_selects_subset; test_fix_cycle_decision_gate_blocks_critic_denied_op; test_fix_cycle_all_rejected; test_hybrid_*; test_team_mode; apply-approved missing/invalid |

**DoD спринта 1:** high-risk без approve не применяются; deny от critic не проходит в auto; `--apply-approved` — только одобренный поднабор; отчёт фиксирует decision trail; regression зелёный.

#### 3.6.6 — Knowledge в Chat и Planner (✅ выполнено)

| Шаг | Артефакты |
| --- | --------- |
| 3.6.6.1 | ✅ CompositeKnowledgeProvider в chat flow; topics из intent/scope; inject как `[Reference]` |
| 3.6.6.2 | ✅ ask_ollama_split_hints получает knowledge_snippet; append к prompt |
| 3.6.6.3 | OSS patterns в diff_hint | ✅ Реализовано в 3.0.5.4: _build_hints_and_params добавляет OSS (proj): module — hint |

#### 3.6.7 — Approvals diff view (✅ выполнено)

| Шаг | Артефакты |
| --- | --------- |
| 3.6.7.1 | ✅ API `preview_operation(root, op)` — old_content, new_content, unified_diff |
| 3.6.7.2 | ✅ POST /api/operation_preview |
| 3.6.7.3 | ✅ Qt Approvals: diff panel по клику на строку |

**Kind:** remove_unused_import, remove_cyclic_import, extract_block_to_helper, extract_nested_function, fix_import.

#### 3.6.8 — Chat понимание и обучение (✅ выполнено)

| Phase | Артефакты |
|-------|-----------|
| 1 | ✅ chat_tools.py: git_status, git_diff, git_commit; «собери коммит» → status+diff; «применяй» → commit |
| 2 | ✅ INTENT_INTERPRETATION_RULES в _build_chat_prompt (коммит→git, ритуал→scan→doctor→fix) |
| 3 | ✅ Кнопки «Полезно»/«Не то»; QInputDialog уточнения; .eurika/chat_feedback.json |
| 4 | ✅ _load_chat_feedback_for_prompt; few-shot из feedback в промпт |

**Критерий:** «собери коммит» → реальный git; «нет, я имел в виду X» → учёт уточнения.

---

### Фаза 2.1 — Саморазвитие и стабилизация (приоритет 1)

**Цель:** закрепить цикл «анализ и исправление собственного кода», добавлять новые функции по запросу, держать тесты и документацию в актуальном состоянии.


| #     | Задача                                                                                                                                                                   | Критерий готовности                                                                                                                           |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- |
| 2.1.1 | Регулярно применять scan/doctor/fix к своей кодовой базе (eurika)                                                                                                        | Артефакты и отчёты обновляются; выявленные проблемы фиксируются или попадают в план                                  |
| 2.1.2 | Добавление новых функций по запросу; **багфиксы** по результатам прогонов (напр. Knowledge: явная пустая карта `topic_urls={}` → дефолт только при `topic_urls is None`) | Тесты зелёные; REPORT и CHANGELOG обновлены при изменении возможностей или числа тестов                                                       |
| 2.1.3 | Актуализировать документацию при изменении поведения                                                                                                                     | README, CLI.md, KNOWLEDGE_LAYER.md, ROADMAP соответствуют коду и текущей задаче                                                               |
| 2.1.4 | Опционально: полный `eurika fix .` без --dry-run на Eurika (с venv)                                                                                                      | ✓ Выполнено: verify 129 passed после багфикса topic_urls                                                                                      |
| 2.1.5 | Опционально: прогоны scan/doctor/fix на других проектах (farm_helper, optweb, binance/bbot и т.д.)                                                                       | ✓ farm_helper (5), optweb (38); ✓ binance/bbot/34 (11, scan+doctor+fix --dry-run); ✓ binance/binance-trade-bot (26, scan) — отработали штатно |


**Выход из фазы:** стабильный цикл работы над собой; новые функции и правки вносятся по запросу; известные баги зафиксированы или закрыты.

---

### Фаза 2.2 — Качество Knowledge Layer (приоритет 2, по желанию)

**Цель:** улучшить качество и предсказуемость контента, который подставляется в doctor/architect при работе над собой (и при анализе других проектов); снизить зависимость от доступности внешних URL.


| #     | Задача                                                                 | Критерий готовности                                                                                         |
| ----- | ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| 2.2.1 | Чистка HTML в `_fetch_url`: убрать шапку, навбар, футер, лишние блоки  | ✓ Удаление script/style; обрезка ведущего boilerplate до What's New/Summary; тест test_fetch_html_cleanup   |
| 2.2.2 | Опционально: кэширование сетевых ответов (TTL или файл в .eurika/)     | ✓ cache_dir + ttl_seconds (24h); .eurika/knowledge_cache; врач/architect используют кэш; KNOWLEDGE_LAYER.md |
| 2.2.3 | Наполнение `eurika_knowledge.json` и примера в docs по мере надобности | ✓ Добавлены version_migration, security, async_patterns                                                     |


**Выход из фазы:** Reference в doctor даёт понятные фрагменты; при отсутствии сети или при частых запусках поведение приемлемое (кэш или только local).

---

### Фаза 2.3 — Orchestrator / единая точка управления (приоритет 3, по необходимости)

**Цель:** при дальнейшем росте числа сценариев — выделить единый фасад цикла (scan → diagnose → plan → patch → verify), чтобы упростить добавление новых режимов и тестирование при работе над собой и по запросу.


| #     | Задача                                                                                                          | Критерий готовности                                                                                              |
| ----- | --------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| 2.3.1 | Выделить фасад (например `run_doctor_cycle(path, ...)`, `run_fix_cycle(path, ...)`) в core или отдельный модуль | ✓ cli/orchestrator.py: run_doctor_cycle, run_fix_cycle; doctor и fix вызывают фасад; логика стадий в одном месте |
| 2.3.2 | Опционально: общий «Orchestrator» с конфигурируемыми стадиями (scan → diagnose → plan → patch → verify)         | ✓ run_cycle(path, mode=doctor/fix); handlers вызывают run_cycle                                                  |


**Выход из фазы:** цикл управляется из одного слоя; проще добавлять новые режимы (например «только scan + report») и тесты на цикл.

---

### Фаза 2.4 — Интеграция remove_unused_import в fix cycle (приоритет: повышение операционности)

**Цель:** `eurika fix` выполняет реальный фикс (clean-imports), а не только append TODO. См. «Причина низкой операционности» выше.


| #     | Задача                                                                   | Критерий готовности                                                                   |
| ----- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------- |
| 2.4.1 | Добавить handler `remove_unused_import` в patch_apply                    | ✓ kind="remove_unused_import" вызывает remove_unused_imports, пишет результат         |
| 2.4.2 | Генерировать clean-imports ops и препендить к patch_plan в run_fix_cycle | ✓ get_clean_imports_operations + prepend в orchestrator                               |
| 2.4.3 | Опция --no-clean-imports в fix/cycle                                     | ✓ fix, cycle; флаг отключает clean-imports                                            |
| 2.4.4 | Тест: fix cycle применяет remove_unused_import                           | ✓ test_fix_cycle_includes_clean_imports, test_fix_no_clean_imports_excludes_clean_ops |


**Выход из фазы:** ✓ `eurika fix .` без --dry-run удаляет unused imports (если есть) как часть цикла; доля реальных фиксов растёт.

---

### Фаза 2.6 — Semi-Autonomous Agent (по review.md §v2.6)

**Цель:** Eurika сама предлагает изменения. Минимальная автономность: повтор по расписанию, реакция на изменения, обучение на результатах.


| #     | Шаг                           | Задача                                    | Критерий готовности                                                                                           |
| ----- | ----------------------------- | ----------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| 2.6.1 | Auto-run mode                 | Повторять fix/cycle по интервалу          | ✓ `eurika fix . --interval SEC`, `eurika cycle . --interval SEC`; Ctrl+C для остановки; v2.6.1                |
| 2.6.2 | Continuous monitoring         | Запуск цикла при изменении файлов (watch) | ✓ `eurika watch [path]` — polling .py mtimes, --poll N; триггер fix при изменении; v2.6.2                     |
| 2.6.3 | Performance-based improvement | Адаптация плана по success rate           | ✓ Пропуск ops с success_rate < 0.25 при total >= 3; тест test_build_patch_plan_filters_low_success_rate_ops   |
| 2.6.4 | Event-based learning          | Обучение на событиях patch/verify         | ✓ LearningView над EventStore; patch_plan использует learning_stats для сортировки; aggregate_by_smell_action |


**Выход из фазы:** ✓ Eurika может работать в фоне (--interval) или реагировать на изменения (`eurika watch`); план учитывает прошлые успехи.

**LLM — только после 2.1.** Orchestrator: cli/orchestrator.py ✓; EurikaOrchestrator (core/) — опционально.

**Детальный дизайн (review.md):** Часть 1 — Orchestrator Core (EurikaOrchestrator, PatchOperation, принципы LLM=стратег / PatchEngine=исполнитель); Часть 2 — roadmap до 3.0; варианты — хирургическая интеграция или новая архитектура.

---

---

### Фаза 2.7 — Нативный Agent Runtime в Eurika (без внешней прослойки)

**Цель:** встроить Cursor-подобный workflow напрямую в кодовую базу Eurika: управляемый цикл решений, политики безопасности, объяснимые патчи, session-memory и гибридный режим auto/manual для рефакторинга.

**Статус: все шаги 2.7.1–2.7.10 реализованы.**


| #      | Шаг                     | Задача                                                                                                                                                   | Критерий готовности                                                                                                    |
| ------ | ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| 2.7.1  | Agent Runtime Core      | Добавить единый runtime-цикл (`observe -> reason -> propose -> apply -> verify -> learn`) в `eurika/agent/runtime.py`; режимы `assist`, `hybrid`, `auto` | ✅ run_agent_cycle, _STAGES; AgentRuntimeState; --runtime-mode; test_agent_runtime_stage_exception; scan/doctor/fix без изменения контракта |
| 2.7.2  | Tool Contract Layer     | Ввести типизированные адаптеры инструментов (scan, patch, verify, rollback, tests, git-read) с единым `ToolResult`                                       | ✅ DefaultToolContract, OrchestratorToolset; tests/test_tool_contract.py; dry-run воспроизводим                                                                 |
| 2.7.3  | Policy Engine           | Реализовать policy-конфиг для auto-apply (ограничения по risk, file patterns, max files/ops, API-breaking guard)                                         | ✅ PolicyConfig, evaluate_operation; allow/deny/review; deny_patterns, max_ops, api_breaking_guard; tests/test_agent_policy.py                                 |
| 2.7.4  | Explainability Record   | Для каждой операции сохранять `why`, `risk`, `expected_outcome`, `rollback_plan` и outcome verify                                                        | ✅ operation_explanations в eurika_fix_report.json; eurika explain; tests/test_explainability.py                                                                 |
| 2.7.5  | Session Memory          | Добавить память сессии/кампании: история решений, повторные провалы, подавление шумовых операций                                                         | ✅ SessionMemory, rejected_keys, verify_fail_keys; apply_campaign_memory; --allow-campaign-retry; tests/test_session_memory.py, test_cycle                                                |
| 2.7.6  | Human-in-the-loop CLI   | Добавить интерактивный approval в `fix` для `hybrid` (approve/reject/skip/all), с `--non-interactive` для CI                                             | ✅ select_hybrid_operations, read_hybrid_choice; --approve-ops, --reject-ops, --non-interactive; tests/test_hitl_cli.py                                                                    |
| 2.7.7  | Safety & Rollback Gates | Ужесточить guardrails: обязательный verify-gate, авто-rollback при regressions, лимиты на серию операций                                                 | ✅ auto_rollback=True, backup=True; enrich_report_with_rescan; record_verify_failure; tests/test_safety_rollback_gates.py                                                                 |
| 2.7.8  | Telemetry & KPIs        | Добавить метрики операционности: apply-rate, rollback-rate, no-op-rate, median verify time                                                               | ✅ telemetry в fix report; aggregate_operational_metrics; suggest_policy_from_telemetry; /api/operational_metrics; Dashboard; campaign_skipped/session_skipped                                 |
| 2.7.9  | Stability Campaign      | Провести серию прогонов runtime (assist/hybrid/auto) на Eurika                                                                   | ✅ CYCLE_REPORT: стабильные циклы; split_module guard на *_extracted.py                                                                                         |
| 2.7.10 | Docs & Migration        | Обновить CLI.md, ROADMAP, CYCLE_REPORT с новым режимом runtime и правилами эксплуатации                                                      | ✅ CLI.md, CYCLE_REPORT, UI.md — runtime-режимы, --allow-campaign-retry, telemetry, operational_metrics                                                                                  |


**Порядок внедрения (рекомендуемый):** 2.7.1 -> 2.7.2 -> 2.7.3 -> 2.7.4 -> 2.7.5 -> 2.7.6 -> 2.7.7 -> 2.7.8 -> 2.7.9 -> 2.7.10.

**Фактический прогресс (фаза 2.7):**

- 2.7.1 Agent Runtime Core — ✅ цикл `observe→reason→propose→apply→verify→learn` в `eurika/agent/runtime.py`; режимы assist/hybrid/auto; unit-тесты; CLI без изменения scan/doctor/fix
- 2.7.2 Tool Contract Layer — ✅ DefaultToolContract, OrchestratorToolset; ToolResult; tool_contract.py; tests/test_tool_contract.py
- 2.7.3 Policy Engine — ✅ PolicyConfig, load_policy_config; evaluate_operation; allow/deny/review; deny_patterns, max_ops, api_breaking_guard; tests/test_agent_policy.py
- 2.7.4 Explainability Record — ✅ operation_explanations (why, risk, expected_outcome, rollback_plan, verify_outcome); eurika explain; tests/test_explainability.py
- 2.7.5 Session Memory — ✅ SessionMemory; rejected_keys, verify_fail_keys; apply_campaign_memory; record_verify_failure; --allow-campaign-retry; tests
- 2.7.6 Human-in-the-loop CLI — ✅ select_hybrid_operations, read_hybrid_choice; --approve-ops, --reject-ops, --non-interactive; tests/test_hitl_cli.py
- 2.7.7 Safety & Rollback Gates — ✅ auto_rollback, backup=True; enrich_report_with_rescan; record_verify_failure; tests/test_safety_rollback_gates.py
- 2.7.8 Telemetry & KPIs — ✅ apply_rate, rollback_rate, no_op_rate; aggregate_operational_metrics; suggest_policy_from_telemetry; /api/operational_metrics; Dashboard; campaign_skipped/session_skipped
- 2.7.9 Stability Campaign — ✅ CYCLE_REPORT; split_module guard на *_extracted; стабильные циклы
- 2.7.10 Docs & Migration — ✅ CLI.md, CYCLE_REPORT, UI.md; runtime-режимы, telemetry, --allow-campaign-retry

**Метрики выхода из фазы 2.7 (DoD):**

- apply-rate в `eurika fix` устойчиво растёт, а no-op-rate снижается относительно базовой линии.
- В `hybrid` режиме пользователь контролирует medium/high-risk операции без потери воспроизводимости.
- Каждый применённый патч имеет machine-readable rationale и rollback trail.
- Новые режимы не ухудшают verify-success и не повышают шум в git diff.

### Фаза 2.8 — Декомпозиция слоёв и анти-монолитный контур (по review v2.7.0)

**Цель:** остановить рост монолитности в точках концентрации (`cli/orchestrator.py`, `eurika_cli.py`, `architecture_planner.py`, `patch_apply.py`), формализовать слои и зафиксировать импорт-контракт между подсистемами.

**Статус: все шаги 2.8.1–2.8.8 реализованы.**

| #     | Шаг                          | Задача                                                                                                                                                               | Критерий готовности                                                                                                      |
| ----- | ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| 2.8.1 | Layer Map                    | Формально зафиксировать слои в `ARCHITECTURE.md`: Infrastructure (IO/CLI/FS) → Core graph model → Analysis → Planning → Execution → Reporting                        | ✅ Architecture.md §0 L0–L6; allowed deps; anti-patterns; mapping модулей; ссылки в CLI.md                                 |
| 2.8.2 | Dependency Guard             | Ввести проверку «запрещённых импортов» (no upward deps) как тест/линт-гейт                                                                                           | ✅ test_dependency_guard.py, test_dependency_firewall.py; eurika.checks.dependency_firewall; EURIKA_STRICT_LAYER_FIREWALL=1; release_check, CI                                            |
| 2.8.3 | Orchestrator Split           | Разрезать `cli/orchestrator.py` на `cli/orchestration/` модули стадий + `cli/wiring/` + тонкий фасад `run_cycle`                                                     | ✅ cli/orchestration/ (full_cycle, fix_cycle_impl, prepare, apply_stage, doctor, hybrid_approval, facade); cli/orchestrator тонкий фасад                                                 |
| 2.8.4 | CLI Wiring Split             | Декомпозировать `eurika_cli.py`: parser builders/command registration/wiring по модулям                                                                              | ✅ cli/wiring/ (parser.py, dispatch.py); тесты CLI-парсинга зелёные                                                        |
| 2.8.5 | Planner Boundary             | Разделить `architecture_planner.py` на анализ рисков, правила планирования и сборку операций (без смешения отчётности/форматирования)                                | ✅ architecture_planner_build_plan, _build_patch_plan, _build_action_plan; get_patch_plan/build_patch_plan совместимы                                                                     |
| 2.8.6 | Patch Subsystem              | Эволюционировать `patch_apply.py` в подсистему (`patch/planner.py`, `patch/executor.py`, `patch/validator.py`, `patch/rollback.py`) с обратной совместимостью фасада | ✅ patch_apply*, patch_engine* (apply_patch, verify_patch, rollback_patch, apply_and_verify); публичный API сохранён                                                                      |
| 2.8.7 | Violation Audit              | Найти и закрыть реальные нарушения слоёв (анализ ↔ execution ↔ reporting)                                                                                            | ✅ CYCLE_REPORT; 0 violations (Architecture.md); закрыты cross-layer patch_apply из CLI, wildcard-shims в reasoning/*                                                                    |
| 2.8.8 | Dogfooding on New Boundaries | Провести 3 цикла `doctor + fix --dry-run + fix` после декомпозиции                                                                                                   | ✅ CYCLE_REPORT; verify стабилен; rollback/no-op без всплеска; telemetry и safety-gates стабильны                                                                                        |


**Порядок внедрения (рекомендуемый):** 2.8.1 -> 2.8.2 -> 2.8.3 -> 2.8.4 -> 2.8.5 -> 2.8.6 -> 2.8.7 -> 2.8.8.

**Фактический прогресс (актуально):**

- 2.8.1 Layer Map — ✅ Architecture.md §0 L0–L6; allowed deps; anti-patterns; mapping модулей; ссылки CLI.md
- 2.8.2 Dependency Guard — ✅ test_dependency_guard.py, test_dependency_firewall.py; dependency_firewall; EURIKA_STRICT_LAYER_FIREWALL=1; 0 violations
- 2.8.3 Orchestrator Split — ✅ cli/orchestration/ (full_cycle, fix_cycle_impl, prepare, apply_stage, doctor); cli/orchestrator тонкий фасад
- 2.8.4 CLI Wiring Split — ✅ cli/wiring/ (parser, dispatch); тесты CLI зелёные
- 2.8.5 Planner Boundary — ✅ architecture_planner_build_plan, _build_patch_plan, _build_action_plan; get_patch_plan сохранён
- 2.8.6 Patch Subsystem — ✅ patch_apply_*, patch_engine_*; API patch_apply/patch_engine сохранён
- 2.8.7 Violation Audit — ✅ CYCLE_REPORT; 0 violations; закрыты cross-layer patch_apply, wildcard-shims в reasoning/*
- 2.8.8 Dogfooding on New Boundaries — ✅ doctor → fix --dry-run → fix; verify стабилен; telemetry/safety-gates без регресса
- Доп. стабилизация planner (R4): guard на `*_extracted.py` для split_module; test_build_patch_plan_skips_split_for_already_extracted_module

**Метрики выхода из фазы 2.8 (DoD):**

- Уменьшение централизации по файлам: `cli/orchestrator.py`, `eurika_cli.py`, `architecture_planner.py`, `patch_apply.py` больше не являются top outliers по LOC/смешению ролей.
- Импорт-контракт слоёв формализован и автоматически проверяется.
- Runtime (assist/hybrid/auto) сохраняет поведение и тестовую стабильность после декомпозиции.
- Нет всплеска no-op/rollback-rate из-за структурных изменений.

#### Детализация 2.8.3 — Orchestrator Split (план коммитов)

**Идея:** делать «тонкий фасад + вынос по стадиям» без больших взрывных PR; каждый шаг сохраняет поведение и проходит тесты.

**Статус: план выполнен (2.8.3 завершён).**

| Коммит  | Что переносим                                                                                     | Целевые файлы                                                    | Критерий                                                                        |
| ------- | ------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| 2.8.3.a | Вынести общие модели/типы цикла (`FixCycleContext`, `FixCycleResult`, protocol-обёртки deps)      | `cli/orchestration/models.py`, `cli/orchestration/deps.py`       | ✅ FixCycleContext в models; FixCycleDeps в deps; orchestrator импортирует        |
| 2.8.3.b | Вынести pre-stage (`scan/diagnose/plan/policy/session-filter`)                                    | `cli/orchestration/prepare.py`                                   | ✅ prepare_fix_cycle_operations, apply_campaign_memory; dry-run идентично        |
| 2.8.3.c | Вынести apply-stage (`apply+verify`, rescan enrich, write report, memory append)                  | `cli/orchestration/apply_stage.py`                               | ✅ execute_fix_apply_stage, build_fix_cycle_result; verify/rollback/telemetry OK   |
| 2.8.3.d | Вынести doctor/full-flow wiring                                                                   | `cli/orchestration/doctor.py`, `cli/orchestration/full_cycle.py` | ✅ run_doctor_cycle, run_cycle_entry; run_cycle(mode=doctor/full) тот же payload   |
| 2.8.3.e | Оставить в `cli/orchestrator.py` только фасад (`run_cycle`, thin wrappers, compatibility imports) | `cli/orchestrator.py`                                            | ✅ ~250 LOC; run_cycle, run_doctor_cycle, run_fix_cycle, run_full_cycle; делегация |
| 2.8.3.f | Добавить regression-тесты на эквивалентность stage-вывода и edge-cases                            | `tests/test_cycle.py`, `tests/test_cli_runtime_mode.py`          | ✅ test_cycle, test_cli_runtime_mode, test_cycle_state; зелёные                  |


**Жёсткие ограничения при переносе:**

- Не менять JSON-контракт `eurika_fix_report.json` и поля `telemetry/safety_gates/policy_decisions`.
- Не ломать CLI-флаги (`--runtime-mode`, `--non-interactive`, `--session-id`, `--dry-run`, `--quiet`).
- Сначала перенос кода 1:1, потом только точечные улучшения.

**Критерий «2.8.3 завершена»:**

- `cli/orchestrator.py` — фасадный слой (без тяжёлой бизнес-логики стадий).
- Поведение `doctor/fix/cycle` эквивалентно до/после (по regression-тестам и dry-run снапшотам).
- Документация (`CYCLE_REPORT.md`) содержит «до/после» по LOC и список вынесенных модулей.

---

### Фаза 2.9 — Углубление цикла (LLM + Knowledge + Learning) — **приоритет над 3.0**

**Цель:** делать цикл «умнее» в рамках одного проекта: анализ → поиск решений (Ollama + документация) → рефакторинг → обучение. Глубина перед широтой (3.0 multi-repo).

**Приоритет:** фаза 2.9 важнее 3.0 — сначала повысить качество и интеллект single-project цикла, затем масштабировать.

**Статус: все шаги 2.9.1–2.9.5 реализованы.**

| #     | Шаг                            | Задача                                                                                                                                                       | Критерий готовности                                                                                                   |
| ----- | ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------- |
| 2.9.1 | Architect → рекомендации «как» | Расширить architect: не только «что не так», но и «что делать и как» — на основе Knowledge Layer (PEP, docs.python.org, release notes)                       | ✅ Recommendation (how to fix); Reference (from documentation); SMELL_TO_KNOWLEDGE_TOPICS; test_architect.py          |
| 2.9.2 | LLM в планировании             | Для сложных smell (god_module, hub, bottleneck) — запрос к Ollama: «предложи точки разбиения»; результат в patch_plan как hints или уточнённые target/params | ✅ ask_ollama_split_hints; hints в patch_plan; EURIKA_USE_LLM_HINTS; ask_llm_extract_method_hints; test_planner_llm.py |
| 2.9.3 | Knowledge Layer — PEP/RFC      | Добавить провайдеры PEP, RFC, What's New (docs.python.org); темы по smell_type (god_module → module_structure, long_function → extract_method)               | ✅ PEPProvider, LocalKnowledgeProvider, CompositeKnowledgeProvider; SMELL_TO_KNOWLEDGE_TOPICS; doctor/planner/chat     |
| 2.9.4 | Обучение в цикле               | Корректировка policy из telemetry; suggest_policy_from_telemetry выводится в doctor; опция применять suggested policy                                        | ✅ doctor «Suggested policy»; load_suggested_policy_for_apply; --apply-suggested-policy; test_doctor, test_cycle       |
| 2.9.5 | Dogfooding 2.9                 | 3 цикла с LLM + Knowledge на Eurika; сравнить качество плана (релевантность подсказок) и apply-rate                                                          | ✅ CYCLE_REPORT; architect «как»; apply-rate и learning стабильны                                                      |


**Порядок внедрения (рекомендуемый):** 2.9.1 → 2.9.3 → 2.9.2 → 2.9.4 → 2.9.5. Architect и Knowledge — основа; LLM в planner — поверх; learning — замкнутый цикл.

**Фактический прогресс (фаза 2.9):**

- 2.9.1 Architect рекомендации — ✅ Recommendation (how to fix), Reference (from documentation); architect.py, architect_format.py; test_architect.py
- 2.9.2 LLM в планировании — ✅ planner_llm.ask_ollama_split_hints, ask_llm_extract_method_hints; EURIKA_USE_LLM_HINTS; hints в planner_patch_ops; test_planner_llm.py
- 2.9.3 Knowledge PEP/RFC — ✅ eurika.knowledge: PEPProvider, SMELL_TO_KNOWLEDGE_TOPICS; doctor/planner/chat используют; test_knowledge.py
- 2.9.4 Обучение в цикле — ✅ suggest_policy_from_telemetry; doctor Suggested policy; load_suggested_policy_for_apply; --apply-suggested-policy
- 2.9.5 Dogfooding 2.9 — ✅ CYCLE_REPORT; verify ✓; apply-rate, learning стабильны

**Метрики выхода из фазы 2.9 (DoD):**

- Architect при god_module даёт «разбить по ответственностям X, Y, Z» с reference на доку.
- При Ollama: planner для high-risk smell получает LLM-hints (опционально).
- doctor выводит suggested policy при низком apply_rate.
- Dogfooding: apply-rate не падает; релевантность рекомендаций растёт.

**Связь с 3.0:** 2.9 углубляет single-project; 3.0 расширяет на multi-repo. Рекомендуется завершить 2.9.1–2.9.3 до активной работы над 3.0.2 (cross-project memory).

---

### Статус рекомендаций review.md

**review v3.0.1 (§6 — v3.1):**

- Формализовать слои (L0–L6) → Фаза 3.1-arch.1
- API-границы подсистем → 3.1-arch.2
- Лимит размера файлов (>400/600 LOC) → 3.1-arch.3
- Domain vs presentation → 3.1-arch.4

**review §7 (ранее):**


| Пункт review                        | Статус | Примечание                                                  |
| ----------------------------------- | ------ | ----------------------------------------------------------- |
| 1. Event Engine                     | ✓      | eurika/storage/event_engine.py, ProjectMemory.events        |
| 2. Усилить execution                | ✓      | apply_patch, verify_patch, rollback_patch, auto_rollback    |
| 3. Verify stage обязательный        | ✓      | verify после patch, откат при провале                       |
| 4. Граф как операционный инструмент | ✓      | Фаза 3.1: приоритеты, триггеры, метрики, targets_from_graph |
| 5. Центральный orchestrator         | ✓      | run_cycle(path, mode=doctor/fix), cli/orchestrator.py       |


---

### Фаза 3.0 — Architectural AI Engineer (дорожная карта)

**Цель v3.0:** Eurika работает с несколькими репозиториями, общей памятью между проектами, расширенным Knowledge Layer и режимом совместной работы.

**Рекомендуемый порядок:** 3.0.1 → 3.0.2 → 3.0.3 → 3.0.4. Multi-repo — предпосылка для cross-project memory; online knowledge расширяет существующий Knowledge Layer; team-mode опирается на policy и session-memory.

**Статус: 3.0.1–3.0.4 реализованы; 3.0.5 (Learning from GitHub) — частично.**

| #     | Шаг                           | Задача                                                                                                                            | Критерий готовности                                                                                                                                          |
| ----- | ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 3.0.1 | Multi-Repo Scan               | Поддержка `eurika scan <path1> <path2> ...` для нескольких корней проектов                                                        | ✅ path nargs="*"; последовательное выполнение; "--- Project N/M ---"; _aggregate_multi_repo_reports                                                           |
| 3.0.2 | Cross-Project Memory          | Общая директория памяти (`~/.eurika/` или `EURIKA_GLOBAL_MEMORY`) для learning/feedback между проектами                          | ✅ global_memory.py; get_merged_learning_stats; append_learn_to_global; test_global_memory.py                                                                   |
| 3.0.3 | Online Knowledge (расширение) | Расширить Knowledge Layer: fetch по запросу, провайдеры PEP/RFC, интеграция с architect                                          | ✅ --online в doctor/fix/cycle/architect; force_online; TTL, rate_limit в PEPProvider                                                                        |
| 3.0.4 | Team Mode                     | Роли, shared session, approvals между пользователями; интеграция с CI (отдельный approve-step)                                    | ✅ --team-mode, --apply-approved; pending_plan.json; team_mode.py; CYCLE_REPORT сценарии                                                                    |


**Фактический прогресс (фаза 3.0):**

- 3.0.1 Multi-Repo Scan — ✅ path nargs="*"; _paths_from_args; последовательное выполнение; "--- Project N/M ---"; _aggregate_multi_repo_reports
- 3.0.2 Cross-Project Memory — ✅ get_merged_learning_stats; append_learn_to_global; ~/.eurika/ или EURIKA_GLOBAL_MEMORY; planner использует merged stats
- 3.0.3 Online Knowledge — ✅ --online; force_online в PEPProvider; doctor/architect получают свежие фрагменты
- 3.0.4 Team Mode — ✅ --team-mode, --apply-approved; pending_plan.json; team_mode.py; документация в CYCLE_REPORT

**Метрики выхода из фазы 3.0 (DoD):**

- Один вызов `eurika cycle` может обработать несколько репозиториев с агрегированным отчётом.
- Learning из одного проекта влияет на план fix в другом (при наличии cross-project memory).
- Architect при multi-repo получает контекст из online knowledge.
- Team-mode сценарий (propose → approve → apply) задокументирован и покрыт тестами.

**Зависимости:** 3.0.1 не зависит от остальных; 3.0.2 требует 3.0.1 (multi-repo как источник проектов для memory); 3.0.3 можно вести параллельно; 3.0.4 опирается на policy/session-memory (2.7.5, 2.7.6).

#### 3.0.5 Learning from GitHub (в работе)

**Интерпретация multi-repo:** не только «сканировать несколько локальных путей», но и **учиться на открытых проектах GitHub** — искать паттерны, успешные рефакторинги, примеры хорошей структуры модулей.

**Фактический прогресс:**

- 3.0.5.1 Curated repos — `eurika learn-github [path]`; `eurika/learning/curated_repos.py` (CURATED_REPOS, clone_repo, load_curated_repos, ensure_repo_cloned); `docs/curated_repos.example.json`; опция `--scan` — scan после клонирования; кэш `path/../curated_repos/` (рядом с проектом)
- 3.0.5.2 GitHub search — `eurika learn-github . --search "language:python stars:>1000"`; `eurika/learning/github_search.py` (search_repositories); GITHUB_TOKEN для повышения rate limit
- 3.0.5.4 Operability — build_patch_plan loads .eurika/pattern_library.json; planner_patch_ops adds OSS examples to god_module/hub/bottleneck/cyclic_dependency diff hints


| #       | Шаг             | Задача                                                                                          | Критерий готовности                                                                                                                                                                                    |
| ------- | --------------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 3.0.5.1 | Curated repos   | Список OSS-проектов (Django, FastAPI и т.п.) для периодического анализа                         | ✓ Клонирование/сканирование; извлечение примеров smell→fix — в 3.0.5.3                                                                                                                                 |
| 3.0.5.2 | GitHub search   | Поиск проектов по критериям (language:python, stars, topics)                                    | ✓ --search QUERY; GitHub REST API; GITHUB_TOKEN опционально                                                                                                                                            |
| 3.0.5.3 | Pattern library | Сбор «что сработало»: split_module, extract_class, refactor_code_smell в реальных кодовых базах | ✓ extract_patterns_from_repos; OSSPatternProvider; .eurika/pattern_library.json; architect получает [oss_patterns] в Reference при architecture_refactor                                               |
| 3.0.5.4 | Операционность  | Использование паттернов для улучшения apply-rate: реальные фиксы вместо только TODO             | ✓ build_patch_plan загружает .eurika/pattern_library.json; god_module, hub, bottleneck, cyclic_dependency получают OSS-примеры в diff hints; refactor_code_smell по-прежнему в WEAK_SMELL_ACTION_PAIRS |


**Цель:** повысить операционность за счёт обучения на алгоритмах и структуре успешных OSS-проектов.

---

### Фаза 3.1 — Граф как движок (по review §7.4, §3.3)

**Цель:** граф не только анализирует, но определяет приоритет рефакторинга, триггерит операции, служит базой метрик (источник приоритетов, триггер операций, база метрик).


| #     | Шаг                             | Задача                                                                                                                             | Критерий готовности                                                                                                              |
| ----- | ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| 3.1.1 | Приоритизация из графа          | Функция `priority_from_graph(graph, smells)` → упорядоченный список модулей для рефакторинга (по degree, severity, fan-in/fan-out) | ✓ graph_ops.priority_from_graph; get_patch_plan использует; тесты test_priority_from_graph_*                                     |
| 3.1.2 | Триггер операций по типам smell | По god_module/hub/bottleneck в графе — автоматически маппинг в split_module / introduce_facade в patch_plan                        | ✓ graph_ops.SMELL_TYPE_TO_REFACTOR_KIND, refactor_kind_for_smells(); planner использует; hub→split_module; тесты                 |
| 3.1.3 | Граф как база метрик            | health_score, risk_score, centrality — вычисляются из графа; влияют на verify_metrics и evolution                                  | ✓ graph_ops.metrics_from_graph, centrality_from_graph; history и orchestrator используют; тесты                                  |
| 3.1.4 | Инициация операций графом       | Граф не только «рекомендует», но передаёт в patch_plan конкретные цели (target_file, kind) из своей структуры                      | ✓ targets_from_graph; build_patch_plan использует graph.nodes/edges; introduce_facade params от suggest_facade_candidates; тесты |


**Выход из фазы:** граф — стратегический слой; patch_plan формируется с опорой на граф, а не только на эвристики.

---

### Фаза 3.1-arch — Архитектурная дисциплина (по review v3.0.1)

**Цель:** переход от «сложной утилиты» к «архитектурной платформе»; зафиксировать слои, ограничить зависимости, почистить центры тяжести. Диагноз review: зрелость выше средней, но риск монолитизации; нужен дисциплинированный этап.

**Статус: все шаги 3.1-arch.1–3.1-arch.7 реализованы.**

| #          | Шаг                            | Задача                                                                                                                                                            | Критерий готовности                                                                     |
| ---------- | ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| 3.1-arch.1 | Формальные слои                | Зафиксировать слои в документе: L0 Infrastructure → L1 Core model → L2 Analysis → L3 Planning → L4 Execution → L5 Reporting → L6 CLI; запретить зависимости вверх | ✅ Architecture.md §0; L0–L6; allowed deps; dependency guard + layer firewall; 0 violations |
| 3.1-arch.2 | API-границы подсистем          | Каждая подсистема экспортирует 1–2 публичные точки входа; остальное private                                                                                       | ✅ __all__ в patch_engine, eurika.core, eurika.analysis, eurika.smells; API_BOUNDARIES.md |
| 3.1-arch.3 | Лимит размера файлов           | Правило: >400 строк — кандидат на разбиение; >600 строк — обязательно делить                                                                                      | ✅ eurika.checks.file_size; check_file_size_limits; self-check; test_file_size_check.py  |
| 3.1-arch.4 | Domain vs presentation         | Модули, которые и вычисляют, и форматируют Markdown — разделить на domain + presentation                                                                          | ✅ architecture_report (rendering); central_modules_for_topology; runtime_scan → верхний слой |
| 3.1-arch.5 | Облегчить CLI                  | CLI только принимает команды и передаёт оркестратору; убрать бизнес-логику и сложные пайплайны из CLI-слоя                                                        | ✅ format_report_snapshot; eurika.api фасады; handlers тонкие; test_handle_report_snapshot_delegates |
| 3.1-arch.6 | Развести Planning и Execution  | Planner строит план; Executor исполняет; убрать взаимное знание деталей                                                                                           | ✅ Architecture.md §0.5 Planner–Executor Contract; planner без patch_apply; dependency guard |
| 3.1-arch.7 | Dogfooding на новой дисциплине | 3 цикла scan → doctor → fix после внедрения ограничений                                                                                                           | ✅ CYCLE_REPORT §28; verify ✓; eurika fix . без регресса                                 |


**Порядок внедрения (рекомендуемый):** 3.1-arch.1 → 3.1-arch.2 → 3.1-arch.5 → 3.1-arch.6 → 3.1-arch.4 → 3.1-arch.3 → 3.1-arch.7.

**Фактический прогресс (фаза 3.1-arch):**

- 3.1-arch.1 Формальные слои — ✅ Architecture.md §0; L0–L6; dependency guard; EURIKA_STRICT_LAYER_FIREWALL=1
- 3.1-arch.2 API-границы подсистем — ✅ __all__ в patch_engine, eurika.core, eurika.analysis, eurika.smells, eurika.evolution, eurika.reporting
- 3.1-arch.3 Лимит размера файлов — ✅ check_file_size_limits; >400 candidate, >600 must split; self-check; python -m eurika.checks.file_size
- 3.1-arch.4 Domain vs presentation — ✅ architecture_report rendering; central_modules_for_topology
- 3.1-arch.5 Облегчить CLI — ✅ format_report_snapshot; eurika.api фасады; test_handle_report_snapshot_delegates_to_format
- 3.1-arch.6 Развести Planning и Execution — ✅ Planner–Executor Contract; planner без patch_apply; dependency guard eurika/reasoning/
- 3.1-arch.7 Dogfooding — ✅ CYCLE_REPORT §28; verify стабилен

**Связь с review v3.0.1:** пункты §6 «Что я рекомендую сделать в v3.1».

---

### Фаза 3.2 — Единая модель памяти (по review §3.2)

**Цель:** память как система знаний, а не набор разрозненных файлов; единая модель события; Event — первичная сущность.


| #     | Шаг                          | Задача                                                                                                                 | Критерий готовности                                                                                                                                          |
| ----- | ---------------------------- | ---------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 3.2.1 | Консолидация storage         | Learning, feedback, events — единый ProjectMemory; один формат сериализации (JSONL или структурированный JSON)         | ✓ Все артефакты в project_root/.eurika/: events.json, learning.json, feedback.json, observations.json, history.json; миграция из legacy путей                |
| 3.2.2 | Event как первичная сущность | Решение (Decision), действие (Action), результат (Result) записываются как Event; логи и история — проекции EventStore | ✓ LearningView, FeedbackView — views над EventStore; append пишет type=learn/feedback; aggregate_* читают из events.by_type()                                |
| 3.2.3 | Контекст для architect       | Из EventStore извлекать последние патчи, результаты verify для подстановки в architect/LLM                             | ✓ EventStore.recent_events; _format_recent_events; architect использует recent_events в prompt (template + LLM); handle_architect, run_doctor_cycle передают |


**Выход из фазы:** memory концептуально единая; тормоз эволюции (раздробленность) снят.

---

### Горизонт 3 — Roadmap до 3.0 (по обновлённому review.md)

**Версионирование:** major.minor берётся из фазы ROADMAP (2.1, 2.3, 2.6, 3.0); patch — инкремент внутри фазы. pyproject.toml и eurika_cli следуют этой схеме.

**Направление (без жёстких дат):** движение к архитектурному AI-инженеру. Фундамент заложен; фазы 2.7, 2.8, 2.9, 3.0, 3.1-arch и 3.2 реализованы.


| Версия   | Цель                      | Содержание                                                                                     |
| -------- | ------------------------- | ---------------------------------------------------------------------------------------------- |
| **v2.1** | Execution Milestone       | Orchestrator ✓; PatchEngine v1 ✓; Verify ✓; Rollback ✓; 3 детермин. операции ✓.                |
| **v2.3** | Stability Phase           | Метрики; priority engine ✓; CI-ready ✓ (CLI.md § CI/CD); CLI doctor/fix/explain ✓.             |
| **v2.6** | Semi-Autonomous Agent     | auto-run ✓; continuous monitoring ✓; performance-based improvement ✓; event-based learning ✓.  |
| **v3.0** | Architectural AI Engineer | multi-repo ✓; cross-project memory ✓; online knowledge ✓; team-mode ✓.                         |


---

## Архив: выполненные этапы v0.1–1.0

_Ниже — исторические разделы; нумерация 1–7 не связана с фазами 2.x/3.x._

## Стратегия выхода в 1.0


| Версия | Фокус                                               |
| ------ | --------------------------------------------------- |
| v0.5   | стабилизация pipeline ✓                             |
| v0.6   | history + diff ✓                                    |
| v0.7   | CLI UX ✓                                            |
| v0.8   | smells 2.0 ✓                                        |
| v0.9   | layout skeleton + eurika.* imports + документация ✓ |
| v1.0   | релиз ✓                                             |


---

### 1. Архитектурная целостность

- Pipeline: scan → graph → smells → summary → history → diff → report
- ArchitectureSnapshot как единый объект
- core/pipeline.py, cli/handlers.py
- Скелет eurika/ + фасады + импорты среднего слоя (analysis, smells.rules, evolution, reporting, self_map, topology)
- Перенос реализации в eurika/*: smells (detector, models, health, advisor), analysis.metrics; плоские файлы — реэкспорты
- architecture_summary → eurika.smells.summary (реализация в пакете, плоский — реэкспорт)
- evolution (history, diff) → eurika.evolution.history, eurika.evolution.diff (реализация в пакете, плоские — реэкспорты; architecture_diff.py сохраняет CLI)

---

### 2. Architecture History Engine

#### 2.1 Модель данных

- version (pyproject.toml)
- git_commit (опционально)
- diff metrics (дельты, не только абсолюты)

#### 2.2 Регрессии

- god_module, bottleneck, hub — отдельно
- risk score (0–100)

#### 2.3 Будущее

- JSON API под future UI: `eurika.api` (get_summary, get_history, get_diff), `eurika serve` (GET /api/summary, /api/history, /api/diff)

---

## 3. Smell Engine

- Уровень серьёзности: low / medium / high / critical (severity_to_level)
- Remediation hints (что делать) — REMEDIATION_HINTS, get_remediation_hint
- Корреляция со history — Smell history (per-type counts in evolution_report)

---

## 4. Architecture Diff Engine

- Топ-модули по росту fan-in
- Модули, ставшие bottleneck
- Деградация maturity
- Блок "Recommended actions: refactor X, split Y, isolate Z"

---

## 5. CLI

### 5.1 Команды

- eurika scan ., arch-summary, arch-history, arch-diff, self-check
- eurika history (алиас arch-history)
- eurika report (summary + evolution report)
- eurika explain module.py
- eurika serve [path] (JSON API для UI)

### 5.2 UX

- Цветной вывод (--color / --no-color)
- ASCII charts (health score, risk score)
- Markdown (--format markdown)

---

## 6. Документация

- README, Architecture, CLI.md, THEORY.md

---

## PyTorch (опционально, после стабилизации ядра)

Статус: **не обязательная зависимость** для базового Qt/CLI/API контура.

### Когда подключать

Подключаем PyTorch только при наличии измеримого выигрыша в одном из сценариев:

1. Локальные embeddings/RAG без внешних API.
2. Локальный классификатор intent/risk/confidence для Universal Task Executor.
3. Дообучение/ранжирование на outcome-данных (`execute+verify`) для повышения качества планов.

### Критерии входа

- Текущий детерминированный контур стабилен (execute/verify/report, risk-gate, rollback).
- Есть baseline-метрики качества (intent accuracy, false-positive action rate, verify success rate).
- Есть офлайн-набор данных (chat+outcome events), достаточный для валидации.

### Принципы интеграции

- `torch` ставится как optional extra (например, `.[ml]`), не в базовый install.
- По умолчанию fallback на текущий rule-based + LLM контур.
- Любая ML-ветка должна иметь деградацию в deterministic режим при ошибках/отсутствии модели.

### Метрики успеха

- +N% к точности intent/risk при неизменном или меньшем false-positive rate.
- Снижение доли лишних уточнений без роста ошибочных исполнений.
- Рост `verify_success_rate` по `smell|action|target` в контролируемом окне.

---

## Чеклист перед v1.0 (выполнен)

- Разделы 1–6 ROADMAP выполнены (архитектура, history, smells, diff, CLI, документация)
- JSON API и eurika serve реализованы
- Версия обновлена на 1.0.0, CHANGELOG v1.0.0 записан

---

## 7. Мини-AI слой (после v1.0)

- Интерпретация архитектуры: `eurika architect [path]` — шаблонная сводка + опционально LLM (OPENAI_API_KEY; поддержка OpenRouter через OPENAI_BASE_URL, OPENAI_MODEL); ответ в стиле "архитектор проекта"
- Генерация рефакторинг-плана (эвристики): `eurika suggest-plan [path]` и `eurika.reasoning.refactor_plan.suggest_refactor_plan` — из summary/risks или из build_recommendations; LLM — в перспективе
- Расширение: подсказки архитектора связаны с patch-plan и explain (ROADMAP §7)

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

### ~~TODO до продуктовой 1.0~~ (закрыто)

- ~~Консолидация памяти~~ — **выполнено (Фаза 3.2):** EventStore, LearningView, FeedbackView, .eurika/
- ~~Замкнутый цикл (скелет)~~ — **выполнено:** scan → diagnose → plan → patch → verify → learn; Patch Engine, verify, rollback
- ~~Killer-feature~~ — **выполнено:** remove_cyclic_import, remove_unused_import, split_module; eurika fix с verify и откатом
- ~~CLI режимы~~ — **выполнено:** scan, doctor, fix, explain — первые 4 продуктовые; остальные в Advanced

### Уже есть (не дублировать)

- Pipeline scan → graph → smells → summary → history → diff → report.
- patch-apply, --verify, learning loop, architecture_history, evolution_report.
- `eurika architect` (интерпретация), `eurika explain`, JSON API, self-check.

---

## Что по-прежнему не хватает (по review.md)

- ~~**Нет полноценного операционного цикла**~~ — **выполнено:** Scan → Diagnose → Plan → Patch → Verify → Log; apply_and_verify, auto_rollback, run_cycle.
- ~~**Граф недоиспользован**~~ — **выполнено (Фаза 3.1):** priority_from_graph, SMELL_TYPE_TO_REFACTOR_KIND, targets_from_graph, metrics_from_graph — patch_plan формируется с опорой на граф.
- ~~**Memory концептуально раздроблена**~~ — **выполнено (Фаза 3.2):** консолидация в .eurika/; EventStore; LearningView, FeedbackView; architect.recent_events.

### Причина низкой операционности (5/10): TODO vs реальные фиксы

Цикл fix формально завершён, но **patch часто = append TODO-комментарий**, а не изменение кода. По данным learning: refactor_code_smell — 0% success; добавлен в WEAK_SMELL_ACTION_PAIRS (hybrid: review, auto: deny).


| Операция                | Результат                                                                                                                                              |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| remove_cyclic_import    | ✓ Реальный фикс (AST)                                                                                                                                  |
| remove_unused_import    | ✓ Реальный фикс (в fix cycle по умолчанию, фаза 2.4)                                                                                                   |
| introduce_facade        | ✓ Реальный фикс (создаёт {stem}_api.py)                                                                                                                |
| extract_class           | ✓ Реальный фикс; god_class|extract_class в WEAK (hybrid: review, auto: deny); *tool_contract*.py в EXTRACT_CLASS_SKIP_PATTERNS                         |
| split_module (успех)    | ✓ Реальный фикс                                                                                                                                        |
| split_module (fallback) | ✓ Часто реальный (by_function, infer imports, relaxed extraction)                                                                                      |
| refactor_code_smell     | TODO-маркер когда нет реального фикса; deep_nesting: extract_block_to_helper (гибрид) или TODO; в WEAK_SMELL_ACTION_PAIRS — hybrid: review, auto: deny |
| refactor_module         | ✓ Пробует split_module chain, иначе TODO                                                                                                               |


**Приоритет:** стабилизация цикла, прогоны на других проектах.

**Для повышения операционности** допустимо обращаться к **интернету** (документация, примеры, best practices) и к **LLM** — для улучшения промптов, подбора стратегий фиксов, расширения pattern library, обучения на curated repos.

---

## Версия 2.1 — инженерный инструмент (целевое состояние)

Цель: 2.0 → «инженерный инструмент» (конкретная польза, автофиксы, стабильный CLI). Путь инженерный, не академический.


| Элемент                    | Статус | Задача                                                                                                                                                          |
| -------------------------- | ------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Patch Engine**           | ✓      | `patch_engine.py`: **apply_patch**, **verify_patch**, **rollback_patch**; apply_and_verify(..., **auto_rollback=True**) при провале verify откатывает изменения |
| **Verify stage**           | ✓      | После patch: перескан, сравнение health score; при ухудшении — откат (verify_metrics + rollback reason)                                                         |
| **Замкнутый цикл**         | ✓      | `eurika fix` = scan → diagnose → plan → patch → verify → learn; agent runtime (assist/hybrid/auto)                                                              |
| **Единая модель Event**    | ✓      | Фаза 3.2: .eurika/, EventStore, LearningView, FeedbackView, architect.recent_events                                                                             |
| **Граф как движок**        | ✓      | Фаза 3.1: priority_from_graph, SMELL_TYPE_TO_REFACTOR_KIND, targets_from_graph                                                                                  |
| **Архитектурные операции** | ✓      | Remove unused imports, remove_cyclic_import, split_module, introduce_facade, extract_class; refactor_code_smell в WEAK_SMELL_ACTION_PAIRS (hybrid/auto)         |


Детальный разбор — в **review.md**.

---

## План прорыва (этапы по review.md)

### Этап 1 — Patch Engine (критично)

- Создать/дополнить `patch_engine.py`: **apply_patch(plan)**, **verify_patch()**, **rollback_patch()**; **apply_and_verify(..., auto_rollback=True)** при провале verify откатывает изменения.

### Этап 2 — Три архитектурные операции

- Remove unused imports (`eurika clean-imports`, eurika.refactor.remove_unused_import)
- Detect and break cyclic imports (remove_cyclic_import в patch plan + patch_apply)
- Split oversized module (split_module по god_module: import-based + class-based)

### Этап 3 — Verify Stage

- После patch: пересканировать, сравнить health (risk_score); если after_score < before_score — откат и report["verify_metrics"], report["rollback"]["reason"] = "metrics_worsened".

### Этап 4 — Упростить Memory → Event Engine

- `eurika/storage/event_engine.py` — единая точка входа `event_engine(project_root)` → EventStore; Event { type, input, output/action, result, timestamp }; ProjectMemory.events использует event_engine; сериализация с полем `action` (review).

### Этап 5 — Упростить CLI

- Четыре продуктовых режима первыми: `eurika scan .`, `eurika doctor .`, `eurika fix .`, `eurika explain file.py`; остальные команды в блоке «Other», agent — «Advanced». Help и usage выводят 4 режима как Product.

### Dogfooding

- Провести полный цикл на самом проекте Eurika: scan → doctor → fix --dry-run.

---

## Стратегический вывод (по review.md)

> Доказать, что можешь сделать инструмент, который **меняет код** — а не только анализирует его.

Продуктовая 1.0 в полном смысле = после выполнения этапов 1–5 (Patch Engine, 3 автофикса, Verify, Event Engine, CLI 4 режима).

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

