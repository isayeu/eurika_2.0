# Eurika 2.0 — ROADMAP до v1.0

Единый план задач. Контракт — в SPEC.md.

---

## Текущее состояние (v1.2.3)

**Выполнено (включая 2.1):**
- Всё перечисленное в v0.8 (pipeline, Smells 2.0, CLI рефакторинг, self-check, History v0.6, CLI UX, документация)
- Скелет пакета `eurika/` по target layout (Architecture.md §1): core, analysis, smells, evolution, reporting, storage, reasoning, utils, **api**
- Фасады и импорты среднего слоя из `eurika.*`; фасады self_map, topology в analysis
- **Реализация в пакете:** eurika.smells (detector, models, health, advisor, summary), eurika.analysis.metrics, eurika.evolution (history, diff). Плоские файлы — реэкспорты.
- **JSON API (§2.3):** eurika.api (get_summary, get_history, get_diff), `eurika serve` (HTTP GET /api/summary, /api/history, /api/diff)
- **ROADMAP 2.1:** Patch Engine, Event model, граф в планировании, remove_cyclic_import (AST-based)

**Оценка:** ядро стабилизировано; разделы 1–6 выполнены; 2.1 — «инженерный инструмент» достигнут.

---

## Следующий шаг

👉 **v1.2.3** ✓ (extract_class, split_module fallback, eurika_fix_report). Следующее: god_class detection.

---

## Стратегия выхода в 1.0

| Версия | Фокус |
|--------|-------|
| v0.5 | стабилизация pipeline ✓ |
| v0.6 | history + diff ✓ |
| v0.7 | CLI UX ✓ |
| v0.8 | smells 2.0 ✓ |
| v0.9 | layout skeleton + eurika.* imports + документация ✓ |
| v1.0 | релиз ✓ |

---

## 1. Архитектурная целостность

