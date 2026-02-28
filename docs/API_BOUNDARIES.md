# API Boundaries (R4)

Публичные точки входа подсистем. Клиенты должны импортировать только через эти фасады. См. Architecture.md §0.7, docs/DEPENDENCY_FIREWALL.md.

## Таблица: пакет → публичный API → как импортировать

| Пакет | Публичные точки входа | Импорт |
|-------|------------------------|--------|
| **eurika.storage** | `ProjectMemory`, `Event`, `EventStore`, `event_engine`, `SessionMemory`, `operation_key`, `aggregate_operational_metrics` | `from eurika.storage import ProjectMemory, event_engine` |
| **eurika.agent** | `run_agent_cycle`, `DefaultToolContract`, `OrchestratorToolset`, `WEAK_SMELL_ACTION_PAIRS`, `evaluate_operation` | `from eurika.agent import run_agent_cycle, OrchestratorToolset` |
| **eurika.reasoning** | `advisor`, `architect`, `planner`, `heuristics`, `graph_ops` | `from eurika.reasoning import architect`<br>`from eurika.reasoning.architect import build_context_sources` |
| **eurika.reasoning.architect** | `build_context_sources`, `call_llm_with_prompt`, `interpret_architecture` | `from eurika.reasoning.architect import build_context_sources` |
| **eurika.reasoning.planner** | `Action`, `ActionPlan`, `PatchOperation`, `PatchPlan`, `build_plan`, `build_action_plan`, `build_patch_plan` | `from eurika.reasoning.planner import build_patch_plan` |
| **eurika.knowledge** | `SMELL_TO_KNOWLEDGE_TOPICS`, providers (`CompositeKnowledgeProvider`, `LocalKnowledgeProvider`, …) | `from eurika.knowledge import SMELL_TO_KNOWLEDGE_TOPICS, CompositeKnowledgeProvider` |
| **eurika.analysis** | `graph`, `scanner`, `metrics`, `cycles`, `self_map`, `topology` | `from eurika.analysis import graph, scanner` |
| **eurika.smells** | `detector`, `rules`, `models` | `from eurika.smells import detector` |
| **eurika.evolution** | `history`, `diff` | `from eurika.evolution import history` |
| **eurika.refactor** | `remove_import_from_file`, `remove_unused_imports` | `from eurika.refactor import remove_unused_imports` |
| **eurika.reporting** | `text`, `markdown`, `json_reporting` | `from eurika.reporting import markdown` |
| **eurika.core** | `pipeline`, `snapshot` | `from eurika.core import pipeline` |
| **eurika.checks** | `check_file_size_limits`, `collect_dependency_violations` | `from eurika.checks import check_file_size_limits` |
| **patch_engine** | `apply_and_verify`, `apply_patch`, `verify_patch`, `rollback_patch` | `from patch_engine import apply_and_verify` |
| **cli.orchestration** | doctor, fix, full_cycle, prepare, apply_stage (фасады) | через `cli.orchestrator` / handlers |

## Запрещённые импорты (SubsystemBypassRule)

| Клиент | Запрещено | Использовать вместо |
|--------|-----------|----------------------|
| `cli/` | `eurika.agent.policy`, `eurika.agent.runtime`, `eurika.agent.tools` | `eurika.agent` |
| `cli/`, `eurika.api/` | `eurika.reasoning.context_sources` | `eurika.reasoning.architect` (build_context_sources) |
| `eurika.reasoning/` | `eurika.knowledge.base` | `eurika.knowledge` |
| `architecture_planner*` | `eurika.reasoning.planner_patch_ops` | *Exception: circular import; см. dependency_firewall* |

## Исключения

`architecture_planner_build_patch_plan` импортирует `eurika.reasoning.planner_patch_ops` напрямую из‑за циклического импорта (planner → architecture_planner → build_patch_plan → planner). Исключение задокументировано в `DEFAULT_SUBSYSTEM_BYPASS_EXCEPTIONS`.
