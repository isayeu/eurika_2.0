# Eurika UI — Qt-first + legacy Web reference

Текущий приоритет интерфейса — desktop-first Qt shell на `PySide6` (пакет `qt_app/`, запуск `eurika-qt`).

## Qt tabs (актуальный интерфейс)

| Вкладка | Назначение |
|---------|------------|
| **Chat** (первая) | Chat-first: слева **рейка как в Cursor** — воркспейс = Project root, дети = чаты; **‹/›** сворачивает панель; **Новый чат** выбирает каталог; **+** — тред в этом root; ПКМ по чату — переименовать/удалить; ПКМ по воркспейсу — убрать из списка (каталог на диске не трогается). Подвкладки **Агент** / **Market**. Правки агента → **Approvals**. Market: Live paper, без live-ордеров. См. [CHAT.md](CHAT.md) |
| **Terminal** | Классический экран: ввод после `$ ` (Enter = Run), Stop/Clear сверху; вывод Commands + shell |
| **Models** | Подвкладки **LLM** / **ML**. LLM: Ollama, GPU, chat provider. ML: PyTorch + **Market learning**. См. [CHAT.md](CHAT.md) / [HARDWARE.md](HARDWARE.md) |
| **Commands** | scan/doctor/fix/cycle/explain/…, **bug-hunt** (C.14 HITL), learn-github; Run/Stop; Quality: Ruff, Mypy, Release check |
| **Dashboard** | Summary (modules, deps, cycles, risk, maturity, trends, **Energy**), Top risks, Operational metrics, Learning insights, **ARCHITECTURE METRICS** (blast radius, dependency_density, fragility heatmap 🟢🟡🔴 RV10); Energy — MetricVector (ROADMAP §5.7); автообновление при смене project root |
| **Graph** | Интерактивный граф зависимостей. Требует `eurika scan .` перед использованием. |
| **Approvals** | Chat-агент (Qt, `reviewInApprovals`) кладёт полный патч (`agent_edit`) в `.eurika/pending_plan.json`; после ответа с `approvalsQueued>0` вкладка открывается сама. Load plan → **approve** → **Save** или **Run apply-approved**. Desktop: та же цепочка через `approval/save` / `approval/apply`. `git_commit`/`git_push` в этом режиме **отложены** до apply на диск (потом отдельный HITL / повторный запрос). Также team-mode `eurika fix`. Для extract_block/extract_nested — OSS Reference (Learning from GitHub). |
| **Terminal** | Классический экран (inline `$ `), Stop/Clear сверху; Commands + shell (ls, pwd, eurika scan .) |
| **Notes** | Персональные заметки во время работы. Сохраняются в `.eurika/notes.txt` проекта (или `~/.eurika/notes.txt` без проекта). Загрузка при смене project root. |
| **Помощь** | Индекс документов: Architecture, CLI, **CHAT**, ROADMAP, MEMORY, TROUBLESHOOTING и др. Кнопка Open — открыть в редакторе. |

### Тема оформления (Dark theme)

**View → Dark theme** — переключение светлой/тёмной темы. Выбор сохраняется в `~/.eurika/qt_settings.json`. При запуске тема загружается из настроек.

### Chat: @-mentions (ROADMAP 3.6.5)

Сужение контекста через `@module` и `@smell`. В поле Chat при вводе `@` — автодополнение кандидатов из `self_map.json` + smell-типов (Tab/Enter вставить, Esc закрыть). Примеры (по данным `eurika scan` / `eurika doctor`):

| Запрос | Результат |
|--------|-----------|
| `рефактори @patch_engine.py` | target=patch_engine.py, scope на god_module (severity 14) |
| `рефактори @code_awareness.py с учётом @god_module` | modules + smells в scope |
| `проверь @cli/core_handlers.py` | focus на long_function кандидате |

---

> **Исторический reference (не рантайм).** Web static UI удалён. `eurika serve` — только JSON API (`/api/*`). Актуальный интерфейс — Qt (`eurika-qt`), см. таблицы вкладок выше и [VISION.md](VISION.md). Ниже — описание старого web-контура для архива.

---

## MVP статус (legacy Web)

MVP для Web UI закрыт: покрыты базовые операторские сценарии запуска цикла, обзора архитектуры, ручного approve/reject и диалога с архитектором/чатом.

