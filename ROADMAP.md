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
| Продуктовая готовность  | 5/10   |
| Потенциал               | 9.5/10 |


**Диагноз (review):** «Архитектурный аналитик с амбициями автономного агента» — автономным агентом пока не является. Усиливать LLM — преждевременно; усиливать execution — критично. Стратегическое заключение: при вводе Patch Engine, Verify+Rollback, детерминированных refactor-операций и единого Event Engine Eurika станет «автономным архитектурным инструментом»; иначе останется «очень умным архитектурным советником». Долгосрочная цель (вывод в review): полноценный AI-агент, способный к самоусовершенствованию; начало закладываем сейчас.

**План прорыва (путь 2) выполнен:** Patch Engine, Verify, Rollback, Event Engine, CLI 4 режима — реализованы.

---

## План прорыва выполнен

Этапы 1–5 и dogfooding закрыты. Продуктовая 1.0 в смысле плана достигнута.

---

## Следующий горизонт (кратко)

- **Состояние v3.0.7:** фазы 2.1–2.9, 3.0, 3.1, 3.1-arch, 3.2, 3.5 — выполнены. Web UI: Dashboard, Graph, Approve, Terminal, Ask Architect, Run cycle.
- **Фокус:** работа над собой — регулярный scan/doctor/fix, добавление функций по запросу, багфиксы, актуализация документации.
- **Стабилизация:** тесты зелёные, доки соответствуют коду.
- **Операционность 5/10:** refactor_code_smell 0% success (в WEAK_SMELL_ACTION_PAIRS); приоритет — 3.0.5 Learning from GitHub или продуктовая готовность.
- **Дальше:** см. «Следующий фокус (после 3.5)» и новый активный бэклог ниже.

### Следующий фокус (после 3.5)

Три направления на выбор:


| Направление                            | Описание                                                                                               | Быстрота  |
| -------------------------------------- | ------------------------------------------------------------------------------------------------------ | --------- |
| **A. 3.0.5 Learning from GitHub**      | Curated repos (Django, FastAPI) → pattern library → повышение apply-rate                               | Долго     |
| **B. Продуктовая готовность (5→6/10)** | UI.md ✓; README (getting started, примеры); критерии готовности в ROADMAP; venv-нейтральные инструкции | Быстро    |
| **C. Ритуал 2.1**                      | Регулярно: scan, doctor, report-snapshot; обновлять CYCLE_REPORT; без новых фич                        | Постоянно |


### Критерии продуктовой готовности 6/10 (направление B)


| #   | Критерий                                                                                          | Статус                                                 |
| --- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| B.1 | README: быстрый старт без привязки к конкретному venv-пути                                        | ✓ venv: `pip install -e ".[test]"`; инструкции generic |
| B.2 | README: все 4 продуктовые команды с примерами (scan, doctor, fix --dry-run, serve)                | ✓                                                      |
| B.3 | UI.md: полный список вкладок + описание Chat                                                      | ✓                                                      |
| B.4 | CLI.md: раздел CI/CD и рекомендуемый цикл                                                         | ✓                                                      |
| B.5 | Новый пользователь может за 5 минут: install → scan → doctor → fix --dry-run без чтения 10 файлов | Достигается при B.1–B.4                                |
| B.6 | Тесты зелёные, CYCLE_REPORT актуален                                                              | Ритуал 2.1                                             |


**Цель:** пользователь клонирует репо, читает README и через 5 минут понимает, что делает Eurika и как её запустить.

---

### Новый вектор из обновлённого review (логическая интеграция)

Ниже — не «перенос пунктов 1:1», а встраивание рекомендаций в текущую логику ROADMAP:
сначала структурная стабилизация ядра, затем защитные контуры, потом модульная платформа и только после этого — расширение интеллектуальности.

#### Контур R1 — Structural Hardening (ближайший приоритет)

**Цель:** закрепить архитектурный контракт и убрать источники непредсказуемости перед новыми фичами.


| Поток                  | Что делаем                                                                                                               | Критерий готовности                                                                      |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| Layer discipline       | Перепроверка и донастройка карты слоёв (allowed deps + no-upward imports) по факту текущих модулей                       | Dependency guard стабильно ловит нарушения; в CYCLE_REPORT есть «до/после» по violations |
| Domain vs Presentation | Убираем форматирование отчётов/markdown из domain-кода; domain возвращает структуры, rendering только в reporting/UI/CLI | Для выбранных целевых модулей domain не возвращает форматированный текст                 |
| Size budget            | Жёстко применяем бюджет размера файлов (>400 warning, >600 split required) в self-check/ритуале                          | Нет новых файлов >600; список >400 прозрачно контролируется                              |
| Public subsystem API   | Для ключевых подсистем оставляем 1-2 публичные точки входа, остальное private                                            | Для core/analysis/planning/execution/reporting зафиксированы API-границы                 |


#### Контур R2 — Runtime Robustness (после R1)

**Цель:** сделать runtime-поведение наблюдаемым и устойчивым в ошибочных сценариях.


| Поток                        | Что делаем                                                                                  | Критерий готовности                                                  |
| ---------------------------- | ------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| Явная state-модель цикла     | Ввести формальное состояние выполнения runtime (idle/thinking/error/done) и тесты переходов | Есть unit-тесты переходов и корректная фиксация error-state          |
| Fallback-устойчивость        | Аудит fallback-путей (LLM/knowledge/runtime) с обязательным детерминированным degraded mode | При недоступности внешних зависимостей цикл завершается предсказуемо |
| Централизованное логирование | Привести runtime/CLI к единому logging-контуру (уровни, verbose/debug режимы)               | Отсутствуют «слепые» print-пути в критическом цикле                  |


