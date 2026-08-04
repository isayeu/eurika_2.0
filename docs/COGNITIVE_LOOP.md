# R8 — Cognitive Loop (полная формализация)

**Источник:** docs/archive/review.md §Cognitive Loop, Architecture.md §0.9, REVIEW_2026_IV_ANALYSIS R8.

**Цель:** формализовать восьмиэтапный когнитивный цикл Eurika как контракты входа/выхода, потоки данных и маппинг на код.

---

## 1. Цикл

```
Analyze → Build State → Generate → Simulate → Evaluate → Select → Execute → Learn
```

| # | Этап | archive/review.md | Architecture §0.9 |
|---|------|-----------|-------------------|
| 1 | **Analyze** | Analyze | run_fix_scan_stage, run_fix_diagnose_stage |
| 2 | **Build State** | Build State | snapshot_before (ArchitectureSnapshot) |
| 3 | **Generate** | Generate Hypotheses | PlannerEngine (candidates, patch_plan) |
| 4 | **Simulate** | Simulate | simulate_patch (dry-run) |
| 5 | **Evaluate** | Evaluate (Energy) | DeltaEvaluator.compute_delta; ΔEnergy |
| 6 | **Select** | Select | rank_operations_by_energy, filter_executable, select_hybrid |
| 7 | **Execute** | Execute | apply_and_verify (PatchExecutor) |
| 8 | **Learn** | Learn | record_outcome → EventLog, adapt_weights (default on) |

---

## 2. Контракты этапов

### 2.1 Analyze

| Атрибут | Значение |
|---------|----------|
| **Вход** | `path: Path`, `quiet: bool`, `run_scan: Callable` |
| **Выход** | `bool` — успех сканирования |
| **Артефакты** | `self_map.json` на диске |
| **Модули** | `eurika.orchestration.prepare.run_fix_scan_stage` |

**Зависимости:** pipeline runtime_scan → self_map.json. Без self_map следующие этапы не выполняются.

---

### 2.2 Build State

| Атрибут | Значение |
|---------|----------|
| **Вход** | `path: Path`, `patch_plan: PatchPlan | None` (опционально для risk_report) |
| **Выход** | `ExecutionContext` с `snapshot_before: ArchitectureSnapshot` |
| **Артефакты** | `ctx.snapshot_before`, `ctx.risk_report` (после Generate) |
| **Модули** | `_build_execution_context` → `ArchitectureSnapshot.from_core_snapshot(core_snap)` |

**Источник состояния:** `build_snapshot_from_self_map(self_map_path)` → `ArchitectureSnapshot.from_core_snapshot`.

---

### 2.3 Generate (Hypotheses)

| Атрибут | Значение |
|---------|----------|
| **Вход** | `path`, `window`, `execution_context` (ctx.snapshot_before) |
| **Выход** | `result.output["proposals"]` с `patch_plan`, `operations` |
| **Артефакты** | `PatchPlan`, `list[OperationRecord]` |
| **Модули** | `run_fix_diagnose_stage` → `ArchReviewAgentCore` → `PlannerEngine` (extract_patch_plan_from_result) |

**Внутренний поток:** agent получает `ctx.snapshot_before` → `_structure_from_snapshot` → graph, summary, smells → planner строит candidates.

---

### 2.4 Simulate

| Атрибут | Значение |
|---------|----------|
| **Вход** | `path: Path`, `patch_plan: PatchPlan` |
| **Выход** | `Dict` (errors, would_skip, skipped_reasons) |
| **Артефакты** | `ctx.simulation_result = SimulationResult.from_simulate_dict(simulation)` |
| **Модули** | `patch_engine.simulate_patch`, `eurika.execution.simulate_patch` |

**Gate:** при `simulation["errors"]` → abort apply, early exit.

---

### 2.5 Evaluate

