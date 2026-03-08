# Целевая структура v3.x (R6)

**Источник:** docs/review.md, ROADMAP §5.8. Формализация целевой структуры без реализации.

---

## 1. Целевые директории

```
eurika/
    world_model/      # Модели состояния и метрик
    reasoning/        # Анализ, генерация, симуляция, оценка
    execution/        # Patch executor, verifier
    memory/           # Experience, weights (или storage/)
```

**Отличие от текущего:** world_model выделен; execution отделён от patch_engine (root); memory — фасад над storage.

---

## 2. Маппинг текущее → целевое

| Целевое | Текущее | Примечание |
|---------|---------|------------|
| **world_model/** | eurika/analysis/metric_vector, energy_model | Архитектурное состояние; EnergyModel — центр scoring (R3) |
| **world_model/** | eurika/reasoning/planner/models (ArchitectureSnapshot) | Или в core/ |
| **reasoning/** | eurika/reasoning/* | planner, architect, graph_ops, advisor |
| **reasoning/analyzer** | eurika/smells, eurika/analysis | build_graph_and_summary_from_self_map (R2) |
| **reasoning/planner** | eurika/reasoning/planner/* | Уже есть engine, facade |
| **reasoning/simulator** | patch_engine.simulate_patch | Или в execution |
| **execution/** | patch_engine, patch_apply | patch_executor, verifier |
| **memory/** | eurika/storage (EventLog, LearningStore, weight_store) | experience_store, weight_store |

---

## 3. Контракты (из review)

| Слой | Ответственность | Запрещено |
|------|-----------------|-----------|
| world_model | Модели (MetricVector, EnergyModel, Snapshot) | Бизнес-логика |
| reasoning | Анализ, план, симуляция, оценка | Мутация, запись, применение |
| execution | apply, verify, rollback | Решения, планирование |
| memory | Запись/чтение событий, весов | Вызов planner, изменение graph |

---

## 4. Порядок миграции

1. **world_model** — ✅ P7 eurika/world_model/
2. **execution** — ✅ P9 eurika/execution/ alias над patch_engine.
3. **memory** — ✅ eurika/memory/ alias над storage.
4. **reasoning** — уже консолидирован; analyzer/generator/simulator — как функции, не обязательно отдельные модули.

**Приоритет:** R2, R3 выполнены. P7 ✅ eurika/world_model/ — re-exports MetricVector, EnergyModel, WeightVector из analysis.

---

## 5. Связь с ROADMAP

- §5.7 Execution Model — MetricVector, EnergyModel, ΔEnergy
- §5.8 Целевое разделение слоёв
- docs/RISKS.md — Fragmented Intelligence (R1)

**Не начинать** полную реструктуризацию до:
- architecture_pipeline консолидирован (R2)
- EnergyModel явно в центре (R3)

---

## Ссылки

- docs/REVIEW_2026_IV_ANALYSIS.md R6
- docs/review.md (AI-ядро, память)
- docs/Architecture.md §0.9
