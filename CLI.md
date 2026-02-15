# Eurika CLI — Справочник команд

Полный перечень команд и аргументов.

---

## Рекомендуемый цикл (по review.md и ROADMAP)

Целевой поток — от анализа к действию, а не только к отчётам:

```
Scan → Diagnose → Plan → Patch → Verify → Log
```

| Шаг | Команда | Назначение |
|-----|---------|------------|
| **Всё сразу** | `eurika cycle .` | scan → doctor → fix одной командой |
| Scan | `eurika scan .` | Обновить self_map, smells, summary, history |
| Diagnose | `eurika doctor .` или `eurika report .` + `eurika suggest-plan .` | Отчёт + интерпретация + план рефакторинга |
| Plan | `eurika fix . --dry-run` или `eurika agent patch-plan .` | Построить план патчей без применения |
| Patch | `eurika fix .` или `eurika agent patch-apply . --apply` | Применить патчи (с бэкапами) |
| Verify | встроено в `eurika fix` (pytest после apply) | pytest; при провале — подсказка rollback; при ухудшении метрик — автоматический откат |
| Log | автоматически (events, history) | Исходы записываются в `.eurika/events.json`, architect получает recent_events |

**Продуктовые режимы (5):** **scan**, **doctor**, **fix**, **cycle**, **explain**. В `eurika help` выводятся первыми.

---

## Обзор

```bash
eurika [--help] [--version]
eurika <command> [path] [options]
eurika agent <subcommand> [path] [options]
```

- `eurika` (без аргументов) — выводит краткий обзор и справку.
- `eurika --version`, `eurika -V` — версия.
- По умолчанию `path` = `.` (текущий каталог).

**Продуктовые команды (5 режимов):** `scan`, `doctor`, `fix`, `cycle`, `explain`. В `eurika help` они выводятся первыми; остальные команды — Other/Advanced (ROADMAP этап 5).

**Для LLM (doctor, architect, cycle):** запускайте через venv из `/mnt/storage/project/` (см. DOGFOODING.md). Без него — только шаблонный вывод architect.

---

## Product modes

### eurika scan [path]

Полный скан: обновление self_map, smells, summary, history. Основа для doctor/fix.

```bash
eurika scan .
```

---

### eurika doctor [path] [--window N] [--no-llm]

Только диагностика: report (summary + evolution) и интерпретация architect. Патчи не предлагаются и не применяются. **Отчёт сохраняется в `eurika_doctor_report.json`** (summary, history, architect, patch_plan).

**Опции:** `--window N` (размер окна истории), `--no-llm` (architect по шаблону, без LLM).

```bash
eurika doctor .
eurika doctor . --no-llm
```

---

### eurika fix [path] [--window N] [--dry-run] [--quiet] [--no-clean-imports]

Полный цикл: scan → arch-review → patch-apply --apply --verify. **По умолчанию** план fix включает операции **remove_unused_import** (clean-imports) для файлов с неиспользуемыми импортами; затем — архитектурные патчи (remove_cyclic_import, split_module и т.д.). Эквивалент `eurika agent cycle` с применением патчей и проверкой тестами. После apply запускается **pytest**; для верификации нужен установленный pytest: `pip install pytest` или `pip install -e ".[test]"`. **Отчёт сохраняется в `eurika_fix_report.json`** (при apply — полный; при `--dry-run` — `dry_run: true` + `patch_plan`).

**Опции:** `--window N`, `--dry-run` (только план, без apply; сохраняет eurika_fix_report.json), `--quiet` / `-q` (минимальный вывод, итог в JSON), `--no-clean-imports` (исключить remove_unused_import из плана), `--interval SEC` (авто-повтор каждые SEC секунд, 0=один раз; Ctrl+C для остановки).

```bash
eurika fix .
eurika fix . --dry-run
eurika fix . -q
eurika fix . --no-clean-imports
```

---

### eurika cycle [path] [--window N] [--dry-run] [--quiet] [--no-llm] [--no-clean-imports]

Полный ритуал одной командой: **scan → doctor (report + architect) → fix**. Сначала scan, затем вывод полной диагностики (summary, evolution, architect), затем fix (patch-apply --apply --verify). Fix по умолчанию включает remove_unused_import; architect при cycle получает recent_events (последние patch/learn) в контексте.

**Опции:** `--window N`, `--dry-run` (doctor + plan, без apply), `--quiet` / `-q`, `--no-llm` (architect по шаблону, без API-ключа), `--no-clean-imports` (исключить clean-imports из fix), `--interval SEC` (авто-повтор каждые SEC секунд; Ctrl+C для остановки).

