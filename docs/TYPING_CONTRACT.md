# R3 Typing Contract

Type-hints на границах подсистем; mypy как optional-gate. Ошибки типов не накапливаются в core-контрактах.

## Запуск

```bash
pip install -e ".[typecheck]"
mypy eurika cli
```

## Конфигурация

- `pyproject.toml` → `[tool.mypy]`: python_version, `follow_imports = "skip"`, `warn_unused_ignores`
- `[[tool.mypy.overrides]]`: boundary-модули (orchestration, agent, storage, reasoning, smells, analysis, reporting, core, checks, utils) с `check_untyped_defs`, `disallow_incomplete_defs`

## CI

- **test job:** шаг "Type check (mypy, optional-gate)" — `continue-on-error: true`, не блокирует merge
- **release-hygiene:** `release_check.sh` шаг 5 — локально блокирует, в CI только warning
- Перед релизом: `mypy eurika cli` должен проходить (release gate)

## Границы (boundary modules)

Слой за слоем: CLI entry → orchestration → API surface → agent/storage/event-memory → learning/knowledge → reasoning → runtime/tool-contract → evolution → smells/core → analysis/reporting → checks/utils/storage-sidecar.

См. полный список в `pyproject.toml` → `[[tool.mypy.overrides]]` → `module`.
