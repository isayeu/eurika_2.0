# Eurika 2.0 — ROADMAP

Единый план задач. Контракт — в SPEC.md.

---

## Принцип ROADMAP

**Сейчас основная задача — саморазвитие:** анализ и исправление собственного кода, добавление новых функций по запросу. Eurika в первую очередь работает над собой (scan/doctor/fix по своей кодовой базе, доработки по обратной связи). Использование на других проектах — вторично и по мере надобности.

Долгосрочное видение — полноценный агент (звонки, финансы, код по запросу, собственная LLM и т.д.); до этого очень далеко. Ниже: текущее состояние → выполненный план прорыва → следующие шаги (горизонт 2, в фокусе работа над собой) → горизонт 3 (далёкое будущее).

---

## Текущее состояние (v2.7.x, актуальная ветка)

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
- **Текущий приоритет:** **Фаза 2.9** (углубление цикла: LLM + Knowledge + learning) — умнее в одном проекте перед масштабированием (3.0 multi-repo).
- **Стабилизация:** тесты зелёные, доки соответствуют коду.
- **Фазы 2.2 и 2.3:** выполнены (Knowledge: кэш, наполнение; Orchestrator: run_cycle).
- **Фазы 3.1 и 3.2:** выполнены (граф как движок; единая модель памяти).
- **По review v3.0.1:** добавлена **Фаза 3.1-arch** (архитектурная дисциплина) — формализация слоёв, API-границы, лимиты размера файлов, разделение domain/presentation.
- **Дальше:** повышать операционность и интеллект цикла (2.9); снижать noisy/unstable операции по learning-метрикам; держать документацию синхронной с кодом.

---

## Следующие шаги (горизонт 2)

План прорыва выполнен. Ниже — фазы без жёстких сроков, в приоритете саморазвитие и работа над собственной кодовой базой.

### Активный бэклог (операционность, ближайший фокус)

- [x] Повысить долю реальных apply в `eurika fix` (уменьшить долю `skipped: diff already in content` за счёт более точных операций) — _drop_noop_append_ops в prepare
- [x] Пересобрать policy для слабых пар learning (`hub|split_module`, `long_function|extract_nested_function`): фильтрация/понижение приоритета — WEAK_SMELL_ACTION_PAIRS, _deprioritize_weak_pairs
- [x] Добавить `long_function|refactor_code_smell` и `deep_nesting|refactor_code_smell` в WEAK_SMELL_ACTION_PAIRS (learning 0% success) — hybrid: review, auto: deny
- [x] Актуализировать артефакты после контрольных прогонов (`eurika_doctor_report.json`, `CYCLE_REPORT.md`) — `eurika report-snapshot .`, DOGFOODING
- [x] Поддерживать “малые рефакторинги + тесты” для топ-long/deep функций в core CLI/pipeline — _append_default_refactor_operation, _early_exit, _apply_content_replacement

### Фаза 2.7 — Нативный Agent Runtime в Eurika (без внешней прослойки)

**Цель:** встроить Cursor-подобный workflow напрямую в кодовую базу Eurika: управляемый цикл решений, политики безопасности, объяснимые патчи, session-memory и гибридный режим auto/manual для рефакторинга.

