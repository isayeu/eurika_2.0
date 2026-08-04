# Архитектурный разбор памяти (2026-03)

Честный аудит без смягчений. Источник: пользовательский review.

---

## Оценка

| Критерий | Оценка |
|----------|--------|
| Структурность | 8.5/10 |
| Минимализм | 9/10 |
| Автономность | 6.5/10 (потенциал есть) |
| Риск скрытой сложности | 7/10 |

**Главное:** три конкретных механизма вместо иллюзии STM/LTM — правильно.

---

## 1. Двойная истина (FailureLog vs EventLog)

**Проблема:** FailureLog (.eurika/failures.json) — отдельный файл. Learn-события в EventLog тоже содержат verify_success. Divergence risk.

**Решение:** EventLog — единственный источник. FailureLog = bounded view/projection над EventLog (learn, result=False).

---

## 2. FailureLog — формат обогащён

**Реализовано (2026-03):** goal_id, plan_hash, confidence в learn event output.

- **goal_id** — первый op target|kind (причинно-следственная связь)
- **plan_hash** — sha256(sorted(target, kind)) для strategy deprioritization
- **confidence** — опционально
- **action_kind** — kind есть в каждом op

Planner: при совпадении plan_hash с недавними провалами — reverse порядка ops (разная стратегия).

---

## 3. LearningStore — сильное место

Aggregation по (smell_type, action_kind) — reinforcement-like. Риск: exploitation lock если planner просто сортирует по success_rate.

Нужно: `score = success_rate * recency_weight * exploration_bonus`. **Проверить позже.**

---

## 4. Логическая асимметрия

Сейчас: failures → FailureLog отдельно, successes → только LearningStore.

Правильнее: все outcomes → EventLog. FailureLog = projection. **Реализовано в приоритете 1.**

---

## 5. STM

EventLog, FailureLog, LearningStore — LTM. STM = ExecutionContext (текущий цикл).

**Добавлено (2026-03):** current_goal, attempt_count, session_failures в ExecutionContext. Поля опциональны; популяция — при retry/сессионной логике.

---

## План (по приоритету)

1. **Убрать двойную истину** — FailureLog = view над EventLog ✅
2. **Обогатить failure-событие** — goal_id, plan_hash, confidence ✅
3. **Минимальный STM** — ExecutionContext.current_goal, attempt_count, session_failures ✅
4. **Проверить адаптацию** — агент меняет поведение после провалов ✅

**Критический риск:** не расширять memory, пока не видно реального изменения поведения.

---

## Верификация (2026-03)

| Проверка | Тест | Результат |
|----------|------|-----------|
| Planner deprioritize op после провалов | test_planner_deprioritizes_after_failures | ✅ penalized.py|split_module последний |
| Decay снижает priority модуля | test_priority_from_graph_deprioritizes_after_failures | ✅ b.py выше a.py после 3 провалов a.py |
