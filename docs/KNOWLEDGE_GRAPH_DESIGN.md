# R10 — Knowledge Graph (целевая модель)

**Источник:** docs/review.md §9, R10_EXTENSIBILITY_AND_KNOWLEDGE.md, TARGET_V3_STRUCTURE §5.

**Статус:** v3.x стабилизация пройдена. Реализовано: code_graph, build_test_links, get_knowledge_graph; GET /api/test_links, /api/knowledge_graph.

**Связь:** Knowledge Provider (query по topic) — [KNOWLEDGE_LAYER.md](KNOWLEDGE_LAYER.md).

---

## 1. Три уровня графа (review.md §9)

```
code graph         — modules, functions, imports, calls
architecture graph — слои, зависимости, smells
knowledge graph    — tests, связи code↔tests, семантика
```

---

## 2. Code Graph

### 2.1 Текущее состояние

| Сущность | Источник | Формат |
|----------|----------|--------|
| **Модули** | self_map.json `modules` | `[{path, name, ...}]` |
| **Импорты** | self_map.json `dependencies` | `{module_key: [imported_names]}` |
| **Файлы → файлы** | ProjectGraph.from_self_map | nodes=paths, edges=import deps |

### 2.2 Gap

| Сущность | Статус | Примечание |
|----------|--------|------------|
| **Функции** | ❌ | Нет явного графа функций внутри модуля |
| **Вызовы (calls)** | Частично | code_awareness — AST; не граф call→callee |
| **Классы** | Частично | architecture_smells, code_awareness |

### 2.3 Целевая схема (design)

```
CodeGraph:
  nodes: {file_path, function_id?, class_id?}
  edges:
    - import(file_a → file_b)
    - call(fn_a → fn_b)  [опционально]
    - contains(file → function | class)
```

**Реализация:** `eurika/knowledge/code_graph.py` — `build_code_graph(self_map) -> CodeGraph`. Пока: modules + import edges (ProjectGraph). functions, calls — следующий этап.

---

## 3. Architecture Graph

### 3.1 Текущее состояние ✅

| Сущность | Реализация |
|----------|------------|
| **Слои** | ProjectGraph.node_metrics().layer, DependencyGraph |
| **Зависимости** | ProjectGraph.edges, DependencyGraph |
| **Smells** | ArchSmell, SmellReport, architecture_smells |
| **Метрики** | MetricVector, EnergyModel, NodeMetrics |

Основной фокус Eurika — architecture graph уже есть.

---

## 4. Knowledge Graph

### 4.1 Текущее состояние

| Сущность | Реализация |
|----------|------------|
| **KnowledgeProvider** | eurika/knowledge/base.py — query(topic) → StructuredKnowledge |
| **Curated topics** | LocalKnowledgeProvider, topics.py |
| **Tests** | build_test_links |
| **Code↔Test связи** | build_test_links; GET /api/test_links |
| **Семантические роли** | — |

### 4.2 Gap

- Нет графа тестов и связей `test_file → tested_module`
- Нет семантических ролей (UI, domain, infra и т.д.) в графе

### 4.3 Целевая схема (design)

```
KnowledgeGraph:
  nodes:
    - code_entity (file, function, class)
    - test_entity (test_file, test_fn)
    - semantic_role (label: "ui" | "domain" | "infra" | ...)
  edges:
    - tests(test_fn → code_entity)
    - role_of(code_entity → semantic_role)
```

**Реализация:** `eurika/knowledge/knowledge_graph.py` — `build_test_links(project_root, code_graph)` → `list[tuple[str, str]]`. По импортам в tests/test_*.py сопоставляет с узлами code_graph.

---

## 5. Единый фасад (целевой)

```
KnowledgeGraphFacade:
  - code: CodeGraph (modules, imports; opt. functions, calls)
  - architecture: DependencyGraph + SmellReport + MetricVector
  - knowledge: test_links, semantic_roles (опционально)
```

**Реализация:** `get_knowledge_graph(project_root)` → `{code: {nodes, edges_count}, test_links}`. GET /api/knowledge_graph.

---

## 6. Порядок внедрения

1. **v3.x стабилизация** — world_model, execution, memory (✅)
2. **Code graph extension** — при необходимости: functions, calls (если нужны для refactor)
3. **Knowledge layer** — test_links после code graph; semantic roles — по приоритету

---

## 7. Связь с ROADMAP

- **R10_EXTENSIBILITY_AND_KNOWLEDGE.md** — plugins ✅; KG — этот документ
- **TARGET_V3_STRUCTURE §5** — v3 стабилизация пройдена; KG implementation started
- **review.md §9** — целевая структура трёх графов
