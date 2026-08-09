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

## Lifecycle hooks `after_*`

Канонический pipeline поддерживает наблюдательные hooks после реальных стадий:

`after_scan`, `after_plan`, `after_apply`, `after_verify`.

Они срабатывают в CLI/API/Qt одинаково, потому что подключены не к оболочкам,
а к scan/prepare/apply/verify границам. `after_scan` получает
`metadata.scan_reason=standalone|cycle_initial|post_apply`.

V1 покрывает canonical scan и fix/full orchestration. Chat task-executor и
legacy `agent patch-apply` — отдельные lifecycle и пока hooks не публикуют.

```toml
# .eurika/plugins.toml
[[hooks]]
event = "after_apply"
entry_point = "my_plugin:on_applied"

# Альтернатива в pyproject.toml:
[tool.eurika.hooks]
after_verify = "my_plugin:on_verified"
```

```python
from eurika.plugins import HookContext

def on_applied(context: HookContext) -> None:
    # context — immutable snapshot; hook не меняет результат стадии.
    print(context.event, context.status, context.payload)
```

Гарантии:

- порядок вызова совпадает с порядком деклараций;
- повтор одного `event + entry_point` игнорируется;
- context — versioned JSON-safe immutable snapshot результата стадии;
- hook работает fail-open: исключение не останавливает verify/rollback;
- каждый запуск пишется как `plugin_hook` в `.eurika/events.json`, а компактный
  результат попадает в `report.plugin_hooks`;
- hook не может заменить результат стадии через API.

**Безопасность:** entry point импортируется и выполняется в процессе Eurika с
правами текущего пользователя. Это механизм только для доверенных локальных
плагинов, не sandbox для стороннего кода.

Public API: `HookContext`, `HookRegistry`, `HookExecution`,
`load_hook_registry`, `dispatch_project_hooks` из `eurika.plugins`.

---

## Version Contract (RV15)

**Цель:** явный контракт, чтобы плагины не ломались при обновлении Eurika; внутренний API защищён.

### Стабильный контракт (backward compatible)

| Элемент | Описание |
|---------|----------|
| Сигнатура | `analyze(project_root: Path) -> List[ArchSmell]` |
| ArchSmell | `type: str`, `nodes: List[str]`, `severity: float`, `description: str` |
| Регистрация | `.eurika/plugins.toml`, `pyproject.toml` [tool.eurika.plugins] |
| Lifecycle | `HookContext` schema v1; события `after_scan/plan/apply/verify` |
| Импорт | `from eurika.smells.models import ArchSmell` или `from eurika.smells.detector import ArchSmell` |

**Политика совместимости:** изменения в PATCH (X.Y.**Z**) не ломают плагины. Изменения в MINOR (X.**Y**.Z) могут добавлять поля в ArchSmell, но не удалять. MAJOR (**X**.Y.Z) может вводить breaking changes с предупреждением в release notes.

### Разрешённые зависимости плагина

- `eurika.smells.models.ArchSmell` — data model
- `eurika.smells.detector` — ArchSmell re-export (для совместимости)
- `pathlib.Path` — входной аргумент
- `eurika.plugins.HookContext` — read-only lifecycle context
- Стандартная библиотека Python

### Запрещённые зависимости (internal API)

Плагин **не должен** импортировать:

- `eurika.orchestration.*`, `eurika.agent.*`, `eurika.api.*` (кроме document public API)
- `eurika.analysis.graph.ProjectGraph` — внутренняя модель графа
- `patch_engine`, `patch_apply`, `architecture_planner`, `cli.*`

**Причина:** эти модули могут менять сигнатуры и структуру между релизами. Плагин получает только `Path` и возвращает `List[ArchSmell]`.

### Deprecation

При изменении контракта: один MINOR релиз с `DeprecationWarning`, затем breaking change в следующем MAJOR.