#### Контур R3 — Quality Gate (параллельно R1/R2)

**Цель:** поднять доверие к изменениям через жёсткий quality gate.


| Поток                    | Что делаем                                                                              | Критерий готовности                                                    |
| ------------------------ | --------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Coverage критичного ядра | Приоритетно покрывать тестами runtime/policy/memory/planning contracts                  | Рост покрытия по критическим пакетам, без деградации regression-набора |
| Edge-case matrix         | Формализовать edge-cases: пустой/огромный вход, model/network error, memory write error | Отдельный блок тестов на edge-cases в CI                               |
| Typing contract          | Усилить type-hints на границах подсистем; mypy как optional-gate                        | Ошибки типов не накапливаются в core-контрактах                        |


#### Контур R4 — Modular Platform (после R1–R3)

**Цель:** подготовить Eurika к масштабированию без архитектурного долга.


| Поток                   | Что делаем                                                                                     | Критерий готовности                                |
| ----------------------- | ---------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| Subsystem decomposition | Укрепить пакетную изоляцию (core/analysis/planning/execution/reporting) и контракты между ними | Нет прямых «соседских» обходов мимо публичных API  |
| Dependency firewall     | Автотест графа зависимостей как контракт архитектуры                                           | CI падает при нарушении firewall-правил            |
| Release hygiene         | Перед релизами: dead code cleanup, TODO hygiene, lint/type/test, clean-start check             | Релизный чеклист выполняется как обязательный gate |


#### Контур R5 — Strategic Horizon (дальний)

После завершения структурных контуров:

- **Self-guard/Meta-architecture:** авто-детекция layer violations, complexity budget alarms, centralization trend.
- **Intelligence upgrade:** risk prediction + более точный recommendation engine.
- **Extensibility:** plugin interface и подключение внешних анализаторов через единый контракт.

---

## Следующие шаги (горизонт 2)

План прорыва выполнен. Ниже — фазы без жёстких сроков, в приоритете саморазвитие и работа над собственной кодовой базой.

**Фазы по возрастанию:** 2.1 → 2.2 → 2.3 → 2.4 → 2.6 → 2.7 → 2.8 → 2.9 → 3.0 (3.0.5) → 3.1 → 3.1-arch → 3.2 → 3.5 (3.5.1–3.5.10)

---

### Активный бэклог (после закрытия предыдущего)

**Закрыто:**