- [x] Pipeline: scan → graph → smells → summary → history → diff → report
- [x] ArchitectureSnapshot как единый объект
- [x] core/pipeline.py, cli/handlers.py
- [x] Скелет eurika/ + фасады + импорты среднего слоя (analysis, smells.rules, evolution, reporting, self_map, topology)
- [x] Перенос реализации в eurika/*: smells (detector, models, health, advisor), analysis.metrics; плоские файлы — реэкспорты
- [x] architecture_summary → eurika.smells.summary (реализация в пакете, плоский — реэкспорт)
- [x] evolution (history, diff) → eurika.evolution.history, eurika.evolution.diff (реализация в пакете, плоские — реэкспорты; architecture_diff.py сохраняет CLI)

---

## 2. Architecture History Engine

### 2.1 Модель данных
- [x] version (pyproject.toml)
- [x] git_commit (опционально)
- [x] diff metrics (дельты, не только абсолюты)

### 2.2 Регрессии
- [x] god_module, bottleneck, hub — отдельно
- [x] risk score (0–100)

### 2.3 Будущее
- [x] JSON API под future UI: `eurika.api` (get_summary, get_history, get_diff), `eurika serve` (GET /api/summary, /api/history, /api/diff)

---

## 3. Smell Engine

- [x] Уровень серьёзности: low / medium / high / critical (severity_to_level)
- [x] Remediation hints (что делать) — REMEDIATION_HINTS, get_remediation_hint
- [x] Корреляция со history — Smell history (per-type counts in evolution_report)

---

## 4. Architecture Diff Engine

- [x] Топ-модули по росту fan-in
- [x] Модули, ставшие bottleneck
- [x] Деградация maturity
- [x] Блок "Recommended actions: refactor X, split Y, isolate Z"

---

## 5. CLI

### 5.1 Команды
- [x] eurika scan ., arch-summary, arch-history, arch-diff, self-check
- [x] eurika history (алиас arch-history)
- [x] eurika report (summary + evolution report)
- [x] eurika explain module.py
- [x] eurika serve [path] (JSON API для UI)

### 5.2 UX
- [x] Цветной вывод (--color / --no-color)
- [x] ASCII charts (health score, risk score)
- [x] Markdown (--format markdown)

---

## 6. Документация

- [x] README, Architecture, CLI.md, THEORY.md

---

## Чеклист перед v1.0 (выполнен)

- [x] Разделы 1–6 ROADMAP выполнены (архитектура, history, smells, diff, CLI, документация)
- [x] JSON API и eurika serve реализованы
- [x] Версия обновлена на 1.0.0, CHANGELOG v1.0.0 записан

---

## 7. Мини-AI слой (после v1.0)

- [x] Интерпретация архитектуры: `eurika architect [path]` — шаблонная сводка + опционально LLM (OPENAI_API_KEY; поддержка OpenRouter через OPENAI_BASE_URL, OPENAI_MODEL); ответ в стиле "архитектор проекта"
- [x] Генерация рефакторинг-плана (эвристики): `eurika suggest-plan [path]` и `eurika.reasoning.refactor_plan.suggest_refactor_plan` — из summary/risks или из build_recommendations; LLM — в перспективе
- [ ] Расширение: больше подсказок в стиле архитектора (связка с patch-plan, explain)

---

## Этапы v0.1–v0.7 (выполнены)

- **0–8**: Заморозка контракта, аудит, core, memory, reasoning loop, code awareness, sandbox, feedback, freeze
- **A–C**: AgentCore (arch-review, arch-evolution), FeedbackStore, SPEC v0.2
- **D**: Prioritize modules
- **E–H**: Action plan, patch apply, learning loop, cycle
- **I–J**: Pipeline, ArchitectureSnapshot, self-check
- **K–L**: History v0.6 (version, git, risk_score), документация §6, CLI v0.7
- **M**: Smells v0.8 (severity_level, remediation_hints)

---

## Продукт 1.0 (по review.md)

Ориентир: *«Архитектурный инженер-практик»* — не только анализ, но и понятные действия. Риск: «умный, но бесполезный»; противодействие — замкнутый цикл и один чёткий сценарий.

### Цель продукта

- **Eurika = автономный архитектурный ревьюер и рефакторинг-ассистент:** анализирует → находит проблемы → формирует план → предлагает патчи (и при желании применяет с verify).

### TODO до продуктовой 1.0

- [x] **Консолидация памяти:** единый контракт и точка входа — `eurika.storage.ProjectMemory(project_root)` (`.feedback`, `.learning`, `.observations`, `.history`); файлы по-прежнему architecture_feedback.json, architecture_learning.json, eurika_observations.json, architecture_history.json. Вызовы переведены на ProjectMemory в cli/agent_handlers, agent_core_arch_review, runtime_scan, architecture_pipeline, core/pipeline, eurika.api.
- [x] **Замкнутый цикл в одном сценарии:** явный поток `scan → diagnose → plan → patch → verify → learn`; оформлен как `eurika fix` (и `eurika agent cycle`).
- [x] **Killer-feature:** remove_cyclic_import, clean-imports (мёртвые импорты), eurika fix с итоговой сводкой.
- [x] **CLI как продукт:** 4 режима — `eurika scan`, `eurika doctor` (report + architect, без патчей), `eurika fix` (полный цикл = agent cycle), `eurika explain <module>`.

### Уже есть (не дублировать)

- Pipeline scan → graph → smells → summary → history → diff → report.
- patch-apply, --verify, learning loop, architecture_history, evolution_report.
- `eurika architect` (интерпретация), `eurika explain`, JSON API, self-check.

---

## Версия 2.1 (по review.md)

Оценка review: 2.0 — «архитектурный аналитик»; цель 2.1 — «инженерный инструмент». Путь: инженерный (конкретная польза, 3 типа автофиксов, стабильный CLI), не академический.

| Элемент | Статус | Задача |
|--------|--------|--------|
| **Patch Engine** | ✓ | Модуль `patch_engine.py`: apply_and_verify, rollback, list_backups; cycle и patch-apply --verify переведены на фасад |
| **Verify stage** | ✓ | После patch: перескан, pytest; при провале — подсказка rollback |
| **Замкнутый цикл** | ✓ | `eurika fix` = scan → diagnose → plan → patch → verify → learn |
| **Единая модель Event** | ✓ | Event (type, input, output, result, timestamp), EventStore в eurika.storage.events, ProjectMemory.events; запись при scan и patch (eurika_events.json) |
| **Граф как инструмент** | ✓ | Граф передаётся в build_patch_plan; graph_ops даёт конкретные hints: cycle break edge, facade candidates, split hints |
| **Архитектурные операции** | ✓ | Remove Cyclic Import ✓; Split Module ✓; Extract Class ✓ (методы без self → статик) |

Детальный разбор — в **review.md**.

---

## Главное правило

> Если модуль нельзя чётко протестировать — он не готов к существованию.
