# Dependency Firewall (R4)

Проверки границ архитектурных слоёв и подсистем. CI падает при нарушении правил.

См. также: Architecture.md §0.6 Verification, §0.7 API Boundaries; docs/RELEASE_CHECKLIST.md.

## Как запустить

```bash
# Все проверки (forbidden imports, layer contract, subsystem bypass)
pytest tests/test_dependency_guard.py tests/test_dependency_firewall.py -v

# Строгий режим layer firewall (обязателен в CI)
EURIKA_STRICT_LAYER_FIREWALL=1 pytest tests/test_dependency_guard.py -v
```

## Типы правил

### 1. ImportRule — запрещённые импорты

`path_pattern` → `forbidden_imports` (корневые имена модулей).

Пример: CLI не должен импортировать `patch_apply` напрямую — только через `patch_engine`.

### 2. Layer rules — направление зависимостей

`LayerPathRule` и `LayerImportRule` задают слои (0..6). Модуль может импортировать только из того же или более нижнего слоя. См. Architecture.md §0.

### 3. SubsystemBypassRule — обход фасадов (R4)

`path_pattern` → `forbidden_import_prefix`. Внешние клиенты должны использовать публичный API пакета, а не внутренние подмодули.

Пример: `cli/` не импортирует `eurika.agent.policy` — только `eurika.agent` (который реэкспортирует нужное).

## Как добавить правило

В `eurika/checks/dependency_firewall.py`:

```python
# ImportRule (корневые имена)
ImportRule(path_pattern="path/to/", forbidden_imports=("forbidden_module",))

# SubsystemBypassRule (полный префикс)
SubsystemBypassRule(
    path_pattern="cli/",
    forbidden_import_prefix="eurika.agent.policy",
)
```

## Как добавить exception

### LayerException (layer contract)

```python
LayerException(
    path_pattern="path/to/module.py",
    allowed_import_prefixes=("eurika.special.module",),
    reason="Временный waiver; migrate to facade in R4.2",
)
```

Добавить в `LAYER_FIREWALL_EXCEPTIONS` в `tests/test_dependency_guard.py` или в `DEFAULT_LAYER_EXCEPTIONS` в `dependency_firewall.py`.

### SubsystemBypassException

```python
SubsystemBypassException(
    path_pattern="architecture_planner",
    allowed_import_prefix="eurika.reasoning.planner_patch_ops",
    reason="Legacy planner scripts; migrate to facade",
)
```

Добавить в `DEFAULT_SUBSYSTEM_BYPASS_EXCEPTIONS` в `dependency_firewall.py`.

## Файлы

| Файл | Назначение |
|------|------------|
| `eurika/checks/dependency_firewall.py` | Правила, исключения, функции сбора нарушений |
| `tests/test_dependency_guard.py` | Интеграционные тесты: `test_no_forbidden_imports`, `test_layer_firewall_contract_soft_start`, `test_subsystem_imports_via_public_api` |
| `tests/test_dependency_firewall.py` | Юнит-тесты функций `collect_dependency_violations`, `collect_layer_violations` |
