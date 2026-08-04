# REPORT — Текущий статус Eurika

_Обновлено: 2026-03. Ветка v3.0.x (Qt-first, Execution Model, R8/R10)._

---

## 1. Статус

**Основная задача:** операционность (apply/verify) + безопасность (policy/learning). R1–R10 реализованы.

**Ключевое состояние:**

- `extract_block_to_helper` в guarded-path:
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

### Оценка зрелости (2026-03)

| Компонент               | Оценка |
| ----------------------- | ------ |
| Архитектурная структура | 9/10   |
| Качество кода           | 8/10   |
| Концепция               | 9/10   |
| Операционность          | 5/10   |
| Продуктовая готовность  | 7/10   |
| Потенциал               | 9.5/10 |

---

## 2. Текущий фокус

1. Рост `verify_success_rate` по `smell|action|target` (а не только общий apply-rate).
   - `eurika learning-kpi [path]` — KPI блок, promote/deprioritize рекомендации.
   - Policy динамический deny из deny_candidates; context prioritization по rate.
2. Точечный rollout risky ops через whitelist + campaign learning.
3. Эксплуатационная стабильность UI/CLI как единого контура запуска ритуалов.

---

## 3. Быстрый операционный цикл

```bash
# из корня проекта
.venv/bin/python -m eurika_cli scan .
.venv/bin/python -m eurika_cli doctor .
.venv/bin/python -m eurika_cli fix . --dry-run
.venv/bin/python -m eurika_cli report-snapshot .
```

Для controlled apply:

```bash
.venv/bin/python -m eurika_cli fix . --runtime-mode hybrid --non-interactive --approve-ops 1
```

---

## 4. Ключевые документы

| Документ | Назначение |
|----------|------------|
| ROADMAP.md | План, приоритеты, R1–R10, §4.5 фокус |
| CYCLE_REPORT.md | Снапшоты ритуалов, #150–155 |
| REVIEW_2026_IV_ANALYSIS.md | Анализ Review IV |
| COGNITIVE_LOOP.md | R8: Cognitive Loop |
| KNOWLEDGE_GRAPH_DESIGN.md | R10: Knowledge Graph |
| CLI.md | Команды, флаги, whitelist-draft |
| DOGFOODING.md | Ритуал запусков |
| archive/MIGRATION_WEB_TO_QT.md | Миграция Web → Qt |
