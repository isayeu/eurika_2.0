# Planner consolidation plan (ROADMAP v3.0 Stage 1, §5.6)

**Цель:** сократить количество ролей (planner_rules, planner_actions, planner_analysis, planner_patch_ops, planner_llm) до структуры `eurika/reasoning/planner/`.

## Текущие модули (размеры)

| Модуль | LOC | Назначение |
|--------|-----|------------|
| planner_types.py | 38 | PlanStep, ArchitecturePlan |
| planner_rules.py | 115 | SMELL_ACTION_SEP, DIFF_HINTS, EXTRACT_CLASS_SKIP_PATTERNS |
| planner_analysis.py | 77 | index_smells_by_node, build_steps_from_priorities |
| planner_actions.py | 83 | actions_from_arch_plan |
| planner_patch_ops.py | 460 | build_patch_operations |
| planner_llm.py | 490 | ask_ollama_split_hints, ask_llm_extract_patch |
| planner.py | 20 | фасад (Action, ActionPlan, build_*) |

## Целевая структура

```
eurika/reasoning/planner/
    __init__.py      # фасад, re-export из submodules
    types.py         # PlanStep, ArchitecturePlan (из planner_types)
    heuristics.py    # правила, DIFF_HINTS (из planner_rules)
    analysis.py      # index_smells_by_node, build_steps (из planner_analysis)
    actions.py       # actions_from_arch_plan + build_patch_ops (из planner_actions + planner_patch_ops)
    llm_adapter.py   # Ollama/LiteLLM (из planner_llm)
```

## Зависимости (обновить при миграции)

- architecture_planner.py → planner.types
- architecture_planner_build_plan.py → planner.analysis
- architecture_planner_build_action_plan.py → planner.actions
- architecture_planner_build_patch_plan.py → planner.analysis, planner.actions
- eurika/api/ops.py → planner.llm_adapter
- eurika/orchestration/prepare.py → planner.llm_adapter
- tests/edge_cases/ → planner.actions

## Обратная совместимость

Создать thin shims в eurika.reasoning:
- `planner_types.py` → `from eurika.reasoning.planner.types import *`
- Аналогично для rules, analysis, actions, patch_ops, llm

Либо перевести все импорты на `eurika.reasoning.planner.*` за один проход.

## Очередность миграции

1. Создать `planner/` пакет и `planner/types.py`
2. Добавить shim `planner_types.py` → import from planner.types
3. Повторить для rules, analysis, actions, patch_ops, llm
4. Удалить shims, обновить все импорты
5. Обновить dependency_firewall (planner/ path)
