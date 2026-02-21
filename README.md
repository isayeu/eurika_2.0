# Eurika 2.0

**Architecture Awareness Engine** — анализ кода и архитектуры, планирование рефакторинга, применение патчей с бэкапами и учётом прошлого опыта. Целевой цикл: *scan → diagnose → plan → patch → verify → learn* (команда `eurika fix`).

*Требования: Python 3.9+.* Для проверки после `eurika fix` нужен pytest: `pip install pytest` или `pip install -e ".[test]"`.

**Текущий фокус (по review):** переход от «архитектурного аналитика» к «инженерному инструменту» — полноценный Patch Engine (apply/verify/rollback), автофиксы, единый Event Engine. Детали — в **review.md** и **ROADMAP.md**.

## Быстрый старт

После `pip install -e .`:

```bash
eurika scan .           # полный скан → self_map.json, smells, summary
eurika doctor .         # диагностика (report + architect) без патчей
eurika fix . --dry-run  # план рефакторинга без применения
eurika serve .          # Web UI на http://127.0.0.1:8765/
```

Или напрямую: `python eurika_cli.py scan .`.

**Для LLM (doctor, architect, cycle):** в venv установите `pip install -e ".[test]"` (включает openai, pytest). Без openai LLM не вызывается — вывод шаблонный. Подробнее — **DOGFOODING.md**.

**Ollama (локальный LLM):** для architect/cycle с ollama запустите сервер, при необходимости с переменными для AMD GPU:
```bash
HSA_OVERRIDE_GFX_VERSION=10.3.0 ROCR_VISIBLE_DEVICES=0 HIP_VISIBLE_DEVICES=0 ollama serve
```

**Pipeline:** `cli → core/pipeline → code_awareness → scan → graph → smells → summary → history → report`

## Режимы (продуктовые)

- **`eurika scan [path]`** — полный скан и обновление артефактов.
- **`eurika doctor [path]`** — только диагностика: report + architect (без патчей). Опции: `--window N`, `--no-llm`. При наличии `eurika_knowledge.json` темы подбираются по диагнозу (всегда `python`; при циклах — `cyclic_imports`; при god/hub — `architecture_refactor`) или задаются через `EURIKA_KNOWLEDGE_TOPIC` (см. **docs/KNOWLEDGE_LAYER.md**).
- **`eurika fix [path]`** — полный цикл: scan → plan → patch-apply --apply --verify. Опции: `--window N`, `--dry-run`, `--quiet`, `--no-clean-imports`.
- **`eurika cycle [path]`** — ритуал одной командой: scan → doctor (report + architect) → fix. Опции: `--window N`, `--dry-run`, `--quiet`, `--no-llm`, `--no-clean-imports`.

**CI:** `eurika fix . --quiet` — exit 0 при успехе, 1 при провале verify или ошибках. См. CLI.md § CI/CD.
- **`eurika explain <module> [path]`** — роль и риски модуля.
- **`eurika serve [path]`** — Web UI: Dashboard, Summary, History, Diff, Graph, Approve, Explain, Terminal, Ask Architect, Chat. См. **UI.md**.

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
- **`eurika serve [path]`**: Web UI + JSON API (Dashboard, Chat, Graph, /api/summary, /api/history и др.). Опции: `--port`, `--host`.
- **`eurika learn-github [path]`**: клонирует curated OSS (Django, FastAPI и др.) в `../curated_repos/` (рядом с проектом); `--scan` — scan после clone (ROADMAP 3.0.5.1).

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

## Документация

- **UI.md** — Web UI: запуск `eurika serve`, вкладки (Dashboard, Summary, History, Diff, Graph, Approve, Explain, Terminal, Ask Architect, Chat), JSON API
- **review.md** — разбор, диагноз зрелости, план прорыва (5 этапов)
- **ROADMAP.md** — план задач, оценка зрелости, «что не хватает», план прорыва, этапы до продуктовой 1.0
- **REPORT.md** — текущий статус, оценка по review, следующий шаг
- **Architecture.md** — структура системы, замкнутый цикл, Patch Engine (целевой API), направление 2.1
- **CLI.md** — справочник команд, рекомендуемый цикл
- **DOGFOODING.md** — ритуал полного цикла на самом Eurika (scan → doctor → fix), про venv
- **docs/KNOWLEDGE_LAYER.md** — Knowledge Provider Layer (контракт, формат `eurika_knowledge.json`, интеграция с doctor/architect). Пример: `docs/eurika_knowledge.example.json`.
- **SPEC.md** — контракт проекта (v0.1–v0.4), текущий фокус
- **THEORY.md** — идеология и философия Eurika

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

