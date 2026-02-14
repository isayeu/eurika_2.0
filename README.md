# Eurika 2.0

**Architecture Awareness Engine** — анализ кода и архитектуры, планирование рефакторинга, применение патчей с бэкапами и учётом прошлого опыта. Целевой цикл: *scan → diagnose → plan → patch → verify → learn* (команда `eurika fix`).

*Требования: Python 3.9+.* Для проверки после `eurika fix` нужен pytest: `pip install pytest` или `pip install -e ".[test]"`.

## Быстрый старт

```bash
python eurika_cli.py scan .
```

or, after `pip install -e .`:

```bash
eurika scan .
```

**Pipeline:** `cli → core/pipeline → code_awareness → scan → graph → smells → summary → history → report`

## Режимы (продуктовые)

- **`eurika scan [path]`** — полный скан и обновление артефактов.
- **`eurika doctor [path]`** — только диагностика: report + architect (без патчей). Опции: `--window N`, `--no-llm`.
- **`eurika fix [path]`** — полный цикл: scan → plan → patch-apply --apply --verify. Опции: `--window N`, `--dry-run`, `--quiet`.
- **`eurika explain <module> [path]`** — роль и риски модуля.

## CLI commands

### Core

- **`eurika scan [path]`**: полный сценарий — сканирование, smells, summary, рекомендации, history, observation memory. Каталог `.eurika_backups` исключён из анализа.
- **`eurika doctor [path]`**: диагностика без патчей (report + architect). Опции: `--window N`, `--no-llm`.
- **`eurika fix [path]`**: полный цикл исправлений (scan → plan → apply → verify). Опции: `--window N`, `--dry-run`, `--quiet`.
- **`eurika arch-summary [path]`**: только архитектурный summary по текущему `self_map.json`.
- **`eurika arch-history [path]`**: выводит последний `Architecture Evolution Analysis` из `architecture_history.json`.
- **`eurika history [path]`**: алиас для arch-history.
- **`eurika report [path]`**: summary + evolution report (без повторного сканирования). Опции: `--json`, `--window N`.
- **`eurika explain <module> [path]`**: роль и риски модуля в графе.
- **`eurika architect [path]`**: интерпретация в стиле «архитектор проекта» (2–4 предложения). По умолчанию — шаблон; при заданных переменных окружения вызывается LLM (OpenAI или OpenRouter). Опции: `--window N`, `--no-llm`.
- **`eurika suggest-plan [path]`**: эвристический рефакторинг-план по summary и рискам (или по build_recommendations при наличии self_map). Опция: `--window N`.
- **`eurika arch-diff old.json new.json`**: сравнивает два снапшота `self_map.json`. Опция `--json`.
- **`eurika serve [path]`**: HTTP JSON API (GET /api/summary, /api/history, /api/diff). Опции: `--port`, `--host`.

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
- **Architecture History**: тренды, dynamic maturity, version (pyproject), risk score (0–100), опционально git hash (`architecture_history.json`).
- **Action Plan / Patch Plan**: приоритизация модулей и план рефакторинга (read-only).
- **Patch Engine** (`patch_engine.py`): фасад apply_and_verify (применить план + pytest) и rollback; используется в `eurika fix` и `eurika agent patch-apply --apply --verify`.
- **Patch Apply**: применение patch plan с бэкапами в `.eurika_backups/<run_id>/`, опционально `--verify` (pytest).
- **Patch Rollback**: восстановление из бэкапа.
- **Learning Loop**: после `patch-apply --apply --verify` записываются исходы в `architecture_learning.json`; при следующих arch-review/action-dry-run прошлые success rate используются для коррекции expected_benefit (`learned_signals`).

## Документация

- **review.md** — технический разбор версии 2.0 и направление 2.1 (Patch Engine, Event, инженерный путь)
- **Architecture.md** — структура системы, замкнутый цикл, Patch Engine, оценка по review
- **CLI.md** — полный справочник команд и рекомендуемый цикл
- **ROADMAP.md** — план задач, блок «Версия 2.1 (по review.md)»
- **REPORT.md** — краткий статус и фокус по review
- **SPEC.md** — контракт проекта (v0.1–v0.4)
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

