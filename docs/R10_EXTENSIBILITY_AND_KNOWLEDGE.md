# R10 — Plugin system и Knowledge Graph

**Источник:** docs/review.md, REVIEW_2026_IV_ANALYSIS §3.3. Долгосрочная задача.

---

## 1. Plugin system

| Атрибут | Текущее | Примечание |
|---------|---------|------------|
| **Контракт** | `analyze(project_root: Path) -> List[ArchSmell]` | R5_PLUGIN_INTERFACE.md |
| **Регистрация** | `.eurika/plugins.toml`, `pyproject.toml [tool.eurika.plugins]` | ✅ |
| **Реализация** | `eurika/plugins/registry.py`, `aggregate.py` | load_plugins, run_plugins |
| **API** | `GET /api/smells_with_plugins`, summary `include_plugins=1` | ✅ |
| **Gap** | Только analyzer plugins; refactor/hypothesis plugins — в плане | review.md: plugin analyzers ✅, plugin refactors — целевое |

**Ссылки:** docs/R5_PLUGIN_INTERFACE.md, eurika/plugins/

---

## 2. Knowledge Graph

**Целевое (review.md §9):** расширить граф до

```
code graph         — modules, functions, imports, calls
architecture graph — слои, зависимости, smells
knowledge graph    — tests, связи code↔tests, семантика
```

| Уровень | Текущее | Gap |
|---------|---------|-----|
| **Code** | project_graph, self_map (imports, modules) | functions, calls — частично (code_awareness) |
| **Architecture** | DependencyGraph, smells, metrics | ✅ основной фокус |
| **Knowledge** | — | tests, code↔test связи, семантические роли |

**Принцип:** не начинать до стабилизации ядра (R2, R3). Knowledge Graph — этап после v3.x target structure.

---

## 3. Связь с ROADMAP

- **R5 Strategic Horizon:** plugins ✅ (analyzer)
- **TARGET_V3_STRUCTURE:** world_model, reasoning, execution, memory — до Knowledge Graph
- **Порядок:** Plugin refactors → затем Knowledge Graph (при необходимости)
