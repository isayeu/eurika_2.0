# Eurika Chat — команды и настройка

Справочник для вкладки **Chat** в `eurika-qt` и для `eurika.api.chat_send`.

Чат работает с **текущим Project root** (воркспейс, как папка в Cursor) и выбранным **чатом** в левой рейке. **Новый чат** открывает диалог каталога; **+** у корня — новый тред в этом root; ПКМ по чату — переименовать/удалить.

## Два режима ответа

| Режим | Когда | Пример |
|-------|--------|--------|
| **Прямой обработчик** | Узкий ритуал / HITL (scan, ritual, коммит→применяй, …) | «проведи ритуал» |
| **Голая shell-строка** | Сообщение целиком — команда (`pwd`, `sudo whoami`, `ls -la`), без русского текста и без «покажи пример…» | `sudo whoami` → запуск + диалог sudo |
| **Локальный coding-agent** | Правки кода / layout UI (вкладка Models, боковая панель воркспейсов, IMPLEMENT) | Qt: очередь в **Approvals** (автофокус при `approvalsQueued>0`). Без agent HTTP — явная ошибка, не fallback в обычный chat. |

Прямые ответы — для ритуалов и HITL. Списки файлов / дерево больше не шаблонизируются: тот же tool-loop, что и для host facts (A1 chat-first).

### Tool-loop (`eurika/api/chat_host_ops.py`)

Один цикл вместо двухфазного ритуала: **LLM → инструмент → LLM**.

1. Модель получает описание инструмента `host_shell` (cwd = project root) и, если нужны факты, выводит блок ```` ```eurika-cmds ```` с командами (`ls -la`, `git status`, `pwd`, …).
2. Eurika выполняет их сама через `bash -c` (**без** binary allowlist), пишет `$ cmd` + вывод во вкладку **Terminal**. Если нужны права — Qt предлагает: пароль sudo / продолжить без пароля (с ограничениями) / пропустить.
3. Вывод возвращается модели, она отвечает своими словами. Пустой блок `eurika-cmds` — модели сообщают об этом, и она может повторить. Если вместо проверки хоста модель выдала лекцию (`netstat`/`ifconfig`/Activity Monitor) — цикл один раз требует реальный `eurika-cmds`. Если на вопрос про Wi‑Fi/VPN она сняла только порты (`ss`/`lsof`/`netstat`) — цикл требует `nmcli`/`ip`. Обычные ```` ```bash ```` / ```` ```python ```` **не** автозапускаются (для UI Copy/Run).
4. Удачные tool-turns пишутся в `.eurika/chat_tool_turns.jsonl` (команды + `outcome_hint`) и подмешиваются в промпт **по релевантности** к текущему сообщению (не только хвост файла; не YAML phrase-book).
5. В каждый промпт кладётся `[Host identity]` (`uname` / os-release) — чтобы не выдумывать macOS. Вопросы про **успехи обучения market ML** — факты из `resolve_market_root()` (`[Market facts]` = `format_market_learning_report`: таблицы банк / live / тени / головы / ворота / LLM-учитель + **вердикт** по equity/net edge). Прямой интент «успехи на маркете» отдаёт тот же отчёт без сжатия LLM. **Не** `eurika scan`. Убыток по банку нельзя смягчать через accuracy.

Ответ пользователю формирует **только LLM** — в коде нет шаблонов вроде «Проверка на хосте», подсказок «напиши проверь» и пост-фильтров над текстом модели. Блоки `eurika-cmds` вырезаются из финального ответа (это синтаксис протокола); обычные code fence остаются для рамки Copy/Run.

**Права:** пароль sudo запрашивается в UI при необходимости; без пароля команда может выполниться с ограничениями — об этом явно пишется в вывод. Пароль не логируется.

**Хардкод:** ручные доменные списки фраз — нет. Списки request/response допустимы, когда Eurika **сама** их набирает из опыта (см. `docs/VISION.md` → Политика хардкода). Shell allowlist бинарников для tool-loop **снят** (2026-08-07): гейт — диалог привилегий, не список команд.

**Связка ML + LLM (опционально):** `EURIKA_USE_ML_INTENT=1` — после YAML/прямых фактов маленький PyTorch-роутер (`eurika.ml.intent_router`) предлагает handler или «в LLM». Веса: `.eurika/ml/weights/intent_router.pt`. YAML-интенты всегда главнее.

**Отправка в Qt:** кнопка Send или **Ctrl+Enter** (Enter — новая строка). Пока идёт запрос к LLM — подсказка «Eurika печатает…» и кнопка **Cancel** (ответ не попадёт в историю; Ollama может ещё доработать в фоне).

**Формат ответа в Qt:** транскрипт рендерит лёгкий markdown — **GFM-таблицы** (`| col |`) сеткой; fenced-блоки `` ``` `` в рамке с **Copy**; для `bash`/`sh`/`shell`/`console` (и пустого lang с CLI-эвристикой) — ещё **Run** (запуск во вкладке Terminal через `execute_command_from_chat`). Clear сбрасывает payload-ссылки блоков.

