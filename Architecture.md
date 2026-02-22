# Eurika Architecture v0.6

---

## 0. Layer Map (ROADMAP 2.8.1, 3.1-arch.1)

Формальная карта слоёв и правил зависимостей. Ссылки: **ROADMAP.md** § Фаза 2.8, § Фаза 3.1-arch, **CLI.md** § Рекомендуемый цикл, **review.md** §6.

Нотация L0–L6 соответствует рекомендациям review v3.0.1.

### 0.1 Слои (снизу вверх, L0 → L6)

```
L0: Infrastructure  ← IO, FS, backup/restore, paths, low-level storage
L1: Core            ← graph model, snapshot, pipeline
L2: Analysis        ← smells, graph, metrics, scanner
L3: Planning        ← patch plan, action plan, architecture planner
L4: Execution       ← patch apply, verify, rollback, refactor
L5: Reporting       ← отчёты, форматирование, JSON/Markdown
L6: CLI             ← command parsing, dispatch, orchestration wiring
```

**Правило:** модуль слоя N может зависеть только от слоёв 0..N−1 (и от того же слоя). Зависимость «вверх» (N → N+k, k>0) запрещена.

### 0.2 Allowed Dependencies

| From layer | May import from |
|------------|-----------------|
| L0 Infrastructure | stdlib, same layer |
| L1 Core | L0 |
| L2 Analysis | L1, L0 |
| L3 Planning | L2, L1, L0 |
| L4 Execution | L3, L2, L1, L0 |
| L5 Reporting | L4..L0 |
| L6 CLI | L5..L0 |

### 0.3 Mapping modules → layers (v3.1)

| Layer | Модули / пакеты |
|-------|-----------------|
| L0 Infrastructure | `eurika/utils/fs`, `patch_apply_backup`, `eurika/storage/paths` |
| L1 Core | `core/pipeline`, `core/snapshot`, `project_graph`, `project_graph_api`, `self_map_io` |
| L2 Analysis | `code_awareness*`, `eurika/analysis/*`, `eurika/smells/*`, `graph_analysis`, `semantic_architecture`, `system_topology` |
| L3 Planning | `architecture_planner*`, `eurika/reasoning/planner*`, `action_plan*`, `patch_plan` |
| L4 Execution | `patch_apply`, `patch_engine*`, `patch_apply_handlers`, `eurika/refactor/*`, `executor_sandbox` |
| L5 Reporting | `report/ux`, `eurika/reporting/*`, `architecture_*` (summary, history, diff, feedback, advisor) |
| L6 CLI | `eurika_cli`, `cli/` (wiring, handlers, orchestration) |

### 0.4 Anti-patterns (запрещённые зависимости)

❌ **Analysis → Execution:** `eurika/smells/*` не должен импортировать `patch_apply` или `patch_engine`.

❌ **Planning → Execution:** `architecture_planner` не должен вызывать `apply_patch_plan` напрямую; планирование и исполнение разделены.

❌ **Infrastructure → Planning:** CLI-слой не должен импортировать `build_patch_plan` или `architecture_planner` напрямую; маршрут через orchestration/deps и фасады.

❌ **Cross-layer facade bypass:** Вызов `patch_apply.apply_patch_plan` из CLI вместо `patch_engine.apply_patch` — нарушение; patch-подсистема доступна только через фасад `patch_engine`.

### 0.5 Planner–Executor Contract (ROADMAP 3.1-arch.6)

| Роль | Модули | Ответственность | Контракт |
|------|--------|-----------------|----------|
| **Planner** | architecture_planner*, eurika/reasoning/planner*, planner_patch_ops | Строит план (PatchPlan, dict) из summary/smells/graph | Не импортирует patch_apply, patch_engine. Выход: `plan.to_dict()` или `{"operations": [...]}` |
| **Executor** | patch_engine, patch_apply, executor_sandbox | Применяет план, verify, rollback | Вход: dict с ключом `operations`; вызывает patch_engine.apply_patch или apply_and_verify |

Планирование и исполнение не знают деталей друг друга: Planner выдаёт структурированный dict; Executor принимает его и выполняет.

### 0.6 Verification

Автоматическая проверка: `tests/test_dependency_guard.py` (ROADMAP 2.8.2).
- `test_no_forbidden_imports` — строгий guard для явных запрещённых импортов.
- `test_layer_firewall_contract_soft_start` — проверка layer-контракта L0–L6 в soft-start режиме.
  Для hard-gate режима в CI включить `EURIKA_STRICT_LAYER_FIREWALL=1`.