| # | Шаг | Задача | Критерий готовности |
|---|-----|--------|----------------------|
| 2.7.1 | Agent Runtime Core | Добавить единый runtime-цикл (`observe -> reason -> propose -> apply -> verify -> learn`) в `eurika/agent/runtime.py`; режимы `assist`, `hybrid`, `auto` | Есть unit-тесты на переходы состояний; цикл запускается из CLI без изменения существующего контракта `scan/doctor/fix` |
| 2.7.2 | Tool Contract Layer | Ввести типизированные адаптеры инструментов (scan, patch, verify, rollback, tests, git-read) с единым `ToolResult` | Runtime использует только tool-contract API; ошибки нормализованы; поведение воспроизводимо в dry-run |
| 2.7.3 | Policy Engine | Реализовать policy-конфиг для auto-apply (ограничения по risk, file patterns, max files/ops, API-breaking guard) | Для `hybrid/auto` есть policy-решение `allow/deny/review`; покрытие тестами deny-правил и граничных кейсов |
| 2.7.4 | Explainability Record | Для каждой операции сохранять `why`, `risk`, `expected_outcome`, `rollback_plan` и outcome verify | В `eurika_fix_report.json`/events видны объяснения по каждому op; `eurika explain` показывает rationale из runtime |
| 2.7.5 | Session Memory | Добавить память сессии/кампании: история решений, повторные провалы, подавление шумовых операций | Повторный запуск учитывает прошлые fail/skip; уменьшается churn по TODO/no-op операциям |
| 2.7.6 | Human-in-the-loop CLI | Добавить интерактивный approval в `fix` для `hybrid` (approve/reject/skip/all), с `--non-interactive` для CI | CLI-UX покрыт интеграционными тестами; в CI-режиме поведение детерминировано без промптов |
| 2.7.7 | Safety & Rollback Gates | Ужесточить guardrails: обязательный verify-gate, авто-rollback при regressions, лимиты на серию операций | Нет частично-применённых невалидных сессий; rollback покрыт тестами на fail verify |
| 2.7.8 | Telemetry & KPIs | Добавить метрики операционности: apply-rate, rollback-rate, no-op-rate, median verify time | Метрики выводятся в doctor/fix report и используются для корректировки policy |
| 2.7.9 | Dogfooding Campaign | Провести серию dogfooding-прогонов только новым runtime (assist/hybrid/auto) на Eurika | Минимум 3 стабильных цикла подряд без шумовых TODO-патчей; тесты зелёные |
| 2.7.10 | Docs & Migration | Обновить CLI.md, ROADMAP, DOGFOODING, CYCLE_REPORT с новым режимом runtime и правилами эксплуатации | Документация синхронизирована с кодом; сценарии запуска/отката описаны и проверены |

**Порядок внедрения (рекомендуемый):** 2.7.1 -> 2.7.2 -> 2.7.3 -> 2.7.4 -> 2.7.5 -> 2.7.6 -> 2.7.7 -> 2.7.8 -> 2.7.9 -> 2.7.10.

**Фактический прогресс (фаза 2.7):**
- [x] 2.7.1 Agent Runtime Core — цикл `observe→reason→propose→apply→verify→learn` в `eurika/agent/runtime.py`; режимы assist/hybrid/auto; unit-тесты на stop-on-error, exception handling, skip missing stages; CLI оркестратор использует runtime для hybrid/auto
- [x] 2.7.2 Tool Contract Layer — типизированные адаптеры scan, patch, verify, rollback, tests, git_read в `eurika/agent/tool_contract.py`; единый ToolResult; ошибки нормализованы; dry-run воспроизводим; OrchestratorToolset получает contract; tests/test_tool_contract.py
- [x] 2.7.3 Policy Engine — policy-конфиг: risk, max_ops, max_files, deny_patterns, api_breaking_guard; allow/deny/review для hybrid/auto; hybrid сохраняет review для HITL; тесты deny-правил и граничных кейсов в test_agent_policy.py
- [x] 2.7.4 Explainability Record — why, risk, expected_outcome, rollback_plan, verify_outcome в operation_explanations; eurika_fix_report.json и dry-run; eurika explain показывает Runtime rationale из последнего fix; tests/test_explainability.py
- [x] 2.7.5 Session Memory — campaign memory в SessionMemory: rejected_keys (из любой сессии), verify_fail_keys (2+ fail → skip); apply_campaign_memory в prepare; record_verify_failure при verify fail; tests
- [x] 2.7.6 Human-in-the-loop CLI — approve/reject/A/R/s в hybrid; --non-interactive для CI (детерминировано, без stdin); tests/test_hitl_cli.py (non_interactive, isatty, mocked input)
- [x] 2.7.7 Safety & Rollback Gates — обязательный verify, auto_rollback при fail; backup=True; enrich_report_with_rescan → rollback при metrics_worsened; tests/test_safety_rollback_gates.py; policy max_ops/max_files
- [x] 2.7.8 Telemetry & KPIs — apply-rate, rollback-rate, no-op-rate, median_verify_time_ms; telemetry в fix report; report-snapshot и doctor (last_fix_telemetry); suggest_policy_from_telemetry для корректировки policy
- [x] 2.7.9 Dogfooding Campaign — 3 стабильных цикла подряд; verify ✓, тесты зелёные; split_module architecture_planner → build_plan, build_action_plan
- [x] 2.7.10 Docs & Migration — CLI.md, ROADMAP, DOGFOODING, CYCLE_REPORT обновлены; runtime-режимы и telemetry описаны

