# Eurika 2.0

**Architecture Awareness Engine** — анализ кода и архитектуры, планирование рефакторинга, применение патчей с бэкапами и учётом прошлого опыта. Целевой цикл: *scan → diagnose → plan → patch → verify → learn* (команда `eurika fix`).

*Требования: Python 3.10+.* Для проверки после `eurika fix` нужен pytest: `pip install pytest` или `pip install -e ".[test]"`. Рекомендуется Python 3.12/3.13 для Qt.

**Текущий фокус (по review):** переход от «архитектурного аналитика» к «инженерному инструменту» — полноценный Patch Engine (apply/verify/rollback), автофиксы, единый Event Engine. Детали — в **docs/review.md** и **docs/ROADMAP.md**.

## Быстрый старт

### Установка (venv-нейтрально)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
```

### Базовые команды

После установки:

```bash
eurika scan .           # полный скан → self_map.json, smells, summary
eurika doctor .         # диагностика (report + architect) без патчей
eurika fix . --dry-run  # план рефакторинга без применения
eurika serve .          # JSON API на http://127.0.0.1:8765/api
```

### Qt desktop shell (PySide6, Qt-first)

Desktop-first интерфейс поверх CLI/API-ядра:

```bash
pip install -e ".[test,qt]"
eurika-qt .
```

Вкладки Qt-интерфейса:

- **Models** — управление Ollama: Start/Stop, переменные окружения, список моделей, установка
- **Chat** — чат с Apply/Reject для подтверждения планов; создание вкладок (в т.ч. Terminal) по intent
- **Commands** — scan/doctor/fix/cycle/explain/report-snapshot/learning-kpi, live output, stop/cancel
- **Dashboard** — summary/history, top verify_success, рекомендации по whitelist
- **Approvals** — approve/reject flow для pending plan

Выбор chat provider/model: `auto`, `openai`, `ollama`. Проект задаётся через picker или аргумент `eurika-qt .`.

Или напрямую: `python eurika_cli.py scan .`.

**Для LLM (doctor, architect, cycle):** установите `pip install -e ".[test]"` (включает openai, pytest). Без openai LLM не вызывается — вывод шаблонный. Подробнее — **docs/DOGFOODING.md**.

**Ollama (локальный LLM):** для architect/cycle с ollama запустите сервер, при необходимости с переменными для AMD GPU:
```bash
HSA_OVERRIDE_GFX_VERSION=10.3.0 ROCR_VISIBLE_DEVICES=0 HIP_VISIBLE_DEVICES=0 ollama serve
```

Fallback-модель для локального OpenAI-compatible endpoint Ollama задаётся через `OLLAMA_OPENAI_MODEL` (по умолчанию: `qwen2.5-coder:7b`).

**Pipeline:** `cli → core/pipeline → code_awareness → scan → graph → smells → summary → history → report`

## Режимы (продуктовые)

- **`eurika scan [path]`** — полный скан и обновление артефактов.
- **`eurika doctor [path]`** — только диагностика: report + architect (без патчей). Опции: `--window N`, `--no-llm`. При наличии `eurika_knowledge.json` темы подбираются по диагнозу (всегда `python`; при циклах — `cyclic_imports`; при god/hub — `architecture_refactor`) или задаются через `EURIKA_KNOWLEDGE_TOPIC` (см. **docs/KNOWLEDGE_LAYER.md**).
- **`eurika fix [path]`** — полный цикл: scan → plan → patch-apply --apply --verify. Опции: `--window N`, `--dry-run`, `--quiet`, `--no-clean-imports`.
- **`eurika cycle [path]`** — ритуал одной командой: scan → doctor (report + architect) → fix. Опции: `--window N`, `--dry-run`, `--quiet`, `--no-llm`, `--no-clean-imports`.

**CI:** `eurika fix . --quiet` — exit 0 при успехе, 1 при провале verify или ошибках. См. docs/CLI.md § CI/CD.
- **`eurika explain <module> [path]`** — роль и риски модуля.
- **`eurika serve [path]`** — JSON API для интеграций и внешних клиентов (Qt shell и др.).

## CLI commands

### Core

- **`eurika scan [path]`**: полный сценарий — сканирование, smells, summary, рекомендации, history, observation memory. Каталог `.eurika_backups` исключён из анализа.
- **`eurika doctor [path]`**: диагностика без патчей (report + architect). Опции: `--window N`, `--no-llm`.
- **`eurika fix [path]`**: полный цикл исправлений (scan → plan → apply → verify). Опции: `--window N`, `--dry-run`, `--quiet`.
- **`eurika cycle [path]`**: scan → doctor → fix одной командой. Опции: `--window N`, `--dry-run`, `--quiet`, `--no-llm`.
- **`eurika arch-summary [path]`**: только архитектурный summary по текущему `self_map.json`.
- **`eurika arch-history [path]`**: выводит последний `Architecture Evolution Analysis` из `architecture_history.json`.
- **`eurika history [path]`**: алиас для arch-history.
- **`eurika report [path]`**: summary + evolution report (без повторного сканирования). Опции: `--json`, `--window N`.
- **`eurika explain <module> [path]`**: роль и риски модуля в графе.
- **`eurika architect [path]`**: интерпретация в стиле «архитектор проекта» (2–4 предложения). По умолчанию — шаблон; при заданных переменных окружения вызывается LLM (OpenAI или OpenRouter). Опции: `--window N`, `--no-llm`.
- **`eurika suggest-plan [path]`**: эвристический рефакторинг-план по summary и рискам (или по build_recommendations при наличии self_map). Опция: `--window N`.
- **`eurika arch-diff old.json new.json`**: сравнивает два снапшота `self_map.json`. Опция `--json`.
- **`eurika serve [path]`**: JSON API only (`/api/*`) для интеграций и UI-клиентов (Qt shell и др.). Опции: `--port`, `--host`.
- **`eurika learn-github [path]`**: клонирует curated OSS (Django, FastAPI и др.) в `../curated_repos/`; `--scan` — scan после clone; `--build-patterns` — pattern library (включая long_function/deep_nesting).
- **`eurika learning-kpi [path]`**: KPI verify_success_rate по smell|action|target, promote/deprioritize рекомендации. `--json`, `--top-n`.
- **`eurika report-snapshot [path]`**: CYCLE_REPORT-style markdown из doctor/fix артефактов.

### AgentCore (experimental)

- **`eurika agent arch-review [path]`**: агрегирует summary, history, observations в предложения (explain_risk, summarize_evolution, prioritize_modules, suggest_refactor_plan, suggest_action_plan, suggest_patch_plan).
- **`eurika agent arch-evolution [path]`**: эволюция архитектуры по `architecture_history.json`.
- **`eurika agent prioritize-modules [path]`**: печатает приоритизированный список модулей (JSON).
- **`eurika agent action-dry-run [path]`**: строит ActionPlan из диагностики, печатает без выполнения.
- **`eurika agent action-simulate [path]`**: строит ActionPlan и прогоняет ExecutorSandbox.dry_run (логирование без изменения кода).
- **`eurika agent action-apply [path]`** [`--no-backup`]: строит ActionPlan и выполняет ExecutorSandbox.execute (добавляет TODO-блок в целевые файлы; бэкапы по умолчанию).
- **`eurika agent patch-plan [path]`** [`-o FILE`]: строит patch plan (рефакторинг по модулям), выводит JSON или пишет в файл.
- **`eurika agent patch-apply [path]`** [`--apply`] [`--verify`] [`--no-backup`]: применяет patch plan (добавляет TODO-блоки). По умолчанию dry-run; `--apply` пишет в файлы; `--verify` запускает pytest после apply; бэкапы в `.eurika_backups/` создаются по умолчанию.
- **`eurika agent patch-rollback [path]`** [`--run-id ID`] [`--list`]: восстанавливает файлы из `.eurika_backups/` (по умолчанию последний run); `--list` — список доступных run_id.
- **`eurika agent cycle [path]`** [`--window N`] [`--dry-run`] [`--quiet`|`-q`]: scan → arch-review → patch-apply --apply --verify; при успехе — rescan и `rescan_diff`; `--dry-run` — только patch-plan; `--quiet` — только итоговый JSON.
- **`eurika agent learning-summary [path]`**: статистика по patch-apply + verify: `by_action_kind` и `by_smell_action` (пары smell_type|action_kind).
- **`eurika agent feedback-summary [path]`**: статистика по ручному фидбеку (`architecture_feedback.json`).

### Self-analysis

- **`eurika self-check [path]`**: ритуал самоанализа — полный scan проекта. Запускайте из корня Eurika: `eurika self-check .` — Eurika анализирует свою собственную архитектуру. Рекомендуется после значимых изменений.

### Architect (LLM, опционально)

Для вывода от LLM задайте в окружении (или в `.env` в корне проекта, при установленном `python-dotenv`):

- **`OPENAI_API_KEY`** — ключ API (OpenAI или OpenRouter).
- **`OPENAI_BASE_URL`** — для OpenRouter: `https://openrouter.ai/api/v1`.
- **`OPENAI_MODEL`** — модель, например `mistralai/mistral-small-3.2-24b-instruct` или `gpt-4o-mini`.

Установка: `pip install openai` (и при необходимости `pip install python-dotenv` для загрузки `.env`). Без ключа выводится шаблонная сводка.

### Помощь

- **`eurika help`**: краткий обзор команд.

## Architecture Awareness Engine

При `scan` Eurika строит архитектурный срез проекта:

- **Self-introspection**: `self_map.json` (модули, строки, зависимости). Каталог `.eurika_backups` исключён.
- **Architecture Smells**: `god_module`, `hub`, `bottleneck`, циклы.
- **Architecture Summary**: центральные модули, риски, maturity.
- **Architecture Advisor**: рекомендации по smells.
- **Architecture History**: тренды, dynamic maturity, version (pyproject), risk score (0–100), опционально git hash (`.eurika/history.json`).
- **Action Plan / Patch Plan**: приоритизация модулей и план рефакторинга (read-only).
- **Patch Engine** (`patch_engine.py`): фасад apply_and_verify и rollback; используется в `eurika fix` и `eurika agent patch-apply --apply --verify`. Цель (ROADMAP): полноценные apply_patch / verify_patch / rollback_patch и автоматический откат при провале верификации.
- **Patch Apply**: применение patch plan с бэкапами в `.eurika_backups/<run_id>/`, опционально `--verify` (pytest).
- **Patch Rollback**: восстановление из бэкапа.
- **Learning Loop**: после `patch-apply --apply --verify` исходы записываются как события (type=learn) в `.eurika/events.json`; architect использует recent_events в промпте; при arch-review прошлые success rate — для `learned_signals`.

## Зависимости и расширения

Полный список — **docs/DEPENDENCIES.md**. Расширения (v3.0.13+):

- **refactor** — libcst (round-trip AST, сохранение форматирования)
- **cli** — rich (прогресс, таблицы, подсветка)
- **extras** — pydantic, watchdog, ruff, structlog, ollama

Установка всего: `pip install -e ".[test,qt,refactor,cli,extras]"`.

## Документация

Все документы — в каталоге **docs/** ([docs/README.md](docs/README.md) — навигация).

- **docs/UI.md** — legacy reference по архивному Web UI (история, не текущий интерфейс)
- **docs/MIGRATION_WEB_TO_QT.md** — практический статус миграции интерфейса: что удалено, что осталось, как запускать сейчас
- **docs/review.md** — разбор, диагноз зрелости, план прорыва (5 этапов)
- **docs/ROADMAP.md** — план задач, оценка зрелости, «что не хватает», план прорыва, этапы до продуктовой 1.0
- **docs/REPORT.md** — текущий статус, оценка по review, следующий шаг
- **docs/Architecture.md** — структура системы, замкнутый цикл, Patch Engine (целевой API), направление 2.1
- **docs/CLI.md** — справочник команд, рекомендуемый цикл
- **docs/DOGFOODING.md** — ритуал полного цикла на самом Eurika (scan → doctor → fix), про venv
- **docs/KNOWLEDGE_LAYER.md** — Knowledge Provider Layer (контракт, формат `eurika_knowledge.json`, интеграция с doctor/architect). Пример: `docs/eurika_knowledge.example.json`.
- **docs/SPEC.md** — контракт проекта (v0.1–v0.4), текущий фокус
- **docs/THEORY.md** — идеология и философия Eurika

## Self-analysis ritual

Eurika должна быть эталоном архитектурной чистоты. Команда `eurika self-check .` запускает полный анализ собственной кодовой базы. Рекомендуется выполнять после рефакторинга или перед релизом.

## How to read the reports

- **Scan Report** — обзорная статистика:
  - количество файлов, строк, локальные code smells;
  - список модулей, участвующих в анализе.
- **Architecture Smells** — ключевые архитектурные проблемы:
  - `god_module` / `hub` / `bottleneck` по именам файлов;
  - стоит воспринимать как точки повышенного риска и кандидатов на декомпозицию.
- **Architecture Summary** — системный портрет:
  - какие модули являются «центрами тяжести» (fan-in/fan-out);
  - сколько циклов, каков общий уровень сложности (syntactic maturity);
  - блок Risks — краткий список самых опасных мест.
- **Architecture Recommendations** — конкретные советы:
  - что именно вынести, где ввести фасад, какие модули разделить;
  - пригодно как чек-лист для следующего рефакторинга.
- **Architecture Evolution Analysis** — динамика во времени:
  - Version (из pyproject), Risk score (0–100), Git hash (если репозиторий);
  - тренды сложности / централизации / smells;
  - регрессии (включая рост god_module, bottleneck, hub по отдельности);
  - `Maturity (dynamic)` — ощущение траектории: улучшается архитектура или деградирует.