**Terminal mirror:** любые shell-команды из Chat (`scan`, `self-check`, `ls`, ритуал, release check, smoke, git status/diff/commit) пишутся во вкладку **Terminal** как `[Chat] $ …` + полный вывод + `exit_code` (без скрытого второго запуска).
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
| `что за проект?`, `какой проект открыт?` | Обзор: README/PROMPT, точка входа, структура каталогов, scan |
| `что дальше по развитию?`, `просмотри roadmap`, бэклог | Выжимка из `docs/VISION.md` (fallback ROADMAP) |
| `приступай`, `продолжай` | Компактный следующий шаг VISION A1 + цель `continue_dev` |
| `сколько файлов?`, `пересчитай файлы`, `сколько всего там файлов?` | Подсчёт файлов с диска |
| `покажи дерево`, `структуру проекта`, `покажи структуру` | LLM tool-loop (`eurika-cmds`: find/tree) |
| `какие документы по проекту?`, `покажи документацию` | README, docs/, notes/, .eurika/rules |
| `выполни ls`, `ls` | Голый `ls` → host_shell; «выполни ls» → LLM tool-loop |
| `покажи содержимое каталога проекта` | LLM tool-loop (`ls -la`); не путать с «покажи файл …» |
| `покажи файл app.py` | Содержимое файла |

### Анализ Eurika

| Фраза | Действие |
|-------|----------|
| `просканируй проект` / `scan` / `скан` | `eurika scan .` |
| `предложи полигон эксперимент` / `prove-cycle --propose` | C.14: seed `imports_ok` → Approvals (**без** apply); mirror в Terminal + live_activity; автофокус Approvals |
| `второй полигон` / `предложи полигон extract` | C.14: seed `extractable_block` (`extract_block_to_helper`) → Approvals |
| `третий полигон` / `предложи полигон long` | C.14: seed `long_function` (`extract_nested_function`) → Approvals |
| `четвёртый полигон` / `полигон llm` | C.14: seed `llm_extract` (`llm_extract_block`, live LLM или offline synthetic) → Approvals |
| опечатка вроде `scsn` | Подсказка; **да** → scan, **нет** → отмена (не list_docs) |
| `покажи отчёт`, `doctor report` | Отчёт doctor |
| `какие документы по проекту?`, `покажи документацию` | Список README / docs / rules |
| `прочти всю документацию, что реализовано?` | Аудит VISION/ROADMAP vs код (LLM/Groq; fallback по ✅) |
| `какая цель?`, `что в контексте?` | Статус active_goal / pending / last run |
| `что получилось?`, `итог цели` | Reflection: факты + краткий narrative (Groq/Ollama); без LLM — только факты |
| ↑/↓ в поле Chat | История отправленных запросов (персист `.eurika/chat_prompt_history.json`) |
| `@` в поле Chat | Автодополнение модулей из `self_map.json` и smell-типов (`@patch_engine.py`, `@god_module`); Tab/Enter — вставить, Esc — закрыть |
| `сбрось цель`, `clear goal` | Очистить active_goal + pending_clarification + last_execution (не HITL Apply) |
| `проведи ритуал` | scan → doctor → report-snapshot |
| `прогони release check` | `./scripts/release_check.sh` |
| `проведи smoke test`, `smoke` | Быстрый smoke: PyTorch + Qt pytest (без LLM) |
| `проведи self-check` | `eurika self-check .` — **проект/env** (torch, Binance, LBOT, layers) |
| `проверь операционку` / `здоровье ОС` / Arch | **Хост** (uptime/RAM/диск/journal/GPU) + краткий LLM; не путать с self-check проекта |
| `включи EURIKA_USE_ML_INTENT=1` | Записать флаг в `.env`, обучить chat-роутер |
| `выключи EURIKA_USE_ML_INTENT` | Выключить ML-роутер |
| `проверь включен ли ML_INTENT`, `статус EURIKA_USE_ML_INTENT` | Показать флаг / `.env` / acc роутера |
| `проверь статус ML`, `статус ML` | Сводка: PyTorch + ML_INTENT + VECTOR + полный Market-отчёт |
| `успехи на маркете`, `как твои успехи на маркете и обучении торговле?` | Полный paper-экзамен: таблицы equity/edge/головы/ворота/LLM-учитель |
| `ML хоть раз отработала по совету LLM?` | Нет: LLM только метки/train; проверка `paper_trades` vs teacher |
| `включен ли VECTOR_INTENT` | Статус `EURIKA_USE_VECTOR_INTENT` |
| `включи EURIKA_USE_VECTOR_INTENT=1` | Fuzzy embeddings (нужен `nomic-embed-text`) |
| вопрос про тикеры / общую модель market ML | Прямой ответ из кода (без LLM) |

