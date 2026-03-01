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