- Текущее состояние R4: **0 нарушений / 0 waiver-исключений** в baseline.
- Временные допуски (если появятся) фиксируются только в `LAYER_FIREWALL_EXCEPTIONS` (обязателен `reason`).
Команды:
- `pytest tests/test_dependency_guard.py -v`
- `EURIKA_STRICT_LAYER_FIREWALL=1 pytest tests/test_dependency_guard.py -v`

### 0.7 API Boundaries (ROADMAP 3.1-arch.2)

Каждая подсистема экспортирует ограниченный публичный API через `__all__`. Остальное считается private.

| Подсистема | Публичные точки входа |
|------------|------------------------|
| **Storage** | `ProjectMemory`, `event_engine`, `SessionMemory` |
| **Agent** | `run_agent_cycle`, `DefaultToolContract` |
| **Patch Engine** | `apply_and_verify`, `apply_patch`, `verify_patch`, `rollback_patch` |
| **Planning** | `build_patch_plan`, `build_plan`, `build_action_plan` (architecture_planner) |
| **Reasoning** | `advisor`, `architect`, `planner` |
| **CLI orchestration** | `run_doctor_cycle`, `run_full_cycle`, `prepare_fix_cycle_operations`, `execute_fix_apply_stage` |
| **CLI wiring** | `build_parser`, `dispatch_command` |

Ключевые пакеты с `__all__`: `eurika.storage`, `eurika.agent`, `eurika.reasoning`, `eurika.refactor`, `eurika.knowledge`, `eurika.analysis`, `eurika.smells`, `eurika.evolution`, `eurika.reporting`, `eurika.core`, `patch_engine`, `cli.orchestration`, `cli.wiring`.

### 0.8 File Size Limits (ROADMAP 3.1-arch.3)

| Лимит | Правило |
|-------|---------|
| >400 LOC | Кандидат на разбиение |
| >600 LOC | Обязательно делить |

Проверка: `eurika self-check .` выводит блок FILE SIZE LIMITS; отдельно: `python -m eurika.checks.file_size [path]`.

---

## 1. Target Project Structure (v1.0)

Целевой скелет проекта. Текущий код — плоская структура; миграция к этой layout — в ROADMAP.

```
eurika/
├── cli/
│   └── main.py
│
├── core/
│   ├── pipeline.py          # единый orchestration pipeline
│   ├── snapshot.py          # ArchitectureSnapshot
│   ├── context.py           # runtime context
│   └── config.py
│
├── analysis/
│   ├── scanner.py           # AST + import scanning
│   ├── graph.py             # ProjectGraph
│   ├── metrics.py           # метрики сложности
│   └── cycles.py
│
├── smells/
│   ├── detector.py
│   ├── rules.py
│   └── models.py
│
├── evolution/
│   ├── history.py
│   ├── diff.py
│   └── trend.py
│
├── reasoning/               # будущий AI-слой
│   ├── advisor.py
│   ├── planner.py
│   └── heuristics.py
│
├── reporting/
│   ├── text.py
│   ├── markdown.py
│   └── json.py
│
├── storage/
│   └── persistence.py
│
└── utils/
    ├── fs.py
    └── logging.py
```

### Маппинг текущего кода (v0.9) → target

| Target | Текущие модули |
|--------|----------------|
| cli/main.py | eurika_cli.py, cli/handlers.py, cli/core_handlers.py, cli/agent_handlers.py |
| core/ | core/pipeline.py, core/snapshot.py; фасад eurika.core |
| analysis/ | code_awareness.py, project_graph*.py, self_map_io.py, semantic_architecture.py, system_topology.py; **реализация в пакете:** eurika.analysis.metrics (из graph_analysis); фасады graph, scanner, self_map, topology, cycles |
| smells/ | **реализация в пакете:** eurika.smells.detector, models, health, advisor, summary (из architecture_diagnostics, architecture_smells, architecture_health, architecture_advisor, architecture_summary); плоские файлы — реэкспорты |
| evolution/ | **реализация в пакете:** eurika.evolution.history, diff (из architecture_history, architecture_diff); плоские файлы — реэкспорты |
| reasoning/ | agent_core*.py, architecture_planner.py, action_plan.py, patch_plan.py, patch_apply.py, executor_sandbox.py, memory, reasoner_dummy, selector; **eurika.reasoning.architect** (интерпретация в стиле архитектора; опционально LLM: OpenAI или OpenRouter через OPENAI_BASE_URL, OPENAI_MODEL) |
| reporting/ | report/ux.py, report/architecture_report.py |
| api/ | eurika.api (get_summary, get_history, get_diff); eurika serve — HTTP JSON API для UI (ROADMAP §2.3) |
| storage/ | **ProjectMemory** (eurika.storage) — единая точка входа: .feedback, .learning, .observations, .history; реализации: observation_memory.py, architecture_feedback.py, architecture_learning.py, eurika.evolution.history |
| utils/ | (пока нет) |