- Повысить долю реальных apply в `eurika fix` — _drop_noop_append_ops в prepare
- WEAK_SMELL_ACTION_PAIRS, _deprioritize_weak_pairs
- refactor_code_smell в WEAK_SMELL_ACTION_PAIRS (hybrid: review, auto: deny)
- god_class|extract_class в WEAK_SMELL_ACTION_PAIRS + EXTRACT_CLASS_SKIP_PATTERNS (*tool_contract*.py) — защита от повторных ошибок (CYCLE_REPORT #34)
- report-snapshot, DOGFOODING
- Малые рефакторинги + тесты для топ-long/deep функций

**Новый бэклог (следующие шаги):**

- Добавить UI.md — инструкция по запуску `eurika serve`, вкладки (Dashboard, Terminal, Approve, Ask Architect, Chat), Run cycle (ROADMAP 3.5 DoD)
- Прогон `eurika report-snapshot .` и актуализация CYCLE_REPORT (ритуал 2.1)
- Опционально: обновить README — getting started, примеры `eurika scan .`, `eurika doctor .`, `eurika fix . --dry-run`
- B. Продуктовая готовность — критерии в ROADMAP; README/CLI.md без machine-specific venv; UI.md + Chat
- long_function|extract_nested_function: extend suggest/extract — extract with params (1–3 parent vars) — повышение success rate

**Дальнейшая доработка (long_function / deep_nesting):**

- refactor_code_smell — по умолчанию не эмитить при отсутствии реального фикса; `EURIKA_EMIT_CODE_SMELL_TODO=1` для старого поведения (TODO-маркеры)
- deep_nesting — гибрид: suggest_extract_block + extract_block_to_helper (эвристика для простых блоков); EURIKA_DEEP_NESTING_MODE=heuristic|hybrid|llm|skip; TODO/LLM при неудаче
- long_function без вложенных def — fallback на suggest_extract_block (if/for/while блок 5+ строк) когда extract_nested_function не срабатывает

---

### Фаза 2.1 — Саморазвитие и стабилизация (приоритет 1)

**Цель:** закрепить цикл «анализ и исправление собственного кода», добавлять новые функции по запросу, держать тесты и документацию в актуальном состоянии.


| #     | Задача                                                                                                                                                                   | Критерий готовности                                                                                                                           |
| ----- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- |
| 2.1.1 | Регулярно применять scan/doctor/fix к своей кодовой базе (eurika)                                                                                                        | Ритуал по DOGFOODING.md; артефакты и отчёты обновляются; выявленные проблемы фиксируются или попадают в план                                  |
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


| #      | Шаг                     | Задача                                                                                                                                                   | Критерий готовности                                                                                                    |
| ------ | ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| 2.7.1  | Agent Runtime Core      | Добавить единый runtime-цикл (`observe -> reason -> propose -> apply -> verify -> learn`) в `eurika/agent/runtime.py`; режимы `assist`, `hybrid`, `auto` | Есть unit-тесты на переходы состояний; цикл запускается из CLI без изменения существующего контракта `scan/doctor/fix` |
| 2.7.2  | Tool Contract Layer     | Ввести типизированные адаптеры инструментов (scan, patch, verify, rollback, tests, git-read) с единым `ToolResult`                                       | Runtime использует только tool-contract API; ошибки нормализованы; поведение воспроизводимо в dry-run                  |
| 2.7.3  | Policy Engine           | Реализовать policy-конфиг для auto-apply (ограничения по risk, file patterns, max files/ops, API-breaking guard)                                         | Для `hybrid/auto` есть policy-решение `allow/deny/review`; покрытие тестами deny-правил и граничных кейсов             |
| 2.7.4  | Explainability Record   | Для каждой операции сохранять `why`, `risk`, `expected_outcome`, `rollback_plan` и outcome verify                                                        | В `eurika_fix_report.json`/events видны объяснения по каждому op; `eurika explain` показывает rationale из runtime     |
| 2.7.5  | Session Memory          | Добавить память сессии/кампании: история решений, повторные провалы, подавление шумовых операций                                                         | Повторный запуск учитывает прошлые fail/skip; уменьшается churn по TODO/no-op операциям                                |
| 2.7.6  | Human-in-the-loop CLI   | Добавить интерактивный approval в `fix` для `hybrid` (approve/reject/skip/all), с `--non-interactive` для CI                                             | CLI-UX покрыт интеграционными тестами; в CI-режиме поведение детерминировано без промптов                              |
| 2.7.7  | Safety & Rollback Gates | Ужесточить guardrails: обязательный verify-gate, авто-rollback при regressions, лимиты на серию операций                                                 | Нет частично-применённых невалидных сессий; rollback покрыт тестами на fail verify                                     |
| 2.7.8  | Telemetry & KPIs        | Добавить метрики операционности: apply-rate, rollback-rate, no-op-rate, median verify time                                                               | Метрики выводятся в doctor/fix report и используются для корректировки policy                                          |
| 2.7.9  | Dogfooding Campaign     | Провести серию dogfooding-прогонов только новым runtime (assist/hybrid/auto) на Eurika                                                                   | Минимум 3 стабильных цикла подряд без шумовых TODO-патчей; тесты зелёные                                               |
| 2.7.10 | Docs & Migration        | Обновить CLI.md, ROADMAP, DOGFOODING, CYCLE_REPORT с новым режимом runtime и правилами эксплуатации                                                      | Документация синхронизирована с кодом; сценарии запуска/отката описаны и проверены                                     |


**Порядок внедрения (рекомендуемый):** 2.7.1 -> 2.7.2 -> 2.7.3 -> 2.7.4 -> 2.7.5 -> 2.7.6 -> 2.7.7 -> 2.7.8 -> 2.7.9 -> 2.7.10.

**Фактический прогресс (фаза 2.7):**

- 2.7.1 Agent Runtime Core — цикл `observe→reason→propose→apply→verify→learn` в `eurika/agent/runtime.py`; режимы assist/hybrid/auto; unit-тесты на stop-on-error, exception handling, skip missing stages; CLI оркестратор использует runtime для hybrid/auto
- 2.7.2 Tool Contract Layer — типизированные адаптеры scan, patch, verify, rollback, tests, git_read в `eurika/agent/tool_contract.py`; единый ToolResult; ошибки нормализованы; dry-run воспроизводим; OrchestratorToolset получает contract; tests/test_tool_contract.py
- 2.7.3 Policy Engine — policy-конфиг: risk, max_ops, max_files, deny_patterns, api_breaking_guard; allow/deny/review для hybrid/auto; hybrid сохраняет review для HITL; тесты deny-правил и граничных кейсов в test_agent_policy.py
- 2.7.4 Explainability Record — why, risk, expected_outcome, rollback_plan, verify_outcome в operation_explanations; eurika_fix_report.json и dry-run; eurika explain показывает Runtime rationale из последнего fix; tests/test_explainability.py
- 2.7.5 Session Memory — campaign memory в SessionMemory: rejected_keys (из любой сессии), verify_fail_keys (2+ fail → skip); apply_campaign_memory в prepare; record_verify_failure при verify fail; добавлен scoped retry-флаг `--allow-campaign-retry` (одноразовый обход campaign-skip без глобального env bypass); tests
- 2.7.6 Human-in-the-loop CLI — approve/reject/A/R/s в hybrid; --non-interactive для CI (детерминировано, без stdin); tests/test_hitl_cli.py (non_interactive, isatty, mocked input)
- 2.7.7 Safety & Rollback Gates — обязательный verify, auto_rollback при fail; backup=True; enrich_report_with_rescan → rollback при metrics_worsened; tests/test_safety_rollback_gates.py; policy max_ops/max_files
- 2.7.8 Telemetry & KPIs — apply-rate, rollback-rate, no-op-rate, median_verify_time_ms; telemetry в fix report; report-snapshot и doctor (last_fix_telemetry); no-op репортинг прозрачен для campaign/session skip (`campaign_skipped`, `session_skipped`) и согласован с telemetry (`skipped_count`, `no_op_rate`); suggest_policy_from_telemetry; aggregate_operational_metrics (rolling); /api/operational_metrics; Dashboard card
- 2.7.9 Dogfooding Campaign — 3 стабильных цикла подряд; verify ✓, тесты зелёные; split_module architecture_planner → build_plan, build_action_plan
- 2.7.10 Docs & Migration — CLI.md, ROADMAP, DOGFOODING, CYCLE_REPORT обновлены; runtime-режимы и telemetry описаны; добавлен операторский сценарий controlled re-apply через `--allow-campaign-retry`

**Метрики выхода из фазы 2.7 (DoD):**

- apply-rate в `eurika fix` устойчиво растёт, а no-op-rate снижается относительно базовой линии.
- В `hybrid` режиме пользователь контролирует medium/high-risk операции без потери воспроизводимости.
- Каждый применённый патч имеет machine-readable rationale и rollback trail.
- По итогам dogfooding новые режимы не ухудшают verify-success и не повышают шум в git diff.

### Фаза 2.8 — Декомпозиция слоёв и анти-монолитный контур (по review v2.7.0)

**Цель:** остановить рост монолитности в точках концентрации (`cli/orchestrator.py`, `eurika_cli.py`, `architecture_planner.py`, `patch_apply.py`), формализовать слои и зафиксировать импорт-контракт между подсистемами.


| #     | Шаг                          | Задача                                                                                                                                                               | Критерий готовности                                                                                                      |
| ----- | ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| 2.8.1 | Layer Map                    | Формально зафиксировать слои в `ARCHITECTURE.md`: Infrastructure (IO/CLI/FS) → Core graph model → Analysis → Planning → Execution → Reporting                        | В документе есть карта слоёв, allowed deps и anti-pattern примеры; ссылки из ROADMAP/CLI                                 |
| 2.8.2 | Dependency Guard             | Ввести проверку «запрещённых импортов» (no upward deps) как тест/линт-гейт                                                                                           | Есть автоматическая проверка в `tests/` или отдельный check-командлет; CI падает при нарушении                           |
| 2.8.3 | Orchestrator Split           | Разрезать `cli/orchestrator.py` на `cli/orchestration/` модули стадий + `cli/wiring/` + тонкий фасад `run_cycle`                                                     | `cli/orchestrator.py` остаётся тонким фасадом; ключевые stage-функции вынесены; поведение `doctor/fix/cycle` не изменено |
| 2.8.4 | CLI Wiring Split             | Декомпозировать `eurika_cli.py`: parser builders/command registration/wiring по модулям                                                                              | Главный CLI-файл существенно уменьшается; тесты CLI-парсинга зелёные                                                     |
| 2.8.5 | Planner Boundary             | Разделить `architecture_planner.py` на анализ рисков, правила планирования и сборку операций (без смешения отчётности/форматирования)                                | Отдельные модули с явными интерфейсами; `get_patch_plan` остаётся совместимым                                            |
| 2.8.6 | Patch Subsystem              | Эволюционировать `patch_apply.py` в подсистему (`patch/planner.py`, `patch/executor.py`, `patch/validator.py`, `patch/rollback.py`) с обратной совместимостью фасада | Публичный API не ломается (`patch_apply`/`patch_engine`), но реализация разделена по ролям                               |
| 2.8.7 | Violation Audit              | Найти и закрыть реальные нарушения слоёв (анализ ↔ execution ↔ reporting)                                                                                            | Есть список нарушений «до/после» и закрытые пункты в `CYCLE_REPORT.md`                                                   |
| 2.8.8 | Dogfooding on New Boundaries | Провести 3 цикла `doctor + fix --dry-run + fix` после декомпозиции                                                                                                   | Нет регресса в verify-success; telemetry и safety-gates остаются стабильными                                             |


**Порядок внедрения (рекомендуемый):** 2.8.1 -> 2.8.2 -> 2.8.3 -> 2.8.4 -> 2.8.5 -> 2.8.6 -> 2.8.7 -> 2.8.8.

**Фактический прогресс (актуально):**

- 2.8.1 Layer Map — выполнено (Architecture.md §0 Layer Map; allowed deps, anti-patterns, ссылки в CLI.md)
- 2.8.2 Dependency Guard — выполнено (tests/test_dependency_guard.py + eurika.checks.dependency_firewall; strict mode: EURIKA_STRICT_LAYER_FIREWALL=1; baseline: 0 violations / 0 waivers)
- 2.8.3 Orchestrator Split — выполнено
- 2.8.4 CLI Wiring Split — выполнено
- 2.8.5 Planner Boundary — выполнено
- 2.8.6 Patch Subsystem — выполнено (рефакторинг через фасады и выделенные модули `patch_apply_`*, `patch_engine_*`, API сохранен)
- 2.8.7 Violation Audit — выполнено (закрыты прямые cross-layer вызовы patch_apply из CLI и wildcard-shims в `eurika/reasoning/*`)
- 2.8.8 Dogfooding on New Boundaries — выполнено (контур `doctor -> fix --dry-run -> fix` пройден; verify стабилен, rollback/no-op без всплеска)

**Метрики выхода из фазы 2.8 (DoD):**

- Уменьшение централизации по файлам: `cli/orchestrator.py`, `eurika_cli.py`, `architecture_planner.py`, `patch_apply.py` больше не являются top outliers по LOC/смешению ролей.
- Импорт-контракт слоёв формализован и автоматически проверяется.
- Runtime (assist/hybrid/auto) сохраняет поведение и тестовую стабильность после декомпозиции.
- В dogfooding нет всплеска no-op/rollback-rate из-за структурных изменений.

#### Детализация 2.8.3 — Orchestrator Split (план коммитов)

**Идея:** делать «тонкий фасад + вынос по стадиям» без больших взрывных PR; каждый шаг сохраняет поведение и проходит тесты.


| Коммит  | Что переносим                                                                                     | Целевые файлы                                                    | Критерий                                                                        |
| ------- | ------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| 2.8.3.a | Вынести общие модели/типы цикла (`FixCycleContext`, `FixCycleResult`, protocol-обёртки deps)      | `cli/orchestration/models.py`, `cli/orchestration/deps.py`       | `cli/orchestrator.py` компилируется, тесты без регресса                         |
| 2.8.3.b | Вынести pre-stage (`scan/diagnose/plan/policy/session-filter`)                                    | `cli/orchestration/prepare.py`                                   | `_prepare_fix_cycle_operations` уходит из god-file, dry-run поведение идентично |
| 2.8.3.c | Вынести apply-stage (`apply+verify`, rescan enrich, write report, memory append)                  | `cli/orchestration/apply_stage.py`                               | verify/rollback/telemetry контракты не меняются                                 |
| 2.8.3.d | Вынести doctor/full-flow wiring                                                                   | `cli/orchestration/doctor.py`, `cli/orchestration/full_cycle.py` | `run_cycle(mode=doctor/full)` возвращает тот же payload                         |
| 2.8.3.e | Оставить в `cli/orchestrator.py` только фасад (`run_cycle`, thin wrappers, compatibility imports) | `cli/orchestrator.py`                                            | Размер файла заметно снижен; публичные функции сохранены                        |
| 2.8.3.f | Добавить regression-тесты на эквивалентность stage-вывода и edge-cases                            | `tests/test_cycle.py`, `tests/test_cli_runtime_mode.py`          | Старые + новые тесты зелёные                                                    |


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


| #     | Шаг                            | Задача                                                                                                                                                       | Критерий готовности                                                                                                   |
| ----- | ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------- |
| 2.9.1 | Architect → рекомендации «как» | Расширить architect: не только «что не так», но и «что делать и как» — на основе Knowledge Layer (PEP, docs.python.org, release notes)                       | Architect при god_module/bottleneck выдаёт конкретные подсказки с reference на доку; блок Reference в doctor расширен |
| 2.9.2 | LLM в планировании             | Для сложных smell (god_module, hub, bottleneck) — запрос к Ollama: «предложи точки разбиения»; результат в patch_plan как hints или уточнённые target/params | При наличии Ollama и high-risk smell: planner получает LLM-подсказки; fallback на эвристики без LLM                   |
| 2.9.3 | Knowledge Layer — PEP/RFC      | Добавить провайдеры PEP, RFC, What's New (docs.python.org); темы по smell_type (god_module → module_structure, long_function → extract_method)               | eurika.knowledge: PEPProvider, WhatNewProvider; маппинг smell_type → knowledge_topic; architect и planner используют  |
| 2.9.4 | Обучение в цикле               | Корректировка policy из telemetry; suggest_policy_from_telemetry выводится в doctor; опция применять suggested policy                                        | doctor показывает блок «Suggested policy» при низком apply_rate; CLI или env для принятия suggestion                  |
| 2.9.5 | Dogfooding 2.9                 | 3 цикла с LLM + Knowledge на Eurika; сравнить качество плана (релевантность подсказок) и apply-rate                                                          | Отчёт в CYCLE_REPORT; architect даёт «как»; learning улучшает выбор ops                                               |


**Порядок внедрения (рекомендуемый):** 2.9.1 → 2.9.3 → 2.9.2 → 2.9.4 → 2.9.5. Architect и Knowledge — основа; LLM в planner — поверх; learning — замкнутый цикл.

**Фактический прогресс (фаза 2.9):**

- 2.9.1 Architect рекомендации — блок «Recommendation (how to fix)» с конкретными шагами по smell (god_module, bottleneck, hub, cyclic_dependency); блок «Reference (from documentation)» при наличии Knowledge; LLM и template
- 2.9.2 LLM в планировании — planner_llm.ask_ollama_split_hints для god_module/hub/bottleneck; hints в patch_plan; fallback на эвристики (EURIKA_USE_LLM_HINTS=0)
- 2.9.3 Knowledge PEP/RFC — PEPProvider в eurika.knowledge; SMELL_TO_KNOWLEDGE_TOPICS в doctor; architect/planner получают темы по smell (god_module→architecture_refactor, long_function→pep_8)
- 2.9.4 Обучение в цикле — doctor блок «Suggested policy» при низком apply_rate; load_suggested_policy_for_apply; --apply-suggested-policy в fix/cycle
- 2.9.5 Dogfooding 2.9 — 3 стабильных цикла с LLM + Knowledge на Eurika; verify ✓; apply-rate и learning стабильны

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


| #     | Шаг                           | Задача                                                                                                                            | Критерий готовности                                                                                                                                          |
| ----- | ----------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 3.0.1 | Multi-Repo Scan               | Поддержка `eurika scan <path1> <path2> ...` и `eurika cycle --paths path1,path2` для нескольких корней проектов                   | CLI принимает несколько путей; scan/doctor/fix выполняются последовательно или параллельно по каждому; отчёт агрегирует summary/risks по всем проектам       |
| 3.0.2 | Cross-Project Memory          | Общая директория памяти (напр. `~/.eurika/` или `EURIKA_GLOBAL_MEMORY`) для learning/feedback между проектами                     | Learning/feedback из проекта A учитываются при fix проекта B (при совпадении smell|action); формат агрегации и приоритет local vs global описан в spec       |
| 3.0.3 | Online Knowledge (расширение) | Расширить Knowledge Layer: актуальный fetch по запросу (не только кэш), провайдеры PEP/RFC, интеграция с architect при cross-repo | Новые провайдеры или опция `--online`; architect получает релевантные фрагменты при анализе нескольких проектов; TTL и rate-limit для сетевых запросов       |
| 3.0.4 | Team Mode                     | Роли, shared session, approvals между пользователями; интеграция с CI (отдельный approve-step)                                    | `eurika fix --team-mode` или отдельная команда; policy учитывает "approved by" для high-risk ops; документация сценариев (один предлагает, другой применяет) |


**Фактический прогресс (фаза 3.0):**

- 3.0.1 Multi-Repo Scan — `eurika scan/doctor/fix/cycle path1 [path2 ...]`; последовательное выполнение по каждому пути; заголовки "--- Project N/M ---"; агрегированный JSON-отчёт — в плане
- 3.0.2 Cross-Project Memory — общая память ~/.eurika/ или EURIKA_GLOBAL_MEMORY; append learn при fix; get_merged_learning_stats(local+global) при build patch plan; merge: sum total/success/fail per smell|action; EURIKA_DISABLE_GLOBAL_MEMORY для отключения
- 3.0.3 Online Knowledge — `--online` в doctor/cycle/fix/architect; force_online, rate_limit; TTL/RATE_LIMIT env; KNOWLEDGE_LAYER.md
- 3.0.4 Team Mode — --team-mode (propose), --apply-approved; .eurika/pending_plan.json; EURIKA_APPROVALS_FILE

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


| #          | Шаг                            | Задача                                                                                                                                                            | Критерий готовности                                                                     |
| ---------- | ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| 3.1-arch.1 | Формальные слои                | Зафиксировать слои в документе: L0 Infrastructure → L1 Core model → L2 Analysis → L3 Planning → L4 Execution → L5 Reporting → L6 CLI; запретить зависимости вверх | ARCHITECTURE.md или LAYERS.md с картой слоёв; dependency guard проверяет no upward deps |
| 3.1-arch.2 | API-границы подсистем          | Каждая подсистема экспортирует 1–2 публичные точки входа; остальное private                                                                                       | Документ или `__all_`_ в ключевых модулях; рекомендации в CYCLE_REPORT                  |
| 3.1-arch.3 | Лимит размера файлов           | Правило: >400 строк — кандидат на разбиение; >600 строк — обязательно делить                                                                                      | Линт/скрипт или checklist; список файлов-нарушителей в self-check или report            |
| 3.1-arch.4 | Domain vs presentation         | Модули, которые и вычисляют, и форматируют Markdown — разделить на domain + presentation                                                                          | Аудит смешанных модулей; план разбиения и выполненные выносы                            |
| 3.1-arch.5 | Облегчить CLI                  | CLI только принимает команды и передаёт оркестратору; убрать бизнес-логику и сложные пайплайны из CLI-слоя                                                        | CLI handlers — тонкие обёртки; тесты на изоляцию                                        |
| 3.1-arch.6 | Развести Planning и Execution  | Planner строит план; Executor исполняет; убрать взаимное знание деталей                                                                                           | Аудит planner_* и patch_apply_*; явные контракты между ними                             |
| 3.1-arch.7 | Dogfooding на новой дисциплине | 3 цикла scan → doctor → fix после внедрения ограничений                                                                                                           | Нет регресса; verify стабилен; новые правила не ломают цикл                             |


**Порядок внедрения (рекомендуемый):** 3.1-arch.1 → 3.1-arch.2 → 3.1-arch.5 → 3.1-arch.6 → 3.1-arch.4 → 3.1-arch.3 → 3.1-arch.7.

**Фактический прогресс (фаза 3.1-arch):**

- 3.1-arch.1 Формальные слои — Architecture.md §0: нотация L0–L6 (Infra→Core→Analysis→Planning→Execution→Reporting→CLI); allowed deps; mapping модулей; no upward deps; dependency guard + layer firewall (strict) проверяет
- 3.1-arch.2 API-границы подсистем — Architecture.md §0.6; **all** в patch_engine, eurika.core, eurika.analysis, eurika.smells, eurika.evolution, eurika.reporting; рекомендации в CYCLE_REPORT §23
- 3.1-arch.3 Лимит размера файлов — eurika.checks.file_size; >400 candidate, >600 must split; self-check выводит блок; python -m eurika.checks.file_size
- 3.1-arch.4 Domain vs presentation — report/architecture_report.py (rendering); runtime_scan импортирует rendering на верхнем слое (без core->report зависимости); central_modules_for_topology в system_topology
- 3.1-arch.5 Облегчить CLI — report/report_snapshot.format_report_snapshot; eurika.api: explain_module, get_suggest_plan_text, clean_imports_scan_apply; handlers тонкие обёртки; test_handle_report_snapshot_delegates_to_format
- 3.1-arch.6 Развести Planning и Execution — eurika.reasoning.planner без patch_apply/patch_engine; planner_patch_ops без зависимости на eurika.refactor; Architecture.md §0.5 Planner–Executor Contract; dependency guard для eurika/reasoning/
- 3.1-arch.7 Dogfooding — eurika fix . (6 modified), 3× eurika fix . --dry-run (0 ops fixpoint); verify ✓ 287 passed; CYCLE_REPORT §28

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

**Направление (без жёстких дат):** движение к архитектурному AI-инженеру. Фундамент (Patch Engine, Verify, Event Engine, Orchestrator) заложен; фазы 3.1 и 3.2 реализованы.


| Версия   | Цель                      | Содержание                                                                                     |
| -------- | ------------------------- | ---------------------------------------------------------------------------------------------- |
| **v2.1** | Execution Milestone       | Orchestrator ✓; PatchEngine v1 ✓; Verify ✓; Rollback ✓; 3 детермин. операции ✓.                |
| **v2.3** | Stability Phase           | Метрики; priority engine ✓; CI-ready ✓ (CLI.md § CI/CD); CLI doctor/fix/explain ✓.             |
| **v2.6** | Semi-Autonomous Agent     | auto-run ✓; continuous monitoring ✓; performance-based improvement ✓; event-based learning ✓.  |
| **v3.0** | Architectural AI Engineer | multi-repo; cross-project memory; online knowledge; team-mode.                                 |
| **v3.5** | Web UI                    | dashboard; summary/history/explain в браузере; опционально: approve/reject, граф зависимостей. |


---

### Фаза 3.5 — Web UI (дашборд поверх JSON API)

**Цель:** веб-интерфейс для просмотра архитектурного анализа, истории эволюции и (опционально) approve/reject операций в hybrid-режиме. Основа — существующий `eurika serve` (GET /api/summary, /api/history, /api/diff). UI не заменяет CLI, а дополняет для пользователей, предпочитающих браузер.

**Предпосылки:** JSON API готов (eurika.api, eurika serve). Нужен только frontend.


| #      | Шаг                             | Задача                                                                                                                                                                                                                                                       | Критерий готовности                                                                                                            |
| ------ | ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------ |
| 3.5.1  | API-расширение для UI           | Добавить в `eurika serve` endpoints: `/api/doctor` (report), `/api/patch_plan` (operations), `/api/explain?module=...`                                                                                                                                       | GET возвращает тот же JSON, что формируют handle_doctor, get_patch_plan, explain_module; project_root из query или default     |
| 3.5.2  | Static SPA или SSR              | Создать frontend: React/Vue/Svelte или простой HTML+JS; отображение summary (модули, риски, health score), history (trends, evolution_report)                                                                                                                | `eurika serve` раздаёт статику из `eurika/ui/` или отдельного каталога; одна точка входа для UI                                |
| 3.5.3  | Dashboard                       | Страница дашборда: system metrics (modules, deps, cycles), central modules, top risks, health/risk score, trends                                                                                                                                             | Визуально читаемый обзор; ASCII-чарты или простые bar/line (Chart.js, D3, или CSS-only)                                        |
| 3.5.4  | History & diff                  | Страницы: evolution history (окно window), diff между двумя self_map                                                                                                                                                                                         | Таблица/список points; diff в виде «добавлено/удалено/изменено»                                                                |
| 3.5.5  | Explain module                  | Страница или модальное окно: ввод имени модуля → вывод role, risks, rationale из explain_module                                                                                                                                                              | Интеграция с /api/explain                                                                                                      |
| 3.5.6  | (Опционально) Approve/reject UI | При hybrid-режиме: UI для approve/reject/skip операций из patch_plan; POST /api/approve с op_index и decision                                                                                                                                                | Требует WebSocket или long-polling для real-time; можно отложить в пользу CLI HITL                                             |
| 3.5.7  | Граф зависимостей (опционально) | Визуализация графа модулей (nodes = modules, edges = imports); библиотека (Cytoscape.js, vis.js, D3)                                                                                                                                                         | Интерактивный граф: zoom, pan, click на узел → explain                                                                         |
| 3.5.8  | Terminal в UI                   | Вкладка Terminal: input + output area; POST /api/exec с whitelist команд eurika                                                                                                                                                                              | Пользователь выполняет eurika scan/doctor/fix из браузера; безопасно (только eurika-команды)                                   |
| 3.5.9  | Run cycle из UI                 | Кнопка «Run cycle» на Dashboard → eurika cycle . или doctor                                                                                                                                                                                                  | Одним кликом запуск полного цикла; вывод в output/лог                                                                          |
| 3.5.10 | Ask architect (опционально)     | Поле ввода вопроса → architect с промптом; ответ в UI                                                                                                                                                                                                        | Вопрос-ответ по архитектуре через браузер                                                                                      |
| 3.5.11 | Chat & Learn                    | Чат в UI: прослойка Eurika → Ollama; контекст проекта; сохранение диалогов в .eurika/chat_history/; векторное хранилище (embeddings) для RAG — похожие запросы дополняют промпт примерами; опционально: intent→action («сохрани код в X») через patch engine | POST /api/chat; вкладка Chat; логирование (query, context, response, outcome); RAG при похожих запросах; интеграция с learning |


**Порядок внедрения (рекомендуемый):** 3.5.1 → 3.5.2 → 3.5.3 → 3.5.4 → 3.5.5 → 3.5.6 → 3.5.7 → 3.5.8 → 3.5.9; 3.5.10 — по желанию; 3.5.11 — после 3.5.10.

**Фактический прогресс (фаза 3.5):**

- 3.5.1 API-расширение — eurika serve: /api/doctor, /api/patch_plan, /api/explain; CLI.md
- 3.5.2 Static SPA — eurika/ui/ (index.html + app.js), summary/history/explain tabs, serve static
- 3.5.3 Dashboard — вкладка Dashboard: risk bar, system grid, trends badges, central/risks
- 3.5.4 History & diff — вкладка Diff в UI: old/new paths → /api/diff
- 3.5.5 Explain module — вкладка Explain Module в UI (3.5.2)
- 3.5.6 Approve/reject UI — вкладка Approve; GET /api/pending_plan, POST /api/approve; approve/reject per op, Save; eurika fix . --apply-approved
- 3.5.7 Граф зависимостей — vis-network; GET /api/graph; вкладка Graph в UI; double-click → Explain
- 3.5.8 Terminal в UI — POST /api/exec; вкладка Terminal (input + output); whitelist eurika-команд
- 3.5.9 Run cycle из UI — кнопка «Run cycle» на Dashboard; POST /api/exec с `eurika cycle .`
- 3.5.10 Ask architect — POST /api/ask_architect; вкладка Ask в UI; вопрос → architect → ответ
- 3.5.11 Chat & Learn — чат через Eurika→Ollama; контекст + RAG; intent→action (save, refactor, delete, create, remember/recall)
- 3.5.11.A (этап A) — POST /api/chat; eurika.api.chat.chat_send; .eurika/chat_history/chat.jsonl; вкладка Chat в UI
- 3.5.11.B (этап B) — RAG: chat_rag.retrieve_similar_chats (TF-IDF), format_rag_examples; подстановка похожих диалогов в промпт
- 3.5.11.C (этап C) — intent: save, refactor, delete, create, remember, recall; chat_intent.detect_intent; user_context.json

**Chat & Learn (3.5.11) — развитие идеи:**

- A (минимально): прокси в Ollama + JSON-лог диалогов в .eurika/ ✓
- B (+RAG): при похожем запросе — подтягивать прошлые успешные примеры в промпт (TF-IDF, pure Python) ✓
- C (агентно): save (код → write file), refactor (eurika fix), delete, create (пустой файл), remember/recall (user context) ✓

#### Детальный план 3.5.11.A (этап A — минимум)


| #          | Шаг                    | Задача                                                                                                                                                                   | Критерий готовности                                                                |
| ---------- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------- |
| 3.5.11.A.1 | POST /api/chat         | Добавить endpoint: `POST /api/chat` с body `{ "message": "...", "project_root": "..." }`                                                                                 | serve.py обрабатывает path; возвращает `{ "text": "...", "error": "..."? }`        |
| 3.5.11.A.2 | chat_send (eurika.api) | Функция `chat_send(project_root, message, history?: [])` — обогащает промпт контекстом (summary, recent_events), вызывает Ollama (или существующий LLM-контур architect) | eurika.api.chat_send; fallback на template если Ollama недоступен                  |
| 3.5.11.A.3 | Chat history storage   | Логирование в `.eurika/chat_history/chat.jsonl`: JSONL со строками `{ "ts", "role", "content", "context_snapshot" }`                                                     | Append на каждое сообщение; одна сессия — append; формат читаемый для будущего RAG |
| 3.5.11.A.4 | UI: вкладка Chat       | Вкладка Chat в UI: input, список сообщений, Send → POST /api/chat; отображение ответа                                                                                    | Аналогично Ask, но диалог (история в сессии); UI.md обновлён                       |


**Порядок внедрения 3.5.11.A:** 3.5.11.A.1 → 3.5.11.A.2 → 3.5.11.A.3 → 3.5.11.A.4

**Метрики выхода из 3.5.11.A:** пользователь вводит сообщение → получает ответ от Ollama с контекстом проекта; диалог логируется в .eurika/chat_history/.

**Метрики выхода из фазы 3.5 (DoD):**

- Пользователь может открыть `http://localhost:8765` (или настроенный порт) и получить рабочий дашборд.
- Summary, history, explain доступны через UI без CLI.
- Документация: CLI.md или отдельный UI.md с инструкцией по запуску и настройке.

**Зависимости:** 3.5 опирается на eurika serve и eurika.api; не зависит от 3.0.4 Team Mode. Можно вести параллельно с 3.0.4.

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

## 1. Архитектурная целостность

- Pipeline: scan → graph → smells → summary → history → diff → report
- ArchitectureSnapshot как единый объект
- core/pipeline.py, cli/handlers.py
- Скелет eurika/ + фасады + импорты среднего слоя (analysis, smells.rules, evolution, reporting, self_map, topology)
- Перенос реализации в eurika/*: smells (detector, models, health, advisor), analysis.metrics; плоские файлы — реэкспорты
- architecture_summary → eurika.smells.summary (реализация в пакете, плоский — реэкспорт)
- evolution (history, diff) → eurika.evolution.history, eurika.evolution.diff (реализация в пакете, плоские — реэкспорты; architecture_diff.py сохраняет CLI)

---

## 2. Architecture History Engine

### 2.1 Модель данных

- version (pyproject.toml)
- git_commit (опционально)
- diff metrics (дельты, не только абсолюты)

### 2.2 Регрессии

- god_module, bottleneck, hub — отдельно
- risk score (0–100)

### 2.3 Будущее

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

### TODO до продуктовой 1.0

- **Консолидация памяти:** единый контракт — `eurika.storage.ProjectMemory(project_root)`. Довести до единого Event Engine — см. Этап 4 плана прорыва.
- **Замкнутый цикл (скелет):** поток `eurika fix` = scan → diagnose → plan → patch → verify → learn есть; довести verify + rollback и полноценный Patch Engine — этапы 1, 3.
- **Killer-feature (цель):** remove_cyclic_import, remove unused imports, split oversized module; eurika fix с verify и откатом при провале — этапы 1–2, 3.
- **CLI режимы есть:** scan, doctor, fix, explain. Упростить до 4 режимов без dev-команд — этап 5.

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

- Провести полный цикл на самом проекте Eurika: scan → doctor → fix --dry-run. Инструкция — **DOGFOODING.md** (в т.ч. про venv для verify).

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

