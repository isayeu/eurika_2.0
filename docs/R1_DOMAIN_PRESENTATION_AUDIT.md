# R1 Domain vs Presentation — аудит

**Цель (ROADMAP R1):** domain возвращает структуры, rendering только в reporting/UI/CLI.
**Статус:** отложено; ниже каталог нарушений для будущего плана.

---

## Модули с форматированием в domain

| Модуль | Нарушение | Рекомендация |
|--------|-----------|--------------|
| `eurika/reasoning/architect.py` | ~~_template_interpret~~ | ✅ **Сделано:** `get_architect_data()` возвращает структуру; `format_architect_template` в `report/architect_format.py`; `_template_interpret` делегирует presentation |
| `eurika/api/__init__.py` | ~~explain_module~~ | ✅ **Сделано:** `get_explain_data()` возвращает структуру; `format_explain_result` в `report/explain_format.py`; `explain_module` — thin wrapper |
| `eurika/api/__init__.py` | `get_suggest_plan_text` — форматированный план | Аналогично: структура → presentation |
| `report/ux.py` | Смешение отчётов и markdown | Уже в presentation; проверить, что core не импортирует |

---

## Не в scope (допустимо)

- `eurika/api/chat.py` — API-слой, форматирование ответов пользователю допустимо
- `eurika/reporting/*` — предназначены для rendering
- `report/report_snapshot.py` — presentation layer по дизайну

---

## Приоритет

Низкий. ROADMAP R1 Domain vs Presentation помечен «отложено». При рефакторинге architect/explain — разделять domain и presentation.
