# REPORT — Текущий статус Eurika

_Обновлено: актуально для ветки v3.0.x (runtime policy + whitelist rollout + Qt-first interface)._

---

## Статус

**Основная задача (сейчас):** повышать операционность (качество apply/verify), сохраняя безопасность rollout через policy/learning.

**Ключевое состояние:**

- `extract_block_to_helper` переведён в guarded-path:
  - weak-pair policy (`hybrid: review`, `auto: deny`);
  - target-aware demote при `verify_fail >= 2`;
  - whitelist для controlled rollout (`.eurika/operation_whitelist.json`).
- Добавлена mini-automation для campaign memory:
  - учёт `verify_success` и кандидаты в whitelist;
  - генерация черновика whitelist: `eurika whitelist-draft`.
- Интерфейс переведён в Qt-first режим:
  - основной UI-контур: `eurika-qt` (`qt_app/`) — вкладки Models, Chat, Commands, Dashboard, Approvals;
  - Chat: Apply/Reject для планов, создание вкладок (в т.ч. Terminal) по intent; Models — управление Ollama;
  - `eurika serve` работает в API-only режиме (`/api/*`);
  - legacy web static (`eurika/ui/*`) выведен из активного рантайма.
- Добавлена прозрачность learning-результатов в Dashboard Qt:
  - top `verify_success` по `smell|action|target`;
  - рекомендации для whitelist / policy review на основе фактических исходов.

### Оценка зрелости (по review)

| Компонент               | Оценка |
| ----------------------- | ------ |
| Архитектурная структура | 8.5/10 |
| Качество кода           | 8/10   |
| Концепция               | 9/10   |
| Операционность          | 5/10   |
| Продуктовая готовность  | 6/10   |
| Потенциал               | 9.5/10 |

---

## Текущий рабочий фокус

1. Рост `verify_success_rate` по `smell|action|target` (а не только общий apply-rate).
2. Точечный rollout risky ops через whitelist + campaign learning.
3. Эксплуатационная стабильность UI/CLI как единого контура запуска ритуалов.

---

## Быстрый операционный цикл

```bash
# из корня проекта
../.venv/bin/python -m eurika_cli scan .
../.venv/bin/python -m eurika_cli doctor .
../.venv/bin/python -m eurika_cli fix . --dry-run
../.venv/bin/python -m eurika_cli report-snapshot .
```

Для controlled apply:

```bash
../.venv/bin/python -m eurika_cli fix . --runtime-mode hybrid --non-interactive --approve-ops 1
```

---

## Ключевые документы

| Документ | Назначение |
| --- | --- |
| `ROADMAP.md` | Текущий план и приоритеты (operability + guarded rollout) |
| `CYCLE_REPORT.md` | Фактические снапшоты ритуалов и выводы по метрикам |
| `CLI.md` | Актуальные команды/флаги, включая `whitelist-draft` |
| `UI.md` | Legacy reference по архивному Web UI |
| `MIGRATION_WEB_TO_QT.md` | Текущий статус миграции интерфейса (API-only + Qt-first) |
| `DOGFOODING.md` | Практика запусков и верификации в локальном окружении |
| `CHANGELOG.md` | История релизных изменений |