| Атрибут | Значение |
|---------|----------|
| **Вход** | `old_snap`, `new_snap` (ArchitectureSnapshot), `metrics_from_graph` |
| **Выход** | `verify_metrics: {before_score, after_score, success}` |
| **Артефакты** | `ctx.delta_score = after_score - before_score` |
| **Модули** | `eurika.evaluation.compute_delta` (DeltaEvaluator) |

**Когда вызывается:** после apply_and_verify + rescan → `enrich_report_with_rescan` → `compute_delta(old_snap, new_snap, metrics_from_graph)`.

---

### 2.6 Select

| Атрибут | Значение |
|---------|----------|
| **Вход** | `operations`, `graph`, `smells`; policy, campaign, session filters |
| **Выход** | `list[OperationRecord]` — отфильтрованные и отсортированные |
| **Артефакты** | `rank_operations_by_energy` → heuristic ΔEnergy; `filter_executable`, `select_hybrid_operations` |
| **Модули** | `eurika.reasoning.planner.energy_ranking.rank_operations_by_energy`, `prepare._filter_and_policy_operations` |

**Порядок:** prepend (clean_imports, code_smells) → drop_noop → deprioritize → runtime_policy → campaign_memory → session_rejections.

---

### 2.7 Execute

| Атрибут | Значение |
|---------|----------|
| **Вход** | `path`, `patch_plan`, `operations`, `verify_cmd`, `verify_timeout` |
| **Выход** | `FixReport` (modified, verify.success, operation_results) |
| **Артефакты** | изменённые файлы, backup, `report` |
| **Модули** | `apply_stage.execute_fix_apply_stage` → `apply_and_verify` (patch_engine/eurika.execution) |

**Safety:** simulation-first; при errors в simulate — abort без apply.

---

### 2.8 Learn

| Атрибут | Значение |
|---------|----------|
| **Вход** | `path`, `result`, `operations`, `report`, `verify_success` |
| **Выход** | — (side-effect) |
| **Артефакты** | EventLog (record_outcome), SessionMemory, adapt_weights (default on) |
| **Модули** | `append_fix_cycle_memory` → `record_outcome(..., delta_energy=ctx.delta_score)`; `adapt_weights_from_experience` (default; EURIKA_WEIGHT_ADAPTATION=0 отключает) |

---

## 3. Поток данных (ExecutionContext)

```
Analyze     → self_map.json
Build State → ctx.snapshot_before
Generate    → ctx.risk_report, patch_plan, operations
Simulate    → ctx.simulation_result
Select     → operations (filtered)
Execute    → report.modified, report.verify, ctx.snapshot_after (после rescan)
Evaluate   → ctx.delta_score, report.verify_metrics
Learn      → record_outcome(modules, ops, risks, verify_success, delta_energy)
```

---

## 4. Связь с fix-cycle pipeline

| fix-cycle §0.5.1 | Cognitive Loop |
|------------------|----------------|
| Input | Analyze + Build State |
| Plan | Generate + Select |
| Validate | Simulate (gate) |
| Apply | Execute |
| Verify | Execute (внутри apply_and_verify) + Evaluate (rescan) |
| Learn | Learn |

---

## 5. Порядок вызовов в коде

```
prepare_fix_cycle_operations:
  1. run_fix_scan_stage        [Analyze]
  2. _build_execution_context  [Build State]
  3. run_fix_diagnose_stage    [Generate] (использует ctx.snapshot_before)
  4. extract_patch_plan, _filter_and_policy_operations [Select]
     - rank_operations_by_energy внутри planner (при diagnose)
     - apply_runtime_policy, campaign_memory, session_rejections

execute_fix_apply_stage:
  5. simulate_patch            [Simulate]
  6. apply_and_verify          [Execute]
  7. run_scan (rescan)         [для Evaluate]
  8. enrich_report_with_rescan → compute_delta [Evaluate]
  9. append_fix_cycle_memory   [Learn]
```

---

## 6. Ссылки

- Architecture.md §0.9, §0.5.1
- docs/archive/EXECUTION_MODEL_PLAN.md
- docs/archive/review.md (Cognitive Loop)
- eurika/orchestration/prepare.py, apply_stage.py