### eurika watch [path] [--poll SEC] [--quiet] [--no-clean-imports]

Мониторинг .py файлов: при изменении (mtime) запускает fix. Опрос каждые `--poll` секунд (default 5). Ctrl+C для остановки. ROADMAP 2.6.2.

```bash
eurika cycle .
eurika cycle . --dry-run --no-llm
eurika cycle . -q
eurika cycle . --no-clean-imports
```

---

### eurika explain <module> [path] [--window N]

Роль и риски модуля в графе. См. секцию ниже. Опция `--window N` — окно для patch-plan.

---

## CI/CD

Команды `eurika fix` и `eurika cycle` возвращают **exit code 0** при успехе, **1** при ошибке (scan failed, verify failed, metrics worsened + rollback). Подходят для CI.

**Рекомендуемые команды для CI:**

| Сценарий | Команда | Описание |
|----------|---------|----------|
| Применить фиксы и проверить | `eurika fix . --quiet` | scan → plan → apply → verify; минимум вывода; exit 1 при провале pytest или ухудшении метрик |
| Только план (dry-run) | `eurika fix . --dry-run --quiet` | Построить план без применения; exit 0; для проверки «что было бы сделано» |
| Полный ритуал без LLM | `eurika cycle . --quiet --no-llm` | scan → doctor (шаблон) → fix; не требует OPENAI_API_KEY |

**Требования:** `pip install pytest` для verify. Артефакты: `eurika_fix_report.json`, `.eurika/`.

---

## Core commands

### eurika scan [path] (подробно)

Полный сценарий: сканирование, smells, summary, рекомендации, evolution, health, observation memory.

**Артефакты:** `self_map.json`, `.eurika/history.json`, `.eurika/observations.json`, `.eurika/events.json`

**Опции v0.7:**
- `--format`, `-f` — `text` (по умолчанию) или `markdown`
- `--color` — принудительно включить ANSI-цвета
- `--no-color` — отключить цвета

```bash
eurika scan .
eurika scan /path/to/project
eurika scan . -f markdown
eurika scan . --no-color
```

---

### eurika arch-summary [path]

Только архитектурный summary по текущему `self_map.json`. Читает существующие артефакты (не обновляет).

```bash
eurika arch-summary .
```

---

### eurika arch-history [path] [--window N]

Evolution report из `.eurika/history.json`: тренды, регрессии, maturity, version, risk score.

```bash
eurika arch-history .
eurika arch-history . --window 10
```

---

### eurika arch-diff old.json new.json

Сравнение двух снапшотов `self_map.json`: структурные изменения, centrality shifts, smell dynamics, maturity.

```bash
eurika arch-diff self_map_old.json self_map_new.json
```

---

### eurika self-check [path]

Ритуал самоанализа — полный scan. Рекомендуется выполнять из корня проекта после рефакторинга.

**Опции v0.7:** те же, что у `scan` — `--format`, `--color`, `--no-color`.

```bash
eurika self-check .
eurika self-check . -f markdown
```

---

### eurika help

Краткий обзор команд и детальная справка argparse.

```bash
eurika help
```

---

### eurika report [path] [--json] [--window N]

Summary + evolution report без повторного сканирования. С флагом `--json` — вывод в JSON.

```bash
eurika report .
eurika report . --json --window 5
```

---

### eurika explain <module> [path] [--window N]

Роль и риски модуля в графе (fan-in/fan-out, central, smells). Planned operations берутся из patch-plan (get_patch_plan с заданным окном).

**Опции:** `--window N` — окно истории для patch-plan (по умолчанию 5).

```bash
eurika explain architecture_diff.py
eurika explain cli/handlers.py .
eurika explain action_plan.py . --window 10
```

---

### eurika architect [path] [--window N] [--no-llm]

Интерпретация в стиле «архитектор проекта»: 2–4 предложения по summary и history. По умолчанию — шаблон; при заданных переменных окружения вызывается LLM (OpenAI или OpenRouter).

**Опции:**
- `--window N` — размер окна истории (по умолчанию 5)
- `--no-llm` — только шаблонная сводка, без вызова API

**Переменные окружения (опционально):**
- `OPENAI_API_KEY` — ключ API (обязателен для LLM)
- `OPENAI_BASE_URL` — для OpenRouter: `https://openrouter.ai/api/v1`
- `OPENAI_MODEL` — модель, например `mistralai/mistral-small-3.2-24b-instruct` или `gpt-4o-mini`

