# Release Checklist (R4 Release Hygiene)

Обязательный gate перед тегом релиза. См. [R4_MODULAR_PLATFORM_PLAN.md](R4_MODULAR_PLATFORM_PLAN.md) §3.

## Автоматический прогон

```bash
./scripts/release_check.sh
```

Скрипт прогоняет пункты 1–9. Пункт 10 — ручная проверка CHANGELOG.

## Чеклист по пунктам

| # | Проверка | Команда |
|---|----------|---------|
| 1 | Tests pass | `pytest tests/ -q` |
| 2 | Edge-case tests | `pytest -m edge_case -v` |
| 3 | Dependency firewall (strict) | `EURIKA_STRICT_LAYER_FIREWALL=1 pytest tests/test_dependency_guard.py tests/test_dependency_firewall.py -v` |
| 4 | Lint (ruff) | `ruff check eurika cli` (требует `pip install -e ".[extras]"`) |
| 5 | Type check (mypy) | `mypy eurika cli` |
| 6 | File size limits | `eurika self-check .` (блок FILE SIZE LIMITS) |
| 7 | Layer discipline | `eurika self-check .` (блок LAYER DISCIPLINE) |
| 8 | TODO/FIXME audit | `rg "TODO|FIXME|XXX" --type py -g '!*test*'` (informational) |
| 9 | Smoke | `pip install -e . && eurika scan . && eurika doctor . --no-llm` |
| 10 | CHANGELOG updated | Проверить, что версия и изменения описаны в CHANGELOG.md |

## Venv

Скрипт ожидает venv `../.venv` (относительно корня проекта, см. `.cursor/rules/venv.mdc`).

```bash
source ../.venv/bin/activate
./scripts/release_check.sh
```

Без venv скрипт завершится с ошибкой.

## CI

GitHub Actions (`.github/workflows/ci.yml`):
- **test** — pytest, dependency firewall (strict), edge-case tests
- **release-hygiene** — полный прогон `./scripts/release_check.sh` (после test)

Скрипт работает и локально (venv `../.venv`), и в CI (python/pip из PATH). В CI ruff/mypy при ошибках только предупреждают; локально — блокируют.

См. `docs/DEPENDENCY_FIREWALL.md` для деталей по правилам и исключениям.
