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
| Продуктовая готовность  | 6.5/10 | Продакшн-готовность   | 4/10   |
| Потенциал               | 9.5/10 |                       |        |

**Вывод ревью (2026):** «Функционально мощный, архитектурно нестабильный, структурно перегруженный.» Риски: God CLI, backups в дереве, orchestration без формальной модели. **Стратегия:** усиливать execution — критично; усиливать LLM — преждевременно.

**Обновление (февраль 2026):** Split тяжёлых модулей (task_executor, serve, fix_cycle_impl, core_handlers, chat) — P0.4 выполнен; pipeline_model; test_cycle → test_cycle_report; CR rules (docs, pre-commit, test-api) в .eurika/rules; Qt MVP: hybrid approvals, dashboard, Stop. **Рост:** чистота структуры 4→5.5, контроль сложности 5→6, тестируемость ?→6, продуктовая 6→6.5. **Остаётся:** refactor_code_smell 0%, test_chat_api/test_api_serve крупные, продакшн 4/10.

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

Curated repos (Django, FastAPI) → pattern library → повышение verify_success_rate. **Статус:** частично (3.0.5.1–3.0.5.4); долго.

### 4.2 Направление B — Продуктовая готовность 6→7/10

UI.md ✓; README ✓; критерии для 7/10:

| #   | Критерий                         | Описание                                      |
| --- | -------------------------------- | --------------------------------------------- |
| B.7 | `release_check.sh` проходит      | ruff, mypy, pytest — без ошибок               |
| B.8 | Notes tab в GUI                  | Заметки сохраняются в `.eurika/notes.txt`     |
| B.9 | Onboarding ≤ 10 мин              | Новичок: clone → scan/doctor/fix за 10 мин    |
| B.10| `.eurika/rules/*` в проекте      | docs.mdc, pre-commit.mdc, test-api.mdc        |

**Быстро.**

### 4.3 Направление C — Ритуал 2.1

Регулярно: scan, doctor, report-snapshot; обновлять CYCLE_REPORT. **Постоянно.**

### 4.4 Qt MVP (eurika_2.0.Qt)

Цели: запуск Qt, folder picker, Commands tab (scan/doctor/fix), live output, Stop, hybrid approvals, dashboard. Стартовый промпт — см. §6.

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
| CR-E1 | Сценарии для Composer        | split модуля, вынос domain vs presentation      | —      |
| CR-E2 | Шаблон промпта Composer      | контекст + план 3–7 шагов + критерии            | —      |
| CR-E3 | Практика: крупный рефакторинг в Composer | один пример в CYCLE_REPORT                | —      |
| CR-F1 | Команды для агента           | eurika serve, pytest, release_check.sh           | —      |
| CR-F2 | Паттерн «изменение → проверка» | pytest по модулю после правок                 | —      |
| CR-F3 | Интерпретация ошибок         | Ruff → __all__/импорт; mypy → type hint         | —      |

### 5.4 Chat intents config (CR-G)

| #     | Шаг                    | Описание                                          | Статус |
| ----- | ---------------------- | ------------------------------------------------- | ------ |
| CR-G1 | chat_intents.yaml      | Паттерны, emit, intent_hints; match_direct_intent | ✅     |
| CR-G2 | Векторная память       | Embeddings для fuzzy match (опционально)          | —      |
| CR-G3 | PyTorch-классификатор  | Только при 100+ интентов (опционально)            | —      |

---

## 6. Открытый бэклог (следующие шаги)

### 6.1 Структура и размер файлов

- ~~Разбить `eurika/api/task_executor.py` (767 LOC), `eurika/api/serve.py` (598)~~ ✅ P0.4: task_executor → helpers, types, executors, patch; serve → utils, exec, routes_get, routes_post
- ~~Разбить `eurika/orchestration/fix_cycle_impl.py` (586)~~ ✅ fix_cycle_helpers, fix_cycle_apply_approved
- ~~test_cycle.py~~ → test_cycle_report.py (report-snapshot, telemetry, whitelist-draft) ✅
- Разбить при необходимости: `test_cycle.py`, `test_chat_api.py`, `test_api_serve.py`

### 6.2 Qt и UI

- CR-A2: Commands tab — scan/doctor/fix в GUI (QProcess) ✅
- CR-A4: qt_app.mdc с правилами для агента ✅
- Live output + Stop/Cancel ✅
- Hybrid approvals: Load plan, approve/reject per row, Save, apply-approved ✅ (Save feedback: "X approved, Y rejected")
- Dashboard: Summary, risks, SELF-GUARD, Ops, History sub-tab, Run scan button ✅

### 6.3 Операционность

- KPI: `verify_success_rate` по smell|action|target (prioritized_smell_actions ✅)
- refactor_code_smell — 0% success в WEAK_SMELL_ACTION_PAIRS; для повышения — pattern library, curated repos, LLM

### 6.4 Cursor Rules (незакрытые)

- ~~CR-B1, CR-C1, CR-C2, CR-C3, CR-D3~~ ✅
- CR-D1–CR-D2: @-ссылки, паттерны по типам задач
- CR-E, CR-F: Composer и Terminal

### 6.5 Multi-repo и Learning

- 3.0.1: eurika_fix_report_aggregated.json при fix/cycle [path1 path2 ...]
- 3.0.5: расширение Learning from GitHub (pattern library, OSS examples)

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

**Для повышения:** интернет, LLM, pattern library, curated repos (3.0.5).

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
- **Knowledge Layer:** после стабилизации ядра; контракт в docs/KNOWLEDGE_LAYER.md