**Метрики выхода из фазы 2.7 (DoD):**
- apply-rate в `eurika fix` устойчиво растёт, а no-op-rate снижается относительно базовой линии.
- В `hybrid` режиме пользователь контролирует medium/high-risk операции без потери воспроизводимости.
- Каждый применённый патч имеет machine-readable rationale и rollback trail.
- По итогам dogfooding новые режимы не ухудшают verify-success и не повышают шум в git diff.

### Фаза 2.8 — Декомпозиция слоёв и анти-монолитный контур (по review v2.7.0)

**Цель:** остановить рост монолитности в точках концентрации (`cli/orchestrator.py`, `eurika_cli.py`, `architecture_planner.py`, `patch_apply.py`), формализовать слои и зафиксировать импорт-контракт между подсистемами.

| # | Шаг | Задача | Критерий готовности |
|---|-----|--------|----------------------|
| 2.8.1 | Layer Map | Формально зафиксировать слои в `ARCHITECTURE.md`: Infrastructure (IO/CLI/FS) → Core graph model → Analysis → Planning → Execution → Reporting | В документе есть карта слоёв, allowed deps и anti-pattern примеры; ссылки из ROADMAP/CLI |
| 2.8.2 | Dependency Guard | Ввести проверку «запрещённых импортов» (no upward deps) как тест/линт-гейт | Есть автоматическая проверка в `tests/` или отдельный check-командлет; CI падает при нарушении |
| 2.8.3 | Orchestrator Split | Разрезать `cli/orchestrator.py` на `cli/orchestration/` модули стадий + `cli/wiring/` + тонкий фасад `run_cycle` | `cli/orchestrator.py` остаётся тонким фасадом; ключевые stage-функции вынесены; поведение `doctor/fix/cycle` не изменено |
| 2.8.4 | CLI Wiring Split | Декомпозировать `eurika_cli.py`: parser builders/command registration/wiring по модулям | Главный CLI-файл существенно уменьшается; тесты CLI-парсинга зелёные |
| 2.8.5 | Planner Boundary | Разделить `architecture_planner.py` на анализ рисков, правила планирования и сборку операций (без смешения отчётности/форматирования) | Отдельные модули с явными интерфейсами; `get_patch_plan` остаётся совместимым |
| 2.8.6 | Patch Subsystem | Эволюционировать `patch_apply.py` в подсистему (`patch/planner.py`, `patch/executor.py`, `patch/validator.py`, `patch/rollback.py`) с обратной совместимостью фасада | Публичный API не ломается (`patch_apply`/`patch_engine`), но реализация разделена по ролям |
| 2.8.7 | Violation Audit | Найти и закрыть реальные нарушения слоёв (анализ ↔ execution ↔ reporting) | Есть список нарушений «до/после» и закрытые пункты в `CYCLE_REPORT.md` |
| 2.8.8 | Dogfooding on New Boundaries | Провести 3 цикла `doctor + fix --dry-run + fix` после декомпозиции | Нет регресса в verify-success; telemetry и safety-gates остаются стабильными |

**Порядок внедрения (рекомендуемый):** 2.8.1 -> 2.8.2 -> 2.8.3 -> 2.8.4 -> 2.8.5 -> 2.8.6 -> 2.8.7 -> 2.8.8.