**Артефакты (генерируемые):** `self_map.json`, `architecture_history.json`, `eurika_observations.json`, `eurika_events.json` (единый лог событий), `architecture_feedback.json`, `architecture_learning.json`, `.eurika_backups/<run_id>/`

---

## 2. Design Principles

* **Core ≠ Intelligence** — Core only orchestrates lifecycle and contracts
* **No magic** — every decision is traceable and reproducible
* **Isolation first** — modules are dumb, explicit, testable
* **No self-modifying code** — only proposals, never execution
* **Human-in-the-loop** by design

### Цель продукта 1.0 (по review.md)

**Eurika = автономный архитектурный ревьюер и рефакторинг-ассистент:** анализирует проект → находит проблемы → формирует план исправлений → предлагает (и при желании применяет) патчи. Не «архитектурный симулятор», а «инженер-практик»: меньше самоанализа ради самоанализа, больше понятных действий (diagnose → plan → patch → verify → learn).

### Замкнутый цикл (целевой)

Целевой поток для продуктового сценария:

```
scan → diagnose → plan → patch → verify → learn
```

**Реализовано:** один сценарий оформлен как `eurika fix` (и `eurika agent cycle`): scan → arch-review → patch-apply --apply --verify; при успехе — rescan и rescan_diff; при провале verify — подсказка rollback. Learning записывается в ProjectMemory.learning.

### Patch Engine (2.1)

**Модуль `patch_engine.py`** — фасад «применить план → проверить → откат». Текущая реализация: apply_and_verify, rollback, list_backups. **Целевой API (по review.md):** явные операции **apply_patch(plan)**, **verify_patch()** (перескан + метрики), **rollback_patch()**; при провале verify — автоматический откат. Без этого Eurika не станет автономной. Детали — ROADMAP § «Этап 1 — Patch Engine».

### Консолидация памяти

Реализовано: **event_engine(project_root)** (eurika.storage.event_engine) — единая точка входа для журнала событий; хранилище eurika_events.json. Event { type, input, output/action, result, timestamp }; сериализация с полем `action`. **ProjectMemory.events** возвращает event_engine(project_root). Запись при scan и patch. Файлы feedback/learning/observations/history по-прежнему отдельные для своих API; единый лог «что произошло» — eurika_events.json.

### Оценка по review.md и направление 2.1

- **Актуальный review (review.md):** диагноз — «архитектурный аналитик с амбициями автономного агента»; таблица оценок (архитектура 8.5, код 8, концепция 9, операционность 5, продукт 5, потенциал 9.5); вывод — усиливать execution критично, LLM преждевременно; долгосрочная цель — полноценный AI-агент с самоусовершенствованием.
- **2.1 (план прорыва) выполнен:** Patch Engine (apply_patch, verify_patch, rollback_patch), Verify stage, Event Engine, три автофикса, CLI 4 режима — реализованы. Дальше — Knowledge Layer, стабилизация, использование.

### Knowledge Layer / онлайн-слой (после 1.0, по review.md)

Подключать внешние источники (документация, релизы, PEP) **только после** стабилизации детерминированного ядра. Не «поиск в интернете», а **Knowledge Provider Layer**: абстракция `KnowledgeProvider.query(topic) -> StructuredKnowledge`; реализации — Local, OfficialDocs, ReleaseNotes, StaticAnalyzer. LLM формулирует гипотезу → Knowledge layer проверяет по отобранным источникам → план уточняется → Patch engine применяет детерминированный патч → Verify. Онлайн-слой имеет смысл только когда Eurika уже автономный агент с verify и rollback. Детали — **review.md** (раздел про онлайн-ресурсы и Knowledge Layer).

