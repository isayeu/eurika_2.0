# Execution Model — план миграции (review 2026 II)

Переход на единый ExecutionContext и ArchitectureSnapshot в fix-cycle. Обоснование: **docs/review.md** §1–3, **Architecture.md** §0.9, **ROADMAP.md** §5.7.

---

## Bounded evolution в Execution Model (2026-03)

**Статус:** целевой вектор зафиксирован. Адаптация доказана (CYCLE_REPORT #123, 100 циклов).

**Следующий шаг:** EnergyModel как **resource constraint** (energy budget, caps) — контракт документирован в docs/BOUNDED_EVOLUTION.md §7. Ограничения (MAX_EVENTS, EURIKA_MAX_OPS_PER_CYCLE) — часть execution contract. Реализация энергобюджета — по мере пробелов.

---

## Текущее состояние

| Компонент | Статус | Где |
|-----------|--------|-----|
| **ExecutionContext** | Интегрирован в fix-cycle | `prepare.py`, `apply_stage.py` — A–E реализованы |
| **ArchitectureSnapshot** | Тип + from_core_snapshot | `eurika/reasoning/planner/models.py` |
| **MetricVector, EnergyModel** | Реализованы | `eurika/analysis/` |
| **experience_store, weight_store** | Реализованы | `eurika/storage/` |
| **Orchestration fix-cycle** | Context через prepare→diagnose→apply | `prepare.py` (ctx до diagnose), `apply_stage.py` (simulation_result, snapshot_after, delta_score) |

**Состояние после A–E:** ExecutionContext проходит через prepare (snapshot_before, risk_report) → agent (snapshot для planner) → apply_stage (simulation_result, snapshot_after, delta_score). Delta persist в patch/learn events. Один источник истины — context.

---

## Целевая модель (review §1)

```python
class ExecutionContext:
    snapshot_before: ArchitectureSnapshot
    proposed_actions: list[RefactorAction]  # или candidates → selected
    simulation_result: SimulationReport
    risk_report: RiskReport
    snapshot_after: ArchitectureSnapshot
```

Все сервисы читают/пишут только через context. Orchestrator — единственный, кто мутирует context.

---

## Этапы миграции (инкрементально)

### Этап A: Внедрить context в prepare (read-only) ✅

**Цель:** ExecutionContext создаётся в prepare и передаётся дальше. Не ломать текущий flow.

**Реализовано (2026-03):** `_build_execution_context(path)` в prepare.py; snapshot_before из ArchitectureSnapshot.from_core_snapshot; context в result.output["execution_context"] и в early-exit dict при no ops.

1. В `prepare_fix_cycle_operations` (prepare.py) после получения patch_plan:
   - Построить `ArchitectureSnapshot.from_core_snapshot(core_snap)` → `snapshot_before`
   - Построить `ExecutionContext(snapshot_before=...)`
   - Добавить в result.output["execution_context"] и в early-exit dict
2. Fix_cycle_impl получает context через result.output (пока не передаёт в apply)
3. Тесты: test_architecture_snapshot, test_prepare_fix_cycle_reports_campaign_skipped ✅

**Результат:** snapshot_before заполнен, контекст доступен в result.output для следующих этапов.

---

### Этап B: RiskReport через context ✅

**Реализовано (2026-03):** `_build_execution_context(path, patch_plan)` в prepare.py; risk_report_from_plan(patch_plan) → context.risk_report; оба вызова (early-exit и нормальный return) передают patch_plan.

1. В prepare: вычислить `RiskReport` из patch_plan (уже есть `risk_report_from_plan` в planner.models)
2. Записать `context.risk_report = risk_report_from_plan(patch_plan)`
3. Использовать context.risk_report в policy/validate вместо ad-hoc расчётов (если есть дублирование)

---

### Этап C: snapshot_after и delta_score ✅

**Реализовано (2026-03):** `_update_execution_context_after_rescan` в apply_stage.py; после enrich_report_with_rescan обновляет context.snapshot_after, context.delta_score; report["delta_score"] → eurika_fix_report.json.

1. В apply_stage после apply + verify (и при успехе без rollback):
   - Запустить rescan (уже есть в apply_stage)
   - Построить snapshot_after из нового self_map
   - Вычислить delta_score = score(snapshot_after) - score(snapshot_before)
   - Записать в context
2. Передать context в write_fix_report для телеметрии (delta_score в eurika_fix_report.json)

---

### Этап D: SimulationResult в context ✅

**Реализовано (2026-03):** context.simulation_result = SimulationResult.from_simulate_dict(simulation) в apply_stage сразу после simulate_patch; заполняется и при abort (simulation errors), и при успешном proceed.

1. Перед apply: вызвать simulate_patch (если не dry_run)
2. Записать результат в `context.simulated_snapshot` или добавить `simulation_result: SimulationResult`
3. Использовать для pre-flight проверок (abort при errors)

---

### Этап E: Переключить planner на context.snapshot_before ✅

**Реализовано (2026-03):** prepare строит ctx до diagnose; run_fix_diagnose_stage передаёт ctx в payload; ArchReviewAgentCore при ctx.snapshot_before использует _structure_from_snapshot (graph, summary, ArchSmell из SmellReport) вместо _load_structure.

1. В `build_patch_plan` / `prepare`: передавать `context.snapshot_before` вместо сырых summary/smells/graph
2. planner.models уже принимает summary, smells — адаптировать к ArchitectureSnapshot
3. Убрать дублирование: один источник истины — context

---

## Порядок реализации

| # | Этап | Сложность | Зависимости |
|---|------|-----------|-------------|
| 1 | A: context в prepare | низкая | — |
| 2 | B: RiskReport в context | низкая | A |
| 3 | C: snapshot_after, delta | средняя | A |
| 4 | D: SimulationResult | средняя | A |
| 5 | E: planner через snapshot | высокая | A, B |

**Рекомендация:** начать с этапа A. После A — оценка, нужны ли B–E в ближайших итерациях или достаточно «context существует и заполняется» для отчётности.

---

## Аудит стабильного ядра (2026-03)

| Критерий | Статус | Детали |
|----------|--------|--------|
| **Planner чистый** | ✅ | Planner читает storage (get_recent_failures, learning_stats), не пишет. Запись только из orchestration/apply_stage. |
| **Storage dumb** | ✅ | experience_store, failure_log — тонкие фасады. event_views — read-side агрегация, без planning-логики. |
| **Snapshot единственный источник** | ✅ | prepare → ctx.snapshot_before; ArchReviewAgentCore при ctx использует _structure_from_snapshot; fallback _load_structure только при ctx=None (нет self_map). |
| **Самокоррекция** | ✅ | failure_reason: aborted_reason/rollback.reason/verify_failed → record_outcome → failure_log; planner_patch_ops вызывает get_recent_failures → sort_and_reindex_by_learning(recent_failures=...) для deprioritize. |

**Planner read-side:** `_suggest_extract_class`, `_is_thin_reexport_module` читают `file_path.read_text()` — допустимые heuristics; planner не мутирует storage/orchestration.

**Edge-case ctx=None:** При skip_scan или отсутствии self_map.json `_build_execution_context` возвращает None. Agent получает ctx=None и использует `_load_structure` → FileNotFoundError при отсутствии self_map. Ожидаемо: fix требует предварительный scan (или self_map из прошлого run). Два источника (snapshot vs load_structure) не используются в одном проходе.

---

## Ссылки

- **review.md** — §1 ExecutionContext, §2 разделение слоёв, §3 Score Delta
- **Architecture.md** §0.9 — Target pipeline v3.x
- **ROADMAP.md** §5.7 — этапы 1–7 (типы есть; интеграция — этот план)