**Фактический прогресс (актуально):**
- [x] 2.8.1 Layer Map — выполнено (Architecture.md §0 Layer Map; allowed deps, anti-patterns, ссылки в CLI.md)
- [x] 2.8.2 Dependency Guard — выполнено (tests/test_dependency_guard.py; CI падает при нарушении)
- [x] 2.8.3 Orchestrator Split — выполнено
- [x] 2.8.4 CLI Wiring Split — выполнено
- [x] 2.8.5 Planner Boundary — выполнено
- [x] 2.8.6 Patch Subsystem — выполнено (рефакторинг через фасады и выделенные модули `patch_apply_*`, `patch_engine_*`, API сохранен)
- [x] 2.8.7 Violation Audit — выполнено (закрыты прямые cross-layer вызовы patch_apply из CLI и wildcard-shims в `eurika/reasoning/*`)
- [x] 2.8.8 Dogfooding on New Boundaries — выполнено (контур `doctor -> fix --dry-run -> fix` пройден; verify стабилен, rollback/no-op без всплеска)

**Метрики выхода из фазы 2.8 (DoD):**
- Уменьшение централизации по файлам: `cli/orchestrator.py`, `eurika_cli.py`, `architecture_planner.py`, `patch_apply.py` больше не являются top outliers по LOC/смешению ролей.
- Импорт-контракт слоёв формализован и автоматически проверяется.
- Runtime (assist/hybrid/auto) сохраняет поведение и тестовую стабильность после декомпозиции.
- В dogfooding нет всплеска no-op/rollback-rate из-за структурных изменений.

---

### Фаза 3.1-arch — Архитектурная дисциплина (по review v3.0.1)

**Цель:** переход от «сложной утилиты» к «архитектурной платформе»; зафиксировать слои, ограничить зависимости, почистить центры тяжести. Диагноз review: зрелость выше средней, но риск монолитизации; нужен дисциплинированный этап.

| # | Шаг | Задача | Критерий готовности |
|---|-----|--------|----------------------|
| 3.1-arch.1 | Формальные слои | Зафиксировать слои в документе: L0 Infrastructure → L1 Core model → L2 Analysis → L3 Planning → L4 Execution → L5 Reporting → L6 CLI; запретить зависимости вверх | ARCHITECTURE.md или LAYERS.md с картой слоёв; dependency guard проверяет no upward deps |
| 3.1-arch.2 | API-границы подсистем | Каждая подсистема экспортирует 1–2 публичные точки входа; остальное private | Документ или `__all__` в ключевых модулях; рекомендации в CYCLE_REPORT |
| 3.1-arch.3 | Лимит размера файлов | Правило: >400 строк — кандидат на разбиение; >600 строк — обязательно делить | Линт/скрипт или checklist; список файлов-нарушителей в self-check или report |
| 3.1-arch.4 | Domain vs presentation | Модули, которые и вычисляют, и форматируют Markdown — разделить на domain + presentation | Аудит смешанных модулей; план разбиения и выполненные выносы |
| 3.1-arch.5 | Облегчить CLI | CLI только принимает команды и передаёт оркестратору; убрать бизнес-логику и сложные пайплайны из CLI-слоя | CLI handlers — тонкие обёртки; тесты на изоляцию |
| 3.1-arch.6 | Развести Planning и Execution | Planner строит план; Executor исполняет; убрать взаимное знание деталей | Аудит planner_* и patch_apply_*; явные контракты между ними |
| 3.1-arch.7 | Dogfooding на новой дисциплине | 3 цикла scan → doctor → fix после внедрения ограничений | Нет регресса; verify стабилен; новые правила не ломают цикл |

**Порядок внедрения (рекомендуемый):** 3.1-arch.1 → 3.1-arch.2 → 3.1-arch.5 → 3.1-arch.6 → 3.1-arch.4 → 3.1-arch.3 → 3.1-arch.7.