Переменные можно задать в `.env` в корне проекта; тогда нужен `pip install python-dotenv` (или `eurika[env]`). При ошибке LLM в stderr выводится причина и используется шаблон.

```bash
eurika architect .
eurika architect . --window 10
eurika architect . --no-llm
```

---

### eurika suggest-plan [path] [--window N]

Эвристический рефакторинг-план: нумерованный список шагов из summary/risks или из build_recommendations (если есть self_map.json). Без LLM.

**Опции:** `--window N` — окно истории для контекста (по умолчанию 5).

```bash
eurika suggest-plan .
eurika suggest-plan . --window 10
```

---

### eurika serve [path] [--port N] [--host HOST]

HTTP-сервер JSON API для будущего UI: GET `/api/summary`, `/api/history`, `/api/diff`. По умолчанию порт 8765, хост 127.0.0.1.

```bash
eurika serve .
eurika serve . --port 9000
```

---

## AgentCore commands (experimental)

### eurika agent arch-review [path] [--window N]

Агрегирует summary, history, observations в предложения: explain_risk, summarize_evolution, prioritize_modules, suggest_refactor_plan, suggest_action_plan, suggest_patch_plan.

```bash
eurika agent arch-review .
eurika agent arch-review . --window 5
```

---

### eurika agent arch-evolution [path] [--window N]

Эволюция архитектуры по `.eurika/history.json`.

```bash
eurika agent arch-evolution .
```

---

### eurika agent prioritize-modules [path] [--window N]

Печатает приоритизированный список модулей (JSON).

```bash
eurika agent prioritize-modules .
```

---

### eurika agent action-dry-run [path] [--window N]

Строит ActionPlan из диагностики, выводит без выполнения.

```bash
eurika agent action-dry-run .
```

---

### eurika agent action-simulate [path] [--window N]

ActionPlan + ExecutorSandbox.dry_run (логирование без изменения кода).

```bash
eurika agent action-simulate .
```

---

### eurika agent action-apply [path] [--no-backup] [--window N]

Строит ActionPlan и выполняет (добавляет TODO-блоки). Бэкапы по умолчанию.

```bash
eurika agent action-apply .
eurika agent action-apply . --no-backup
```

---

### eurika agent patch-plan [path] [-o FILE] [--window N]

Строит patch plan (рефакторинг по модулям). Выводит JSON или пишет в файл.

```bash
eurika agent patch-plan .
eurika agent patch-plan . -o patch.json
```

---

### eurika agent patch-apply [path] [--apply] [--verify] [--no-backup] [--window N]

Применяет patch plan. По умолчанию dry-run; `--apply` пишет в файлы; `--verify` запускает pytest после apply.

```bash
eurika agent patch-apply .
eurika agent patch-apply . --apply --verify
```

---

### eurika agent patch-rollback [path] [--run-id ID] [--list]

Восстанавливает файлы из `.eurika_backups/`. По умолчанию последний run.

```bash
eurika agent patch-rollback .
eurika agent patch-rollback . --list
eurika agent patch-rollback . --run-id 20260212_100319
```

---

### eurika agent cycle [path] [--window N] [--dry-run] [--quiet]

Полный цикл: scan → arch-review → patch-apply --apply --verify. При успехе — rescan и `rescan_diff`.

```bash
eurika agent cycle .
eurika agent cycle . --dry-run   # только patch-plan, без apply
eurika agent cycle . -q          # только итоговый JSON на stdout
```

---

### eurika agent learning-summary [path]

Статистика по patch-apply + verify: `by_action_kind`, `by_smell_action`.

```bash
eurika agent learning-summary .
```

---

### eurika agent feedback-summary [path]

Статистика по ручному фидбеку (события type=feedback в `.eurika/events.json`).

```bash
eurika agent feedback-summary .
```

---

## Артефакты

| Файл | Описание |
|------|----------|
| `self_map.json` | Модули, строки, зависимости |
| `.eurika/events.json` | Единый журнал событий (scan, patch, learn, feedback) — ROADMAP 3.2 |
| `.eurika/history.json` | История снимков, version, risk_score |
| `.eurika/observations.json` | Журнал наблюдений scan |
| `eurika_fix_report.json` | Отчёт fix (modified, skipped, rescan_diff, verify) — по умолчанию |
| `eurika_doctor_report.json` | Отчёт doctor (summary, history, architect, patch_plan) — по умолчанию |
| `.eurika_backups/<run_id>/` | Бэкапы при patch-apply --apply |
