# Eurika 2.0 — SPECIFICATION

Единый контракт проекта. История версий: v0.1 → v0.2 → v0.3 → v0.4 (текущая).

---

## 1. Назначение проекта

**Eurika 2.0** — долгоживущий инженерный ИИ-агент для анализа систем (в первую очередь собственного кода), выявления проблем и формирования проверяемых инженерных предложений.

Ориентирован на **практическую полезность**, воспроизводимость и постепенное расширение.

---

## 2. Чего Eurika НЕ является

- не оптимизирует ради красоты — только ради измеримого улучшения
- не самосознающий субъект, не обладает "Я"
- не обучается весами (no fine-tuning, no RL)
- не принимает автономных решений без верификации
- не изменяет код в production без явного opt-in
- не действует вне заданных доменных ограничений

> Самосознание — инженерная метафора, не реальное свойство.

---

## 3. v0.1 — Architecture Awareness Engine

**v0.1 = observe only.** scan → analyze → explain → log.

- Self-introspection (`self_map.json`)
- Граф зависимостей, smells, summary, recommendations
- History, evolution, diff
- Только read-only, никаких действий над кодом

---

## 4. v0.2 — AgentCore

**Строится поверх v0.1.** AgentCore — архитектурный советник, не исполнитель.

### Входы

- `self_map.json`, architecture summary, smells
- `architecture_history.json`, тренды, регрессии
- `eurika_observations.json`

### Выходы

- `DecisionProposal`: action (explain_risk, suggest_refactor_plan, prioritize_modules, summarize_evolution), arguments, confidence, rationale
- `Result`: success, output, side_effects

### События

- `arch_review` — анализ, объяснение рисков, план рефакторинга
- `arch_evolution_query` — эволюция, тренды, предупреждения

### Запрещено в v0.2

- модифицировать код, self_map, history
- выполнять shell, сетевые вызовы
- принимать автономные решения

---

## 5. v0.3 — Prioritization

- `prioritize_modules` — модули по архитектурному риску
- `architecture_planner` — PlanStep, suggest_refactor_plan, suggest_patch_plan
- Эвристики: smells, centrality, history, feedback

---

## 6. v0.4 — Action Layer (текущая)

### Что добавляет v0.4

- **ActionPlan** — type, target, description, risk, expected_benefit; dry-run / execute
- **PatchPlan** — операции (target_file, kind, smell_type, diff); diff — TODO-блоки
- **Patch Apply** — бэкапы в `.eurika_backups/<run_id>/`, verify (pytest), пропуск если diff уже в файле
- **Rollback** — restore по run_id
- **Learning Store** — `architecture_learning.json`; aggregate_by_action_kind, aggregate_by_smell_action
- **Cycle** — scan → arch-review → patch-apply --apply --verify; rescan_diff при успехе; rollback hint при падении
- **Cycle --dry-run** — только до patch-plan
- **Cycle --quiet** — только итоговый JSON

### Чего v0.4 НЕ делает

- не применяет изменения без `--apply`
- не выполняет произвольный shell/code
- не меняет без бэкапа
- patch — только добавление текста в конец файла

### CLI v0.4

| Команда | Назначение |
|--------|------------|
| `eurika agent action-dry-run` | ActionPlan, вывод без выполнения |
| `eurika agent action-simulate` | dry_run через ExecutorSandbox |
| `eurika agent action-apply` | execute с бэкапом |
| `eurika agent patch-plan` | Patch plan |
| `eurika agent patch-apply` | --apply, --verify, --no-backup |
| `eurika agent patch-rollback` | restore из бэкапа |
| `eurika agent cycle` | полный цикл |
| `eurika agent learning-summary` | агрегаты по action/smell |

---

## 7. Архитектурные принципы

- **Модульность** — чёткий контракт на модуль
- **Read-only first** — анализ без изменений по умолчанию
- **Человек в контуре** — всё подлежит просмотру
- **История важнее мгновенного вывода**

---

## 8. Core-модули

- **Self-Introspection** — scan, self_map.json
- **Code Analysis** — AST, smells, дубликаты (read-only)
- **Memory** — findings, decisions, errors (без chain-of-thought)
- **Report** — человекочитаемый отчёт, без эмоций

---

## 9. LLM

В v0.1+ LLM — вспомогательный инструмент:
- объяснение проблем, формулирование отчётов
- не принимает решения, не управляет агентом

---

## 10. Безопасность

- отсутствие self-modifying behavior
- воспроизводимость отчётов
- детерминированность core-логики
- opt-in для модификации кода, бэкапы при apply

---

## 11. Философское ограничение

> Eurika — система. Не субъект, не разум, не личность.
> Любое развитие — развитие инженерных возможностей.

---

**Контракт проекта.** Изменения архитектуры или поведения требуют согласования с данной спецификацией.