В Qt панель **Контекст** (справа в Агент) показывает те же блоки: Цель / Pending Diff / Итог; после run цель может быть «нет», а итог ещё виден до «сбрось цель».

### Git

| Фраза | Действие |
|-------|----------|
| `собери коммит` | Status+diff + предложение сообщения → **применяй** (HITL) |
| `git status` / `git diff` / «покажи git status» | Голый `git status` → host_shell; фразы → LLM tool-loop |
| `применяй` | Подтверждение pending-плана или коммита |
| «сделай вкладку Models/LLM эргономичнее» | Локальный агент: полный патч → **Approvals** (вкладка открывается сама) → approve / apply-approved; git commit/push — после apply |

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
| `EURIKA_CHAT_PROVIDER` | `auto` \| `ollama` \| `openai` \| `codex` \| `cursor` — маршрутизация чата |
| `OPENAI_API_KEY` | Ключ OpenAI **или** любого OpenAI-compatible API (Groq/OpenRouter/Gemini/…) |
| `OPENAI_MODEL` | Модель (например `gpt-4o-mini`, `openai/gpt-oss-120b`, `gemini-2.0-flash`) |
| `OPENAI_BASE_URL` | Базовый URL API (по умолчанию OpenAI; см. пресеты ниже) |
| `OLLAMA_OPENAI_BASE_URL` | Ollama OpenAI-совместимый endpoint (обычно `http://127.0.0.1:11434/v1`) |
| `OLLAMA_OPENAI_MODEL` | Имя модели Ollama (должна быть установлена: `ollama pull …`) |
| `OLLAMA_OPENAI_API_KEY` | Для Ollama часто `ollama` |
| `EURIKA_OLLAMA_CLI_TIMEOUT_SEC` | Таймаут CLI Ollama, сек. (по умолчанию `120`; CPU-модели медленные) |
| `EURIKA_OLLAMA_PROGRESS` | `1` / `0` — спиннер прогресса в терминале при Ollama CLI |
| `CURSOR_API_KEY` | User API key Cursor (gitignored `.env`) |
| `CURSOR_MODEL` | id модели (`composer-2.5`, `auto-smart`, …) |
| `CURSOR_OPTIMIZE_FOR` | Router: `cost` \| `balanced` \| `intelligence` (только Auto / auto-smart) |

**Поведение `auto`:** при наличии `OPENAI_API_KEY` — remote OpenAI-compatible API; иначе Ollama. `codex` — только remote API, без fallback на Ollama. `cursor` — модели Cursor SDK (`CURSOR_API_KEY` в `.env`; вкладка Models → Cursor model / Router).

### Free / cloud LLM presets

Отдельный SDK не нужен — тот же OpenAI-compatible HTTP. В Qt: **Models → API preset** (подставляет `OPENAI_BASE_URL` + модель по умолчанию). Ключ только в `.env` как `OPENAI_API_KEY`.