**Фактический прогресс (фаза 3.1-arch):**
- [x] 3.1-arch.1 Формальные слои — Architecture.md §0: нотация L0–L6 (Infra→Core→Analysis→Planning→Execution→Reporting→CLI); allowed deps; mapping модулей; no upward deps; dependency guard проверяет
- [x] 3.1-arch.2 API-границы подсистем — Architecture.md §0.6; __all__ в patch_engine, eurika.core, eurika.analysis, eurika.smells, eurika.evolution, eurika.reporting; рекомендации в CYCLE_REPORT §23
- [x] 3.1-arch.3 Лимит размера файлов — eurika.checks.file_size; >400 candidate, >600 must split; self-check выводит блок; python -m eurika.checks.file_size
- [x] 3.1-arch.4 Domain vs presentation — report/architecture_report.py (rendering); core/pipeline делегирует; central_modules_for_topology в system_topology
- [x] 3.1-arch.5 Облегчить CLI — report/report_snapshot.format_report_snapshot; eurika.api: explain_module, get_suggest_plan_text, clean_imports_scan_apply; handlers тонкие обёртки; test_handle_report_snapshot_delegates_to_format
- [x] 3.1-arch.6 Развести Planning и Execution — eurika.reasoning.planner без patch_apply/patch_engine; Architecture.md §0.5 Planner–Executor Contract; dependency guard для eurika/reasoning/
- [x] 3.1-arch.7 Dogfooding — eurika fix . (6 modified), 3× eurika fix . --dry-run (0 ops fixpoint); verify ✓ 287 passed; CYCLE_REPORT §28

**Связь с review v3.0.1:** пункты §6 «Что я рекомендую сделать в v3.1».

---

### Фаза 2.9 — Углубление цикла (LLM + Knowledge + Learning) — **приоритет над 3.0**

**Цель:** делать цикл «умнее» в рамках одного проекта: анализ → поиск решений (Ollama + документация) → рефакторинг → обучение. Глубина перед широтой (3.0 multi-repo).

**Приоритет:** фаза 2.9 важнее 3.0 — сначала повысить качество и интеллект single-project цикла, затем масштабировать.

| # | Шаг | Задача | Критерий готовности |
|---|-----|--------|----------------------|
| 2.9.1 | Architect → рекомендации «как» | Расширить architect: не только «что не так», но и «что делать и как» — на основе Knowledge Layer (PEP, docs.python.org, release notes) | Architect при god_module/bottleneck выдаёт конкретные подсказки с reference на доку; блок Reference в doctor расширен |
| 2.9.2 | LLM в планировании | Для сложных smell (god_module, hub, bottleneck) — запрос к Ollama: «предложи точки разбиения»; результат в patch_plan как hints или уточнённые target/params | При наличии Ollama и high-risk smell: planner получает LLM-подсказки; fallback на эвристики без LLM |
| 2.9.3 | Knowledge Layer — PEP/RFC | Добавить провайдеры PEP, RFC, What's New (docs.python.org); темы по smell_type (god_module → module_structure, long_function → extract_method) | eurika.knowledge: PEPProvider, WhatNewProvider; маппинг smell_type → knowledge_topic; architect и planner используют |
| 2.9.4 | Обучение в цикле | Корректировка policy из telemetry; suggest_policy_from_telemetry выводится в doctor; опция применять suggested policy | doctor показывает блок «Suggested policy» при низком apply_rate; CLI или env для принятия suggestion |
| 2.9.5 | Dogfooding 2.9 | 3 цикла с LLM + Knowledge на Eurika; сравнить качество плана (релевантность подсказок) и apply-rate | Отчёт в CYCLE_REPORT; architect даёт «как»; learning улучшает выбор ops |

**Порядок внедрения (рекомендуемый):** 2.9.1 → 2.9.3 → 2.9.2 → 2.9.4 → 2.9.5. Architect и Knowledge — основа; LLM в planner — поверх; learning — замкнутый цикл.