**MVP-чеклист:**
- запуск через `eurika serve [path]`;
- вкладки: `Dashboard`, `Terminal`, `Approve`, `Ask Architect`, `Chat` (а также `Summary`, `History`, `Diff`, `Graph`, `Explain Module`);
- запуск ритуала из UI: `Scan`, `Doctor`, `Fix`, `Report snapshot`, `Cycle (dry-run)`;
- безопасный exec-контур через whitelist eurika-команд (`POST /api/exec`).

---

## Запуск (исторический, до миграции на Qt)

```bash
eurika serve [path]
```

По умолчанию:
- **Host:** 127.0.0.1
- **Port:** 8765
- **Path:** текущий каталог (`.`)

Опции:
```bash
eurika serve . --port 9000
eurika serve /path/to/project --host 0.0.0.0
```

Исторически после запуска открывали в браузере:

```
http://127.0.0.1:8765/

Сейчас это поведение неактуально: используйте `eurika-qt` для UI, а `eurika serve` — только для `/api/*`.
```

---

## Вкладки

### Dashboard
Обзор: risk score, системные метрики (modules, deps, cycles, maturity), operational metrics (apply-rate, rollback-rate, median verify time), тренды, central modules, top risks. **ARCHITECTURE METRICS:** blast radius top N (RV1), dependency_density (RV2), fragility heatmap (RV10) — propagation_depth, blast_radius с цветовой индикацией 🟢🟡🔴.

**Core Command Builder:** запуск `scan/doctor/fix/cycle/explain` из единой формы с параметрами.

- `scan`: `--format`, color flags
- `doctor`: `--window`, `--no-llm`, `--online`, `--runtime-mode`
- `fix`/`cycle`: `--dry-run`, `--runtime-mode`, `--non-interactive`, `--session-id`, `--allow-campaign-retry`, `--allow-low-risk-campaign`, `--no-clean-imports`, `--no-code-smells`, `--verify-timeout`, `--interval`, а также `--team-mode` / `--apply-approved`. При включении **Allow low-risk campaign** GUI добавляет `--runtime-mode auto` для polygon drills и whitelist bypass
- `explain`: module + `--window`

Кнопки:
- **Build command** — формирует команду и подставляет её в Terminal (prompt `$ `)
- **Copy command** — копирует собранную команду в clipboard (fallback: подстановка в Terminal prompt)
- **Run** — выполняет собранную команду через `/api/exec`
- UI динамически показывает только релевантные поля для выбранной команды
- Для `fix/cycle` поля `session-id` и `non-interactive` показываются только при `runtime-mode=hybrid`
- Внизу builder выводится контекстная подсказка по безопасному запуску для выбранной команды

Для некорректных комбинаций (например `team-mode` + `apply-approved`, `non-interactive` вне `runtime-mode=hybrid`) UI показывает ошибку до запуска.

### Summary
Детализированный architecture summary: system metrics, central modules, risks.

### History
Evolution report: тренды (complexity, smells, centralization), регрессии, recent points, evolution report (text).

### Diff
Сравнение двух `self_map.json`: введите пути (например `self_map.json` и `.eurika/backups/self_map_old.json`), нажмите Compare. Результат: maturity, modules added/removed, centrality shifts, bottleneck modules, recommended actions.

### Graph
Интерактивный граф зависимостей модулей (vis-network). Drag — pan, scroll — zoom. Double-click на узел — переход во вкладку Explain с выбранным модулем.

Требует предварительного `eurika scan .` (self_map.json).

### Approve
Управление team-mode планом. Сначала выполните `eurika fix . --team-mode` — план сохранится в `.eurika/pending_plan.json`. В UI: approve/reject по каждой операции, кнопка **View** — раскрывает side-by-side diff (слева текущий файл с красной подсветкой удалений, справа diff/новый фрагмент с зелёной подсветкой). Кнопка Save сохраняет решения. Затем `eurika fix . --apply-approved` применяет только одобренные операции.

**Split module:** визуализация split_module (граф до/после, дерево новых файлов) — в разработке.

### Explain Module
Введите путь к модулю (например `eurika/api/serve.py`) и нажмите Explain. Результат: роль модуля, риски, rationale из explain_module.

### Terminal (исторически)
Выполнение whitelist-команд eurika из браузера:
- `eurika scan .`
- `eurika doctor .`
- `eurika fix . --dry-run`
- `eurika cycle . --dry-run`
- `eurika explain <module>`
- `eurika report-snapshot .`

Путь всегда — project root сервера. В Qt: классический экран — команда после `$ `, Enter; Stop/Clear сверху. Вывод (stdout + stderr) в той же области.

### Ask Architect
Кнопка получает интерпретацию архитектора (architect_text из doctor-цикла): краткая сводка состояния кодовой базы и рекомендаций. Использует тот же контекст, что и `eurika doctor .`.

### Chat
Чат с Eurika через прослойку Ollama: введите сообщение, получите ответ с учётом контекста проекта (summary, recent events). RAG: при похожем запросе — прошлые обмены в промпт.

На Агенте: **Apply / Reject / Diff** для HITL pending-плана (`dialog_state`) и для agent `pendingToolCalls` (git Commit/Push, edit без Approvals-режима). Diff в **Контекст** открывается **автоматически** при pending; **Apply** активен только после Diff (кнопка Diff — обновить). Desktop **Context** — тот же HITL (`context/preview` / `context/decide`). Основной путь правок кода в Qt — вкладка **Approvals** (`agent_edit`), не путать с Chat Apply.

**Agent intents (3.5.11.C):**

| Intent | Пример | Действие |
|--------|--------|----------|
| save | «сохрани код в foo.py», «save to tests/ bar.py» | Извлечение кода из ответа LLM, запись в файл. Поддержка каталога: «в tests/ foo.py», «в каталог tests файл foo.py» |
| refactor | «рефактори», «refactor .» | Запуск `eurika fix .` (или `--dry-run` при «dry run») |
| delete | «удали foo.py», «delete bar.txt» | Удаление файла |
| create | «создай пустой файл 111.txt» | Создание пустого файла |
| remember | «Меня зовут Андрей, запомни это» | Сохранение в `.eurika/chat_history/user_context.json` |
| recall | «как меня зовут?» | Ответ из сохранённого контекста пользователя |

Диалоги логируются в `.eurika/chat_history/chat.jsonl`. Требует Ollama или OPENAI_API_KEY (см. README).

---

## JSON API

Для интеграций доступны endpoints (GET/POST):

| Endpoint | Описание |
|----------|----------|
| GET /api | Список endpoints |
| GET /api/summary | Architecture summary |
| GET /api/history?window=5 | Evolution history |
| GET /api/diff?old=...&new=... | Diff двух self_map |
| GET /api/doctor?window=5&no_llm=0 | Full report + architect |
| GET /api/patch_plan?window=5 | Planned operations |
| GET /api/explain?module=... | Role and risks модуля |
| GET /api/graph | Dependency graph (nodes, edges) |
| GET /api/operational_metrics?window=10 | apply-rate, rollback-rate |
| GET /api/pending_plan | Team-mode plan для approve UI |
| GET /api/market | Paper Market (portfolio, opens, journal) |
| GET /api/learning | Paper learning snapshot |
| POST /api/approve | Сохранить approve/reject решения |
| POST /api/exec | Выполнить whitelist-команду eurika |
| POST /api/ask_architect | Architect interpretation |
| POST /api/chat | Chat with Eurika (Ollama via Eurika layer; logs to .eurika/chat_history/) |

Пример:
```bash
curl http://127.0.0.1:8765/api/summary
curl -X POST http://127.0.0.1:8765/api/exec -H "Content-Type: application/json" -d '{"command":"eurika scan ."}'
```

Qt и Desktop поднимают тот же `/api/*` на `127.0.0.1:18765` с Bearer-токеном (`.eurika/agent_http.json`): `python -m eurika.agent.http_client`.

---

## Предварительные условия

1. **self_map.json** — выполните `eurika scan .` перед использованием Dashboard, Summary, Graph. Без него многие вкладки покажут «No data» или подсказку.
2. **Локальный доступ** — по умолчанию serve биндится на 127.0.0.1 (доступ только с localhost). Для удалённого доступа используйте `--host 0.0.0.0` (осторожно с безопасностью).

---

## См. также

- **CLI.md** — полный справочник команд
- **ROADMAP.md** § Фаза 3.5 — Web UI (DoD, 3.5.1–3.5.11)
