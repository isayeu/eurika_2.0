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

1. **CR-H H5 Thinking (активно, 2026-09-12).** Qt и Desktop рисуют ход в ленте
   под пузырём пользователя: `live_activity` + `tool/started`, раунд модели
   («Model»). Не один молчаливый пузырь 600s. Стрим токенов reasoning —
   следующий срез, не этот. **Не** новый `is_*_request`. **Не** Market.
   После правок — перезапуск клиента (Qt / Desktop).
2. **Стабильность.** Architecture Freeze: proposal → verify → HITL. Не silent
   apply, не бесконечный автономный цикл, не новые продуктовые домены.
3. **Market.** Paper заморожен: не менять торговые правила без разбора journal.
   Не live-ордера, не explore on, не HTF / новый entry.

Сделано в окне (не предлагать как next): H0–H4 + H5 UI/model-round;
4b critic/A/B; 4c Desktop parity v2; 4d Models-tab v0; RV11 diagnostics
read-only; scaffolds `python` / `python-cli`; host admin read-only v0.

## Порядок работы над задачей

1. Сначала проверить соответствующий контракт в Architecture/Firewall.
2. Сделать малый обратимый инкремент с тестом.
3. Выполнить релевантные тесты, `compileall` и `git diff --check`.
4. Для изменений цикла или CLI выполнить [DOGFOODING](DOGFOODING.md).
5. Обновить этот файл только при смене приоритета; подробные факты прогона
   записывать в CYCLE_REPORT, а закрытые планы — в archive.

## Входящие в backlog, но не активные

- Полный CR-H H5: стрим токенов reasoning модели (не только раунд «Model») —
  [ROADMAP.md](ROADMAP.md) §5.4.1.
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