**Фактический прогресс (фаза 2.9):**
- [x] 2.9.1 Architect рекомендации — блок «Recommendation (how to fix)» с конкретными шагами по smell (god_module, bottleneck, hub, cyclic_dependency); блок «Reference (from documentation)» при наличии Knowledge; LLM и template
- [x] 2.9.2 LLM в планировании — planner_llm.ask_ollama_split_hints для god_module/hub/bottleneck; hints в patch_plan; fallback на эвристики (EURIKA_USE_LLM_HINTS=0)
- [x] 2.9.3 Knowledge PEP/RFC — PEPProvider в eurika.knowledge; SMELL_TO_KNOWLEDGE_TOPICS в doctor; architect/planner получают темы по smell (god_module→architecture_refactor, long_function→pep_8)
- [x] 2.9.4 Обучение в цикле — doctor блок «Suggested policy» при низком apply_rate; load_suggested_policy_for_apply; --apply-suggested-policy в fix/cycle
- [x] 2.9.5 Dogfooding 2.9 — 3 стабильных цикла с LLM + Knowledge на Eurika; verify ✓; apply-rate и learning стабильны

**Метрики выхода из фазы 2.9 (DoD):**
- Architect при god_module даёт «разбить по ответственностям X, Y, Z» с reference на доку.
- При Ollama: planner для high-risk smell получает LLM-hints (опционально).
- doctor выводит suggested policy при низком apply_rate.
- Dogfooding: apply-rate не падает; релевантность рекомендаций растёт.

**Связь с 3.0:** 2.9 углубляет single-project; 3.0 расширяет на multi-repo. Рекомендуется завершить 2.9.1–2.9.3 до активной работы над 3.0.2 (cross-project memory).

---

#### Детализация 2.8.3 — Orchestrator Split (план коммитов)

**Идея:** делать «тонкий фасад + вынос по стадиям» без больших взрывных PR; каждый шаг сохраняет поведение и проходит тесты.

| Коммит | Что переносим | Целевые файлы | Критерий |
|--------|----------------|---------------|----------|
| 2.8.3.a | Вынести общие модели/типы цикла (`FixCycleContext`, `FixCycleResult`, protocol-обёртки deps) | `cli/orchestration/models.py`, `cli/orchestration/deps.py` | `cli/orchestrator.py` компилируется, тесты без регресса |
| 2.8.3.b | Вынести pre-stage (`scan/diagnose/plan/policy/session-filter`) | `cli/orchestration/prepare.py` | `_prepare_fix_cycle_operations` уходит из god-file, dry-run поведение идентично |
| 2.8.3.c | Вынести apply-stage (`apply+verify`, rescan enrich, write report, memory append) | `cli/orchestration/apply_stage.py` | verify/rollback/telemetry контракты не меняются |
| 2.8.3.d | Вынести doctor/full-flow wiring | `cli/orchestration/doctor.py`, `cli/orchestration/full_cycle.py` | `run_cycle(mode=doctor/full)` возвращает тот же payload |
| 2.8.3.e | Оставить в `cli/orchestrator.py` только фасад (`run_cycle`, thin wrappers, compatibility imports) | `cli/orchestrator.py` | Размер файла заметно снижен; публичные функции сохранены |
| 2.8.3.f | Добавить regression-тесты на эквивалентность stage-вывода и edge-cases | `tests/test_cycle.py`, `tests/test_cli_runtime_mode.py` | Старые + новые тесты зелёные |

**Жёсткие ограничения при переносе:**
- Не менять JSON-контракт `eurika_fix_report.json` и поля `telemetry/safety_gates/policy_decisions`.
- Не ломать CLI-флаги (`--runtime-mode`, `--non-interactive`, `--session-id`, `--dry-run`, `--quiet`).
- Сначала перенос кода 1:1, потом только точечные улучшения.

