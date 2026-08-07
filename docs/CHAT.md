# Eurika Chat — команды и настройка

Справочник для вкладки **Chat** в `eurika-qt` и для `eurika.api.chat_send`.

Чат работает с **текущим Project root** (поле пути в Qt). Сменили каталог — все команды «про проект» относятся к новому пути.

## Два режима ответа

| Режим | Когда | Пример |
|-------|--------|--------|
| **Прямой обработчик** | Фраза совпала с intent → ответ без LLM, мгновенно | «что за проект?», «покажи дерево» |
| **LLM** | Свободный вопрос, объяснение, код | «почему модуль X связан с Y?» |

Прямые ответы предпочтительны для фактов о проекте: они не галлюцинируют и не зависят от модели.

**Связка ML + LLM (опционально):** `EURIKA_USE_ML_INTENT=1` — после YAML/прямых фактов маленький PyTorch-роутер (`eurika.ml.intent_router`) предлагает handler или «в LLM». Веса: `.eurika/ml/weights/intent_router.pt`. YAML-интенты всегда главнее.

**Отправка в Qt:** кнопка Send или **Ctrl+Enter** (Enter — новая строка). Пока идёт запрос к LLM — подсказка «Eurika печатает…» и кнопка **Cancel** (ответ не попадёт в историю; Ollama может ещё доработать в фоне).

---

## Команды без LLM (прямые интенты)

### Приветствие и справка

| Фраза | Действие |
|-------|----------|
| `привет`, `здравствуй`, `hello` | Краткое приветствие |
| `ты кто?` / вопросы «кто написал / создал / автор …» | Идентичность Eurika (+ создатель ProDG) |
| `что ты умеешь?`, `помощь`, `справка`, `help` | Полный список возможностей |

### Проект на диске

| Фраза | Действие |
|-------|----------|
| `что за проект?`, `какой проект открыт?` | Обзор: тип, файлы, scan (self_map.json) |
| `что дальше по развитию?`, `просмотри roadmap` | Выжимка из `docs/ROADMAP.md` (фокус, следующие шаги) |
| `сколько файлов?`, `пересчитай файлы`, `сколько всего там файлов?` | Подсчёт файлов с диска |
| `покажи дерево`, `структуру проекта`, `покажи структуру` | Дерево каталогов |
| `какие документы по проекту?`, `покажи документацию` | README, docs/, notes/, .eurika/rules |
| `выполни ls`, `ls` | Список в корне проекта |
| `покажи файл app.py` | Содержимое файла |

### Анализ Eurika

| Фраза | Действие |
|-------|----------|
| `просканируй проект` | `eurika scan .` |
| `покажи отчёт`, `doctor report` | Отчёт doctor |
| `какая цель?`, `что в контексте?` | Статус active_goal / pending / last run |
| `что получилось?`, `итог цели` | Reflection: цель + last_execution (без LLM) |
| `сбрось цель`, `clear goal` | Очистить active_goal + pending_clarification + last_execution (не HITL Apply) |
| `проведи ритуал` | scan → doctor → report-snapshot |
| `прогони release check` | `./scripts/release_check.sh` |
| `проведи smoke test`, `smoke` | Быстрый smoke: PyTorch + Qt pytest (без LLM) |
| `проведи self-check` | `eurika self-check .` |
| `включи EURIKA_USE_ML_INTENT=1` | Записать флаг в `.env`, обучить chat-роутер |
| `выключи EURIKA_USE_ML_INTENT` | Выключить ML-роутер |
| `проверь включен ли ML_INTENT`, `статус EURIKA_USE_ML_INTENT` | Показать флаг / `.env` / acc роутера |
| `проверь статус ML`, `статус ML` | Сводка: PyTorch + ML_INTENT + VECTOR + Market learning |
| `включен ли VECTOR_INTENT` | Статус `EURIKA_USE_VECTOR_INTENT` |
| `включи EURIKA_USE_VECTOR_INTENT=1` | Fuzzy embeddings (нужен `nomic-embed-text`) |
| вопрос про тикеры / общую модель market ML | Прямой ответ из кода (без LLM) |

