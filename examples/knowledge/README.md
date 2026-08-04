# Knowledge Layer — примеры (Eurika)

Пакет примеров для Knowledge Layer: Python API, HTTP endpoint, конфиг локального кэша.

## Структура

| Файл | Описание |
|------|----------|
| `01_python_get_knowledge.py` | Прямой вызов `get_knowledge(project_root, topic)` |
| `02_curl_knowledge.sh` | curl-запросы к GET /api/knowledge |
| `eurika_knowledge.variant.json` | Вариант локального кэша (расширенный набор тем) |

## 1. Python API

```bash
# Из корня проекта
.venv/bin/python examples/knowledge/01_python_get_knowledge.py .

# Или с указанием темы
.venv/bin/python examples/knowledge/01_python_get_knowledge.py . --topic cyclic_imports
```

Импорт: `from eurika.api import get_knowledge`

## 2. HTTP endpoint (eurika serve)

```bash
# Запустить сервер
eurika serve .

# В другом терминале — curl (порт по умолчанию 8765)
bash examples/knowledge/02_curl_knowledge.sh
```

## 3. Локальный кэш (eurika_knowledge.json)

Скопируйте `eurika_knowledge.variant.json` или `docs/eurika_knowledge.example.json` в корень проекта как `eurika_knowledge.json` и при необходимости отредактируйте темы.

Подробнее: **docs/KNOWLEDGE_LAYER.md**
