# Eurika Architecture v0.6

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
| reporting/ | report/ux.py |
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

**Явный модуль `patch_engine.py`:** фасад «применить план → проверить (pytest) → откат».

- **apply_and_verify(project_root, plan, backup=..., verify=...)** — вызов apply_patch_plan + при verify запуск pytest; возвращает отчёт с ключами modified, run_id, verify (success, returncode, stdout, stderr).
- **rollback(project_root, run_id=None)** — восстановление из `.eurika_backups/<run_id>` (при run_id=None — последний run).
- **list_backups(project_root)** — список доступных run_id.

План по-прежнему строится в arch-review (suggest_patch_plan); patch_plan.py и patch_apply.py остаются реализацией. Цикл fix и команда patch-apply с --verify используют patch_engine.apply_and_verify.

### Консолидация памяти

Реализовано: единый фасад **ProjectMemory(project_root)** (eurika.storage) — **.events** (единый лог), .feedback, .learning, .observations, .history. **Единая модель события** (review.md): Event с полями type, input, output, result, timestamp; хранилище EventStore, файл eurika_events.json. События пишутся при scan (runtime_scan) и при patch (cycle, patch-apply --verify). Остальные файлы: architecture_feedback.json, architecture_learning.json, eurika_observations.json, architecture_history.json.

### Оценка по review.md и направление 2.1

- **2.0** — «архитектурный аналитик»: анализ и отчёты сильны, действие (patch + verify) есть, но не выделено как главный фокус.
- **2.1** — цель «инженерный инструмент»: явный Patch Engine, граф как источник решений и планирования, единая модель Event, упрощение мета-слоёв. Детали — в **review.md** и ROADMAP § «Версия 2.1».

---

## 3. High-Level System Layout

Ядро Eurika — **Architecture Awareness Engine** с единым orchestration pipeline.

### 3.1 Pipeline (v0.5+)

```
CLI (eurika_cli)  →  parser + dispatch only
   ↓
cli/handlers      →  command logic
   ↓
core/pipeline     →  run_full_analysis(), build_snapshot_from_self_map()
   ↓
CodeAwareness     →  self_map.json
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
render_full_architecture_report()
```

### 3.2 ArchitectureSnapshot (центральный объект)

```python
@dataclass
class ArchitectureSnapshot:
    root: Path
    graph: ProjectGraph
    smells: List[ArchSmell]
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

End of Architecture v0.1
