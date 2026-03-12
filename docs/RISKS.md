# Архитектурные риски (Review IV)

**Источник:** docs/review.md §риски. Мониторинг и статус митигации.

---

## 1. Fragmented Intelligence

**Проблема:** Логика распределена по многим модулям; нет одного центра принятия решений.

| Статус | Митигация |
|--------|-----------|
| Частично | R2: planner → facade; learning/feedback → eurika.storage; architecture_pipeline отложен |
| Остаётся | Единый reasoning engine (analyzer/generator/simulator/evaluator) — R2, R6 |

---

## 2. Patch Explosion (refactor cascade)

**Проблема:** 1 проблема → 5 патчей → 20 новых проблем.

| Статус | Митигация |
|--------|-----------|
| ✅ | simulate_patch перед apply; energy_ranking; EURIKA_ENERGY_CAP; EURIKA_MAX_OPS_PER_CYCLE |
| — | Patch Simulation Layer — уже есть simulate → validate → apply |

---

## 3. Memory Without Learning

**Проблема:** memory хранит данные, но не извлекает знания.

| Статус | Митигация |
|--------|-----------|
| ✅ | record_outcome; get_merged_learning_stats; Learning Loop; filter_policy, deprioritize; pattern_library |
| Частично | adapt_weights_from_experience — включено по умолчанию (EURIKA_WEIGHT_ADAPTATION=0 отключает) |

---

## 4. Graph Only Sees Dependencies

**Проблема:** Граф видит imports/modules, не видит call graph, data flow, test coverage.

| Статус | Митигация |
|--------|-----------|
| Открыто | project_graph — dependency only; call/data flow — вне текущего scope |

---

## 5. No Architectural Scoring

**Проблема:** Нет единой оценки архитектуры до/после.

| Статус | Митигация |
|--------|-----------|
| ✅ | MetricVector, EnergyModel; delta_score в ExecutionContext; compute_delta (delta_evaluator) |

---

## 6. No Strategy Layer

**Проблема:** Реактивное поведение; нет приоритизации.

| Статус | Митигация |
|--------|-----------|
| Частично | priority_from_graph; targets_from_graph; decay; learning_stats sort; policy |

---

## 7. Analyzer Lock

**Проблема:** Один анализатор — точка отказа.

| Статус | Митигация |
|--------|-----------|
| Частично | smells (detector, rules); dependency_firewall; plugins (registry) |
| — | Несколько analyzer plugins — частично через smells |

---

## 8. No Safety Layer

**Проблема:** AI меняет код без гарантий.

| Статус | Митигация |
|--------|-----------|
| ✅ | verify_patch; rollback; policy (deny high-risk); critic; hybrid approval |

---

## 9. No Long-Term Evolution

**Проблема:** Система не улучшает свои стратегии.

| Статус | Митигация |
|--------|-----------|
| Частично | adapt_weights_from_experience; learning_stats; decay; meta_controller |
| — | strategy_learning — через weight adaptation |

---

## 10. No Multi-Agent System

**Проблема:** Один агент вместо ролей (architect, analyzer, refactor, critic).

| Статус | Митигация |
|--------|-----------|
| Открыто | agent_core; architect, planner — отдельные модули, не multi-agent |

---

## Сводка

| Риск | Статус |
|------|--------|
| 1. Fragmented Intelligence | Частично |
| 2. Patch Explosion | ✅ |
| 3. Memory Without Learning | ✅ |
| 4. Graph Only Sees Dependencies | Открыто |
| 5. No Architectural Scoring | ✅ |
| 6. No Strategy Layer | Частично |
| 7. Analyzer Lock | Частично |
| 8. No Safety Layer | ✅ |
| 9. No Long-Term Evolution | Частично |
| 10. No Multi-Agent | Открыто |

**Ссылки:** docs/REVIEW_2026_IV_ANALYSIS.md, docs/review.md, docs/BOUNDED_EVOLUTION.md.