---

## 3. High-Level System Layout

Ядро Eurika — **Architecture Awareness Engine** с единым orchestration pipeline.

### 3.1 Pipeline (v0.5+)

```
CLI (eurika_cli)  →  parser + dispatch only
   ↓
cli/handlers      →  command logic
   ↓
runtime_scan      →  CodeAwareness writes self_map.json
   ↓
core/pipeline     →  run_full_analysis(), build_snapshot_from_self_map()
   ↓
_project_graph    →  граф зависимостей
   ↓
ArchitectureSmells / Diagnostics
   ↓
ArchitectureSummary
   ↓
ArchitectureAdvisor
   ↓
ArchitectureHistory  →  version, git_commit (opt), risk_score, trends
   ↓
report/architecture_report.render_full_architecture_report()
```

### 3.2 ArchitectureSnapshot (центральный объект)

```python
@dataclass
class ArchitectureSnapshot:
    root: Path
    graph: ProjectGraph
    smells: List[object]   # слой Core не зависит от concrete smell-типа
    summary: Dict
    history: Optional[Dict]  # trends, regressions, evolution_report
    diff: Optional[Dict]
```

Все модули (scan, arch-summary, arch-diff) работают через snapshot.

### 3.3 Ключевые принципы

* **read-only first** — модификация кода только по явному `--apply`;
* отчёт воспроизводим по self_map + исходникам;
* patch-apply (v0.4+): бэкапы в `.eurika_backups/`, verify (pytest), rollback.

---

## 4. Legacy Agent Core Design (зарезервировано для v0.2+)

Следующий раздел описывает проектируемый AgentCore для будущих версий.
В **v0.1 он не используется** и считается замороженным дизайном.

### 4.1 High-Level Agent Layout

```
InputEvent
   ↓
AgentCore.step()
   ↓
ContextBuilder
   ↓
Reasoner
   ↓
DecisionSelector
   ↓
Executor
   ↓
Result
   ↓
MemoryRecorder
```

AgentCore knows **nothing** about:

* finance
* files
* goals semantics
* personality
* self-improvement

### 4.2 Core Responsibilities

#### AgentCore

Responsibilities:

* manage one atomic `step`
* call modules in strict order
* enforce contracts
* collect traces

Non-responsibilities:

* reasoning logic
* memory logic
* domain logic
* safety logic

---

## 5. Module Contracts (AgentCore design)

### 5.1 InputEvent

```python
class InputEvent:
    type: str
    payload: dict
    source: str
    timestamp: float
```

---

### 5.2 Context

```python
class Context:
    event: InputEvent
    memory_snapshot: list
    system_state: dict
```

---

### 5.3 Reasoner

```python
class Reasoner:
    def propose(self, context) -> list[DecisionProposal]
```

Must:

* be stateless
* produce multiple options
* never execute

---

### 5.4 DecisionProposal

```python
class DecisionProposal:
    action: str
    arguments: dict
    confidence: float
    rationale: str
```

---

### 5.5 DecisionSelector

```python
class DecisionSelector:
    def select(self, proposals) -> DecisionProposal
```

Rules:

* deterministic
* explainable

---

### 5.6 Executor

```python
class Executor:
    def execute(self, decision) -> Result
```

Executor:

* has access only to allowed tools
* runs inside sandbox

---

### 5.7 Result

```python
class Result:
    success: bool
    output: dict
    side_effects: list
```

---

### 5.8 Memory

```python
class Memory:
    def snapshot(self) -> list
    def record(self, event, decision, result)
```

---

## 6. Forbidden Patterns

❌ Agent modifying its own code
❌ Reasoner executing actions
❌ Memory influencing execution directly
❌ CLI logic inside core
❌ Global mutable state

---

## 7. Evolution Path

* v0.1 — Architecture Awareness Engine (observe-only)
* v0.2 — AgentCore поверх анализатора
* v0.3 — learning via evaluation
* v0.4 — patch-apply, Learning Loop, cycle
* v0.5 — core/pipeline, ArchitectureSnapshot, CLI refactor
* v0.6 — History Engine (version, risk_score, per-smell regressions)

---

## 8. Jarvis Reality Check

Jarvis is NOT:

* conscious
* autonomous coder
* self-evolving god

Jarvis IS:

* tool orchestrator
* decision proposer
* risk-aware assistant
* bounded reasoning system

---

End of Architecture v0.6
