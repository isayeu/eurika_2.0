# Dogfooding — полный цикл на самом Eurika

Ритуал: прогнать продуктовый цикл на корне проекта Eurika, чтобы проверить работу инструмента на своей кодовой базе.

## Где venv

**Рекомендуемый venv для этого репозитория:** `.venv` (symlink в корне проекта).

Пример:

```bash
source .venv/bin/activate
```

или без активации:

```bash
.venv/bin/python -m eurika_cli scan .
.venv/bin/pytest tests/ -q
```

Скан исключает каталоги `venv`, `.venv`, `node_modules` из анализа.

**Runtime modes (ROADMAP 2.7):** `--runtime-mode assist` (default, все ops применяются), `hybrid` (approve/reject для review), `auto` (policy deny для high-risk). `--non-interactive` для CI (hybrid без stdin).

## Шаги

Из **корня репозитория** `eurika_2.0` (где лежит `eurika_cli.py`, `eurika/`, `cli/`):

```bash
# Использовать venv из корня проекта
PY=.venv/bin/python

# 1. Скан и обновление артефактов
$PY -m eurika_cli scan .

# 2. Диагностика (с LLM при OPENAI_API_KEY)
# При наличии eurika_knowledge.json в корне вывод архитектора включает блок Reference (Knowledge Layer).
$PY -m eurika_cli doctor .

# 3. План исправлений без применения
$PY -m eurika_cli fix . --dry-run

# 4. Полный цикл с применением и верификацией (опционально)
$PY -m eurika_cli fix .

# Альтернатива: один вызов scan → doctor → fix
$PY -m eurika_cli cycle .
```

Либо активировать venv и вызывать `eurika` как обычно:

```bash
source .venv/bin/activate
eurika scan .
eurika doctor .
eurika fix . --dry-run
```

После `eurika fix .` (без --dry-run) запускается **pytest** для верификации; при провале тестов выполняется автоматический откат.

## Telemetry (ROADMAP 2.7.8)

После `eurika fix .` (с apply) в `eurika_fix_report.json` появляются:
- `telemetry`: apply_rate, no_op_rate, rollback_rate, verify_duration_ms, median_verify_time_ms
- `safety_gates`: verify_required, verify_passed, rollback_done
- `report-snapshot .` выводит эти блоки

## Обновление CYCLE_REPORT.md после контрольного прогона

После изменения поведения или метрик:

1. Выполнить `eurika doctor .` и `eurika fix .` (или `eurika cycle .`).
2. Запустить `eurika report-snapshot .` — вывод в формате CYCLE_REPORT.
3. Вставить или обновить секции в `CYCLE_REPORT.md` (см. §1 Fix, §2 Doctor, §3 Learning).

## Использование на других проектах

Проекты в `/mnt/storage/project` (farm_helper, optweb, dartopt и др.) можно анализировать, передавая путь к **корню конкретного проекта**.

**Каталог `binance/`** — набор разных проектов и их версий (bbot, binance-trade-bot, binance_watchdog_bot, freqtrade, NostalgiaForInfinity и т.д.). Путь указывать на подпроект, а не на корень binance:

```bash
source .venv/bin/activate
eurika scan /mnt/storage/project/binance/bbot
eurika doctor /mnt/storage/project/binance/bbot
eurika fix /mnt/storage/project/binance/bbot --dry-run
```

Нужны права на запись в целевой каталог (создаются `self_map.json`, `architecture_history.json`, отчёты).

## Проекты без pytest

Если в проекте нет тестов, pytest возвращает returncode 5 ("no tests collected") и Eurika выполняет rollback. Варианты:

1. **Авто-fallback (v2.6.12+):** при returncode 5 и "no tests" Eurika запускает `python -m py_compile` по изменённым файлам — проверка синтаксиса вместо тестов. Rollback не выполняется, если py_compile прошёл.

2. **Явно указать команду верификации:**
```bash
eurika fix /path/to/project --verify-cmd "python -m py_compile"
```

3. **В корне проекта** создать или дополнить `pyproject.toml`:
```toml
[tool.eurika]
verify_cmd = "python -m py_compile"
```

## Knowledge Layer (doctor)

В корне Eurika лежит **eurika_knowledge.json** (копия примера из docs/): при `eurika doctor .` фрагменты по теме `python` (или `EURIKA_KNOWLEDGE_TOPIC`) подставляются в вывод архитектора (блок «Reference»). Без файла поведение как раньше.

## Результаты прогона (пример)

- **scan:** обновляются `self_map.json`, `architecture_history.json`, выводятся summary, smells, evolution.
- **doctor:** создаётся `eurika_doctor_report.json` (summary, history, architect, patch_plan). С eurika_knowledge.json — в architect есть Reference.
- **fix --dry-run:** создаётся `eurika_fix_report.json` с `dry_run: true` и `patch_plan`; файлы не меняются.

## Артефакты и Git

Артефакты (`self_map.json`, `eurika_doctor_report.json`, `eurika_fix_report.json`, `.eurika_backups/`, `.eurika/` — в т.ч. `knowledge_cache`) — генерируемые, в `.gitignore`. Не коммитить.

Дополнительно: не коммитить локальные окружения и IDE-артефакты (`.venv/`, `.cursor/`).
