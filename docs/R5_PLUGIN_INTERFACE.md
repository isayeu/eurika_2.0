# R5 Plugin Interface — Extensibility (ROADMAP R5)

**Цель:** подключение внешних анализаторов через единый контракт.

---

## Контракт

Плагин — callable `analyze(project_root: Path) -> List[ArchSmell]`:

- **Вход:** `Path` — корень проекта
- **Выход:** список объектов с атрибутами `type`, `nodes`, `severity`, `description` (ArchSmell-like)

Источники регистрации:
1. `.eurika/plugins.toml` — `[[plugins]] entry_point = "module:attr"`
2. `pyproject.toml` — `[tool.eurika.plugins] name = "module:attr"`

---

## Пример

```toml
# .eurika/plugins.toml
[[plugins]]
entry_point = "my_plugin:analyze"
```

```python
# my_plugin.py
from pathlib import Path
from eurika.smells.detector import ArchSmell  # or similar structure

def analyze(project_root: Path):
    return [ArchSmell(type="custom_smell", nodes=["a.py"], severity=5, description="...")]
```

---

## Интеграция

- `eurika.plugins.registry`: `load_plugins()`, `run_plugins()`
- Smells от плагинов включаются в общий поток архитектурного анализа (при интеграции в pipeline)

---

## Version Contract (RV15)

**Цель:** явный контракт, чтобы плагины не ломались при обновлении Eurika; внутренний API защищён.

### Стабильный контракт (backward compatible)

| Элемент | Описание |
|---------|----------|
| Сигнатура | `analyze(project_root: Path) -> List[ArchSmell]` |
| ArchSmell | `type: str`, `nodes: List[str]`, `severity: float`, `description: str` |
| Регистрация | `.eurika/plugins.toml`, `pyproject.toml` [tool.eurika.plugins] |
| Импорт | `from eurika.smells.models import ArchSmell` или `from eurika.smells.detector import ArchSmell` |

**Политика совместимости:** изменения в PATCH (X.Y.**Z**) не ломают плагины. Изменения в MINOR (X.**Y**.Z) могут добавлять поля в ArchSmell, но не удалять. MAJOR (**X**.Y.Z) может вводить breaking changes с предупреждением в release notes.

### Разрешённые зависимости плагина

- `eurika.smells.models.ArchSmell` — data model
- `eurika.smells.detector` — ArchSmell re-export (для совместимости)
- `pathlib.Path` — входной аргумент
- Стандартная библиотека Python

### Запрещённые зависимости (internal API)

Плагин **не должен** импортировать:

- `eurika.orchestration.*`, `eurika.agent.*`, `eurika.api.*` (кроме document public API)
- `eurika.analysis.graph.ProjectGraph` — внутренняя модель графа
- `patch_engine`, `patch_apply`, `architecture_planner`, `cli.*`

**Причина:** эти модули могут менять сигнатуры и структуру между релизами. Плагин получает только `Path` и возвращает `List[ArchSmell]`.

### Deprecation

При изменении контракта: один MINOR релиз с `DeprecationWarning`, затем breaking change в следующем MAJOR.
