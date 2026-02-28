# Зависимости Eurika

Документация по внешним библиотекам проекта.

## Основные (optional-dependencies)

| Группа | Пакеты | Назначение |
|--------|--------|------------|
| **llm** | openai, litellm | LLM-провайдеры: OpenAI, Ollama, OpenRouter, Anthropic и др. |
| **env** | python-dotenv | Загрузка `.env` (ключи API, настройки) |
| **test** | pytest | Тесты |
| **qt** | PySide6 | Desktop Qt UI |
| **typecheck** | mypy | Статическая типизация |

## Расширения (интеграция v3.0.13+)

| Группа | Пакеты | Назначение |
|--------|--------|------------|
| **refactor** | libcst | Round-trip AST: изменение кода с сохранением комментариев и форматирования. Используется в `remove_unused_import` (остальные рефакторинги — по мере внедрения). |
| **cli** | rich | Прогресс-бары, таблицы, подсветка, spinner'ы в CLI (doctor heartbeat, scan/doctor/fix). |
| **extras** | pydantic, watchdog, ruff, structlog, ollama | Валидация данных, file watcher, линт, структурированный лог, Ollama Python-клиент. |

## Установка

```bash
# Минимальная (CLI без LLM)
pip install -e ".[test]"

# С LLM и Qt
pip install -e ".[test,qt]"

# Полная (все расширения)
pip install -e ".[test,qt,refactor,cli,extras]"
# или
pip install -e ".[full]"
```

## Использование в коде

- **libcst** — fallback на stdlib `ast` при отсутствии; см. `eurika.refactor._ast_backend`.
- **litellm** — при наличии используется в `eurika.reasoning.architect` вместо цепочки openai→ollama.
- **rich** — при наличии используется для doctor heartbeat и CLI-вывода; fallback на обычный `print`.
- **pydantic** — для валидации API/данных (ввод по мере надобности).
- **watchdog** — для live-обновления Dashboard при сохранении файлов (планируется).
- **ruff** — уже вызывается в `_execute_run_lint`; используется для check/fix.
- **structlog** — опционально для структурированного логирования.
- **ollama** — опциональный Python-клиент Ollama вместо subprocess.
