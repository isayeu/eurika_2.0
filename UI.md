# Eurika Web UI

Веб-интерфейс для просмотра архитектурного анализа и управления циклом рефакторинга. UI дополняет CLI — для пользователей, предпочитающих браузер.

---

## MVP статус

MVP для Web UI закрыт: покрыты базовые операторские сценарии запуска цикла, обзора архитектуры, ручного approve/reject и диалога с архитектором/чатом.

**MVP-чеклист:**
- запуск через `eurika serve [path]`;
- вкладки: `Dashboard`, `Terminal`, `Approve`, `Ask Architect`, `Chat` (а также `Summary`, `History`, `Diff`, `Graph`, `Explain Module`);
- запуск ритуала из UI: `Scan`, `Doctor`, `Fix`, `Report snapshot`, `Cycle (dry-run)`;
- безопасный exec-контур через whitelist eurika-команд (`POST /api/exec`).

---

## Запуск

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

После запуска откройте в браузере:

```
http://127.0.0.1:8765/
```

---

## Вкладки

### Dashboard
Обзор: risk score, системные метрики (modules, deps, cycles, maturity), operational metrics (apply-rate, rollback-rate, median verify time), тренды, central modules, top risks.

**Core Command Builder:** запуск `scan/doctor/fix/cycle/explain` из единой формы с параметрами.

- `scan`: `--format`, color flags
- `doctor`: `--window`, `--no-llm`, `--online`, `--runtime-mode`
- `fix`/`cycle`: `--dry-run`, `--runtime-mode`, `--non-interactive`, `--session-id`, `--allow-campaign-retry`, `--allow-low-risk-campaign`, `--no-clean-imports`, `--no-code-smells`, `--verify-timeout`, `--interval`, а также `--team-mode` / `--apply-approved`
- `explain`: module + `--window`

Кнопки:
- **Build command** — формирует команду и подставляет её в Terminal
- **Copy command** — копирует собранную команду в clipboard (fallback: подстановка в Terminal input)
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

### Terminal
Выполнение whitelist-команд eurika из браузера:
- `eurika scan .`
- `eurika doctor .`
- `eurika fix . --dry-run`
- `eurika cycle . --dry-run`
- `eurika explain <module>`
- `eurika report-snapshot .`

Путь всегда — project root сервера. Введите команду и нажмите Run. Вывод (stdout + stderr) отображается в терминальной области.

### Ask Architect
Кнопка получает интерпретацию архитектора (architect_text из doctor-цикла): краткая сводка состояния кодовой базы и рекомендаций. Использует тот же контекст, что и `eurika doctor .`.

### Chat
Чат с Eurika через прослойку Ollama: введите сообщение, получите ответ с учётом контекста проекта (summary, recent events). RAG: при похожем запросе — прошлые обмены в промпт.

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
| POST /api/approve | Сохранить approve/reject решения |
| POST /api/exec | Выполнить whitelist-команду eurika |
| POST /api/ask_architect | Architect interpretation |
| POST /api/chat | Chat with Eurika (Ollama via Eurika layer; logs to .eurika/chat_history/) |

Пример:
```bash
curl http://127.0.0.1:8765/api/summary
curl -X POST http://127.0.0.1:8765/api/exec -H "Content-Type: application/json" -d '{"command":"eurika scan ."}'
```

---

## Предварительные условия

1. **self_map.json** — выполните `eurika scan .` перед использованием Dashboard, Summary, Graph. Без него многие вкладки покажут «No data» или подсказку.
2. **Локальный доступ** — по умолчанию serve биндится на 127.0.0.1 (доступ только с localhost). Для удалённого доступа используйте `--host 0.0.0.0` (осторожно с безопасностью).

---

## См. также

- **CLI.md** — полный справочник команд
- **ROADMAP.md** § Фаза 3.5 — Web UI (DoD, 3.5.1–3.5.11)
