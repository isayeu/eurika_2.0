# API Boundaries (R4)

Публичные точки входа подсистем. Клиенты должны импортировать только через эти фасады. См. Architecture.md §0.7, docs/DEPENDENCY_FIREWALL.md.

## Таблица: пакет → публичный API → как импортировать

| Пакет | Публичные точки входа | Импорт |
|-------|------------------------|--------|
| **eurika.storage** | `ProjectMemory`, `Event`, `EventStore`, `event_engine`, `ExperienceStore`, `record_outcome`, `get_recent_failures`, `get_recent_failures_enriched`, `get_recent_failed_plan_hashes`, `plan_hash_from_ops`, `get_statistics`, `SessionMemory`, `operation_key`, `aggregate_operational_metrics`, `save_checkpoint`, `load_checkpoint`, `has_checkpoint`, `snapshot_from_checkpoint` | `from eurika.storage import ProjectMemory, get_recent_failures, save_checkpoint` |
| **eurika.agent** | `run_agent_cycle`, `DefaultToolContract`, `OrchestratorToolset`, `WEAK_SMELL_ACTION_PAIRS`, `evaluate_operation`, `is_whitelisted_for_auto` | `from eurika.agent import run_agent_cycle, is_whitelisted_for_auto` |
| **eurika.reasoning** | `advisor`, `architect`, `planner`, `heuristics`, `graph_ops` | `from eurika.reasoning import architect`<br>`from eurika.reasoning.architect import build_context_sources` |
| **eurika.reasoning.architect** | `build_context_sources`, `call_llm_with_prompt`, `interpret_architecture` | `from eurika.reasoning.architect import build_context_sources` |
| **eurika.reasoning.planner** | `analyze`, `detect_smells`, `propose_actions`, `Action`, `ActionPlan`, `ArchitectureModel`, `ArchitectureSnapshot`, `RefactorCandidate`, `PatchOperation`, `PatchPlan`, `RefactorAction`, `RiskReport`, `SmellReport`, `SimulationResult`, `risk_report_from_plan`, `build_plan`, `build_action_plan`, `build_patch_plan` | `from eurika.reasoning.planner import analyze, ArchitectureSnapshot` |
| **eurika.reasoning.execution_context** | `ExecutionContext` | `from eurika.reasoning.execution_context import ExecutionContext` |
| **eurika.reasoning.action_plan** | `Action`, `ActionPlan` | `from eurika.reasoning.action_plan import Action, ActionPlan` |
| **eurika.knowledge** | `CodeGraph`, `build_code_graph`, `build_test_links`, providers. API: `get_knowledge`, `get_test_links`, `get_knowledge_graph` | `from eurika.api import get_knowledge_graph, get_test_links` |
| **eurika.analysis** | `graph`, `scanner`, `metrics`, `cycles`, `self_map`, `topology`, `scoring`, `metric_vector`, `energy_model`, `weight_store`. API: `get_metrics(project_root)` → MetricVector + Energy (ROADMAP §5.7) | `from eurika.analysis import graph, metric_vector, energy_model`; `from eurika.api import get_metrics` |
| **eurika.world_model** | `MetricVector`, `EnergyModel`, `WeightVector` (P7 alias над analysis) | `from eurika.world_model import MetricVector, EnergyModel, WeightVector` |
| **eurika.memory** | `ProjectMemory`, `record_outcome`, `get_statistics`, `EventStore`, `ExperienceStore`, `save_checkpoint`, `load_checkpoint` (P8 alias над storage) | `from eurika.memory import record_outcome, ProjectMemory, save_checkpoint` |
| **eurika.smells** | `detector`, `rules`, `models` | `from eurika.smells import detector` |
| **eurika.evaluation** | `compute_delta` | `from eurika.evaluation import compute_delta` |
| **eurika.evolution** | `history`, `diff` | `from eurika.evolution import history` |
| **eurika.refactor** | `remove_import_from_file`, `remove_unused_imports` | `from eurika.refactor import remove_unused_imports` |
| **eurika.reporting** | `text`, `markdown`, `json_reporting` | `from eurika.reporting import markdown` |
| **eurika.core** | `pipeline`, `snapshot` | `from eurika.core import pipeline` |
| **eurika.checks** | `check_file_size_limits`, `collect_dependency_violations` | `from eurika.checks import check_file_size_limits` |
| **patch_engine** | `apply_and_verify`, `apply_patch`, `verify_patch`, `rollback_patch`, `simulate_patch` | `from patch_engine import apply_and_verify, simulate_patch` |
| **eurika.execution** | `apply_and_verify`, `apply_patch`, `verify_patch`, `rollback_patch`, `simulate_patch`, `apply_patch_dry_run`, `list_backups` (P9 alias над patch_engine) | `from eurika.execution import apply_and_verify, simulate_patch` |
| **eurika.orchestration** | run_cycle, run_doctor_cycle, run_fix_cycle, run_full_cycle, prepare, apply_stage (P0.2, S3) | `from eurika.orchestration import run_cycle` |

## Запрещённые импорты (SubsystemBypassRule)

| Клиент | Запрещено | Использовать вместо |
|--------|-----------|----------------------|
| `cli/` | `eurika.agent.policy`, `eurika.agent.runtime`, `eurika.agent.tools` | `eurika.agent` |
| `cli/`, `eurika.api/` | `eurika.reasoning.context_sources` | `eurika.reasoning.architect` (build_context_sources) |
| `eurika.reasoning/` | `eurika.knowledge.base` | `eurika.knowledge` |
| `eurika.api/chat` | `patch_engine`, `patch_apply`, `eurika.orchestration` | subprocess eurika_cli |

## Chat API boundary (R4)

Модули `eurika/api/chat*.py` не импортируют `patch_engine`, `patch_apply`, `eurika.orchestration`. Fix/doctor — только subprocess. Task executor: файловые операции + code_edit_patch; refactor → subprocess.

## Target v3.x (review 2026 II)

По docs/archive/review.md, ROADMAP §5.7. Целевая структура API после миграции:

| Пакет | Роль |
|-------|------|
| `core/` | `models` (ArchitectureSnapshot, MetricVector, ExecutionContext), `execution_context` |
| `analysis/` | graph, metrics, smells — только анализ |
| `planning/` | planner_engine, candidate_generator, scoring, risk_model |
| `simulation/` | simulator — dry-run без мутации |
| `execution/` | patch_executor, verifier |
| `evaluation/` | delta_evaluator — compare(before, after) → delta |
| `storage/` | state_store, event_log, learning_store — dumb persistence |

Planner: чистый, без side effects. Storage: только запись, без бизнес-логики.