**Критерий «2.8.3 завершена»:**
- `cli/orchestrator.py` — фасадный слой (без тяжёлой бизнес-логики стадий).
- Поведение `doctor/fix/cycle` эквивалентно до/после (по regression-тестам и dry-run снапшотам).
- Документация (`CYCLE_REPORT.md`) содержит «до/после» по LOC и список вынесенных модулей.

### Фаза 2.1 — Саморазвитие и стабилизация (приоритет 1)

**Цель:** закрепить цикл «анализ и исправление собственного кода», добавлять новые функции по запросу, держать тесты и документацию в актуальном состоянии.

| # | Задача | Критерий готовности |
|---|--------|----------------------|
| 2.1.1 | Регулярно применять scan/doctor/fix к своей кодовой базе (eurika) | Ритуал по DOGFOODING.md; артефакты и отчёты обновляются; выявленные проблемы фиксируются или попадают в план |
| 2.1.2 | Добавление новых функций по запросу; **багфиксы** по результатам прогонов (напр. Knowledge: явная пустая карта `topic_urls={}` → дефолт только при `topic_urls is None`) | Тесты зелёные; REPORT и CHANGELOG обновлены при изменении возможностей или числа тестов |
| 2.1.3 | Актуализировать документацию при изменении поведения | README, CLI.md, KNOWLEDGE_LAYER.md, ROADMAP соответствуют коду и текущей задаче |
| 2.1.4 | Опционально: полный `eurika fix .` без --dry-run на Eurika (с venv) | ✓ Выполнено: verify 129 passed после багфикса topic_urls |
| 2.1.5 | Опционально: прогоны scan/doctor/fix на других проектах (farm_helper, optweb, binance/bbot и т.д.) | ✓ farm_helper (5), optweb (38); ✓ binance/bbot/34 (11, scan+doctor+fix --dry-run); ✓ binance/binance-trade-bot (26, scan) — отработали штатно |

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

### Статус рекомендаций review.md

**review v3.0.1 (§6 — v3.1):**
- Формализовать слои (L0–L6) → Фаза 3.1-arch.1
- API-границы подсистем → 3.1-arch.2
- Лимит размера файлов (>400/600 LOC) → 3.1-arch.3
- Domain vs presentation → 3.1-arch.4

**review §7 (ранее):**

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

---

### Фаза 3.0 — Architectural AI Engineer (дорожная карта)

**Цель v3.0:** Eurika работает с несколькими репозиториями, общей памятью между проектами, расширенным Knowledge Layer и режимом совместной работы.

**Рекомендуемый порядок:** 3.0.1 → 3.0.2 → 3.0.3 → 3.0.4. Multi-repo — предпосылка для cross-project memory; online knowledge расширяет существующий Knowledge Layer; team-mode опирается на policy и session-memory.

| # | Шаг | Задача | Критерий готовности |
|---|-----|--------|----------------------|
| 3.0.1 | Multi-Repo Scan | Поддержка `eurika scan <path1> <path2> ...` и `eurika cycle --paths path1,path2` для нескольких корней проектов | CLI принимает несколько путей; scan/doctor/fix выполняются последовательно или параллельно по каждому; отчёт агрегирует summary/risks по всем проектам |
| 3.0.2 | Cross-Project Memory | Общая директория памяти (напр. `~/.eurika/` или `EURIKA_GLOBAL_MEMORY`) для learning/feedback между проектами | Learning/feedback из проекта A учитываются при fix проекта B (при совпадении smell\|action); формат агрегации и приоритет local vs global описан в spec |
| 3.0.3 | Online Knowledge (расширение) | Расширить Knowledge Layer: актуальный fetch по запросу (не только кэш), провайдеры PEP/RFC, интеграция с architect при cross-repo | Новые провайдеры или опция `--online`; architect получает релевантные фрагменты при анализе нескольких проектов; TTL и rate-limit для сетевых запросов |
| 3.0.4 | Team Mode | Роли, shared session, approvals между пользователями; интеграция с CI (отдельный approve-step) | `eurika fix --team-mode` или отдельная команда; policy учитывает "approved by" для high-risk ops; документация сценариев (один предлагает, другой применяет) |