### Git

| Фраза | Действие |
|-------|----------|
| `собери коммит`, `git status` | Статус и предложение сообщения |
| `применяй` | Подтверждение pending-плана или коммита |

### Интернет

| Фраза | Действие |
|-------|----------|
| `поищи в интернете …`, `погугли …`, `web search …` | Веб-поиск (см. § Env ниже) |

**Не путать:** `найди документы по проекту` — локальный поиск в каталоге, не интернет.

### Рискованные действия (через интерпретатор)

Требуют подтверждения `применяй`:

- `рефактори …`, `eurika fix`
- `сохрани в …`, `создай файл …`
- `удали файл …`
- `выполни команду …` (shell)

---

## LLM-провайдеры (Models + `.env`)

Настройка во вкладке **Models** или в `.env` в корне проекта Eurika / открытого проекта.

| Переменная | Назначение |
|------------|------------|
| `EURIKA_CHAT_PROVIDER` | `auto` \| `ollama` \| `openai` \| `codex` — маршрутизация чата |
| `OPENAI_API_KEY` | Ключ OpenAI / совместимого API |
| `OPENAI_MODEL` | Модель (например `gpt-4o-mini`, `gpt-5-codex`) |
| `OPENAI_BASE_URL` | Базовый URL API (по умолчанию OpenAI) |
| `OLLAMA_OPENAI_BASE_URL` | Ollama OpenAI-совместимый endpoint (обычно `http://127.0.0.1:11434/v1`) |
| `OLLAMA_OPENAI_MODEL` | Имя модели Ollama (должна быть установлена: `ollama pull …`) |
| `OLLAMA_OPENAI_API_KEY` | Для Ollama часто `ollama` |
| `EURIKA_OLLAMA_CLI_TIMEOUT_SEC` | Таймаут CLI Ollama, сек. (по умолчанию `120`; CPU-модели медленные) |
| `EURIKA_OLLAMA_PROGRESS` | `1` / `0` — спиннер прогресса в терминале при Ollama CLI |

**Поведение `auto`:** при наличии `OPENAI_API_KEY` — OpenAI API; иначе Ollama. `codex` — только OpenAI API, без fallback на Ollama.

Таймаут чата в Qt задаётся на вкладке Models (поле timeout, по умолчанию 120 с).

### Binance (опционально)

| Переменная | Назначение |
|------------|------------|
| `BINANCE_API_KEY` | API key (не коммитить; шаблон — `.env.example`) |
| `BINANCE_API_SECRET` | API secret |
| `BINANCE_TESTNET` | `1` = testnet; `0` = mainnet (default) |

Ключи в `.env` + read-only probe (`eurika.integrations.binance_readonly`): ping, ticker, балансы без ордеров. `eurika self-check` печатает блок **BINANCE (read-only)**. Live-ордера не подключены.

**Qt Chat:** подвкладки **Агент** (архитектура/LLM; полоска режимов) и **Market** (live paper). Market: Live paper / Авто / **Исследование** (авто-стоп после N live-меток, по умолчанию 80; 0 = без лимита) / **Spot|Futures|Both** / **два списка тикеров** (Spot и Futures независимо, +/−; кнопка **Заполнить spot** из балансов — разово) / **Сброс сирот** (убрать opens вне списков) / свечи `15m`/`1h`, горизонт (при сильном ATR-burst/range-break авто-удлинение до 4) / **1m** (вход market/limit/stop/OCO; **TP/SL/trail ставит ML** `market_levels.pt`, спины UI = потолок; выход TP/SL/трейлинг/горизонт/модель). Лента событий цветная по типу (сделка / итог / анализ / исследование / ошибка) + подсветка ПОКУПКА/ПРОДАЖА и удача/неудача. Свечи spot/futures хранятся раздельно; entry `market_policy.pt` + exit `market_exit.pt` + levels `market_levels.pt`. Статус ML — live/opens с разбивкой spot/fut и **PnL Σ edge** (всего / live / сессия с вкл. Live); статус Market показывает `live/cap` и PnL сессии. Idle без событий — тихо. Ордера на биржу не уходят. Прогресс: **Models → ML**.

