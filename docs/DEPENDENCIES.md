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
| **energy** | numpy | EnergyModel (ROADMAP §5.7): Energy = W·MetricVector. Опционально для vectorized вычислений. |
| **torch** | torch>=2.1 | Опциональный ML runtime (scaffold CR-G3): probe + CPU smoke. **Не** замена LLM (Ollama/OpenAI) — работает **в связке** (маршрутизация/embeddings рядом с generate). **Не** входит в `full`. Learning loop от torch не зависит. См. [HARDWARE.md](HARDWARE.md). |

Binance (optional): `BINANCE_API_KEY` / `BINANCE_API_SECRET` / `BINANCE_TESTNET` in project `.env` (see `.env.example`). Loaded by `load_project_dotenv`. Read-only REST via stdlib (`eurika.integrations.binance_readonly` incl. spot `klines` + USD-M `futures_klines`); no extra pip package; no order placement. Paper ML: `eurika ml-market` → `.eurika/ml/`.

Remote lbot: SSH status via `eurika.integrations.remote_lbot` (`EURIKA_LBOT_SSH_HOST`, default `prodg` → `~/lbot`). BatchMode SSH + remote Python JSON; no paramiko dependency; read-only.

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

# С EnergyModel (numpy)
pip install -e ".[energy]"

# PyTorch scaffold (на 8 GB / старом драйвере — предпочтительно CPU wheel)
pip install -e ".[torch]"
# или явно:
# pip install torch --index-url https://download.pytorch.org/whl/cpu
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
- **numpy** — опционально для EnergyModel: dot(weights, metrics). Можно заменить на pure Python для малых векторов.
- **torch** — опционально: `eurika.ml.torch_runtime` (`torch_available`, `torch_status`, `run_smoke`). По умолчанию device=`cpu` (`EURIKA_TORCH_DEVICE`). Блок в `eurika self-check`. ML дополняет LLM (Models → LLM / ML), не заменяет generate.
