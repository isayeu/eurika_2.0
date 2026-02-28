# Web -> Qt Migration Note

Текущий интерфейс Eurika: **Qt shell (`eurika-qt`)**.
Web static UI (`eurika/ui/index.html`, `eurika/ui/app.js`) удалён из активного рантайма и оставлен только в истории проекта.

## Что изменилось

- `eurika serve` теперь работает как **API-only** сервер (`/api/*`).
- Маршруты web статики (`GET /`, `GET /app.js`, `GET /index.html`) больше не используются.
- Legacy web-артефакты удалены:
  - `eurika/ui/index.html`
  - `eurika/ui/app.js`

## Что осталось и поддерживается

- JSON API в `eurika/api/serve.py`:
  - обзор/история/план/explain/graph/metrics
  - exec/approve/chat endpoints
- CLI-контур (`eurika scan/doctor/fix/cycle/...`)
- Qt shell (`qt_app/`) как основной UI-клиент:
  - **Models** — Ollama Start/Stop, env, список моделей, установка
  - **Chat** — Apply/Reject для планов, создание вкладок (в т.ч. Terminal) по intent
  - **Commands** — scan/doctor/fix/cycle, live output
  - **Dashboard** — summary, verify_success, whitelist-рекомендации
  - **Approvals** — pending plan approve/reject

## Как запускать сейчас

```bash
# API
eurika serve .

# Qt UI (desktop shell)
eurika-qt
```

## Документация

- `README.md` — актуальный вход.
- `CLI.md` — актуальное описание команд.
- `UI.md` — legacy reference (исторический контекст).
