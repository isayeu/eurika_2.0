# Dogfooding — полный цикл на самом Eurika

Ритуал: прогнать продуктовый цикл на корне проекта Eurika, чтобы проверить работу инструмента на своей кодовой базе.

## Где venv

**Venv для этого проекта:** `/mnt/storage/project/venv` (или `/mnt/storage/project/.venv`). Без него **LLM не работает** (doctor/architect с OPENAI_API_KEY). Для verify при `eurika fix` тоже нужен этот Python (pytest и зависимости проекта).

Скан исключает каталоги `venv`, `.venv`, `node_modules` из анализа.

## Шаги

Из **корня репозитория** `eurika_2.0` (где лежит `eurika_cli.py`, `eurika/`, `cli/`):

```bash
# Использовать venv из родительского каталога (иначе LLM не работает)
PY=/mnt/storage/project/venv/bin/python

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
source /mnt/storage/project/venv/bin/activate
eurika scan .
eurika doctor .
eurika fix . --dry-run
```

После `eurika fix .` (без --dry-run) запускается **pytest** для верификации; при провале тестов выполняется автоматический откат.

## Использование на других проектах

Проекты в `/mnt/storage/project` (farm_helper, optweb, dartopt и др.) можно анализировать, передавая путь:

```bash
source /mnt/storage/project/venv/bin/activate
eurika scan /mnt/storage/project/optweb
eurika doctor /mnt/storage/project/optweb
eurika fix /mnt/storage/project/optweb --dry-run
```

Нужны права на запись в целевой каталог (создаются `self_map.json`, `architecture_history.json`, отчёты).

## Knowledge Layer (doctor)

В корне Eurika лежит **eurika_knowledge.json** (копия примера из docs/): при `eurika doctor .` фрагменты по теме `python` (или `EURIKA_KNOWLEDGE_TOPIC`) подставляются в вывод архитектора (блок «Reference»). Без файла поведение как раньше.

## Результаты прогона (пример)

- **scan:** обновляются `self_map.json`, `architecture_history.json`, выводятся summary, smells, evolution.
- **doctor:** создаётся `eurika_doctor_report.json` (summary, history, architect, patch_plan). С eurika_knowledge.json — в architect есть Reference.
- **fix --dry-run:** создаётся `eurika_fix_report.json` с `dry_run: true` и `patch_plan`; файлы не меняются.

## Артефакты и Git

Артефакты (`self_map.json`, `eurika_doctor_report.json`, `eurika_fix_report.json`, `eurika_knowledge.json`, `.eurika_backups/`, `.eurika/` — в т.ч. `knowledge_cache` для сетевых ответов) — генерируемые, в `.gitignore`. Не коммитить.
