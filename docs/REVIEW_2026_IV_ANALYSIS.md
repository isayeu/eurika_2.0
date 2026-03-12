# Review 2026 IV — анализ и задачи

**Источник:** docs/review.md (новый ревью-архив).

**Дата фиксации:** 2026-03-08.

---

## 1. Ключевые выводы


| Критерий              | Оценка | Комментарий                           |
| --------------------- | ------ | ------------------------------------- |
| Архитектурная амбиция | 9/10   | Сильная идея                          |
| Модульная структура   | 7/10   | Доменные зоны есть, границы мягкие    |
| AI-модель             | 7/10   | EnergyModel в центре (R3 ✅); Cognitive Loop формализован (R8) |
| Инженерная дисциплина | 6/10   | Рост быстрее стабилизации             |


**Главный риск:** Eurika — или полноценный AI-архитектор (EnergyModel + WorldState в центре), или «огромный набор инструментов анализа».

---

## 2. Что уже сделано (по ревью)


| Рекомендация              | Статус                                 |
| ------------------------- | -------------------------------------- |
| MetricVector              | ✅ eurika/analysis/metric_vector.py     |
| EnergyModel               | ✅ eurika/analysis/energy_model.py      |
| Planner на ΔEnergy        | ✅ energy_ranking.py, EURIKA_ENERGY_CAP |
| Исключение runtime-мусора | ✅ .gitignore, MANIFEST.in              |


---

## 3. Задачи из ревью

### 3.1 Высокий приоритет


| #   | Задача                      | Источник | Действие                                                                                            |
| --- | --------------------------- | -------- | --------------------------------------------------------------------------------------------------- |
| R1  | **pycache** в архиве/релизе | §1       | ✅ scripts/release_check.sh шаг 8b: build --sdist + grep **pycache**/.pyc                            |
| R2  | Единый reasoning engine     | §4, §9   | ✅ planner→facade; learning/feedback→storage; pipeline→eurika.analysis.build_graph_summary |
| R3  | EnergyModel в центр         | §6       | ✅ Architecture.md §0.9; planner→energy_ranking→ΔEnergy; delta_score→record_outcome                   |
| R4  | Изолировать Chat API        | §5       | ✅ API_BOUNDARIES + SubsystemBypassRule (chat → patch/orchestration)                                 |


### 3.2 Средний приоритет


| #   | Задача                                | Источник |
| --- | ------------------------------------- | -------- |
| R5  | Learning центральный                  | §7       | ✅ Learning Loop в MEMORY.md, Architecture.md §0.5.1 |
| R6  | Целевая структура v3.x                | §5, §3   | ✅ docs/TARGET_V3_STRUCTURE.md — world_model/reasoning/execution/memory |
| R7  | Риски (Fragmented Intelligence и др.) | §риски   | ✅ docs/RISKS.md — 10 рисков, статус митигации |


### 3.3 Долгосрочные


| #   | Задача                                                                                            | Статус |
| --- | ------------------------------------------------------------------------------------------------- | ------ |
| R8  | Cognitive Loop: Analyze → Build State → Generate → Simulate → Evaluate → Select → Execute → Learn | ✅ docs/COGNITIVE_LOOP.md — полная формализация, контракты этапов |
| R9  | Experience Memory с delta_energy                                                                  | ✅ P6: W-=lr×ΔE при EURIKA_WEIGHT_ADAPTATION_DELTA_ENERGY=1 |
| R10 | Plugin system, Knowledge Graph                                                                    | ✅ plugins ✓; code_graph, build_test_links, get_knowledge_graph, GET /api/test_links, /api/knowledge_graph |


---

## 4. Антипаттерны (избегать)

- architecture_* как отдельные роли — должны быть функциями одного reasoning engine
- Добавление фичей до стабилизации ядра
- API протекает внутрь логики

---

## 5. Связь с ROADMAP

- **§5.7 Execution Model** — MetricVector, EnergyModel, ΔEnergy уже есть.
- **§5.8 Review сводка** — выводы Review IV.
- **R1–R10** — задокументированы и реализованы. world_model, execution, memory (TARGET_V3 §4) — ✅.

---

## 6. Связанные документы

| Документ | Назначение |
|----------|-------------|
| ROADMAP.md | §5.10 Review IV, приоритеты |
| CYCLE_REPORT.md | Снапшоты, #150–155 |
| RISKS.md | 10 рисков, митигация (R7) |
| TARGET_V3_STRUCTURE.md | v3.x, маппинг (R6) |
| R10_EXTENSIBILITY_AND_KNOWLEDGE.md | Plugin system, KG (R10) |
| COGNITIVE_LOOP.md | R8 формализация |
| KNOWLEDGE_GRAPH_DESIGN.md | R10 KG схема |