**Фактический прогресс (фаза 3.0):**
- [x] 3.0.1 Multi-Repo Scan — `eurika scan/doctor/fix/cycle path1 [path2 ...]`; последовательное выполнение по каждому пути; заголовки "--- Project N/M ---"; агрегированный JSON-отчёт — в плане
- [x] 3.0.2 Cross-Project Memory — общая память ~/.eurika/ или EURIKA_GLOBAL_MEMORY; append learn при fix; get_merged_learning_stats(local+global) при build patch plan; merge: sum total/success/fail per smell|action; EURIKA_DISABLE_GLOBAL_MEMORY для отключения
- [ ] 3.0.3 Online Knowledge — базовый слой есть (KNOWLEDGE_LAYER.md); расширение — в плане
- [ ] 3.0.4 Team Mode — не начато

**Метрики выхода из фазы 3.0 (DoD):**
- Один вызов `eurika cycle` может обработать несколько репозиториев с агрегированным отчётом.
- Learning из одного проекта влияет на план fix в другом (при наличии cross-project memory).
- Architect при multi-repo получает контекст из online knowledge.
- Team-mode сценарий (propose → approve → apply) задокументирован и покрыт тестами.

**Зависимости:** 3.0.1 не зависит от остальных; 3.0.2 требует 3.0.1 (multi-repo как источник проектов для memory); 3.0.3 можно вести параллельно; 3.0.4 опирается на policy/session-memory (2.7.5, 2.7.6).

---

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
- [x] **Killer-feature (цель):** remove_cyclic_import, remove unused imports, split oversized module; eurika fix с verify и откатом при провале — этапы 1–2, 3.
- [x] **CLI режимы есть:** scan, doctor, fix, explain. Упростить до 4 режимов без dev-команд — этап 5.

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

| Операция | Результат |
|----------|-----------|
| remove_cyclic_import | ✓ Реальный фикс (AST) |
| remove_unused_import | ✓ Реальный фикс (в fix cycle по умолчанию, фаза 2.4) |
| introduce_facade | ✓ Реальный фикс (создаёт {stem}_api.py) |
| extract_class | ✓ Реальный фикс |
| split_module (успех) | ✓ Реальный фикс |
| split_module (fallback) | ✓ Часто реальный (by_function, infer imports, relaxed extraction) |
| refactor_code_smell | TODO-маркер (long_function, deep_nesting); в WEAK_SMELL_ACTION_PAIRS — hybrid: review, auto: deny |
| refactor_module | ✓ Пробует split_module chain, иначе TODO |

**Приоритет:** стабилизация цикла, прогоны на других проектах.

---

## Версия 2.1 — инженерный инструмент (целевое состояние)

Цель: 2.0 → «инженерный инструмент» (конкретная польза, автофиксы, стабильный CLI). Путь инженерный, не академический.

| Элемент | Статус | Задача |
|--------|--------|--------|
| **Patch Engine** | ✓ | `patch_engine.py`: **apply_patch**, **verify_patch**, **rollback_patch**; apply_and_verify(..., **auto_rollback=True**) при провале verify откатывает изменения |
| **Verify stage** | ✓ | После patch: перескан, сравнение health score; при ухудшении — откат (verify_metrics + rollback reason) |
| **Замкнутый цикл** | ✓ | `eurika fix` = scan → diagnose → plan → patch → verify → learn; agent runtime (assist/hybrid/auto) |
| **Единая модель Event** | ✓ | Фаза 3.2: .eurika/, EventStore, LearningView, FeedbackView, architect.recent_events |
| **Граф как движок** | ✓ | Фаза 3.1: priority_from_graph, SMELL_TYPE_TO_REFACTOR_KIND, targets_from_graph |
| **Архитектурные операции** | ✓ | Remove unused imports, remove_cyclic_import, split_module, introduce_facade, extract_class; refactor_code_smell в WEAK_SMELL_ACTION_PAIRS (hybrid/auto) |

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
