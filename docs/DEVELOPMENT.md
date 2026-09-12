# Разработка Eurika

Это единственная точка входа для планирования разработки. Здесь находятся
текущий фокус, порядок принятия решений и ссылки на канонические контракты.
Подробная история не удаляется: она остаётся в [ROADMAP.md](ROADMAP.md),
[CYCLE_REPORT.md](CYCLE_REPORT.md) и [archive/](archive/).

## Роли документов

| Нужен ответ на вопрос | Канонический документ | Не использовать как источник текущих задач |
|---|---|---|
| Зачем существует продукт и какие есть границы | [VISION.md](VISION.md) | ROADMAP, CYCLE_REPORT |
| Какие зависимости и контракты допустимы в коде | [Architecture.md](Architecture.md), [DEPENDENCY_FIREWALL.md](DEPENDENCY_FIREWALL.md), [API_BOUNDARIES.md](API_BOUNDARIES.md) | VISION |
| Как безопасно менять и проверять код | [BOUNDED_EVOLUTION.md](BOUNDED_EVOLUTION.md), [DOGFOODING.md](DOGFOODING.md), [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md) | ROADMAP |
| Что делать следующим | **этот документ** | VISION, historical sections ROADMAP |
| Как пользоваться продуктом | [ONBOARDING.md](ONBOARDING.md), [CLI.md](CLI.md), [UI.md](UI.md), [CHAT.md](CHAT.md) | Architecture |

## Текущий фокус

1. **Стабильность и ясность.** Architecture Freeze остаётся активным: не
   добавлять silent apply, бесконечные автономные циклы и новые продуктовые
   домены. Любое изменение кода проходит proposal → verify → явное одобрение.
2. **RV11: кодовая наблюдаемость.** Статические call graph и conservative
   data flow — `GET /api/graph?include_calls=1`. **Замер v0 (2026-09-12):**
   `call_graph.diagnostics` = labeled accuracy (recall / false resolutions)
   + cost этого дерева (`elapsed_ms`, nodes/edges). Только read-only.
   В planner/policy **не** подключать.
3. **Multi-project v0 + scaffolds.** `eurika init --scaffold python|python-cli`
   и Chat «создай проект my_app как python» пишут src/tests/pyproject поверх
   `.eurika/` + `self_map`. Не расширять HTTP `init` за пределы выбранного
   project_root.
4. **Host admin read-only v0.** Observe через Chat tools; mutate — HITL
   (`.eurika/pending_host_admin.json` + «одобрить»). Не наращивать phrase-book
   «покажи диск / сколько RAM».
4b. **Reasoner/Experimenter v1 (сделано 2026-09-11).** Multi-role critic
   (не LLM-агенты), A/B suite + layer_violations, Self Model
   deps/versions/problems.
4c. **Паритет Qt ↔ Desktop v2 (2026-09-11).** Desktop Chat: режим **Eurika**
   (`chat/send` = Qt `chat_send`) и **Agent** (`session/chat` +
   `reviewInApprovals`). `@`-mentions через `mentions/suggest`. Scaffolds:
   `project/create` (sibling name + HITL). Commands observer-ритуалы и
   host-admin Context — с v1.
4d. **Models-tab parity v0 (2026-09-12).** Desktop панель Models =
   `panel/state models` + `models/prefs` (HITL). Routing (provider / preset /
   model / timeout / torch device) в `qt_settings.json` + `.env`. Ключи не
   пишутся и не возвращаются. Ollama start/stop и trading-ML — вне среза.
5. **Market.** Paper Market заморожен: не менять торговые правила, пока
   метрики журнала не требуют отдельного решения.

## Порядок работы над задачей

1. Сначала проверить соответствующий контракт в Architecture/Firewall.
2. Сделать малый обратимый инкремент с тестом.
3. Выполнить релевантные тесты, `compileall` и `git diff --check`.
4. Для изменений цикла или CLI выполнить [DOGFOODING](DOGFOODING.md).
5. Обновить этот файл только при смене приоритета; подробные факты прогона
   записывать в CYCLE_REPORT, а закрытые планы — в archive.

## Входящие в backlog, но не активные

- Более глубокий data-flow (контейнеры, callbacks, dynamic dispatch).
- Test coverage graph и enrichment архитектурных рекомендаций доказанными
  графовыми данными.
- Более богатые scaffolds (не python) после проверки `minimal`/`python`/`python-cli`.
- Долгосрочные модели Architecture Time Machine и Gravity.

## Правило обновления документации

- Меняется **смысл продукта** → VISION.
- Меняется **кодовый контракт** → Architecture / Firewall / API Boundaries.
- Меняется **безопасностное ограничение** → Bounded Evolution.
- Меняется **приоритет разработки** → этот файл.
- Результат конкретного запуска или закрытого решения → CYCLE_REPORT / archive.