Рабочий торговый бот — **не локальный**, а на сервере `prodg.winex.org` (`~/lbot`, SSH host `prodg`). Статус: `eurika.integrations.remote_lbot` / блок **LBOT (remote read-only)** в self-check (процесс, tmux, open trades, хвост лога; без start/stop/ордеров).

---

## Веб-поиск

| Переменная | Назначение |
|------------|------------|
| `EURIKA_WEB_SEARCH` | `1` (вкл.) / `0` (выкл.) |
| `EURIKA_WEB_SEARCH_PROVIDER` | `auto` \| `duckduckgo` \| `tavily` \| `brave` |
| `TAVILY_API_KEY` | [Tavily](https://tavily.com) — приоритет в `auto` |
| `BRAVE_SEARCH_API_KEY` | Brave Search API — второй приоритет |

**`auto`:** Tavily → Brave → DuckDuckGo (без ключа).

Пример `.env`:

```env
TAVILY_API_KEY=tvly-...
# или
BRAVE_SEARCH_API_KEY=BSA...
```

---

## Дополнительные переменные чата

| Переменная | Назначение |
|------------|------------|
| `EURIKA_USE_VECTOR_INTENT` | `1` — fuzzy-match интентов по embeddings (CR-G2) |
| `EURIKA_USE_ML_INTENT` | `1` — tiny PyTorch-роутер handler/LLM (CR-G3). В чате: «включи EURIKA_USE_ML_INTENT=1» |
| `EURIKA_TORCH_DEVICE` | `cpu` (default) или `cuda`/`mps` если доступны; scaffold `eurika.ml` (ML **рядом** с LLM, не вместо) |
| `EURIKA_CHAT_METRICS` | `1` (default) — писать `.eurika/chat_metrics.jsonl` (`intent_match` / `intent_miss`) |
| `EURIKA_VECTOR_MIN_SIM` | Порог cosine similarity (0.68–0.85, default из config) |
| `EURIKA_KNOWLEDGE_TTL` | TTL кэша Knowledge в промпте, сек. (default 86400) |

---

## Кастомизация интентов

Дефолтные паттерны встроены в код (`eurika/api/chat_intents_default.py`) и работают для **любого** открытого проекта.

Переопределение — файл проекта:

```
.eurika/config/chat_intents.yaml
```

Пример и полный список workflow-интентов: `docs/chat_intents.example.yaml`.

Правила слияния:

- intent в YAML **заменяет** дефолтный intent с тем же id;
- `intent_id: null` — отключает дефолт;
- `intent_hints` — подсказки для LLM в system prompt.

---

## @-mentions (scope)

В свободном чате можно сузить контекст:

```
рефактори @patch_engine.py с учётом @god_module
```

Подробнее: [UI.md](UI.md) § Chat @-mentions.

---

## Обратная связь

Кнопки **Полезно** / **Не то** на вкладке Chat пишут в `.eurika/chat_feedback.json` и используются как few-shot в промпте LLM.

---

## Связанные документы

| Документ | Содержание |
|----------|------------|
| [UI.md](UI.md) | Вкладки Qt, тема, Chat UX |
| [CLI.md](CLI.md) | `eurika scan`, `doctor`, `fix` |
| [chat_intents.example.yaml](chat_intents.example.yaml) | Пример конфига интентов |
| [KNOWLEDGE_LAYER.md](KNOWLEDGE_LAYER.md) | Curated knowledge (не произвольный web search) |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Ollama, timeout, self_map missing |