| Preset | `OPENAI_BASE_URL` | Пример модели | Ключ |
|--------|-------------------|---------------|------|
| Groq | `https://api.groq.com/openai/v1` | `openai/gpt-oss-120b` (или `qwen/qwen3.6-27b`) | console.groq.com/keys |
| OpenRouter | `https://openrouter.ai/api/v1` | `openrouter/free` или `…:free` | openrouter.ai/keys |
| Gemini | `https://generativelanguage.googleapis.com/v1beta/openai/` | `gemini-2.0-flash` | aistudio.google.com/apikey |
| Cerebras | `https://api.cerebras.ai/v1` | `llama-3.3-70b` | cloud.cerebras.ai |
| Mistral | `https://api.mistral.ai/v1` | `mistral-small-latest` | console.mistral.ai |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` | platform.openai.com |

Шаблоны блоков — в `.env.example`. Free-tier лимиты (RPM/TPM) меняются у провайдеров; при 429 снижай timeout/частоту или вернись на Ollama.

Таймаут чата в Qt задаётся на вкладке Models (поле timeout, по умолчанию 120 с).

### Binance (опционально)

| Переменная | Назначение |
|------------|------------|
| `BINANCE_API_KEY` | API key (не коммитить; шаблон — `.env.example`) |
| `BINANCE_API_SECRET` | API secret |
| `BINANCE_TESTNET` | `1` = testnet; `0` = mainnet (default) |

Ключи в `.env` + read-only probe (`eurika.integrations.binance_readonly`): ping, ticker, балансы без ордеров. `eurika self-check` печатает блок **BINANCE (read-only)**. Live-ордера не подключены.

**Qt Chat:** подвкладки **Агент** (архитектура/LLM; полоска режимов) и **Market** (live paper). Market: Live paper / Авто / **Дообучение** / **LLM обучение** (opt-in: каждые 15 мин, TF1+TF2 и рынок Spot|Futures|Both с вкладки Market → метки MLP; оценка по пути свечей; paper-вход только MLP+ворота) / **Portfolio агент** (opt-in 15 мин + кнопка **Цикл**: holistic spot/fut/earn paper, единый cash pool, teacher labels; не live и не MLP exam) / **Исследование** (авто-стоп после N live-меток, по умолчанию 80; 0 = без лимита) / **Spot|Futures|Both** / **два списка тикеров** (Spot и Futures независимо, +/−; кнопка **Заполнить spot** из балансов — разово) / **Сброс сирот** (убрать opens вне списков) / **Отчёт** (карточка в ленту: opens/pending + uPnL, Portfolio агент/holistic, MLP paper/обучение голов, LLM shadow) / свечи `15m`/`1h`, горизонт (при сильном ATR-burst/range-break авто-удлинение до 4) / **1m** (вход market/limit/stop/OCO; **TP/SL/trail ставит ML** `market_levels.pt`, спины UI = потолок; выход TP/SL/трейлинг/горизонт/модель). **Лента компактная:** в UI и journal только важное (сделка / итог / исследование / обучение / LLM / Portfolio / ошибка / сводка) — без per-tick sync/analysis/hold/wait; карточки как в Chat (markdown для LLM). Свечи spot/futures хранятся раздельно; entry `market_policy.pt` + exit `market_exit.pt` + levels `market_levels.pt`. Статус ML — live/opens с разбивкой spot/fut и **PnL Σ edge** (всего / live / сессия с вкл. Live); статус Market показывает `live/cap` и PnL сессии. Idle без событий — тихо. Ордера на биржу не уходят. Прогресс: **Models → ML**.

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
| (всегда) | Удачные tool-turns → `.eurika/chat_tool_turns.jsonl` (опыт для промпта) |
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

## HTTP (Cursor / внешние клиенты)

Пока открыт Qt или Desktop, ядро доступно на loopback (токен в `.eurika/agent_http.json`):

```bash
python -m eurika.agent.http_client chat "Что за проект?"
python -m eurika.agent.http_client market
```

`chat` — тот же `chat_send`, что вкладка Chat. Подробнее: [CLI.md](CLI.md) § `eurika serve`.

---

## Связанные документы

| Документ | Содержание |
|----------|------------|
| [UI.md](UI.md) | Вкладки Qt, тема, Chat UX |
| [CLI.md](CLI.md) | `eurika scan`, `doctor`, `fix` |
| [chat_intents.example.yaml](chat_intents.example.yaml) | Пример конфига интентов |
| [KNOWLEDGE_LAYER.md](KNOWLEDGE_LAYER.md) | Curated knowledge (не произвольный web search) |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Ollama, timeout, self_map missing |
